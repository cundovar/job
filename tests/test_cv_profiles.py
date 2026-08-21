from applications.cv_profiles import load_cv_profiles


def test_load_cv_profiles():
    profiles = load_cv_profiles()
    assert profiles
    assert {profile.id for profile in profiles} >= {
        "webmaster",
        "dev_fullstack",
        "formateur_web",
        "formateur_ia",
    }


def test_load_cv_profiles_has_real_paths():
    from pathlib import Path
    profiles = load_cv_profiles()
    for profile in profiles:
        existing = profile.existing_paths
        assert len(existing) >= 1, f"{profile.id}: aucun CV trouvé (path={profile.path})"
