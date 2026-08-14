"""
MCP tool implementations.

check_permit_status is the first real tool. It does a two-stage lookup:
broad keyword search against the live portal, then local filtering down to
a confident electrical-permit match.

Why filtering happens locally rather than via a PermitTypeId GUID in the
request: the public search page's own "Advanced" panel exposes no permit
-type picker at all (confirmed by inspecting the live DOM, 2026-08-14) — it
only has a sort-by dropdown. There is no PermitTypeId value to discover
through the UI, and passing SearchModule=2 ("Permit"-only) to narrow the
search server-side reliably 500s with this payload shape. So this tool
searches broadly (SearchModule=1 / "All", the combination already proven to
return 200s) and instead recognizes electrical permits by their CaseType
text, e.g. "Electrical (Stand Alone)" — observed directly in a live
response for a keyword="electrical" search.
"""
from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any

from pydantic import ValidationError

from permit_status_agent import config
from permit_status_agent.client import EnerGovClient, EnerGovSearchError
from permit_status_agent.models import (
    InspectionDetailResponse,
    SearchResponse,
    SearchResultRecord,
)

# Matches permit numbers like "2014-1020" (year-sequence) and
# "ELEC-26-00767" (type prefix-year-sequence) — both observed live.
_PERMIT_NUMBER_RE = re.compile(r"^(?:[A-Za-z]+-)?\d{2,4}-\d{2,6}$")

# Substring match against CaseType, case-insensitive. Loose on purpose for
# v1 — refine once we've seen more of the CaseType vocabulary in practice.
_ELECTRICAL_CASE_TYPE_MARKER = "electrical"

_ADDRESS_FUZZY_MATCH_THRESHOLD = 0.6


def _looks_like_permit_number(identifier: str) -> bool:
    return bool(_PERMIT_NUMBER_RE.match(identifier.strip()))


def _is_electrical_permit(record: SearchResultRecord) -> bool:
    return (
        record.ModuleName == config.MODULE_NAME_PERMIT
        and _ELECTRICAL_CASE_TYPE_MARKER in record.CaseType.lower()
    )


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _address_matches(identifier: str, record: SearchResultRecord) -> bool:
    needle = _normalize(identifier)
    haystack = _normalize(record.AddressDisplay)
    if needle in haystack or haystack in needle:
        return True
    return SequenceMatcher(None, needle, haystack).ratio() >= _ADDRESS_FUZZY_MATCH_THRESHOLD


def _record_matches_identifier(identifier: str, record: SearchResultRecord) -> bool:
    if _looks_like_permit_number(identifier):
        return record.CaseNumber.strip().lower() == identifier.strip().lower()
    return _address_matches(identifier, record)


def _record_to_status_dict(record: SearchResultRecord) -> dict[str, Any]:
    return {
        "permit_number": record.CaseNumber,
        "case_type": record.CaseType,
        "work_class": record.CaseWorkclass,
        "status": record.CaseStatus,
        "description": record.Description,
        "address": record.AddressDisplay,
        "apply_date": record.ApplyDate.isoformat() if record.ApplyDate else None,
        "issue_date": record.IssueDate.isoformat() if record.IssueDate else None,
        "expire_date": record.ExpireDate.isoformat() if record.ExpireDate else None,
        "final_date": record.FinalDate.isoformat() if record.FinalDate else None,
    }


def _record_to_candidate_dict(record: SearchResultRecord) -> dict[str, Any]:
    return {
        "permit_number": record.CaseNumber,
        "case_type": record.CaseType,
        "status": record.CaseStatus,
        "address": record.AddressDisplay,
    }


