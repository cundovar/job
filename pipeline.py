"""
Reusable job search pipeline.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

load_dotenv()

import yaml

from analyzers import AIAnalyzer, calculate_score
from front_export import export_front_data
from filters import (
    filter_by_contract,
    filter_by_keywords,
    filter_by_location,
    filter_by_sector,
)
from notifications import EmailSender
from scrapers import (
    AdzunaScraper,
    APECScraper,
    EmploiAssoScraper,
    EmploiESSScraper,
    EmploiTerritorialRssScraper,
    FranceTravailScraper,
    IndeedScraper,
    JoobleScraper,
    LesJeudisScraper,
    RemoteOKScraper,
    WTTJScraper,
)
from storage import JSONStorage
from utils.logger import setup_logger


PipelineResult = Dict[str, Any]


def load_criteria(path: str = "config/criteria.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources(path: str = "config/sources.yaml") -> Dict[str, Any]:
    if not Path(path).exists():
        return {
            "enabled_sources": {
                "france_travail": True,
                "adzuna": True,
                "emploi_territorial": True,
                "jooble": False,
                "remoteok": False,
            }
        }
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_scrapers(sources: Dict[str, Any] | None = None) -> List[Any]:
    sources = sources or load_sources()
    enabled = sources.get("enabled_sources", {})
    scrapers: List[Any] = []

    if enabled.get("france_travail", True):
        scrapers.append(FranceTravailScraper())
    if enabled.get("adzuna", True):
        scrapers.append(AdzunaScraper())
    if enabled.get("emploi_territorial", True):
        scrapers.append(EmploiTerritorialRssScraper())
    if enabled.get("apec", True):
        scrapers.append(APECScraper())
    if enabled.get("indeed", True):
        scrapers.append(IndeedScraper())
    if enabled.get("wttj", True):
        scrapers.append(WTTJScraper())
    if enabled.get("emploi_asso", True):
        scrapers.append(EmploiAssoScraper())
    if enabled.get("emploi_ess", True):
        scrapers.append(EmploiESSScraper())
    if enabled.get("lesjeudis", True):
        scrapers.append(LesJeudisScraper())
    if enabled.get("jooble", False):
        jooble_cfg = sources.get("jooble", {})
        scrapers.append(
            JoobleScraper(
                country=jooble_cfg.get("country", "fr"),
                location=jooble_cfg.get("location", "Paris"),
                max_jobs=int(jooble_cfg.get("max_jobs", 50)),
            )
        )
    if enabled.get("remoteok", False):
        remoteok_cfg = sources.get("remoteok", {})
        scrapers.append(RemoteOKScraper(max_jobs=int(remoteok_cfg.get("max_jobs", 50))))

    return scrapers


def extract_search_keywords(criteria: Dict[str, Any]) -> List[str]:
    """Interleave keywords so every target position gets searched."""
    positions = criteria.get("target_positions", [])
    # Collect keywords grouped by position
    grouped: list[list[str]] = []
    for position in positions:
        kws = [kw for kw in position.get("keywords", [])[:3] if isinstance(kw, str) and kw.strip()]
        if kws:
            grouped.append(kws)

    # Interleave: take first keyword of each, then second, then third
    seen: set[str] = set()
    result: list[str] = []
    max_len = max((len(g) for g in grouped), default=0)
    for i in range(max_len):
        for group in grouped:
            if i < len(group):
                kw = group[i].lower()
                if kw not in seen:
                    seen.add(kw)
                    result.append(kw)
    return result


def build_stats(
    jobs: List[Dict[str, Any]],
    top_jobs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total": len(jobs),
        "postuler": sum(
            1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "POSTULER"
        ),
        "peut_etre": sum(
            1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PEUT-ÊTRE"
        ),
        "passer": sum(
            1 for job in jobs if job.get("ai_analysis", {}).get("recommandation") == "PASSER"
        ),
        "new_for_email": len(top_jobs),
    }

def extract_search_keywords_by_category(criteria: Dict[str, Any]) -> Dict[str, list[str]]:
    """Group keywords by position category for targeted scraping."""
    categories: Dict[str, list[str]] = {}
    for position in criteria.get("target_positions", []):
        name = position.get("name", "").lower()
        keywords = [kw for kw in position.get("keywords", [])[:5] if isinstance(kw, str) and kw.strip()]

        if not keywords:
            continue

        if "formateur" in name:
            categories.setdefault("formateur", []).extend(keywords)
        elif "webmaster" in name or "webmestre" in name or "administrateur web" in name:
            categories.setdefault("webmaster", []).extend(keywords)
        elif "support" in name and "web" in name:
            categories.setdefault("webmaster", []).extend(keywords)
        elif any(kw in name for kw in ["coordinateur", "coordonnateur"]):
            categories.setdefault("webmaster", []).extend(keywords)
        elif any(kw in name for kw in ["frontend", "front-end", "react", "vue", "intégrateur", "integrateur", "javascript", "typescript"]):
            categories.setdefault("frontend", []).extend(keywords)
        elif any(kw in name for kw in ["pédagogique", "elearning", "e-learning", "accessibilité", "rgaa",
                                        "product owner", "amoa", "low-code", "automatisation",
                                        "consultant", "transformation", "devrel", "technical writer",
                                        "médiation", "mediateur", "inclusion", "lms", "moodle",
                                        "humanitaire", "association", "ong", "fondation"]):
            categories.setdefault("nouvelles_portes", []).extend(keywords)
        else:
            categories.setdefault("backend", []).extend(keywords)

    for cat in categories:
        seen = set()
        unique = []
        for kw in categories[cat]:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                unique.append(kw)
        categories[cat] = unique

    return categories


def run_job_search(
    criteria_path: str = "config/criteria.yaml",
    send_outputs: bool | None = None,
) -> PipelineResult:
    criteria = load_criteria(criteria_path)
    sources = load_sources()
    logger = setup_logger("main")
    logger.info("Starting job search automation...")

    all_jobs: List[Dict[str, Any]] = []
    search_keywords = extract_search_keywords(criteria)
    for scraper in build_scrapers(sources):
        try:
            jobs = scraper.scrape(search_keywords)
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
    ai_candidates = sorted(
        [job for job in filtered if job.get("score", 0) >= threshold],
        key=lambda job: job.get("score", 0),
        reverse=True,
    )
    logger.info(f"AI analysis candidates: {len(ai_candidates)}; capped at {max_ai_jobs}")
    if ai_candidates and max_ai_jobs > 0:
        try:
            ai_analyzer = AIAnalyzer()
        except Exception as exc:
            ai_analyzer = None
            logger.error(f"AI analyzer unavailable: {exc}")

        if ai_analyzer:
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
    should_send_outputs = not dry_run if send_outputs is None else send_outputs
    max_email_jobs = int(criteria.get("email", {}).get("content", {}).get("max_jobs_in_email", 5))
    unsent_jobs = storage.get_unsent_jobs(filtered)
    top_jobs = sorted(unsent_jobs, key=lambda x: x.get("score", 0), reverse=True)[:max_email_jobs]
    stats = build_stats(filtered, top_jobs)

    if should_send_outputs:
        try:
            email = EmailSender()
            email.send_daily_report(top_jobs, stats)
            storage.mark_jobs_as_sent(top_jobs)
            logger.info(f"Email sent with {len(top_jobs)} new jobs")
        except Exception as exc:
            logger.error(f"Email failed: {exc}")

    try:
        export_front_data(filtered)
    except Exception as exc:
        logger.error(f"Front export failed: {exc}")

    logger.info(f"Done! Processed {len(filtered)} jobs")
    return {
        "jobs": filtered,
        "top_jobs": top_jobs,
        "stats": stats,
        "all_jobs_count": len(all_jobs),
    }
