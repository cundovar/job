"""
Job offer summary — keyword-based, tuned for Cundo's current profile.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class JobSummary:
    position: str
    company: str
    location: str
    why_interesting: List[str]
    risks: List[str]
    action: str

    def to_markdown(self) -> str:
        interesting = self.why_interesting or ["Aucun point fort specifique detecte."]
        risks = self.risks or ["Aucun risque evident detecte."]
        lines = [
            "## Resume decisionnel",
            "",
            f"- Poste : {self.position}",
            f"- Entreprise : {self.company}",
            f"- Lieu : {self.location}",
            f"- Action : {self.action}",
            "",
            "### Pourquoi interessant",
            "",
        ]
        lines.extend(f"- {item}" for item in interesting)
        lines.extend(["", "### Risques", ""])
        lines.extend(f"- {item}" for item in risks)
        lines.append("")
        return "\n".join(lines)


def _normalize(value: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )
    lowered = without_accents.lower()
    return re.sub(r"\s+", " ", lowered).strip()


def _text(job: Dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            str(job.get(key, ""))
            for key in ("title", "description", "requirements", "sector", "contract_type", "location")
        )
    )


def _analysis_list(job: Dict[str, Any], key: str) -> List[str]:
    analysis = job.get("ai_analysis", {})
    if not isinstance(analysis, dict):
        return []
    value = analysis.get(key, [])
    return value if isinstance(value, list) else []


def _detect_interesting_points(job: Dict[str, Any], text: str) -> List[str]:
    points = list(_analysis_list(job, "points_forts"))
    keyword_points = [
        # Symfony / PHP
        (("symfony", "php 8", "doctrine"), "Stack PHP/Symfony — correspondance directe avec le profil."),
        (("api rest", "api platform"), "API REST — experience back-end alignee."),
        (("qualite de code", "phpstan", "phpunit", "tests unitaires"),
         "Qualite de code et tests — pratique active (PHPStan, PHPUnit)."),
        # Vue.js / React / Front
        (("vue", "nuxt", "vue.js", "vuejs"), "Stack Vue.js/Nuxt — competence solide (DevDoc, missions)."),
        (("react", "next.js", "nextjs"), "Stack React/Next.js — operationnel (missions freelance)."),
        (("typescript", "tailwind"), "Front-end moderne — competences alignees."),
        (("html", "css", "javascript", "frontend", "front-end"),
         "Front-end web — competence de base solide et polyvalente."),
        # WordPress / CMS
        (("wordpress", "woocommerce"), "WordPress/WooCommerce — mission freelance en cours."),
        (("cms", "headless", "jamstack"), "CMS / headless — experience concrete (WordPress headless)."),
        (("webmaster", "webmestre", "administrateur web"), "Webmaster / admin web — profil pertinent."),
        # IA / Automatisation
        (("n8n", "automatisation", "workflow"), "Automatisation IA (n8n) — pratique active."),
        (("ia", "intelligence artificielle", "llm", "agent"),
         "IA / agents — competences en automatisation et orchestration."),
        # Formation / Pédagogie
        (("formateur", "formation", "pedagogie", "enseignant"),
         "Formation et pedagogie — 1,5 an d'experience (Le Pole S)."),
        (("insertion", "public eloigne", "reconversion"),
         "Public insertion — experience directe et engagee."),
        (("titre professionnel", "rncp", "certification"),
         "Contexte formation pro — familiarite avec les certifications."),
        # Secteurs / Valeurs
        (("ess", "economie sociale", "association", "fondation", "ong"),
         "Secteur ESS/impact — coherence avec le parcours."),
        (("service public", "collectivite", "mairie", "ministere"),
         "Service public — environnement familier."),
        (("culture", "edition", "jeunesse", "education"),
         "Secteur culture/education — experience directe (La Magicieuse, DevDoc)."),
        # Conditions
        (("teletravail", "remote", "distanciel", "full remote"),
         "Teletravail — modalite recherchee et appreciee."),
        (("cdi", "permanent"), "CDI — contrat prioritaire."),
        (("paris", "ile-de-france", "idf", "77", "78", "91", "92", "93", "94", "95"),
         "Localisation Paris/IDF — compatible."),
    ]
    for keywords, point in keyword_points:
        if any(keyword in text for keyword in keywords) and point not in points:
            points.append(point)
    return points[:5]


def _detect_risks(job: Dict[str, Any], text: str) -> List[str]:
    risks = list(_analysis_list(job, "points_faibles")) + list(_analysis_list(job, "red_flags"))
    risk_rules = [
        (("bac+5", "bac +5", "master 2", "ingenieur diplome"),
         "Diplome Bac+5 exige — incompatible (VAE CDA niveau 6 en cours)."),
        (("java", "j2ee", ".net", "c#", "cobol", "ruby", "python"),
         "Stack principale hors scope (pas PHP/JS)."),
        (("senior", "expert", "10 ans", "dix ans", "15 ans"),
         "Poste trop senior — experience demandee elevee."),
        (("commercial", "prospection", "business developer", "vente"),
         "Dominante commerciale — hors profil."),
        (("alternance", "stage", "apprentissage"),
         "Contrat etudiant — non prioritaire."),
        (("devops", "kubernetes", "terraform", "aws", "cloud", "sre"),
         "DevOps/Cloud lourd — competences partielles."),
        (("data science", "machine learning", "deep learning", "nlp"),
         "Data science — hors scope."),
        (("sap", "salesforce", "peoplesoft"),
         "ERP proprietaire — hors scope."),
        (("astreinte", "on-call", "24/7"),
         "Astreintes — contrainte forte."),
        (("deplacement", "permis b", "vehicule"),
         "Deplacements frequents — contrainte logistique."),
    ]
    for keywords, risk in risk_rules:
        if any(keyword in text for keyword in keywords) and risk not in risks:
            risks.append(risk)
    return risks[:5]


def _action(job: Dict[str, Any], risks: List[str]) -> str:
    analysis = job.get("ai_analysis", {})
    if isinstance(analysis, dict) and analysis.get("recommandation"):
        return str(analysis["recommandation"])

    score = int(job.get("score") or 0)
    if score >= 75 and len(risks) <= 1:
        return "POSTULER"
    if score >= 50:
        return "PEUT-ÊTRE"
    return "PASSER"


def summarize_job(job: Dict[str, Any]) -> JobSummary:
    text = _text(job)
    risks = _detect_risks(job, text)
    return JobSummary(
        position=str(job.get("title") or "Non renseigne"),
        company=str(job.get("company") or "Non renseignee"),
        location=str(job.get("location") or "Non renseigne"),
        why_interesting=_detect_interesting_points(job, text),
        risks=risks,
        action=_action(job, risks),
    )
