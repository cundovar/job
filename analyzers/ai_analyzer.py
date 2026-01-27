"""
AI analysis with DeepSeek (OpenAI-compatible).
"""
from __future__ import annotations

import json
import os
from typing import Dict

from openai import OpenAI


class AIAnalyzer:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.3"))
        self.max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", "1000"))

    def analyze_job(self, job: Dict, user_profile: Dict) -> Dict:
        system_prompt = (
            "Tu es un conseiller en recherche d'emploi spécialisé dans le secteur du numérique et de l'ESS.\n"
            "Ton rôle est d'analyser des offres d'emploi et de déterminer si elles correspondent au profil suivant :\n\n"
            f"PROFIL CANDIDAT :\n"
            f"- {user_profile.get('name','')}\n"
            f"- Formateur développement web (1 an d'expérience)\n"
            f"- Stack : HTML/CSS/JS/PHP/Symfony/React/Vue.js\n"
            f"- Recherche CDI dans secteur ESS/Public/Impact\n"
            f"- Priorité : postes formateur ou chef de projet digital\n\n"
            "ANALYSE REQUISE :\n"
            "1. Pertinence globale (0-10)\n"
            "2. Points forts de la candidature pour ce poste\n"
            "3. Points faibles / écarts avec le profil\n"
            "4. Red flags détectés\n"
            "5. Recommandation : POSTULER / PEUT-ÊTRE / PASSER\n"
            "6. Angle d'attaque pour la lettre de motivation (si POSTULER)\n"
        )

        user_prompt = (
            "Analyse cette offre d'emploi :\n\n"
            f"TITRE : {job.get('title','')}\n"
            f"ENTREPRISE : {job.get('company','')}\n"
            f"SECTEUR : {job.get('sector','')}\n"
            f"LOCALISATION : {job.get('location','')}\n"
            f"TYPE CONTRAT : {job.get('contract_type','')}\n"
            f"SALAIRE : {job.get('salary','')}\n\n"
            "DESCRIPTION :\n"
            f"{job.get('description','')}\n\n"
            "Fournis ton analyse au format JSON :\n"
            "{\n"
            '  "pertinence_score": 0-10,\n'
            '  "points_forts": ["point1", "point2", ...],\n'
            '  "points_faibles": ["point1", "point2", ...],\n'
            '  "red_flags": ["flag1", "flag2", ...],\n'
            '  "recommandation": "POSTULER|PEUT-ÊTRE|PASSER",\n'
            '  "angle_motivation": "Explication de comment pitcher sa candidature",\n'
            '  "raison_breve": "Résumé en 1 phrase"\n'
            "}\n"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        content = response.choices[0].message.content or "{}"
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"error": "invalid_json", "raw": content}
