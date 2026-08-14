"""
Playwright-based client for the EnerGov search endpoint.

This is the proven pattern from spike/probe_search.py, generalized into a
reusable async client: launch a real Chromium context, load the search
page so the origin/session context is right, then drive fetch() from
*inside* that page via page.evaluate() rather than using a bare HTTP
client. See PROJECT.md for why that's required (TLS/JS fingerprinting) and
what headers/payload shape the endpoint actually needs.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from playwright.async_api import Browser, Page, async_playwright

from permit_status_agent import config

# The full multi-module criteria envelope the search endpoint requires.
# Only PermitCriteria is something callers of this client are expected to
# override in practice (v1 scope is permits), but every module's criteria
# block must be present and shaped correctly or the endpoint 500s.
_EMPTY_CRITERIA_DEFAULTS: dict[str, Any] = {
    "SearchMainAddress": False,
    "PageNumber": 0,
    "PageSize": 0,
    "SortBy": None,
    "SortAscending": False,
}

_DEFAULT_PAYLOAD: dict[str, Any] = {
    "Keyword": "",
    "ExactMatch": False,
    "SearchModule": config.SEARCH_MODULE_ALL,
    "FilterModule": 1,
    "SearchMainAddress": False,
    "PlanCriteria": {
        "PlanNumber": None, "PlanTypeId": None, "PlanWorkclassId": None,
        "PlanStatusId": None, "ProjectName": None, "ApplyDateFrom": None,
        "ApplyDateTo": None, "ExpireDateFrom": None, "ExpireDateTo": None,
        "CompleteDateFrom": None, "CompleteDateTo": None, "Address": None,
        "Description": None, "ContactId": None, "ParcelNumber": None,
        "TypeId": None, "WorkClassIds": None, "ExcludeCases": None,
        "EnableDescriptionSearch": False, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "PermitCriteria": {
        "PermitNumber": None, "PermitTypeId": None, "PermitWorkclassId": None,
        "PermitStatusId": None, "ProjectName": None, "IssueDateFrom": None,
        "IssueDateTo": None, "Address": None, "Description": None,
        "ExpireDateFrom": None, "ExpireDateTo": None, "FinalDateFrom": None,
        "FinalDateTo": None, "ApplyDateFrom": None, "ApplyDateTo": None,
        "ContactId": None, "TypeId": None, "WorkClassIds": None,
        "ParcelNumber": None, "ExcludeCases": None,
        "EnableDescriptionSearch": False, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "InspectionCriteria": {
        "Keyword": None, "ExactMatch": False, "Complete": None,
        "InspectionNumber": None, "InspectionTypeId": None,
        "InspectionStatusId": None, "RequestDateFrom": None,
        "RequestDateTo": None, "ScheduleDateFrom": None, "ScheduleDateTo": None,
        "Address": None, "ContactId": None, "TypeId": [], "WorkClassIds": [],
        "ParcelNumber": None, "DisplayCodeInspections": False,
        "ExcludeCases": [], "ExcludeFilterModules": [],
        "HiddenInspectionTypeIDs": None, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "CodeCaseCriteria": {
        "CodeCaseNumber": None, "CodeCaseTypeId": None, "CodeCaseStatusId": None,
        "ProjectName": None, "OpenedDateFrom": None, "OpenedDateTo": None,
        "ClosedDateFrom": None, "ClosedDateTo": None, "Address": None,
        "ParcelNumber": None, "Description": None, "RequestId": None,
        "ExcludeCases": None, "ContactId": None,
        "EnableDescriptionSearch": False, "HiddenCodeCaseTypeIds": None,
        **_EMPTY_CRITERIA_DEFAULTS,
    },
    "RequestCriteria": {
        "RequestNumber": None, "RequestTypeId": None, "RequestStatusId": None,
        "ProjectName": None, "EnteredDateFrom": None, "EnteredDateTo": None,
        "DeadlineDateFrom": None, "DeadlineDateTo": None,
        "CompleteDateFrom": None, "CompleteDateTo": None, "Address": None,
        "ParcelNumber": None, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "BusinessLicenseCriteria": {
        "LicenseNumber": None, "LicenseTypeId": None, "LicenseClassId": None,
        "LicenseStatusId": None, "BusinessStatusId": None, "LicenseYear": None,
        "ApplicationDateFrom": None, "ApplicationDateTo": None,
        "IssueDateFrom": None, "IssueDateTo": None, "ExpirationDateFrom": None,
        "ExpirationDateTo": None, "CompanyTypeId": None, "CompanyName": None,
        "BusinessTypeId": None, "Description": None,
        "CompanyOpenedDateFrom": None, "CompanyOpenedDateTo": None,
        "CompanyClosedDateFrom": None, "CompanyClosedDateTo": None,
        "LastAuditDateFrom": None, "LastAuditDateTo": None,
        "ParcelNumber": None, "Address": None, "TaxID": None, "DBA": None,
        "ExcludeCases": None, "TypeId": None, "WorkClassIds": None,
        "ContactId": None, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "ProfessionalLicenseCriteria": {
        "LicenseNumber": None, "HolderFirstName": None, "HolderMiddleName": None,
        "HolderLastName": None, "HolderCompanyName": None, "LicenseTypeId": None,
        "LicenseClassId": None, "LicenseStatusId": None, "IssueDateFrom": None,
        "IssueDateTo": None, "ExpirationDateFrom": None, "ExpirationDateTo": None,
        "ApplicationDateFrom": None, "ApplicationDateTo": None, "Address": None,
        "MainParcel": None, "ExcludeCases": None, "TypeId": None,
        "WorkClassIds": None, "ContactId": None, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "LicenseCriteria": {
        "LicenseNumber": None, "LicenseTypeId": None, "LicenseClassId": None,
        "LicenseStatusId": None, "BusinessStatusId": None,
        "ApplicationDateFrom": None, "ApplicationDateTo": None,
        "IssueDateFrom": None, "IssueDateTo": None, "ExpirationDateFrom": None,
        "ExpirationDateTo": None, "CompanyTypeId": None, "CompanyName": None,
        "BusinessTypeId": None, "Description": None,
        "CompanyOpenedDateFrom": None, "CompanyOpenedDateTo": None,
        "CompanyClosedDateFrom": None, "CompanyClosedDateTo": None,
        "LastAuditDateFrom": None, "LastAuditDateTo": None,
        "ParcelNumber": None, "Address": None, "TaxID": None, "DBA": None,
        "ExcludeCases": None, "TypeId": None, "WorkClassIds": None,
        "ContactId": None, "HolderFirstName": None, "HolderMiddleName": None,
        "HolderLastName": None, "MainParcel": None,
        "EnableDescriptionSearchForBLicense": False,
        "EnableDescriptionSearchForPLicense": False,
        "EnableDescriptionSearchForOperationalPermit": False,
        "IsOperationalPermit": False, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "ProjectCriteria": {
        "ProjectNumber": None, "ProjectName": None, "Address": None,
        "ParcelNumber": None, "StartDateFrom": None, "StartDateTo": None,
        "ExpectedEndDateFrom": None, "ExpectedEndDateTo": None,
        "CompleteDateFrom": None, "CompleteDateTo": None, "Description": None,
        "ContactId": None, "TypeId": None, "ExcludeCases": None,
        "EnableDescriptionSearch": False, **_EMPTY_CRITERIA_DEFAULTS,
    },
    "ExcludeCases": None,
    "HiddenInspectionTypeIDs": None,
    "PageNumber": 1,
    "PageSize": config.DEFAULT_PAGE_SIZE,
    "SortBy": None,
    "SortAscending": True,
}

_FETCH_JS = """async ({ endpoint, payload, headers }) => {
    const res = await fetch(endpoint, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
    });
    const text = await res.text();
    let body;
    try {
        body = JSON.parse(text);
    } catch (e) {
        body = text;
    }
    return { status: res.status, body };
}"""

_FETCH_GET_JS = """async ({ endpoint, headers }) => {
    const res = await fetch(endpoint, { method: "GET", headers });
    const text = await res.text();
    let body;
    try {
        body = JSON.parse(text);
    } catch (e) {
        body = text;
    }
    return { status: res.status, body };
}"""


def _merge_top_level(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge `overrides` onto `base`, merging one level deeper for
    any key whose value is itself a dict (e.g. PermitCriteria) so callers
    only need to specify the fields they actually care about."""
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


