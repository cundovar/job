"""
La brique envoi : un dossier APPROVED, une chaîne de contrôles, un envoi, un journal.

Règle d'architecture : l'envoi n'est jamais un outil Hermes. Il se déclenche par
la CLI ci-dessous, que seul l'utilisateur lance. Défaut sec — sans --send, rien
ne part et aucune connexion sortante n'est établie (règle 4 du CLAUDE.md).

Ordre des contrôles, non négociable :
    statut APPROVED → DO_NOT_CONTACT → déduplication → quota → envoi → journal
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

from company_analysis.duplicate import duplicate_check

from .application_tracker import ApplicationTracker
from .mail_template import render_mail_html
from .sender import EmailSender, SendResult

CONTACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
APPROVED_STATUS = "APPROVED"


@dataclass(frozen=True)
class Verdict:
    control: str
    passed: bool
    detail: str


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_public_contact(job: Dict[str, Any]) -> tuple[str, str] | None:
    """Adresse et sa source, uniquement si relevées en clair dans un constat.

    Une adresse qui n'apparaît pas dans les constats vérifiés n'existe pas :
    on ne la reconstitue pas (devinette, schéma supposé, etc.).
    """
    for claim in job.get("public_contact") or []:
        texts = [str(claim.get("claim") or "")] + [str(item) for item in claim.get("evidence") or []]
        for text in texts:
            match = CONTACT_RE.search(text)
            if match:
                return match.group(0), text.strip()
    return None


def extract_public_contacts(job: Dict[str, Any]) -> list[tuple[str, str]]:
    """Return every distinct address found in verified public-contact claims."""
    contacts: list[tuple[str, str]] = []
    seen: set[str] = set()
    for claim in job.get("public_contact") or []:
        texts = [str(claim.get("claim") or "")] + [
            str(item) for item in claim.get("evidence") or []
        ]
        for text in texts:
            for match in CONTACT_RE.finditer(text):
                address = match.group(0).strip().lower()
                if address not in seen:
                    seen.add(address)
                    contacts.append((address, text.strip()))
    return contacts


def _selected_recipients(job: Dict[str, Any], metadata: Dict[str, Any]) -> list[dict[str, str]]:
    """Read the explicit selection, falling back to the historical first address."""
    raw = metadata.get("send_recipients")
    if isinstance(raw, list) and raw:
        return [
            {
                "email": str(item.get("email") or "").strip().lower(),
                "role": str(item.get("role") or ("to" if index == 0 else "cc")).lower(),
                "source": str(item.get("source") or "selection"),
            }
            for index, item in enumerate(raw)
            if isinstance(item, dict) and str(item.get("email") or "").strip()
        ]
    contact = extract_public_contact(job)
    if not contact:
        return []
    return [{"email": contact[0].lower(), "role": "to", "source": contact[1]}]


def include_lettre(metadata: Dict[str, Any]) -> bool:
    """La lettre part-elle avec le mail ? Oui, sauf choix explicite du candidat.

    Une clé absente vaut « oui » : c'est ce que faisaient tous les dossiers
    existants, et un défaut inversé retirerait une pièce jointe sans que
    personne ne l'ait demandé.
    """
    return metadata.get("send_include_lettre", True) is not False


def attachment_paths(dossier: Path, metadata: Dict[str, Any]) -> List[Path]:
    """Les pièces jointes réellement présentes, lettre comprise si elle est voulue."""
    candidates = [dossier / "cv" / "cv_final.pdf"]
    if include_lettre(metadata):
        candidates.append(dossier / "lettre_motivation.pdf")
    return [path for path in candidates if path.exists()]


def recipient_fingerprint(recipients: list[dict[str, str]]) -> str:
    canonical = [
        {"email": item["email"].lower(), "role": item["role"].lower()}
        for item in recipients
    ]
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _companies_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("nom")]


def _mail_parts(mail_path: Path) -> tuple[str, str]:
    """Objet = première ligne « Objet : … », corps = le reste."""
    lines = mail_path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].lower().startswith("objet :"):
        return lines[0].split(":", 1)[1].strip(), "\n".join(lines[1:]).strip()
    return "Candidature", "\n".join(lines).strip()


def run_controls(
    dossier: Path,
    tracker: ApplicationTracker,
    companies: List[Dict[str, str]],
    today: date | None = None,
    daily_quota: int | None = None,
) -> tuple[Dict[str, Any], List[Verdict]]:
    """Évalue tous les contrôles, dans l'ordre imposé, et renvoie dossier + verdicts.

    Tous les verdicts sont calculés : un refus ne court-circuite pas les
    suivants, c'est le rapport qui liste d'abord le contrôle prioritaire.
    """
    today = today or date.today()
    daily_quota = daily_quota if daily_quota is not None else int(os.getenv("SEND_DAILY_QUOTA", "2"))

    job = _load_json(dossier / "job.json")
    metadata = _load_json(dossier / "metadata.json")
    recipients = _selected_recipients(job, metadata)

    status = str(metadata.get("status") or "")
    verdicts = [
        Verdict(
            "statut APPROVED",
            status == APPROVED_STATUS,
            f"statut du dossier : {status or 'inconnu'}"
            if status != APPROVED_STATUS
            else "validé par l'utilisateur",
        )
    ]
    approved_fingerprint = str(metadata.get("approval_recipients_hash") or "")
    current_fingerprint = recipient_fingerprint(recipients) if recipients else ""
    verdicts.append(
        Verdict(
            "approbation des destinataires",
            not recipients or status != APPROVED_STATUS or bool(approved_fingerprint and approved_fingerprint == current_fingerprint),
            "liste identique à celle approuvée"
            if not recipients or status != APPROVED_STATUS or (approved_fingerprint and approved_fingerprint == current_fingerprint)
            else "la liste des destinataires a changé depuis l'approbation",
        )
    )

    # Les deux contrôles suivants posent la même question — « connaît-on déjà
    # cette organisation ? » — à deux registres différents. Une seule mesure les
    # sert, pour qu'ils ne puissent pas répondre selon deux règles distinctes.
    duplicates = duplicate_check(
        job.get("url", ""),
        job.get("company", ""),
        contacted=tracker.contact_history(),
        registry=companies,
    )["value"]

    excluded = duplicates["excluded"]
    verdicts.append(
        Verdict(
            "DO_NOT_CONTACT",
            not excluded,
            f"entreprise marquée ecartee dans companies.csv ({excluded[0]['reason']})"
            if excluded
            else "aucune exclusion",
        )
    )

    already = duplicates["contacted"]
    verdicts.append(
        Verdict(
            "déduplication",
            not already,
            f"un envoi existe déjà pour cette entreprise ({already[0]['reason']})"
            if already
            else "premier contact",
        )
    )

    sent_today = tracker.sent_on(today)
    verdicts.append(
        Verdict(
            "quota du jour",
            sent_today < daily_quota,
            f"{sent_today}/{daily_quota} envoi(s) aujourd'hui",
        )
    )

    return {"job": job, "metadata": metadata, "recipients": recipients, "dossier": dossier}, verdicts


def send_dossier(
    dossier: str | Path,
    sender: EmailSender,
    tracker: ApplicationTracker | None = None,
    companies_csv: str | Path = "config/companies.csv",
    commit: bool = False,
    today: date | None = None,
) -> Dict[str, Any]:
    """Chaîne complète : contrôles, envoi (seulement si commit), journalisation."""
    tracker = tracker or ApplicationTracker()
    dossier_path = Path(dossier)
    payload, verdicts = run_controls(
        dossier_path, tracker, _companies_rows(Path(companies_csv)), today=today
    )
    job = payload["job"]

    result: Dict[str, Any] = {
        "dossier": str(dossier_path),
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "commit": commit,
        "verdicts": [verdict.__dict__ for verdict in verdicts],
        "refused": any(not verdict.passed for verdict in verdicts),
        "sent": False,
    }

    if result["refused"]:
        # Le contrôle prioritaire dans l'ordre imposé porte le motif principal.
        first_failure = next(verdict for verdict in verdicts if not verdict.passed)
        result["refusal"] = f"{first_failure.control} : {first_failure.detail}"
        return result

    recipients = payload["recipients"]
    if not recipients:
        refusal = (
            "destinataire : aucune adresse publique vérifiée dans les constats du dossier — "
            "une adresse ne se reconstitue pas."
        )
        result.update({"refused": True, "refusal": refusal})
        return result
    primary = next((item for item in recipients if item["role"] == "to"), None)
    if primary is None:
        primary = recipients[0]
    address = primary["email"]
    cc = [item["email"] for item in recipients if item is not primary]
    sources = [item.get("source", "") for item in recipients]

    subject, body = _mail_parts(dossier_path / "mail_candidature.md")
    result["would_send"] = {
        "to": address,
        "cc": cc,
        "recipients": [item["email"] for item in recipients],
        "contact_source": sources[0] if sources else "",
        "subject": subject,
    }

    # Pièces jointes du dossier : CV validé + lettre en PDF. Absents = envoi
    # texte seul ; le contrôle CV amont reste maître du refus.
    attachments = attachment_paths(dossier_path, payload["metadata"])
    result["would_send"]["attachments"] = [path.name for path in attachments]

    if not commit:
        # Défaut sec : on s'arrête ici, le fournisseur n'est jamais touché.
        return result

    send_result: SendResult = sender.send(
        to=address, cc=cc, subject=subject, body=body, attachments=attachments,
        html=render_mail_html(subject, body, sender_email=getattr(sender, "sender", "") or ""),
    )
    if send_result.ok:
        tracker.mark_sent(
            job,
            {
                "to": address,
                "cc": cc,
                "recipients": [item["email"] for item in recipients],
                "contact_source": sources[0] if sources else "",
                "provider": send_result.provider,
                "message_id": send_result.message_id,
                "dossier": str(dossier_path),
                "subject": subject,
            },
        )
        result["sent"] = True
        result["message_id"] = send_result.message_id
        result["attachments"] = [Path(a).name for a in attachments]
        # Accusé de réception vers la boîte de Cundo : le contenu de l'envoi.
        confirm_to = (os.getenv("BREVO_CONFIRM_TO") or os.getenv("EMAIL_SENDER") or "").strip()
        if confirm_to:
            recap_lignes = [
                f"Entreprise : {job.get('company', '')}",
                f"Poste : {job.get('title', '')}",
                f"Destinataire : {address}",
                f"Cc : {', '.join(cc) or 'aucun'}",
                f"Objet : {subject}",
                f"Pièces jointes : {', '.join(result['attachments']) or 'aucune'}",
                f"Message : {result.get('message_id') or 'n/a'}",
                f"Dossier : {dossier_path}",
            ]
            recap = "Candidature envoyée.\n\n" + "\n\n".join(recap_lignes)
            try:
                sender.send(
                    to=confirm_to,
                    cc=(),
                    subject=f"✓ Candidature envoyée à {job.get('company', '')}",
                    body=recap,
                    html=render_mail_html(
                        f"✓ Candidature envoyée à {job.get('company', '')}",
                        "Candidature envoyée.\n\n" + "\n\n".join(recap_lignes),
                        sender_email=getattr(sender, "sender", "") or "",
                    ),
                )
            except Exception:
                pass  # l'accusé ne doit jamais casser la confirmation d'envoi
    else:
        tracker.mark_send_failed(job, send_result.error)
        result["send_error"] = send_result.error
    return result


def _print_report(result: Dict[str, Any]) -> None:
    print(f"Dossier : {result['dossier']}")
    print(f"Cible   : {result['company']} — {result['title']}")
    print()
    for verdict in result["verdicts"]:
        mark = "PASS" if verdict["passed"] else "REFUS"
        print(f"  [{mark}] {verdict['control']} — {verdict['detail']}")
    if result.get("would_send"):
        would = result["would_send"]
        print()
        print(f"  Partirait vers : {would['to']}")
        print(f"  Cc            : {', '.join(would.get('cc') or []) or 'aucun'}")
        print(f"  Source adresse : {would['contact_source']}")
        print(f"  Objet          : {would['subject']}")
        # Dire ce qui part évite de découvrir après coup qu'une lettre écartée
        # l'était, ou qu'une lettre voulue manquait au dossier.
        print(f"  Pièces jointes : {', '.join(would.get('attachments') or []) or 'aucune'}")
    print()
    if result["refused"]:
        print(f"REFUSÉ — {result['refusal']}")
    elif not result["commit"]:
        print("DRY-RUN — rien n'a été envoyé. Relancer avec --send pour un envoi réel.")
    elif result["sent"]:
        print(f"ENVOYÉ (message {result.get('message_id') or 'sans identifiant'}).")
    else:
        print(f"ÉCHEC — {result.get('send_error')}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Envoi d'un dossier de candidature. Défaut sec : rien ne part sans --send."
    )
    parser.add_argument("--dossier", required=True, help="Répertoire du dossier de candidature")
    parser.add_argument(
        "--send", action="store_true", help="Envoi réel. Sans ce drapeau, aucune connexion n'est établie."
    )
    parser.add_argument("--tracker", default="data/applications_tracker.json")
    parser.add_argument("--companies", default="config/companies.csv")
    parser.add_argument(
        "--json", action="store_true", help="Sortie machine (JSON) au lieu du rapport lisible."
    )
    args = parser.parse_args(argv)

    sender = None
    if args.send:
        from .sender import build_sender

        try:
            sender = build_sender()
        except RuntimeError as exc:
            print(f"ENVOI IMPOSSIBLE — {exc}")
            return 1
    else:
        # Sans --send, aucun fournisseur n'est même construit : rien ne sort.
        class _DrySender(EmailSender):
            provider = "dry-run"

            def send(self, to, subject, body, attachment=None):
                raise AssertionError("un envoi réel a été tenté sans --send")

        sender = _DrySender()

    result = send_dossier(
        args.dossier,
        sender,
        tracker=ApplicationTracker(args.tracker),
        companies_csv=args.companies,
        commit=args.send,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0 if not result["refused"] else 1
    print()
    _print_report(result)
    return 0 if not result["refused"] else 1


if __name__ == "__main__":
    sys.exit(main())
