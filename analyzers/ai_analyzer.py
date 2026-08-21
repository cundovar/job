"""
AI analysis with DeepSeek — strict scoring, PASSER filter, contextualized for Cundo.
The system prompt is loaded from config/agent_juge_offres.md (single source of truth).
The candidate profile is injected at call time from criteria.yaml.
Fallback: DeepSeek → Claude (Anthropic) si DeepSeek échoue.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict

import yaml
from openai import OpenAI


def _load_system_prompt() -> str:
    """Load the judge system prompt from the project config file."""
    prompt_path = Path(__file__).resolve().parent.parent / "config" / "agent_juge_offres.md"
    return prompt_path.read_text(encoding="utf-8")


def _parse_json_response(content: str) -> Dict:
    """Parse JSON from LLM response, handling markdown wrappers and edge cases."""
    content = (content or "{}").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*\n", "", content)
        content = re.sub(r"\n```\s*$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"recommandation": "PEUT-ÊTRE", "raison_breve": "Erreur parsing analyse"}


class AIAnalyzer:
    def __init__(self) -> None:
        # DeepSeek client
        self._deepseek = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
            timeout=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "30")),
        )
        self._deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self._temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.3"))
        self._max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", "4000"))
        self._system_prompt = _load_system_prompt()

        # Claude fallback (lazy init)
        self._claude = None

    def _get_claude(self):
        """Lazy-init Anthropic client (only if DeepSeek fails)."""
        if self._claude is None:
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY manquante pour le fallback")
            self._claude = anthropic.Anthropic(api_key=api_key)
        return self._claude

    def _call_deepseek(self, user_message: str) -> Dict:
        """Call DeepSeek API."""
        response = self._deepseek.chat.completions.create(
            model=self._deepseek_model,
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return _parse_json_response(response.choices[0].message.content or "{}")

    def _call_claude(self, user_message: str) -> Dict:
        """Fallback: call Claude via Anthropic API."""
        claude = self._get_claude()
        response = claude.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=self._max_tokens,
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
        return _parse_json_response(content)

    def analyze_job(self, job: Dict, criteria: Dict) -> Dict:
        """Analyze a job offer against the full criteria (user_profile injected in prompt).

        Chain: DeepSeek → Claude (fallback automatique).

        Args:
            job: Scraped job dict (title, company, location, contract_type, salary, description, score).
            criteria: Full criteria.yaml as a dict (contains user_profile, scoring rules, etc.).

        Returns:
            Dict with pertinence_score, recommandation, raison_breve, points_forts, etc.
        """
        # ── Quick title-based PASSER (no API call) ──
        title_lower = (job.get("title") or "").lower()
        desc_available = len(job.get("description") or "") > 300

        immediate_pass = False
        pass_reason = ""
        for kw, reason in [
            ("senior", "Senior → XP incompatible"),
            ("lead", "Lead → management technique hors scope"),
            ("tech lead", "Tech Lead → hors scope"),
            ("java ", "Java seul → stack incompatible"),
            (".net ", ".NET → stack incompatible"),
            ("c#", "C# → stack incompatible"),
        ]:
            if kw in title_lower:
                immediate_pass = True
                pass_reason = reason
                break

        # Angular sans PHP/Symfony → PASSER
        if not immediate_pass and "angular" in title_lower and "symfony" not in title_lower and "php" not in title_lower:
            immediate_pass = True
            pass_reason = "Angular sans PHP/Symfony → gap"

        # Ville hors IDF sans remote → PASSER
        villes_hors_idf = [
            "toulouse", "bordeaux", "lyon", "marseille", "nantes", "rennes",
            "lille", "strasbourg", "montpellier", "grenoble", "toulon",
            "nancy", "aix", "chambry", "perpignan",
        ]
        if any(v in title_lower for v in villes_hors_idf):
            if "remote" not in title_lower and "télétravail" not in title_lower and "distanciel" not in title_lower:
                immediate_pass = True
                pass_reason = "Ville hors IDF sans remote"

        # Exception : salaire ≥ 45k ET full remote → analyser même si Senior
        if immediate_pass and not desc_available:
            immediate_pass = False
        elif immediate_pass:
            desc_lower = (job.get("description") or "").lower()
            salaire_haut = any(k in desc_lower for k in ["50k", "55k", "60k", "45k"])
            full_remote = any(k in desc_lower for k in ["full remote", "100% remote", "100% télétravail", "full télétravail"])
            if salaire_haut and full_remote:
                immediate_pass = False

        if immediate_pass:
            return {"recommandation": "PASSER", "raison_breve": pass_reason}

        # ── Build user message with profile from criteria.yaml ──
        user_profile = criteria.get("user_profile", {})
        user_message = (
            f"## PROFIL CANDIDAT (depuis criteria.yaml)\n"
            f"{yaml.dump(user_profile, allow_unicode=True, default_flow_style=False)}\n\n"
            f"## OFFRE À ANALYSER\n"
            f"Titre : {job.get('title', '')}\n"
            f"Entreprise : {job.get('company', '')}\n"
            f"Localisation : {job.get('location', '')}\n"
            f"Contrat : {job.get('contract_type', '')}\n"
            f"Salaire : {job.get('salary', 'Non précisé')}\n"
            f"Score règles (scraper) : {job.get('score', 0)}\n\n"
            f"Description :\n{job.get('description', '')[:2500]}\n\n"
            "Réponds UNIQUEMENT en JSON, pas de markdown autour."
        )

        # ── DeepSeek → Claude fallback ──
        try:
            return self._call_deepseek(user_message)
        except Exception as e:
            print(f"  ⚠️ DeepSeek échoué pour '{job.get('title', '')[:50]}' ({e}), fallback Claude...")
            try:
                return self._call_claude(user_message)
            except Exception as e2:
                print(f"  ❌ Claude aussi échoué ({e2})")
                return {"recommandation": "PEUT-ÊTRE", "raison_breve": "Erreur analyse (DeepSeek+Claude HS)"}
