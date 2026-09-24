"""La brique envoi : chaque contrôle refusant son motif, zéro réseau sans --send."""
import json
from pathlib import Path
from datetime import date

import pytest

from applications.application_tracker import ApplicationTracker
from applications.send import _mail_parts, recipient_fingerprint, send_dossier
from applications.sender import EmailSender, SendResult, SMTPEmailSender


class FakeSender(EmailSender):
    provider = "fake"

    def __init__(self, ok: bool = True):
        self.calls = []
        self.ok = ok

    def send(self, to, subject, body, attachment=None, attachments=None, html=None, cc=()):
        self.calls.append({
            "to": to,
            "cc": list(cc or []),
            "subject": subject,
            "body": body,
            "attachments": [Path(a).name for a in (attachments or [])],
            "html": html,
        })
        if self.ok:
            return SendResult(ok=True, provider=self.provider, message_id="<fake-1@localhost>")
        return SendResult(ok=False, provider=self.provider, error="relais injoignable")


ECONOVIA_CONTACT = [
    {
        "claim": "Econovia affiche publiquement l'adresse de contact contact@econovia.fr.",
        "evidence": ["contact@econovia.fr affichée sur https://econovia.fr/"],
    }
]


def make_dossier(tmp_path, status="APPROVED", company="Econovia", contact=ECONOVIA_CONTACT, recipients=None):
    dossier = tmp_path / "dossier"
    dossier.mkdir()
    job = {
        "title": "Développeur web / Intégrateur",
        "company": company,
        "url": "https://econovia.fr",
        "public_contact": contact,
    }
    (dossier / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    selected = recipients if recipients is not None else (
        [] if not contact else [{"email": "contact@econovia.fr", "role": "to", "source": "https://econovia.fr/"}]
    )
    metadata = {"status": status, "send_recipients": selected}
    if status == "APPROVED":
        metadata["approval_recipients_hash"] = recipient_fingerprint(selected)
    (dossier / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (dossier / "mail_candidature.md").write_text(
        "Objet : Candidature spontanée — Développeur web / Intégrateur\n\n"
        "Bonjour,\n\nCorps du message.\n",
        encoding="utf-8",
    )
    return dossier


CLEAN_COMPANIES = [{"nom": "Econovia", "site": "https://econovia.fr", "statut": "prioritaire"}]


def test_refused_without_approved_status(tmp_path):
    """Un dossier non validé par l'humain ne part pas."""
    dossier = make_dossier(tmp_path, status="ready_to_apply")

    result = send_dossier(
        dossier,
        FakeSender(),
        tracker=ApplicationTracker(tmp_path / "tracker.json"),
        companies_csv="/dev/null",
    )

    assert result["refused"]
    assert "statut APPROVED" in result["refusal"]


def test_refused_for_do_not_contact_company(tmp_path):
    """DO_NOT_CONTACT est prioritaire : une entreprise ecartee ne reçoit jamais."""
    dossier = make_dossier(tmp_path)
    ecartee = [{"nom": "Econovia", "site": "https://econovia.fr", "statut": "ecartee"}]

    result = send_dossier(dossier, FakeSender(), companies_csv=write_companies(tmp_path, ecartee))

    assert result["refused"]
    assert "DO_NOT_CONTACT" in result["refusal"]


def write_companies(tmp_path, rows):
    import csv as _csv

    path = tmp_path / "companies.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(handle, fieldnames=["nom", "site", "statut"])
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_refused_when_company_already_contacted(tmp_path):
    """Un seul contact par entreprise, même via un autre dossier."""
    dossier = make_dossier(tmp_path)
    tracker = ApplicationTracker(tmp_path / "tracker.json")
    tracker.mark_sent(
        {"title": "Autre poste", "company": "Econovia", "url": "https://autre-annonce.fr"}, {}
    )

    result = send_dossier(dossier, FakeSender(), tracker=tracker, companies_csv="/dev/null")

    assert result["refused"]
    assert "déduplication" in result["refusal"]


def test_refused_when_the_same_site_carries_another_name(tmp_path):
    """Faux négatif du nom : même domaine, raison sociale différente, un seul envoi.

    C'est le cas que la comparaison de noms laissait passer — et le second envoi
    partait pour de bon.
    """
    dossier = make_dossier(tmp_path)
    tracker = ApplicationTracker(tmp_path / "tracker.json")
    tracker.mark_sent(
        {"title": "Autre poste", "company": "Studio Econovia Développement",
         "url": "https://www.econovia.fr/contact"},
        {},
    )

    result = send_dossier(dossier, FakeSender(), tracker=tracker, companies_csv="/dev/null")

    assert result["refused"]
    assert "déduplication" in result["refusal"] and "econovia.fr" in result["refusal"]


def test_a_lookalike_name_on_another_site_stays_contactable(tmp_path):
    """Faux positif du nom : « Econovia » ne doit pas bloquer « Econovia Conseil ».

    Deux domaines distincts, deux organisations : la seconde reste joignable.
    """
    dossier = make_dossier(tmp_path)
    tracker = ApplicationTracker(tmp_path / "tracker.json")
    tracker.mark_sent(
        {"title": "Poste", "company": "Econovia Conseil", "url": "https://econovia-conseil.com"}, {}
    )

    result = send_dossier(dossier, FakeSender(), tracker=tracker, companies_csv="/dev/null")

    assert not result["refused"], result.get("refusal")


def test_excluded_company_is_caught_despite_the_www_prefix(tmp_path):
    """DO_NOT_CONTACT ne se contourne pas avec un « www. » ou un slash final."""
    dossier = make_dossier(tmp_path)
    ecartee = [{"nom": "Tout autre nom", "site": "https://www.econovia.fr/", "statut": "ecartee"}]

    result = send_dossier(dossier, FakeSender(), companies_csv=write_companies(tmp_path, ecartee))

    assert result["refused"]
    assert "DO_NOT_CONTACT" in result["refusal"]


def test_refused_when_daily_quota_exhausted(tmp_path, monkeypatch):
    dossier = make_dossier(tmp_path)
    tracker = ApplicationTracker(tmp_path / "tracker.json")
    tracker.mark_sent(
        {"title": "Ailleurs", "company": "Autre Structure", "url": "https://ailleurs.fr"}, {}
    )
    monkeypatch.setenv("SEND_DAILY_QUOTA", "1")

    result = send_dossier(
        dossier, FakeSender(), tracker=tracker, companies_csv="/dev/null", today=date.today()
    )

    assert result["refused"]
    assert "quota" in result["refusal"]


def test_refused_without_verified_address(tmp_path):
    """Pas d'adresse en clair dans les constats : pas de destinataire inventé (cas RUP)."""
    dossier = make_dossier(tmp_path, contact=[])

    result = send_dossier(
        dossier,
        FakeSender(),
        tracker=ApplicationTracker(tmp_path / "tracker.json"),
        companies_csv="/dev/null",
    )

    assert result["refused"]
    assert "ne se reconstitue pas" in result["refusal"]


def test_dry_run_touches_neither_sender_nor_tracker(tmp_path):
    """Sans commit, le fournisseur n'est pas appelé et le tracker reste intact."""
    dossier = make_dossier(tmp_path)
    tracker_path = tmp_path / "tracker.json"
    sender = FakeSender()

    result = send_dossier(
        dossier, sender, tracker=ApplicationTracker(tracker_path), companies_csv="/dev/null"
    )

    assert not result["sent"] and not result["refused"]
    assert sender.calls == []
    assert not tracker_path.exists()
    assert result["would_send"]["to"] == "contact@econovia.fr"
    assert result["would_send"]["cc"] == []
    assert result["would_send"]["subject"].startswith("Candidature spontanée")


def test_multi_recipient_send_uses_one_to_and_ccs(tmp_path):
    recipients = [
        {"email": "contact@econovia.fr", "role": "to", "source": "fixture"},
        {"email": "rh@econovia.fr", "role": "cc", "source": "fixture"},
    ]
    dossier = make_dossier(tmp_path, recipients=recipients)
    sender = FakeSender()

    result = send_dossier(
        dossier,
        sender,
        tracker=ApplicationTracker(tmp_path / "tracker.json"),
        companies_csv="/dev/null",
        commit=True,
    )

    assert result["sent"]
    assert sender.calls[0]["to"] == "contact@econovia.fr"
    assert sender.calls[0]["cc"] == ["rh@econovia.fr"]
    assert len(sender.calls) >= 1
    if len(sender.calls) > 1:
        assert sender.calls[1]["cc"] == []


def test_refused_when_approved_recipient_fingerprint_changed(tmp_path):
    dossier = make_dossier(tmp_path)
    metadata_path = dossier / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["send_recipients"][0]["email"] = "other@econovia.fr"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    result = send_dossier(dossier, FakeSender(), companies_csv="/dev/null")

    assert result["refused"]
    assert "approbation des destinataires" in result["refusal"]


def test_real_send_journals_the_full_feedback_loop(tmp_path, monkeypatch):
    """L'envoi réel journalise tout ce que l'étape 6 du plan attendra."""
    # Déterministe : l'accusé part vers une adresse fixée, pas celle du .env local.
    monkeypatch.setenv("BREVO_CONFIRM_TO", "varas.cundo@gmail.com")
    dossier = make_dossier(tmp_path)
    tracker = ApplicationTracker(tmp_path / "tracker.json")
    sender = FakeSender()

    result = send_dossier(
        dossier, sender, tracker=tracker, companies_csv="/dev/null", commit=True
    )

    assert result["sent"]
    # Envoi réel + accusé de réception vers l'expéditeur (même fournisseur).
    assert len(sender.calls) == 2
    assert sender.calls[1]["to"] == "varas.cundo@gmail.com"
    assert sender.calls[1]["subject"].startswith("✓ Candidature envoyée à Econovia")
    record = tracker.list_records()[0]
    # Contrat règle 5 : les champs minimaux d'un record applied restent là.
    for field in ("status", "applied_at", "follow_up_at", "job_title", "company", "key", "created_at", "updated_at"):
        assert field in record, field
    assert record["status"] == "applied"
    # Et les champs de la boucle de retour sont en place dès le premier envoi.
    send_info = record["send"]
    assert send_info["to"] == "contact@econovia.fr"
    assert send_info["cc"] == []
    assert "econovia.fr" in send_info["contact_source"]
    assert send_info["provider"] == "fake"
    assert send_info["message_id"] == "<fake-1@localhost>"
    assert send_info["dossier"] == str(dossier)
    assert send_info["outcome"] == {"reply": None, "interview": None, "rejection_reason": None}


def test_failed_send_is_journalled_and_blocks_retry(tmp_path):
    """Un envoi raté laisse une trace : on ne retente jamais à l'aveugle."""
    dossier = make_dossier(tmp_path)
    tracker = ApplicationTracker(tmp_path / "tracker.json")
    sender = FakeSender(ok=False)

    result = send_dossier(dossier, sender, tracker=tracker, companies_csv="/dev/null", commit=True)

    assert not result["sent"] and result["send_error"] == "relais injoignable"
    record = tracker.list_records()[0]
    assert record["status"] == "send_failed"
    assert record["send"]["error"] == "relais injoignable"

    retry = send_dossier(dossier, FakeSender(), tracker=tracker, companies_csv="/dev/null")
    assert retry["refused"] and "déduplication" in retry["refusal"]


def test_smtp_sender_sends_through_smtp_without_network(tmp_path, monkeypatch):
    """L'implémentation réelle est exercée via un smtplib factice : zéro réseau.

    Sans EMAIL_SMTP_LOGIN, le login du relais retombe sur l'adresse
    d'expédition. La variable est retirée explicitement : plusieurs modules
    appellent load_dotenv() à l'import, donc le vrai .env entre dans
    l'environnement de la suite et ce repli ne doit pas dépendre de lui.
    """
    captured = {}

    class FakeSMTP:
        def __init__(self, server, port):
            captured["server"] = server
            captured["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            captured["starttls"] = True

        def login(self, user, password):
            captured["login"] = user

        def send_message(self, message):
            captured["to"] = message["To"]
            captured["subject"] = message["Subject"]

    monkeypatch.setattr("applications.sender.smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("EMAIL_SMTP_SERVER", "smtp.test.local")
    monkeypatch.setenv("EMAIL_SMTP_PORT", "587")
    monkeypatch.setenv("EMAIL_SENDER", "cundo@test.local")
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")
    monkeypatch.delenv("EMAIL_SMTP_LOGIN", raising=False)

    result = SMTPEmailSender().send("cible@entreprise.fr", "Objet test", "Corps test")

    assert result.ok and result.provider == "smtp"
    assert captured == {
        "server": "smtp.test.local",
        "port": 587,
        "starttls": True,
        "login": "cundo@test.local",
        "to": "cible@entreprise.fr",
        "subject": "Objet test",
    }


def test_smtp_login_can_differ_from_the_visible_sender(tmp_path, monkeypatch):
    """Sur un relais, on s'authentifie avec le compte et on écrit depuis le domaine.

    Le login du relais ne doit jamais fuiter dans l'en-tête From : le
    destinataire voit l'adresse du domaine, pas l'identité du compte d'envoi.
    """
    captured = {}

    class FakeSMTP:
        def __init__(self, server, port):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            pass

        def login(self, user, password):
            captured["login"] = user

        def send_message(self, message):
            captured["from"] = message["From"]

    monkeypatch.setattr("applications.sender.smtplib.SMTP", FakeSMTP)
    monkeypatch.setenv("EMAIL_SENDER", "contact@domaine.test")
    monkeypatch.setenv("EMAIL_SMTP_LOGIN", "compte-relais@fournisseur.test")
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")

    SMTPEmailSender().send("cible@entreprise.fr", "Objet", "Corps")

    assert captured["login"] == "compte-relais@fournisseur.test"
    assert captured["from"] == "contact@domaine.test"


def test_smtp_sender_refuses_to_build_without_credentials(monkeypatch):
    """Sans identifiants en environnement, l'envoi réel est impossible, pas silencieux."""
    monkeypatch.delenv("EMAIL_SENDER", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="EMAIL_SENDER"):
        SMTPEmailSender()


def test_mail_parts_splits_subject_from_body(tmp_path):
    dossier = make_dossier(tmp_path)
    subject, body = _mail_parts(dossier / "mail_candidature.md")

    assert subject == "Candidature spontanée — Développeur web / Intégrateur"
    assert body.startswith("Bonjour,")
    assert "Objet :" not in body


def test_cli_without_send_flag_establishes_no_connection(tmp_path, capsys):
    """Critère de fin : la commande sans --send n'établit aucune connexion sortante."""
    from applications.send import main

    dossier = make_dossier(tmp_path)
    companies = write_companies(tmp_path, CLEAN_COMPANIES)

    exit_code = main(
        [
            "--dossier", str(dossier),
            "--tracker", str(tmp_path / "tracker.json"),
            "--companies", str(companies),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "DRY-RUN" in output
    assert "statut APPROVED" in output and "DO_NOT_CONTACT" in output
    assert "déduplication" in output and "quota du jour" in output


def _pdfs(dossier):
    """Pose un CV validé et une lettre, comme un dossier prêt à partir."""
    (dossier / "cv").mkdir(exist_ok=True)
    (dossier / "cv" / "cv_final.pdf").write_bytes(b"%PDF-1.4 cv")
    (dossier / "lettre_motivation.pdf").write_bytes(b"%PDF-1.4 lettre")


def test_la_lettre_part_avec_le_cv_par_defaut(tmp_path):
    dossier = make_dossier(tmp_path)
    _pdfs(dossier)
    sender = FakeSender()

    result = send_dossier(
        dossier, sender,
        tracker=ApplicationTracker(tmp_path / "tracker.json"),
        companies_csv="/dev/null", commit=True,
    )

    assert result["attachments"] == ["cv_final.pdf", "lettre_motivation.pdf"]
    assert sender.calls[0]["attachments"] == ["cv_final.pdf", "lettre_motivation.pdf"]


def test_la_lettre_peut_etre_ecartee_de_l_envoi(tmp_path):
    """Le candidat juge parfois la lettre inutile : seul le CV part alors."""
    dossier = make_dossier(tmp_path)
    _pdfs(dossier)
    metadata_path = dossier / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["send_include_lettre"] = False
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    sender = FakeSender()

    result = send_dossier(
        dossier, sender,
        tracker=ApplicationTracker(tmp_path / "tracker.json"),
        companies_csv="/dev/null", commit=True,
    )

    assert result["sent"]
    assert result["attachments"] == ["cv_final.pdf"]
    assert sender.calls[0]["attachments"] == ["cv_final.pdf"]
    # La lettre reste dans le dossier : elle n'est pas jointe, pas supprimée.
    assert (dossier / "lettre_motivation.pdf").exists()


def test_le_dry_run_annonce_les_pieces_jointes(tmp_path):
    dossier = make_dossier(tmp_path)
    _pdfs(dossier)

    result = send_dossier(
        dossier, FakeSender(),
        tracker=ApplicationTracker(tmp_path / "tracker.json"),
        companies_csv="/dev/null",
    )

    assert not result["refused"]
    assert result["would_send"]["attachments"] == ["cv_final.pdf", "lettre_motivation.pdf"]
