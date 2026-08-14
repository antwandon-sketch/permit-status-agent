"""
Spike: prove we can fetch permit search results through a real browser
context (not a bare HTTP client) against Leander TX's EnerGov instance.

Note: the search endpoint returns 500 for a bare/minimal payload. The
request body and headers below were reverse-engineered by driving the
site's own search UI and capturing the exact request it issues (see
spike/inspect_ui2.py). Tyler's Angular app injects tenant headers via an
HTTP interceptor, so a raw fetch() has to set them explicitly.
"""
import json

from playwright.sync_api import sync_playwright

BASE_URL = "https://leandertx-energovpub.tylerhost.net/apps/selfservice#/search"
SEARCH_ENDPOINT = "/apps/selfservice/api/energov/search/search"

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "tenantid": "1",
    "tenantname": "LeanderTXProd",
    "tyler-tenanturl": "LeanderTXProd",
    "tyler-tenant-culture": "en-US",
}

EMPTY_CRITERIA_DEFAULTS = {
    "SearchMainAddress": False,
    "PageNumber": 0,
    "PageSize": 0,
    "SortBy": None,
    "SortAscending": False,
}

SEARCH_PAYLOAD = {
    "Keyword": "COTTON PATCH",
    "ExactMatch": True,
    "SearchModule": 1,
    "FilterModule": 1,
    "SearchMainAddress": False,
    "PlanCriteria": {
        "PlanNumber": None, "PlanTypeId": None, "PlanWorkclassId": None,
        "PlanStatusId": None, "ProjectName": None, "ApplyDateFrom": None,
        "ApplyDateTo": None, "ExpireDateFrom": None, "ExpireDateTo": None,
        "CompleteDateFrom": None, "CompleteDateTo": None, "Address": None,
        "Description": None, "ContactId": None, "ParcelNumber": None,
        "TypeId": None, "WorkClassIds": None, "ExcludeCases": None,
        "EnableDescriptionSearch": False, **EMPTY_CRITERIA_DEFAULTS,
    },
    "PermitCriteria": {
        "PermitNumber": None, "PermitTypeId": None, "PermitWorkclassId": None,
        "PermitStatusId": None, "ProjectName": None, "IssueDateFrom": None,
        "IssueDateTo": None, "Address": None, "Description": None,
        "ExpireDateFrom": None, "ExpireDateTo": None, "FinalDateFrom": None,
        "FinalDateTo": None, "ApplyDateFrom": None, "ApplyDateTo": None,
        "ContactId": None, "TypeId": None, "WorkClassIds": None,
        "ParcelNumber": None, "ExcludeCases": None,
        "EnableDescriptionSearch": False, **EMPTY_CRITERIA_DEFAULTS,
    },
    "InspectionCriteria": {
        "Keyword": None, "ExactMatch": False, "Complete": None,
        "InspectionNumber": None, "InspectionTypeId": None,
        "InspectionStatusId": None, "RequestDateFrom": None,
        "RequestDateTo": None, "ScheduleDateFrom": None, "ScheduleDateTo": None,
        "Address": None, "ContactId": None, "TypeId": [], "WorkClassIds": [],
        "ParcelNumber": None, "DisplayCodeInspections": False,
        "ExcludeCases": [], "ExcludeFilterModules": [],
        "HiddenInspectionTypeIDs": None, **EMPTY_CRITERIA_DEFAULTS,
    },
    "CodeCaseCriteria": {
        "CodeCaseNumber": None, "CodeCaseTypeId": None, "CodeCaseStatusId": None,
        "ProjectName": None, "OpenedDateFrom": None, "OpenedDateTo": None,
        "ClosedDateFrom": None, "ClosedDateTo": None, "Address": None,
        "ParcelNumber": None, "Description": None, "RequestId": None,
        "ExcludeCases": None, "ContactId": None,
        "EnableDescriptionSearch": False, "HiddenCodeCaseTypeIds": None,
        **EMPTY_CRITERIA_DEFAULTS,
    },
    "RequestCriteria": {
        "RequestNumber": None, "RequestTypeId": None, "RequestStatusId": None,
        "ProjectName": None, "EnteredDateFrom": None, "EnteredDateTo": None,
        "DeadlineDateFrom": None, "DeadlineDateTo": None,
        "CompleteDateFrom": None, "CompleteDateTo": None, "Address": None,
        "ParcelNumber": None, **EMPTY_CRITERIA_DEFAULTS,
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
        "ContactId": None, **EMPTY_CRITERIA_DEFAULTS,
    },
    "ProfessionalLicenseCriteria": {
        "LicenseNumber": None, "HolderFirstName": None, "HolderMiddleName": None,
        "HolderLastName": None, "HolderCompanyName": None, "LicenseTypeId": None,
        "LicenseClassId": None, "LicenseStatusId": None, "IssueDateFrom": None,
        "IssueDateTo": None, "ExpirationDateFrom": None, "ExpirationDateTo": None,
        "ApplicationDateFrom": None, "ApplicationDateTo": None, "Address": None,
        "MainParcel": None, "ExcludeCases": None, "TypeId": None,
        "WorkClassIds": None, "ContactId": None, **EMPTY_CRITERIA_DEFAULTS,
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
        "IsOperationalPermit": False, **EMPTY_CRITERIA_DEFAULTS,
    },
    "ProjectCriteria": {
        "ProjectNumber": None, "ProjectName": None, "Address": None,
        "ParcelNumber": None, "StartDateFrom": None, "StartDateTo": None,
        "ExpectedEndDateFrom": None, "ExpectedEndDateTo": None,
        "CompleteDateFrom": None, "CompleteDateTo": None, "Description": None,
        "ContactId": None, "TypeId": None, "ExcludeCases": None,
        "EnableDescriptionSearch": False, **EMPTY_CRITERIA_DEFAULTS,
    },
    "ExcludeCases": None,
    "HiddenInspectionTypeIDs": None,
    "PageNumber": 1,
    "PageSize": 10,
    "SortBy": None,
    "SortAscending": True,
}


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        result = page.evaluate(
            """async ({ endpoint, payload, headers }) => {
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
            }""",
            {"endpoint": SEARCH_ENDPOINT, "payload": SEARCH_PAYLOAD, "headers": HEADERS},
        )

        print(f"HTTP status: {result['status']}")
        print(json.dumps(result["body"], indent=2))

        browser.close()


if __name__ == "__main__":
    main()
