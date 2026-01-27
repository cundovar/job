"""
Google Sheets integration via service account.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

import gspread
from google.oauth2.service_account import Credentials


class GoogleSheetsStorage:
    def __init__(self, sheet_id: str | None = None) -> None:
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
        self._client = None
        self._sheet = None

    def _get_client(self):
        if self._client:
            return self._client
        creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
        if not creds_json:
            raise ValueError("Missing GOOGLE_SHEETS_CREDENTIALS_JSON")
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=scopes
        )
        self._client = gspread.authorize(creds)
        return self._client

    def _get_sheet(self):
        if self._sheet:
            return self._sheet
        if not self.sheet_id:
            raise ValueError("Missing GOOGLE_SHEET_ID")
        client = self._get_client()
        self._sheet = client.open_by_key(self.sheet_id)
        return self._sheet

    def create_or_update_tabs(self, tabs: List[Dict]) -> None:
        sheet = self._get_sheet()
        existing_titles = [ws.title for ws in sheet.worksheets()]
        for tab in tabs:
            name = tab.get("name")
            if not name:
                continue
            if name not in existing_titles:
                sheet.add_worksheet(title=name, rows=1000, cols=30)

        ws = sheet.worksheet("Nouvelles Offres")
        if ws.get_all_values():
            return
        headers = [
            "Date découverte",
            "Score",
            "Recommandation",
            "Titre",
            "Entreprise",
            "Secteur",
            "Localisation",
            "Type contrat",
            "Salaire",
            "Pertinence IA",
            "Points forts",
            "Points faibles",
            "Red flags",
            "Angle motivation",
            "Lien offre",
            "Statut",
        ]
        ws.append_row(headers, value_input_option="RAW")

    def add_jobs(self, jobs: List[Dict]) -> None:
        sheet = self._get_sheet()
        ws = sheet.worksheet("Nouvelles Offres")
        rows = []
        for job in jobs:
            ai = job.get("ai_analysis", {}) or {}
            rows.append(
                [
                    job.get("scraped_at"),
                    job.get("score"),
                    ai.get("recommandation"),
                    job.get("title"),
                    job.get("company"),
                    job.get("sector"),
                    job.get("location"),
                    job.get("contract_type"),
                    job.get("salary"),
                    ai.get("pertinence_score"),
                    ", ".join(ai.get("points_forts", [])) if isinstance(ai.get("points_forts"), list) else "",
                    ", ".join(ai.get("points_faibles", [])) if isinstance(ai.get("points_faibles"), list) else "",
                    ", ".join(ai.get("red_flags", [])) if isinstance(ai.get("red_flags"), list) else "",
                    ai.get("angle_motivation"),
                    job.get("url"),
                    "NOUVEAU",
                ]
            )
        if rows:
            ws.append_rows(rows, value_input_option="RAW")
