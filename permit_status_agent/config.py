"""
Named constants for talking to the Leander, TX EnerGov Citizen Self Service
portal. Values here (base URL, tenant headers) were reverse-engineered by
driving the site's own UI in a real browser and capturing the requests it
issues — see spike/probe_search.py and PROJECT.md for how they were found.
"""
from typing import Final

BASE_URL: Final[str] = "https://leandertx-energovpub.tylerhost.net"
SEARCH_PAGE_URL: Final[str] = f"{BASE_URL}/apps/selfservice#/search"
SEARCH_ENDPOINT: Final[str] = "/apps/selfservice/api/energov/search/search"
INSPECTIONS_ENDPOINT: Final[str] = "/apps/selfservice/api/energov/entity/inspections/search/search"

# Single-inspection detail lookup. Unlike INSPECTIONS_ENDPOINT above (which
# requires an authenticated "contact" on the permit), this one is public —
# confirmed with a bare fetch() and only the standard tenant headers,
# 2026-08-14. Its response includes an exact link (LinkId) back to the
# parent permit's CaseId, which get_inspection_history uses to verify
# candidate inspections found via address search actually belong to the
# permit being looked up.
INSPECTION_DETAIL_ENDPOINT_TEMPLATE: Final[str] = "/apps/selfservice/api/energov/inspections/getById/{inspection_id}"

# Tyler's Angular app injects these via an HTTP interceptor. A raw fetch()
# from page.evaluate() has to set them explicitly or the endpoint 500s.
TENANT_HEADERS: Final[dict[str, str]] = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "tenantid": "1",
    "tenantname": "LeanderTXProd",
    "tyler-tenanturl": "LeanderTXProd",
    "tyler-tenant-culture": "en-US",
}

# Sequential port convention across this portfolio: 5001-5004 used by
# projects 1-4.
PORT: Final[int] = 5005

DEFAULT_HEADLESS: Final[bool] = True
DEFAULT_PAGE_SIZE: Final[int] = 10

# PageSize used by _lookup_electrical_permit, split by identifier shape.
# Permit-number lookups stay narrow (fast, already reliable — a permit
# number doesn't have a crowding problem). Address lookups use a much
# larger page: confirmed empirically (2026-08-14) that a bare street name
# alone (e.g. "DEERCREEK LN", no house number) can rank real electrical
# permits well past position 25 among other record types at the same
# street — search/search itself has no PageSize cap observed up to at
# least 500 (tested), so this isn't the API rejecting a large page, it's
# this client asking for too little. See PROJECT.md for the confirmed
# before/after.
LOOKUP_PAGE_SIZE_PERMIT_NUMBER: Final[int] = 25
LOOKUP_PAGE_SIZE_ADDRESS: Final[int] = 200

# SearchModule values from the site's own <select id="SearchModule">.
# NOTE: only SearchModule=1 ("All") has been proven to work reliably against
# the search endpoint. SearchModule=2 ("Permit") 500s with the payload shape
# this client sends (see PROJECT.md / tools.py for the empirical finding) —
# so we search broadly with SearchModule=1 and filter to permits locally
# via ModuleName / CaseType instead of asking the API to narrow it for us.
SEARCH_MODULE_ALL: Final[int] = 1
SEARCH_MODULE_PERMIT: Final[int] = 2
SEARCH_MODULE_PLAN: Final[int] = 3
SEARCH_MODULE_INSPECTION: Final[int] = 4
SEARCH_MODULE_PROJECT: Final[int] = 11

# ModuleName value stamped on each EntityResults record when it's a permit
# (observed empirically in live search responses, 2026-08-14).
MODULE_NAME_PERMIT: Final[int] = 2

# Same idea for inspection-module records (e.g. CaseType "Electrical Final
# Inspection"). Happens to equal SEARCH_MODULE_INSPECTION's value (4), but
# it's a coincidence, not a shared enum — keep them named separately, same
# reasoning as MODULE_NAME_PERMIT vs SEARCH_MODULE_PERMIT above.
MODULE_NAME_INSPECTION: Final[int] = 4

# entity/inspections/search/search uses a COMPLETELY DIFFERENT module enum
# than search/search's SearchModule above — same numbers, different meaning
# (e.g. Permit=1 here vs Permit=2 for SearchModule). Found by reading the
# Angular app's own bundle (app.Common.SelfServiceModules /
# ModuleHelper.getSelfServiceModuleId), not guessed — see PROJECT.md.
SELF_SERVICE_MODULE_PERMIT: Final[int] = 1
