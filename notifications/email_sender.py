"""
Daily email sender using SMTP with Jinja2 templates.
"""
from __future__ import annotations

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape


class EmailSender:
    def __init__(self) -> None:
        self.smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.sender = os.getenv("EMAIL_SENDER")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.recipient = os.getenv("EMAIL_RECIPIENT")
        self._env = Environment(
            loader=FileSystemLoader("config"),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def _normalize_job(self, job: Dict) -> Dict:
        ai = job.get("ai_analysis") or {}
        recommendation = ai.get("recommandation") or "PEUT-ÊTRE"
        return {
            "title": job.get("title") or "",
            "company": job.get("company") or "",
            "location": job.get("location") or "",
            "contract_type": job.get("contract_type") or "",
            "sector": job.get("sector") or "",
            "salary": job.get("salary") or "",
            "score": job.get("score") or 0,
            "recommandation": recommendation,
            "ai_analysis": ai,
            "url": job.get("url") or "#",
        }

    def send_daily_report(self, jobs: List[Dict], stats: Dict) -> None:
        if os.getenv("DRY_RUN", "false").lower() == "true":
            return
        if not all([self.sender, self.password, self.recipient]):
            raise ValueError("Missing email configuration in environment variables")

        template = self._env.get_template("email_template.html")
        top_jobs = [self._normalize_job(j) for j in jobs]

        body = template.render(
            date=stats.get("date", ""),
            total_jobs=stats.get("total", 0),
            postuler_count=stats.get("postuler", 0),
            peut_etre_count=stats.get("peut_etre", 0),
            passer_count=stats.get("passer", 0),
            top_jobs=top_jobs,
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Rapport quotidien - {stats.get('date', '')}"
        msg["From"] = self.sender
        msg["To"] = self.recipient
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.sender, self.password)
            server.sendmail(self.sender, self.recipient, msg.as_string())
