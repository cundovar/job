"""Utilitaires partagés (étape 4 du plan) : normalisation de texte et JSON atomique."""

import json
import os
import stat

import pytest

from utils.json_files import write_json_atomic
from utils.text import fold, normalize, slugify, strip_accents, words


def test_les_quatre_normalisations_gardent_leur_difference():
    raw = "  Médiateur·rice  SOCIAL.E "
    assert fold(raw) == "  mediateur·rice  social.e "
    assert normalize(raw) == "mediateur·rice social.e"
    # Comportement historique de front_export : un caractère non ASCII disparaît.
    assert words(raw) == "mediateurrice social e"
    assert slugify(raw) == "mediateur-rice-social-e"


def test_valeurs_non_textuelles():
    assert fold(None) == "" and normalize(None) == "" and words(None) == ""
    assert fold(2026) == "2026"
    assert strip_accents("Éclair de Génie") == "Eclair de Genie"
    assert slugify("") == "candidature" and slugify("---", fallback="poste") == "poste"


def test_ecriture_json_atomique_et_droits_conserves(tmp_path):
    target = tmp_path / "tracker.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o640)
    write_json_atomic(target, {"clé": "é"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"clé": "é"}
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ["tracker.json"]


def test_une_ecriture_ratee_laisse_l_ancien_fichier_intact(tmp_path):
    target = tmp_path / "tracker.json"
    target.write_text('{"avant": true}', encoding="utf-8")
    with pytest.raises(TypeError):
        write_json_atomic(target, {"objet": object()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"avant": True}
    assert [p.name for p in tmp_path.iterdir()] == ["tracker.json"]
