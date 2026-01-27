"""
France Travail (ex Pôle Emploi) scraper using official API.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

from .base_scraper import BaseScraper


class FranceTravailScraper(BaseScraper):
    TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
    SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

    def __init__(self) -> None:
        self.client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
        self.client_secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")
        self.max_jobs = int(os.getenv("MAX_JOBS_PER_SITE", "50"))
        self.timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
        self._token: Optional[str] = None

    def _get_token(self) -> str:
        if self._token:
            return self._token

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "api_offresdemploiv2 o2dsoffre",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        resp = requests.post(
            f"{self.TOKEN_URL}?realm=/partenaire",
            data=data,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        self._token = resp.json().get("access_token")
        return self._token

    def _search(self, keyword: str, start: int = 0) -> Dict:
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        params = {
            "motsCles": keyword,
            "region": "11",  # Île-de-France
            "range": f"{start}-{start + 49}",
        }
        resp = requests.get(
            self.SEARCH_URL,
            params=params,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()

    def _parse_job(self, raw: Dict) -> Dict:
        # Extraire la localisation
        lieu = raw.get("lieuTravail", {})
        location = lieu.get("libelle", "") if isinstance(lieu, dict) else str(lieu)

        # Extraire le salaire
        salaire = raw.get("salaire", {})
        if isinstance(salaire, dict):
            libelle = salaire.get("libelle", "")
            complement = salaire.get("complement1", "")
            salary = f"{libelle} {complement}".strip() or None
        else:
            salary = None

        # Extraire le type de contrat
        contrat = raw.get("typeContratLibelle", "") or raw.get("typeContrat", "")

        return {
            "title": raw.get("intitule", ""),
            "company": raw.get("entreprise", {}).get("nom", "") if isinstance(raw.get("entreprise"), dict) else "",
            "location": location,
            "contract_type": contrat,
            "salary": salary,
            "description": raw.get("description", ""),
            "url": raw.get("origineOffre", {}).get("urlOrigine", "") or f"https://candidat.francetravail.fr/offres/recherche/detail/{raw.get('id', '')}",
            "source": "france_travail",
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

    def scrape(self, keywords: List[str]) -> List[Dict]:
        if not self.client_id or not self.client_secret:
            raise ValueError("Missing FRANCE_TRAVAIL_CLIENT_ID or FRANCE_TRAVAIL_CLIENT_SECRET")

        jobs: List[Dict] = []
        seen_ids = set()

        # Utiliser quelques mots-clés principaux
        search_keywords = ["formateur web", "formateur développement", "chef de projet digital", "développeur web ESS"]

        for keyword in search_keywords:
            try:
                data = self._search(keyword)
                results = data.get("resultats", [])

                for raw in results:
                    job_id = raw.get("id")
                    if job_id and job_id not in seen_ids:
                        seen_ids.add(job_id)
                        job = self._parse_job(raw)
                        if job["title"]:
                            jobs.append(job)

                    if len(jobs) >= self.max_jobs:
                        return jobs
            except Exception as e:
                print(f"  Erreur recherche '{keyword}': {e}")
                continue

        return jobs