async def _lookup_electrical_permit(identifier: str, *, headless: bool) -> dict[str, Any]:
    """Shared two-stage lookup used by both check_permit_status and
    get_inspection_history: broad keyword search -> filter to confident
    electrical-permit match(es).

    Returns one of:
      {"outcome": "found", "record": SearchResultRecord}
      {"outcome": "not_found", "identifier": ...}
      {"outcome": "ambiguous", "identifier": ..., "candidates": [...]}
      {"outcome": "error", "identifier": ..., "message": ...}
    """
    identifier = identifier.strip()
    is_permit_number = _looks_like_permit_number(identifier)

    # ExactMatch=True consistently outperforms False for both permit numbers
    # and addresses: it boosts phrase relevance on the search endpoint's
    # side rather than requiring a literal exact string match (empirically,
    # a False search for a common address like "1303 LEANDER DR" got
    # swamped by unrelated records containing "LEANDER" and never surfaced
    # the real match in 65k results; True found it immediately). Confirmed
    # live, 2026-08-14.
    #
    # PageSize differs by identifier shape: a permit number is narrow by
    # nature (small PageSize is fine), but an address — especially a bare
    # street name with no house number — can have real electrical permits
    # ranked well past position 25 among other record types at the same
    # street (confirmed live, 2026-08-14: see PROJECT.md). The API itself
    # doesn't cap PageSize (tested up to 500), so a much larger page for
    # address lookups is a real fix, not a workaround.
    page_size = (
        config.LOOKUP_PAGE_SIZE_PERMIT_NUMBER
        if is_permit_number
        else config.LOOKUP_PAGE_SIZE_ADDRESS
    )
    criteria = {
        "Keyword": identifier,
        "ExactMatch": True,
        "PageSize": page_size,
    }

    async with EnerGovClient(headless=headless) as client:
        try:
            raw = await client.search(criteria)
        except EnerGovSearchError as exc:
            return {"outcome": "error", "identifier": identifier, "message": str(exc)}

    try:
        parsed = SearchResponse(**raw)
    except ValidationError as exc:
        return {
            "outcome": "error",
            "identifier": identifier,
            "message": f"Response failed schema validation (possible API drift): {exc}",
        }

    # TotalFound is the grand total matching this query across every module
    # (permits, plans, inspections, licenses, ...), not just electrical
    # permits. If it exceeds what we actually got back, the server had more
    # to give than this page held — meaning a real electrical-permit match
    # could exist beyond what we scanned. Worth surfacing explicitly rather
    # than presenting a plain not_found/ambiguous as if it were the full
    # picture.
    results_truncated = parsed.Result.TotalFound > len(parsed.Result.EntityResults)

    electrical_matches = [
        record for record in parsed.Result.EntityResults if _is_electrical_permit(record)
    ]
    confident_matches = [
        record for record in electrical_matches if _record_matches_identifier(identifier, record)
    ]

    if len(confident_matches) == 1:
        return {"outcome": "found", "record": confident_matches[0]}

    if len(confident_matches) == 0:
        result: dict[str, Any] = {"outcome": "not_found", "identifier": identifier}
        if results_truncated:
            result["no_match_but_results_truncated"] = True
        return result

    result = {
        "outcome": "ambiguous",
        "identifier": identifier,
        "message": "Multiple electrical permits matched; disambiguation needed.",
        "candidates": [_record_to_candidate_dict(r) for r in confident_matches],
    }
    if results_truncated:
        # Same underlying issue as no_match_but_results_truncated above,
        # applied to the ambiguous case: this candidate list itself may be
        # incomplete, not just the non-match. Confirmed empirically this
        # can happen (a bare street-name query returned 4 candidates while
        # 3 more real electrical permits on that street existed beyond the
        # old PageSize=25 cutoff) — see PROJECT.md.
        result["candidates_possibly_truncated"] = True
    return result


async def check_permit_status(identifier: str, *, headless: bool = config.DEFAULT_HEADLESS) -> dict[str, Any]:
    """Look up an electrical permit by permit number or address.

    Returns one of:
      {"outcome": "found", ...permit fields...}
      {"outcome": "not_found", "identifier": ...}
      {"outcome": "ambiguous", "identifier": ..., "candidates": [...]}
      {"outcome": "error", "identifier": ..., "message": ...}
    """
    result = await _lookup_electrical_permit(identifier, headless=headless)
    if result["outcome"] == "found":
        return {"outcome": "found", **_record_to_status_dict(result["record"])}
    return result


_INSPECTION_DATA_SOURCE = "inferred_from_public_search"
_INSPECTION_CAVEAT = (
    "This is NOT the authoritative per-permit inspection list (that endpoint "
    "requires being a logged-in contact on the record and v1 excludes login — "
    "see PROJECT.md). Instead, each inspection below was found via a public "
    "address search and individually verified to belong to this exact permit "
    "(its LinkId matched this permit's CaseId). Verification per item is "
    "exact, but the candidate search itself may not be exhaustive — an "
    "inspection could exist that this search didn't surface."
)


