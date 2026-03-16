"""
Main entry point for job search automation.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import yaml

from analyzers import AIAnalyzer, calculate_score
from filters import (
    filter_by_contract,
    filter_by_keywords,
    filter_by_location,
    filter_by_sector,
)
from notifications import EmailSender
from scrapers import (
    APECScraper,
    EmploiAssoScraper,
    IndeedScraper,
    WTTJScraper,
    FranceTravailScraper,
    AdzunaScraper,
    EmploiTerritorialRssScraper,
)
from storage import GoogleSheetsStorage, JSONStorage
from utils.logger import setup_logger


def main() -> None:
    with open("config/criteria.yaml", "r", encoding="utf-8") as f:
        criteria = yaml.safe_load(f)

    logger = setup_logger("main")
    logger.info("Starting job search automation...")

    scrapers = [
        FranceTravailScraper(),  # API officielle - fonctionne
        AdzunaScraper(),  # API agrégateur
        EmploiTerritorialRssScraper(),  # Flux RSS
        # Les autres scrapers sont bloqués par les sites
        # IndeedScraper(),
        # EmploiAssoScraper(),
        # APECScraper(),
        # WTTJScraper(),
    ]

    all_jobs = []
    for scraper in scrapers:
        try:
            jobs = scraper.scrape(
                [kw for pos in criteria.get("target_positions", []) for kw in pos.get("keywords", [])]
            )
            all_jobs.extend(jobs)
            logger.info(f"{scraper.__class__.__name__}: {len(jobs)} jobs")
        except Exception as exc:
            logger.error(f"{scraper.__class__.__name__} failed: {exc}")

    filtered = filter_by_keywords(all_jobs, criteria)
    filtered = filter_by_location(filtered, criteria)
    filtered = filter_by_contract(filtered, criteria)
    filtered = filter_by_sector(filtered, criteria)

    for job in filtered:
        job["score"] = calculate_score(job, criteria)

    threshold = int(criteria.get("scoring", {}).get("thresholds", {}).get("basic_ai_analysis", 50))
    max_ai_jobs = int(os.getenv("MAX_AI_JOBS_PER_RUN", "12"))
    ai_analyzer = AIAnalyzer()
    ai_candidates = sorted(
        [job for job in filtered if job.get("score", 0) >= threshold],
        key=lambda job: job.get("score", 0),
        reverse=True,
    )
    logger.info(f"AI analysis candidates: {len(ai_candidates)}; capped at {max_ai_jobs}")
    for job in ai_candidates[:max_ai_jobs]:
        try:
            job["ai_analysis"] = ai_analyzer.analyze_job(job, criteria.get("user_profile", {}))
        except Exception as exc:
            logger.error(f"AI analysis failed: {exc}")

    for job in filtered:
        if "ai_analysis" not in job:
            try:
                recommendation = "PEUT-ÊTRE" if job.get("score", 0) >= threshold else "PASSER"
                job["ai_analysis"] = {
                    "pertinence_score": round(job.get("score", 0) / 10, 1),
                    "points_forts": [],
                    "points_faibles": [],
                    "red_flags": [],
                    "recommandation": recommendation,
                    "angle_motivation": "",
                    "raison_breve": "Analyse IA non disponible sur ce run.",
                }
            except Exception:
                job["ai_analysis"] = {"recommandation": "PEUT-ÊTRE"}

    storage = JSONStorage(cache_days=int(os.getenv("CACHE_DURATION_DAYS", "30")))
    storage.save(filtered)

    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if not dry_run:
        try:
            sheets = GoogleSheetsStorage()
            sheets.create_or_update_tabs(criteria.get("google_sheets", {}).get("tabs", []))
            sheets.add_jobs(filtered)
            logger.info("Google Sheets updated")
        except Exception as exc:
            logger.error(f"Google Sheets failed: {exc}")

        try:
            email = EmailSender()
            max_email_jobs = int(
                criteria.get("email", {}).get("content", {}).get("max_jobs_in_email", 5)
            )
            unsent_jobs = storage.get_unsent_jobs(filtered)
            top_jobs = sorted(unsent_jobs, key=lambda x: x.get("score", 0), reverse=True)[:max_email_jobs]
            sheet_id = os.getenv("GOOGLE_SHEET_ID")
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit" if sheet_id else "#"
            stats = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "total": len(filtered),
                "postuler": sum(
                    1 for j in filtered if j.get("ai_analysis", {}).get("recommandation") == "POSTULER"
                ),
                "peut_etre": sum(
                    1 for j in filtered if j.get("ai_analysis", {}).get("recommandation") == "PEUT-ÊTRE"
                ),
                "passer": sum(
                    1 for j in filtered if j.get("ai_analysis", {}).get("recommandation") == "PASSER"
                ),
                "new_for_email": len(top_jobs),
                "sheet_url": sheet_url,
            }
            email.send_daily_report(top_jobs, stats)
            storage.mark_jobs_as_sent(top_jobs)
            logger.info(f"Email sent with {len(top_jobs)} new jobs")
        except Exception as exc:
            logger.error(f"Email failed: {exc}")

    logger.info(f"Done! Processed {len(filtered)} jobs")


if __name__ == "__main__":
    main()
