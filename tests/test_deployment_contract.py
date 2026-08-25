from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runtime_image_contains_front_export_module():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    copy_commands = [
        line.split()
        for line in dockerfile.splitlines()
        if line.strip().startswith("COPY ")
    ]

    assert any("front_export.py" in command[1:-1] for command in copy_commands)


def test_job_cards_use_a_stable_react_key():
    app_source = (PROJECT_ROOT / "front" / "src" / "App.jsx").read_text(
        encoding="utf-8"
    )

    assert "<article key={prepareKey}" in app_source
    assert "<article key={i}" not in app_source


def test_runtime_installs_pdf_parser_and_assessment_config():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    config = PROJECT_ROOT / "config" / "cv_assessment.json"

    assert "pypdf==" in requirements
    assert "COPY config/ ./config/" in dockerfile
    assert config.exists()
