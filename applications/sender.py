"""
Fournisseurs d'envoi pour la brique candidature.

L'interface est agnostique du choix Gmail personnel vs domaine authentifié :
tout vient de l'environnement (EMAIL_SMTP_SERVER/PORT/SENDER/SMTP_LOGIN/PASSWORD),
rien n'est codé en dur. Zéro appel réseau dans cette brique côté tests : les tests
utilisent leur propre fake ou monkeypatchent smtplib.
"""
from __future__ import annotations

import os
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SendResult:
    ok: bool
    provider: str
    message_id: str = ""
    error: str = ""


class EmailSender(ABC):
    """Ce qui sait partir vers l'extérieur. Une seule implémentation réseau."""

    provider = "abstract"

    @abstractmethod
    def send(self, to: str, subject: str, body: str, attachment: Path | None = None) -> SendResult:
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

    def send(self, to: str, subject: str, body: str, attachment: Path | None = None) -> SendResult:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if attachment is not None:
            message.add_attachment(
                attachment.read_bytes(),
                maintype="application",
                subtype="pdf",
                filename=attachment.name,
            )
        try:
            with smtplib.SMTP(self.server, self.port) as connection:
                connection.starttls()
                connection.login(self.login, self.password)
                connection.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            return SendResult(ok=False, provider=self.provider, error=str(exc))
        return SendResult(ok=True, provider=self.provider, message_id=message["Message-ID"] or "")


def build_sender() -> EmailSender:
    """Point d'assemblage de la CLI : la vraie implémentation, configurée par l'env."""
    return SMTPEmailSender()
