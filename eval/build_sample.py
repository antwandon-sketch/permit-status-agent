"""
Builds a real, reproducible sample of electrical permits from the live
EnerGov portal for eval purposes. Every candidate is a real permit found
via the same search/search endpoint check_permit_status itself uses —
nothing here is invented, and the exact queries run are logged so the
sample is reproducible, not a black box.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from permit_status_agent.client import EnerGovClient, EnerGovSearchError
from permit_status_agent.models import SearchResponse

# One broad keyword net for "electrical" CaseType records regardless of
# address, plus several real Leander street names (all confirmed present
# in live data during prior sessions — see PROJECT.md) to diversify
# addresses/eras represented, since the broad query alone clusters by
# ElasticSearch relevance ranking rather than giving a spread.
SEED_QUERIES: list[dict[str, Any]] = [
    {"Keyword": "electrical", "ExactMatch": False, "PageSize": 100},
    {"Keyword": "COTTON PATCH", "ExactMatch": True, "PageSize": 50},
    {"Keyword": "LEANDER DR", "ExactMatch": True, "PageSize": 50},
    {"Keyword": "CRYSTAL FALLS", "ExactMatch": True, "PageSize": 50},
    {"Keyword": "BAGDAD RD", "ExactMatch": True, "PageSize": 50},
    {"Keyword": "HERO WAY", "ExactMatch": True, "PageSize": 50},
    {"Keyword": "183A TOLL", "ExactMatch": True, "PageSize": 50},
]

SAMPLE_SIZE = 30
RANDOM_SEED = 20260814  # fixed so the selected subset is reproducible


@dataclass
class SampleQueryLogEntry:
    keyword: str
    exact_match: bool
    page_size: int
    raw_entity_count: int = 0
    electrical_permit_count: int = 0
    error: str | None = None


@dataclass
class SampleResult:
    log: list[SampleQueryLogEntry] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    sample: list[dict[str, Any]] = field(default_factory=list)


async def build_sample(
    *, sample_size: int = SAMPLE_SIZE, seed: int = RANDOM_SEED, headless: bool = True
) -> SampleResult:
    log: list[SampleQueryLogEntry] = []
    seen: dict[str, dict[str, Any]] = {}  # CaseNumber -> record dict

    async with EnerGovClient(headless=headless) as client:
        for q in SEED_QUERIES:
            entry = SampleQueryLogEntry(
                keyword=q["Keyword"], exact_match=q["ExactMatch"], page_size=q["PageSize"]
            )
            try:
                raw = await client.search(q)
                parsed = SearchResponse(**raw)
            except (EnerGovSearchError, ValidationError) as exc:
                entry.error = f"{type(exc).__name__}: {exc}"
                log.append(entry)
                continue

            entities = parsed.Result.EntityResults
            electrical = [
                r for r in entities if r.ModuleName == 2 and "electrical" in r.CaseType.lower()
            ]
            for r in electrical:
                if r.CaseNumber not in seen:
                    seen[r.CaseNumber] = {
                        "case_number": r.CaseNumber,
                        "case_type": r.CaseType,
                        "case_status": r.CaseStatus,
                        "address": r.AddressDisplay,
                        "issue_date": r.IssueDate.isoformat() if r.IssueDate else None,
                        "found_via_query": q["Keyword"],
                    }

            entry.raw_entity_count = len(entities)
            entry.electrical_permit_count = len(electrical)
            log.append(entry)

    candidates = list(seen.values())
    rng = random.Random(seed)
    sample = rng.sample(candidates, k=min(sample_size, len(candidates)))

    return SampleResult(log=log, candidates=candidates, sample=sample)
