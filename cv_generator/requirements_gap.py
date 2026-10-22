"""Écarts entre les exigences de l'annonce et le profil du candidat.

Demande Cundo (22/10/2026) : quand l'annonce exige un diplôme ou une durée
d'expérience que le profil ne couvre pas, l'écart est dit noir sur blanc, et
le CV comme la lettre travaillent les compétences pour le compenser — sans
jamais revendiquer un diplôme absent.

Deux sources, complémentaires :
- Python lit le niveau de diplôme et la durée d'expérience exigés dans le texte
  de l'annonce, et les compare au profil maître (diplômes obtenus, périodes
  d'expérience). C'est le filet : un écart de diplôme ne dépend pas de l'IA.
- L'agent analyste peut signaler d'autres écarts (une compétence, un permis…)
  et propose pour chacun ce qui compense. Ce texte n'est qu'une piste : ce que
  le CV en tire passe ensuite par le contrôle de véracité.

Les niveaux suivent la nomenclature française des diplômes : 3 = CAP, 4 = Bac,
5 = Bac+2, 6 = Bac+3/4 (licence, master 1, titre niveau 6), 7 = Bac+5
(master), 8 = doctorat.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Tuple

from .utils import normalize, period_bounds

GAP_TYPES = ("diplome", "experience", "competence", "autre")
MAX_GAPS = 6

# Du plus élevé au plus bas : le premier motif trouvé dans une ligne l'emporte.
_LEVEL_PATTERNS: List[Tuple[int, str, str]] = [
    (8, r"\bdoctorat\b|\bphd\b|\bbac\s*\+\s*8\b|\bniveau\s*8\b", "Doctorat (niveau 8)"),
    (7, r"\bmaster\s*2\b|\bbac\s*\+\s*5\b|\bniveau\s*7\b|\bmba\b|\bdiplome d.ingenieur\b", "Master / Bac+5 (niveau 7)"),
    (7, r"\bmaster\b(?!\s*1)", "Master / Bac+5 (niveau 7)"),
    (6, r"\bmaster\s*1\b|\bbac\s*\+\s*[34]\b|\blicence\b|\bbachelor\b|\bniveau\s*6\b", "Bac+3/4 (niveau 6)"),
    (5, r"\bbac\s*\+\s*2\b|\bbts\b|\bdut\b|\bdeug\b|\bniveau\s*5\b", "Bac+2 (niveau 5)"),
    (4, r"\bbac(?:calaureat)?\b(?!\s*\+)|\bniveau\s*4\b", "Bac (niveau 4)"),
    (3, r"\bcap\b|\bbep\b|\bniveau\s*3\b", "CAP (niveau 3)"),
]
_REQUIREMENT_CONTEXT = re.compile(
    r"niveau|diplome|etudes|formation|titulaire|profil|bac|master|licence|requis|exige|minimum"
)
_YEARS_REQUIRED = [
    re.compile(r"(?:au moins|minimum|min\.?)\s*(\d{1,2})\s*ans?\b[^.\n]{0,40}experience"),
    re.compile(r"experience[^.\n]{0,40}?(?:au moins|minimum|min\.?|de|d.au moins)\s*(\d{1,2})\s*ans?\b"),
    re.compile(r"(\d{1,2})\s*ans?\s*(?:minimum\s*)?d.experience"),
]
_YEARS_CLAIM = re.compile(r"(\d{1,2})\s*(?:\+\s*)?ans?\s*(?:d['’ ]\s*)?exp[ée]rience", re.IGNORECASE)
_IN_PROGRESS = re.compile(r"en cours|vae|preparation|en preparation")


def _level_of(text: str) -> Tuple[int, str]:
    for level, pattern, label in _LEVEL_PATTERNS:
        if re.search(pattern, text):
            return level, label
    return 0, ""


def required_diploma(job_text: str) -> Tuple[int, str, str]:
    """(niveau exigé, libellé, extrait de l'annonce) ; niveau 0 si rien n'est exigé."""
    best = (0, "", "")
    for raw_line in re.split(r"[\n•;]|(?<=\.)\s", str(job_text or "")):
        line = normalize(raw_line)
        if not line or not _REQUIREMENT_CONTEXT.search(line):
            continue
        level, label = _level_of(line)
        if level > best[0]:
            best = (level, label, " ".join(raw_line.split())[:200])
    return best


def candidate_diplomas(master: Dict[str, Any]) -> Tuple[int, str, List[str]]:
    """(plus haut niveau obtenu, son intitulé, diplômes en cours)."""
    best_level, best_title, in_progress = 0, "", []
    for entry in (master.get("person", {}) or {}).get("education", []) or []:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "")
        text = normalize(f"{entry.get('level') or ''} {title}")
        level, _ = _level_of(text)
        if _IN_PROGRESS.search(normalize(entry.get("status") or "")):
            if level:
                in_progress.append(f"{title} (niveau {level}, {entry.get('status')})")
            continue
        if level > best_level:
            best_level, best_title = level, title
    return best_level, best_title, in_progress


def required_years(job_text: str) -> Tuple[int, str]:
    text = normalize(job_text)
    for pattern in _YEARS_REQUIRED:
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 20)
            return int(match.group(1)), text[start:match.end() + 20].strip()
    return 0, ""


def experience_years(master: Dict[str, Any], today: date | None = None) -> float:
    """Années d'expérience couvertes par les périodes du profil (chevauchements comptés une fois)."""
    today = today or date.today()
    now = f"{today.year:04d}-{today.month:02d}"
    months: set[int] = set()
    for entry in (master.get("experience_catalog", {}) or {}).values():
        if not isinstance(entry, dict) or entry.get("retired"):
            continue
        start, end = period_bounds(entry.get("period"))
        if start.startswith("0000"):
            continue
        end = min(end, now)
        sy, sm = (int(x) for x in start.split("-"))
        ey, em = (int(x) for x in end.split("-"))
        months.update(range(sy * 12 + sm, ey * 12 + em + 1))
    return len(months) / 12


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def detect_gaps(job_text: str, master: Dict[str, Any], proposed: Any = None) -> List[Dict[str, Any]]:
    """Écarts détectés par Python, complétés par ceux que l'agent a signalés."""
    agent_gaps: List[Dict[str, Any]] = []
    for item in proposed if isinstance(proposed, list) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "autre").strip().lower()
        agent_gaps.append({
            "type": kind if kind in GAP_TYPES else "autre",
            "exigence": _clip(item.get("exigence"), 200),
            "profil": _clip(item.get("profil"), 300),
            "compensation": _clip(item.get("compensation"), 400),
            "source": "agent",
        })
    agent_by_type = {gap["type"]: gap for gap in agent_gaps}

    gaps: List[Dict[str, Any]] = []
    level, label, extract = required_diploma(job_text)
    held, held_title, in_progress = candidate_diplomas(master)
    if level and held < level:
        profil = f"{held_title} (niveau {held})" if held else "aucun diplôme de ce niveau"
        if in_progress:
            profil += " ; en cours : " + ", ".join(in_progress)
        gaps.append({
            "type": "diplome",
            "exigence": label,
            "extrait": extract,
            "profil": profil,
            "compensation": agent_by_type.get("diplome", {}).get("compensation", ""),
            "source": "python",
        })
    years, years_extract = required_years(job_text)
    covered = experience_years(master)
    if years and covered < years:
        gaps.append({
            "type": "experience",
            "exigence": f"{years} ans d'expérience",
            "extrait": years_extract,
            "profil": f"{covered:.1f} ans couverts par les périodes du profil",
            "compensation": agent_by_type.get("experience", {}).get("compensation", ""),
            "source": "python",
        })
    detected = {gap["type"] for gap in gaps}
    for gap in agent_gaps:
        # Diplôme et durée se mesurent : l'agent ne crée pas un écart que les
        # données démentent, il complète seulement la compensation.
        if gap["type"] in {"diplome", "experience"}:
            continue
        if gap["exigence"]:
            gaps.append(gap)
    return gaps[:MAX_GAPS]


def has_diploma_gap(plan: Dict[str, Any] | None) -> bool:
    return any(gap.get("type") == "diplome" for gap in (plan or {}).get("ecarts") or [])


def years_claims(text: str) -> List[int]:
    """Durées d'expérience affirmées dans un texte (« 4 ans d'expérience »)."""
    return [int(match.group(1)) for match in _YEARS_CLAIM.finditer(str(text or ""))]


GAP_CLAUSE = """
L'annonce exige ce que le profil ne couvre pas (plan_adaptation.ecarts). Compense par les
compétences, sans jamais masquer ni maquiller l'écart :
- l'accroche met en avant les années de pratique réelles et des résultats concrets tirés de la
  source, pas les titres ; toute durée (« N ans d'expérience ») doit découler des périodes de
  source_verite, sinon ne l'écris pas ;
- les compétences et les expériences qui répondent directement aux missions de l'annonce passent
  en premier ; la formation vient en dernier ;
- ne revendique jamais un diplôme absent, ni une « équivalence », ni un niveau supérieur à celui
  de la source ; un diplôme en cours s'affiche comme en cours.
"""


def gap_clause(plan: Dict[str, Any] | None) -> str:
    return GAP_CLAUSE if (plan or {}).get("ecarts") else ""
