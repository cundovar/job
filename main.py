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
    ai_analyzer = AIAnalyzer()
    for job in filtered:
        if job.get("score", 0) >= threshold:
            try:
                job["ai_analysis"] = ai_analyzer.analyze_job(job, criteria.get("user_profile", {}))
            except Exception as exc:
                logger.error(f"AI analysis failed: {exc}")

    JSONStorage(cache_days=int(os.getenv("CACHE_DURATION_DAYS", "30"))).save(filtered)

    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if not dry_run:
        try:
            sheets = GoogleSheetsStorage()
            sheets.create_or_update_tabs(criteria.get("google_sheets", {}).get("tabs", []))
            sheets.add_jobs(filtered)
        except Exception as exc:
            logger.error(f"Google Sheets failed: {exc}")

        try:
            email = EmailSender()
            max_email_jobs = int(
                criteria.get("email", {}).get("content", {}).get("max_jobs_in_email", 5)
            )
            top_jobs = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)[:max_email_jobs]
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
                "sheet_url": sheet_url,
            }
            email.send_daily_report(top_jobs, stats)
        except Exception as exc:
            logger.error(f"Email failed: {exc}")

    logger.info(f"Done! Processed {len(filtered)} jobs")


if __name__ == "__main__":
    main()
