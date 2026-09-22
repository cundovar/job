"""
Fournisseurs d'envoi pour la brique candidature.

L'interface est agnostique du choix Gmail personnel vs domaine authentifié :
tout vient de l'environnement (EMAIL_SMTP_SERVER/PORT/SENDER/SMTP_LOGIN/PASSWORD),
rien n'est codé en dur. Zéro appel réseau dans cette brique côté tests : les tests
utilisent leur propre fake ou monkeypatchent smtplib.
"""
from __future__ import annotations

import base64
import json
import os
import smtplib
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider: str
    message_id: str = ""
    error: str = ""


def _load_repo_env() -> None:
    """Charge le .env du repo (clé=valeur) sans dépendance externe.

    setdefault : une vraie variable d'environnement (Coolify en prod) gagne
    toujours sur le fichier.
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


ATTACHMENT_LABELS = {
    "cv_final.pdf": "CV - Facundo Varas.pdf",
    "cv_ats.pdf": "CV ATS - Facundo Varas.pdf",
    "lettre_motivation.pdf": "Lettre de motivation - Facundo Varas.pdf",
}


def _attachment_label(path: Path) -> str:
    """Nom lisible pour le destinataire, pas un nom de fichier interne."""
    return ATTACHMENT_LABELS.get(Path(path).name.lower(), Path(path).name)


class EmailSender(ABC):
    """Ce qui sait partir vers l'extérieur. Une seule implémentation réseau."""

    provider = "abstract"

    @abstractmethod
    def send(
        self,
        to: str,
        subject: str,
        body: str,
        attachment: Path | None = None,
        attachments: Sequence[Path] = (),
        html: str | None = None,
    ) -> SendResult:
        raise NotImplementedError


class SMTPEmailSender(EmailSender):
    """Envoi SMTP réel. Identifiants lus depuis l'environnement, jamais en dur."""

    provider = "smtp"

    def __init__(self) -> None:
        self.server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        self.port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.sender = os.getenv("EMAIL_SENDER")
        # Le login du relais n'est pas forcément l'adresse d'expédition. Sur un
        # relais type Brevo on s'authentifie avec le compte et on écrit depuis
        # une adresse vérifiée du domaine ; sur une boîte classique les deux
        # coïncident, d'où le repli sur EMAIL_SENDER.
        self.login = os.getenv("EMAIL_SMTP_LOGIN") or os.getenv("EMAIL_SENDER")
        self.password = os.getenv("EMAIL_PASSWORD")
        if not self.sender or not self.password:
            raise RuntimeError(
                "Envoi réel impossible : EMAIL_SENDER et EMAIL_PASSWORD doivent "
                "être définis dans l'environnement."
            )

    def send(self, to: str, subject: str, body: str, attachment: Path | None = None,
             attachments: Sequence[Path] = (), html: str | None = None) -> SendResult:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")
        for path in ([attachment] if attachment else []) + list(attachments):
            message.add_attachment(
                path.read_bytes(),
                maintype="application",
                subtype="pdf",
                filename=_attachment_label(path),
            )
        try:
            with smtplib.SMTP(self.server, self.port) as connection:
                connection.starttls()
                connection.login(self.login, self.password)
                connection.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            return SendResult(ok=False, provider=self.provider, error=str(exc))
        return SendResult(ok=True, provider=self.provider, message_id=message["Message-ID"] or "")


class BrevoEmailSender(EmailSender):
    """Envoi via l'API HTTPS Brevo (https://api.brevo.com/v3/smtp/email).

    Le SMTP sortant (25/465/587) est bloqué sur le VPS : l'API passe par 443.
    Clé et expéditeur validé viennent de l'environnement, jamais en dur.
    """

    provider = "brevo"
    API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self) -> None:
        _load_repo_env()
        self.api_key = os.getenv("BREVO_API_KEY", "").strip()
        self.sender = os.getenv("BREVO_SENDER_EMAIL") or os.getenv("EMAIL_SENDER")
        self.sender_name = os.getenv("BREVO_SENDER_NAME", "Facundo Varas")
        self.reply_to = os.getenv("BREVO_REPLY_TO") or os.getenv("EMAIL_SENDER")
        if not self.api_key or not self.sender:
            raise RuntimeError(
                "Envoi Brevo impossible : BREVO_API_KEY et un expéditeur validé "
                "(BREVO_SENDER_EMAIL ou EMAIL_SENDER) doivent être définis."
            )

    def send(self, to: str, subject: str, body: str, attachment: Path | None = None,
             attachments: Sequence[Path] = (), html: str | None = None) -> SendResult:
        files = []
        for path in ([attachment] if attachment else []) + list(attachments):
            files.append({
                "name": _attachment_label(path),
                "content": base64.b64encode(Path(path).read_bytes()).decode("ascii"),
            })
        payload: dict[str, Any] = {
            "sender": {"name": self.sender_name, "email": self.sender},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        }
        if html:
            payload["htmlContent"] = html
        if self.reply_to:
            payload["replyTo"] = {"email": self.reply_to}
        if files:
            payload["attachment"] = files
        request = urllib.request.Request(
            self.API_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "api-key": self.api_key,
                "content-type": "application/json",
                "accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            return SendResult(ok=False, provider=self.provider, error=f"HTTP {exc.code} : {detail}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return SendResult(ok=False, provider=self.provider, error=str(exc))
        return SendResult(ok=True, provider=self.provider, message_id=str(data.get("messageId") or ""))


def build_sender() -> EmailSender:
    """Brevo d'abord (API HTTPS 443 — le SMTP sortant est bloqué sur le VPS),
    repli SMTP classique pour les environnements qui l'autorisent."""
    if os.getenv("BREVO_API_KEY", "").strip():
        return BrevoEmailSender()
    if os.getenv("EMAIL_SMTP_SERVER") or os.getenv("EMAIL_PASSWORD"):
        return SMTPEmailSender()
    raise RuntimeError(
        "Aucun fournisseur d'envoi configuré : définir BREVO_API_KEY (API Brevo, "
        "recommandé sur ce VPS) ou les variables EMAIL_SMTP_* (relais SMTP sortant)."
    )
