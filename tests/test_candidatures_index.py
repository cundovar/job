import json
from pathlib import Path
from types import SimpleNamespace

from applications.candidatures_index import rebuild_candidatures_index
from hermes_commands import job_prepare_payload


def test_rebuild_candidatures_index_uses_project_owned_application_files(tmp_path):
    applications_dir = tmp_path / "output" / "applications"
    application_dir = applications_dir / "2026-08-26_acme_automation-specialist"
    application_dir.mkdir(parents=True)
    (application_dir / "lettre_motivation.md").write_text(
        "# Lettre Acme\n",
        encoding="utf-8",
    )
    (application_dir / "mail_candidature.md").write_text(
        "Objet : candidature Acme\n",
        encoding="utf-8",
    )
    (application_dir / "metadata.json").write_text(
        json.dumps(
            {
                "job_title": "Automation Specialist",
                "company": "Acme",
                "created_at": "2026-08-26T10:30:00+00:00",
                "recommended_cv": {
                    "cv_name": "Développeur automatisation IA",
                    "score": 12,
                    "matched_keywords": ["n8n", "API"],
                },
            }
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "front" / "public" / "data" / "candidatures.json"

    result = rebuild_candidatures_index(applications_dir, index_path)

    saved = json.loads(index_path.read_text(encoding="utf-8"))
    assert result == {"ok": True, "total": 1}
    assert saved == {
        "candidatures": [
            {
                "id": application_dir.name,
                "date": "2026-08-26",
                "entreprise": "Acme",
                "poste": "Automation Specialist",
                "lettre": "# Lettre Acme\n",
                "mail": "Objet : candidature Acme\n",
                "cv_recommande": (
                    "CV conseillé : Développeur automatisation IA\n"
                    "Score de correspondance : 12\n"
                    "Mots-clés détectés : n8n, API"
                ),
                "created_at": "2026-08-26 12:30",
                "metadata": {
                    "job_title": "Automation Specialist",
                    "company": "Acme",
                    "created_at": "2026-08-26T10:30:00+00:00",
                    "recommended_cv": {
                        "cv_name": "Développeur automatisation IA",
                        "score": 12,
                        "matched_keywords": ["n8n", "API"],
                    },
                },
            }
        ]
    }


def test_prepare_payload_rebuilds_index_without_external_hermes_script(
    tmp_path,
    monkeypatch,
    capsys,
):
    application_dir = (
        tmp_path / "output" / "applications" / "2026-08-26_acme_automation-specialist"
    )

    def fake_build_application_package(job, output_dir, user_profile):
        application_dir.mkdir(parents=True)
        letter_path = application_dir / "lettre_motivation.md"
        email_path = application_dir / "mail_candidature.md"
        metadata_path = application_dir / "metadata.json"
        letter_path.write_text("Lettre", encoding="utf-8")
        email_path.write_text("Mail", encoding="utf-8")
        metadata_path.write_text(
            json.dumps(
                {
                    "job_title": job["title"],
                    "company": job["company"],
                    "created_at": "2026-08-26T10:30:00+00:00",
                    "recommended_cv": {"cv_name": "CV IA", "score": 1},
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(
            directory=str(application_dir),
            motivation_letter_path=str(letter_path),
            application_email_path=str(email_path),
            metadata_path=str(metadata_path),
            recommended_cv=SimpleNamespace(cv_name="CV IA", cv_id="automation_ia"),
        )

    class FakeTracker:
        def __init__(self, path):
            self.path = path

        def mark_ready(self, job, package):
            return {"status": "ready_to_apply"}

    monkeypatch.setattr(job_prepare_payload, "PROJECT", Path(tmp_path))
    monkeypatch.setattr(job_prepare_payload, "load_criteria", lambda: {"user_profile": {}})
    monkeypatch.setattr(
        job_prepare_payload,
        "build_application_package",
        fake_build_application_package,
    )
    monkeypatch.setattr(job_prepare_payload, "ApplicationTracker", FakeTracker)
    monkeypatch.setattr(
        job_prepare_payload.sys,
        "stdin",
        SimpleNamespace(
            read=lambda: json.dumps(
                {"job": {"title": "Automation Specialist", "company": "Acme"}}
            )
        ),
    )

    job_prepare_payload.main()

    result = json.loads(capsys.readouterr().out)
    assert result["index"] == {"ok": True, "total": 1}
    assert result["id"] == application_dir.name
    index_path = tmp_path / "front" / "public" / "data" / "candidatures.json"
    assert json.loads(index_path.read_text(encoding="utf-8"))["candidatures"][0][
        "poste"
    ] == "Automation Specialist"