def _inspection_date(detail) -> datetime | None:
    return detail.ActualDate or detail.ScheduledDate or detail.RequestDate


def _inspection_sort_key(detail) -> datetime:
    return _inspection_date(detail) or datetime.min


async def get_inspection_history(
    permit_number: str, *, headless: bool = config.DEFAULT_HEADLESS
) -> dict[str, Any]:
    """Look up an electrical permit's inspection history.

    Reuses _lookup_electrical_permit for the same permit-matching logic and
    not_found/ambiguous/error shapes as check_permit_status.

    The dedicated per-permit inspection list endpoint
    (entity/inspections/search/search) requires being an authenticated
    "contact" on the record — confirmed against two independent real
    permits, 2026-08-14 — and v1 excludes login, so that endpoint is out.
    Instead: search publicly for Inspection-module records near the
    permit's address, then confirm each candidate via
    inspections/getById/{id} (public, no login) and keep only the ones
    whose LinkId is an exact match for this permit's CaseId. Every returned
    inspection is individually confirmed to belong to this permit; what's
    best-effort is candidate discovery (the address search might not
    surface every inspection tied to the permit). The result always says
    so via data_source/caveat — see _INSPECTION_CAVEAT above.

    Returns one of:
      {"outcome": "found", "permit_number": ..., "inspections": [...],
       "no_inspections_yet": bool, "data_source": ..., "caveat": ...}
      {"outcome": "not_found", "identifier": ...}
      {"outcome": "ambiguous", "identifier": ..., "candidates": [...]}
      {"outcome": "error", ..., "message": ...}
    """
    lookup = await _lookup_electrical_permit(permit_number, headless=headless)
    if lookup["outcome"] != "found":
        return lookup

    record: SearchResultRecord = lookup["record"]

    async with EnerGovClient(headless=headless) as client:
        try:
            raw = await client.search(
                {"Keyword": record.AddressDisplay, "ExactMatch": True, "PageSize": 100}
            )
        except EnerGovSearchError as exc:
            return {"outcome": "error", "permit_number": record.CaseNumber, "message": str(exc)}

        try:
            parsed = SearchResponse(**raw)
        except ValidationError as exc:
            return {
                "outcome": "error",
                "permit_number": record.CaseNumber,
                "message": f"Candidate search failed schema validation (possible API drift): {exc}",
            }

        candidates = [
            r for r in parsed.Result.EntityResults if r.ModuleName == config.MODULE_NAME_INSPECTION
        ]

        confirmed: list[Any] = []
        for candidate in candidates:
            try:
                detail_raw = await client.get_inspection_detail(str(candidate.CaseId))
            except EnerGovSearchError:
                continue  # one bad candidate shouldn't sink the whole lookup

            try:
                detail_parsed = InspectionDetailResponse(**detail_raw)
            except ValidationError:
                continue

            if detail_parsed.Success and detail_parsed.Result.LinkId == record.CaseId:
                confirmed.append(detail_parsed.Result)

    if not confirmed:
        return {
            "outcome": "found",
            "permit_number": record.CaseNumber,
            "inspections": [],
            "no_inspections_yet": True,
            "data_source": _INSPECTION_DATA_SOURCE,
            "caveat": _INSPECTION_CAVEAT,
        }

    ordered = sorted(confirmed, key=_inspection_sort_key)
    return {
        "outcome": "found",
        "permit_number": record.CaseNumber,
        "inspections": [
            {
                "type": insp.TypeName,
                "date": _inspection_date(insp).isoformat() if _inspection_date(insp) else None,
                "result": insp.StatusName,
            }
            for insp in ordered
        ],
        "no_inspections_yet": False,
        "data_source": _INSPECTION_DATA_SOURCE,
        "caveat": _INSPECTION_CAVEAT,
    }


if __name__ == "__main__":
    import json

    args = sys.argv[1:]
    if len(args) == 1:
        mode, target = "status", args[0]
    elif len(args) == 2 and args[0] in ("status", "inspections"):
        mode, target = args
    else:
        print("Usage: python -m permit_status_agent.tools [status|inspections] <permit-number-or-address>")
        sys.exit(1)

    if mode == "status":
        result = asyncio.run(check_permit_status(target, headless=False))
    else:
        result = asyncio.run(get_inspection_history(target, headless=False))
    print(json.dumps(result, indent=2))