class EnerGovSearchError(RuntimeError):
    """Raised when the search endpoint returns a non-200 status."""


class EnerGovClient:
    """Async context manager wrapping a single Playwright browser + page.

    Usage:
        async with EnerGovClient() as client:
            raw = await client.search({"Keyword": "COTTON PATCH", "ExactMatch": True})
    """

    def __init__(self, headless: bool = config.DEFAULT_HEADLESS) -> None:
        self._headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    async def __aenter__(self) -> "EnerGovClient":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        await self._page.goto(config.SEARCH_PAGE_URL)
        await self._page.wait_for_load_state("networkidle")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def search(self, criteria: dict[str, Any]) -> dict[str, Any]:
        """Merge `criteria` onto the proven default envelope and POST it to
        search/search. Returns the raw parsed JSON response body.

        Raises EnerGovSearchError if the endpoint doesn't return HTTP 200.
        """
        if self._page is None:
            raise RuntimeError("EnerGovClient must be used as an async context manager")

        payload = _merge_top_level(_DEFAULT_PAYLOAD, criteria)
        result = await self._page.evaluate(
            _FETCH_JS,
            {
                "endpoint": config.SEARCH_ENDPOINT,
                "payload": payload,
                "headers": config.TENANT_HEADERS,
            },
        )

        if result["status"] != 200:
            raise EnerGovSearchError(
                f"search/search returned HTTP {result['status']}: {result['body']!r}"
            )
        return result["body"]

    async def get_inspections(self, case_id: str, *, page_size: int = 100) -> dict[str, Any]:
        """POST to entity/inspections/search/search for one permit's CaseId.

        The request shape here (ModuleId/EntityId/IsExistingInspection/...)
        was reverse-engineered from the Angular app's own bundle, not
        guessed — see PROJECT.md. Unlike search(), this does NOT raise when
        the endpoint denies access: it returns HTTP 200 even when the
        caller isn't authorized (Success=false, StatusCode=412 in the
        body). Callers must check the parsed response, not catch an
        exception, to distinguish "restricted" from "genuinely empty."
        """
        if self._page is None:
            raise RuntimeError("EnerGovClient must be used as an async context manager")

        payload = {
            "PageNumber": 1,
            "PageSize": page_size,
            "SortField": "",
            "IsSortedInAscendingOrder": True,
            "ModuleId": config.SELF_SERVICE_MODULE_PERMIT,
            "EntityId": case_id,
            "IsExistingInspection": True,
            "IsOptionalInspection": False,
            "IsFailed": False,
        }
        result = await self._page.evaluate(
            _FETCH_JS,
            {
                "endpoint": config.INSPECTIONS_ENDPOINT,
                "payload": payload,
                "headers": config.TENANT_HEADERS,
            },
        )

        if result["status"] != 200:
            raise EnerGovSearchError(
                f"entity/inspections/search/search returned HTTP {result['status']}: {result['body']!r}"
            )
        return result["body"]

    async def get_inspection_detail(self, inspection_id: str) -> dict[str, Any]:
        """GET inspections/getById/{inspection_id} — full detail for one
        inspection. Unlike get_inspections() above, this endpoint is
        public: confirmed with a bare fetch() and only the standard tenant
        headers, no login, 2026-08-14. Its response includes LinkId, an
        exact GUID link back to the parent permit's CaseId.
        """
        if self._page is None:
            raise RuntimeError("EnerGovClient must be used as an async context manager")

        endpoint = config.INSPECTION_DETAIL_ENDPOINT_TEMPLATE.format(inspection_id=inspection_id)
        result = await self._page.evaluate(
            _FETCH_GET_JS,
            {"endpoint": endpoint, "headers": config.TENANT_HEADERS},
        )

        if result["status"] != 200:
            raise EnerGovSearchError(
                f"inspections/getById returned HTTP {result['status']}: {result['body']!r}"
            )
        return result["body"]
