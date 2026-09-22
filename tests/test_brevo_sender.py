"""Tests du fournisseur Brevo (applications/sender.py) : payload, PJ, priorité."""

import base64
import json

from applications.sender import BrevoEmailSender, build_sender


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_brevo_sender_posts_payload_with_attachments(monkeypatch, tmp_path):
    monkeypatch.setenv("BREVO_API_KEY", "key-test")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "me@varascundo.com")
    cv = tmp_path / "cv_final.pdf"
    cv.write_bytes(b"%PDF-1.4 fake")
    captured = {}

    def fake_urlopen(request, timeout=30):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse({"messageId": "msg-123"})

    monkeypatch.setattr("applications.sender.urllib.request.urlopen", fake_urlopen)

    lettre = tmp_path / "lettre_motivation.pdf"
    lettre.write_bytes(b"%PDF-1.4 lettre")
    sender = BrevoEmailSender()
    result = sender.send(
        to="agence@yotta.paris",
        subject="Candidature spontanée",
        body="Bonjour,",
        attachments=[cv, lettre],
        html="<div><p>Bonjour,</p></div>",
    )

    assert result.ok is True
    assert result.provider == "brevo"
    assert result.message_id == "msg-123"
    assert captured["url"].startswith("https://api.brevo.com/v3/smtp/email")
    assert captured["payload"]["to"] == [{"email": "agence@yotta.paris"}]
    assert captured["payload"]["sender"]["email"] == "me@varascundo.com"
    assert captured["payload"]["textContent"] == "Bonjour,"
    assert captured["payload"]["htmlContent"].startswith("<div>")
    names = [a["name"] for a in captured["payload"]["attachment"]]
    assert names == ["cv_final.pdf", "lettre_motivation.pdf"]
    assert captured["payload"]["attachment"][0]["content"] == base64.b64encode(b"%PDF-1.4 fake").decode("ascii")


def test_brevo_sender_requires_key_and_validated_sender(monkeypatch):
    # Le chargeur .env réinjecterait la vraie clé : on le neutralise ici.
    monkeypatch.setattr("applications.sender._load_repo_env", lambda: None)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_SENDER_EMAIL", raising=False)
    try:
        BrevoEmailSender()
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_build_sender_prefers_brevo_over_smtp(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "key-test")
    monkeypatch.setenv("EMAIL_PASSWORD", "smtp-present-trop")
    sender = build_sender()
    assert sender.provider == "brevo"
