import json

from applications.candidatures_index import rebuild_candidatures_index


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
