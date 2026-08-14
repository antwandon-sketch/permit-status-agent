# Permit Status Agent — PROJECT.md

Say "read PROJECT.md" at the start of a new thread for full context.

Last updated: 2026-08-14 (session 10: fixed the bare-street-name address
search gap with a real before/after; pushed to public GitHub)

## Who this is for
Anthony Letson, portfolio piece #5 of an AI Engineer / Forward Deployed Engineer
portfolio. No hard deadline. Communication preferences: concise, direct, no
re-litigating settled decisions, plain-language summaries required at every
Claude Code handoff.

## What this is
An MCP-native agent that checks electrical permit status on the City of
Leander, TX EnerGov Citizen Self Service portal (Tyler Technologies platform,
tenant: leandertx-energovpub.tylerhost.net). Read-only, v1 scope.

## Confirmed architecture (validated via live spike, 2026-08-13/14)
- Portal is Tyler EnerGov Citizen Self Service — an AngularJS SPA with a real
  internal JSON REST API underneath (not a documented/supported public API,
  but a real one). Public "Search Public Records" requires no login.
- Transport: Playwright-driven browser context calling the site's own
  fetch() via page.evaluate() — NOT a bare HTTP client. Proven necessary
  and sufficient in spike; a real browser context handles TLS/JS
  fingerprinting automatically and this exact path has already returned
  clean 200s with real data.
- Hard requirements discovered empirically, not optional:
  1. Four Tyler tenant headers required on every request: tenantid,
     tenantname, tyler-tenanturl, tyler-tenant-culture. Angular injects
     these via an interceptor; a raw fetch() must set them explicitly or
     the request 500s.
  2. Search endpoint (`/apps/selfservice/api/energov/search/search`)
     requires the full multi-module criteria payload shape (PermitCriteria,
     PlanCriteria, InspectionCriteria, etc.), not PermitCriteria alone.
  3. The search endpoint is a broad keyword search across all record types,
     NOT a precise PermitCriteria-only filter. It will return
     topically-adjacent noise. The app must filter/disambiguate results
     itself, not trust the first match.
- Key endpoints identified: search/search (broad search), permits/permitdetail
  (case detail), entity/inspections/search/search (inspection results,
  scoped by CaseId GUID), workflow/summary/activities (next-steps/workflow).
- No robots.txt on the portal host (404). No ToS/acceptable-use link found
  anywhere on the anonymous public-search path. Not a formal legal clearance
  — just: nothing found telling us to stop. Be a good citizen: honest
  User-Agent, conservative rate limits, no unnecessary load.

## Locked v1 scope
- Electrical permits only.
- Two MCP tools, outcome-first (not 1:1 API mapping):
  1. check_permit_status(identifier) — accepts permit number or address.
     Two-stage lookup: broad search -> filter to confident electrical-permit
     match -> pull detail. Ambiguous matches return candidates for
     disambiguation rather than guessing.
  2. get_inspection_history(permit_number) — separate tool, separate API
     call, separate failure mode from tool 1.
- Pydantic models as strict response contracts on every API call.
- Reliability design: retry w/ exponential backoff + circuit breaker for
  transient failures; fail-partial not fail-total on batch/record issues;
  statistical drift monitoring (null-rate per field across runs) as the
  primary defense against silent schema changes on this undocumented API —
  a thrown exception is not the only failure mode to watch for.
- Eval: success rate over N real runs against the live portal, categorized
  by failure mode (transient / contract-drift / ambiguous-match /
  genuinely-not-found).

## Explicit v1 exclusions
- No login, no account creation, no submission into the live system.
- No caching/persistence layer (v2 idea, not v1).
- No permit types beyond electrical.

## Repo mechanics
- Repo: ~/dev/permit-status-agent, git initialized, venv active,
  .env gitignored and confirmed via git check-ignore.
- PORT=5005 (sequential convention: 5001-5004 used by projects 1-4).
- Dependencies: playwright, pydantic, mcp.
- venv Python version: 3.12 (rebuilt from scratch 2026-08-14 — the
  original venv was Python 3.9.6, and the `mcp` package requires 3.10+ for
  every version going back to 1.0.0, so 3.9.6 genuinely could not install
  it at all. New venv built from `/opt/homebrew/bin/python3.12`; all deps
  reinstalled including a fresh `playwright install chromium`. If a
  future session finds Python 3.9 again here, someone rebuilt the venv
  wrong — 3.12 is required going forward.
- mcp SDK version: 2.0.0. This matters because v2 is a breaking rework of
  v1 — `mcp.server.fastmcp.FastMCP` does not exist in v2; the equivalent
  is `mcp.server.mcpserver.MCPServer` (server.py uses this). Client-side,
  v2 has a new high-level `mcp.client.Client` class alongside the v1-style
  `StdioServerParameters` / `stdio_client` (still present, used together —
  see test_mcp_client.py). Always run `pip show mcp` before assuming
  either API surface is what's installed.

## Spike status: COMPLETE
spike/probe_search.py proven end-to-end (2026-08-13/14) — real search
against live portal returned 200 with real permit data (585 total records
matched, 35 permits found on a test keyword). This validated the transport,
headers, and payload shape requirements above. Spike script stays as
reference; real app code lives in permit_status_agent/, not in spike/.

## Real package: built (2026-08-14)
- permit_status_agent/config.py — base URL, tenant headers, port, search
  module/type constants, all as named constants.
- permit_status_agent/client.py — EnerGovClient, an async context manager
  wrapping one Playwright browser/page. `search(criteria)` merges a partial
  criteria dict onto the proven full multi-module payload envelope and
  POSTs it, returning raw parsed JSON. Raises EnerGovSearchError on
  non-200.
- permit_status_agent/models.py — SearchResponse / SearchResultRecord /
  RecordAddress Pydantic models, extra="forbid" everywhere, typed from the
  actual live JSON (UUID fields, datetime fields, no Any passthrough). Note
  the nested address model is named RecordAddress, not Address — pydantic
  v2 silently mis-resolves `Address: Optional[Address]` (a field shadowing
  its own type's name), collapsing the type to NoneType. Confirmed by
  direct repro; renaming the class is the fix, not a config workaround.
- permit_status_agent/tools.py — check_permit_status(identifier), manually
  testable via `python -m permit_status_agent.tools "<identifier>"`.
- server.py — stub, raises NotImplementedError; MCP transport not wired up.

## New empirical findings from building check_permit_status
- No PermitTypeId is discoverable through the public UI: the "Advanced"
  search panel exposes only a sort-by dropdown, no type filter, for any
  module. So filtering to electrical permits happens client-side, on
  CaseType text (e.g. "Electrical (Stand Alone)"), not via a PermitTypeId
  GUID in the request.
- SearchModule=2 ("Permit"-only, server-side) reliably 500s with this
  client's payload shape. SearchModule=1 ("All") is what actually works;
  narrowing to permits happens locally via ModuleName==2 instead.
- ExactMatch=True is required for usable results on both permit-number and
  address lookups — it's a relevance boost on the search backend, not a
  literal-equality filter (it still matched "1303 Leander Drive" against a
  query for "1303 LEANDER DR"). ExactMatch=False on an address containing
  the city name ("...LEANDER DR") got swamped: 65,037 loosely-relevant
  results, real match nowhere in the first page. This was the actual bug in
  the first working version of check_permit_status, found and fixed this
  session.
- Permit number format isn't uniform: both "2014-1020" (year-sequence) and
  "ELEC-24-00375" (type prefix-year-sequence) are real, live formats.
- Address field can legitimately be null on non-permit record types
  returned by the same broad search (e.g. some license/project records) —
  modeled as Optional, not assumed always-present.

## Verified live (2026-08-14)
- check_permit_status("ELEC-24-00375") -> found, full status/dates.
- check_permit_status("1303 LEANDER DR") -> found, same permit via address.
- check_permit_status("2014-1020") -> not_found (real permit, but it's a
  residential-construction case, not electrical — correctly excluded by
  v1's electrical-only scope).
- check_permit_status("9999 NONEXISTENT ST") -> not_found (genuinely no
  match).
- Ambiguous-match branch (multiple confident candidates) is implemented but
  not yet exercised against a live example that actually produces it —
  worth a real test once we're doing more than manual spot-checks.
- get_inspection_history("ELEC-24-00375") -> found, 3 real inspections
  (Electrical Underground, Permanent Power-Electric Meter Release,
  Electrical Final), each individually LinkId-confirmed, chronological.
- get_inspection_history("2016-8666") -> found, 1 real inspection
  (Electrical Final Inspection, 2016), confirmed the same way.
- get_inspection_history("2022-41675") -> not_found, consistent with
  check_permit_status (correct — see CaseType correction above).

## get_inspection_history: built (2026-08-14), redesigned same day
First version called the dedicated per-permit inspection list endpoint
(entity/inspections/search/search) and got gated — see finding below.
Second version, now active, uses a different real endpoint instead:

- permit_status_agent/client.py:
  - EnerGovClient.get_inspections(case_id) — the ORIGINAL, gated,
    per-permit list endpoint. Kept as accurate reference (real, correctly
    implemented, just not usable anonymously), but get_inspection_history
    no longer calls it.
  - EnerGovClient.get_inspection_detail(inspection_id) — NEW. GET
    inspections/getById/{id}. Public, no login required — confirmed with a
    bare fetch() and only the standard tenant headers, 2026-08-14.
- permit_status_agent/models.py:
  - InspectionDetail / InspectionDetailResponse — NEW, fully confirmed
    against one real live response (extra="forbid" like the rest of the
    file; a few instance-state fields kept Optional on reasoned inference
    from n=1, documented in the docstring).
  - InspectionSearchResponse / InspectionRecord — kept as documentation of
    the gated endpoint finding, not part of the active code path anymore.
- permit_status_agent/tools.py — get_inspection_history(permit_number)
  redesigned: look up the permit (shared _lookup_electrical_permit helper,
  same as before) → public address search for Inspection-module (ModuleName
  ==4) candidates near that address → for each candidate, call
  get_inspection_detail and keep it only if its LinkId exactly matches the
  permit's CaseId (a GUID equality check, not a fuzzy match). Every
  returned inspection is individually confirmed to belong to the permit;
  what's best-effort is candidate discovery (the address search might not
  surface every inspection tied to the permit — no pagination beyond
  PageSize=100 yet). The result always says so explicitly via
  `data_source` and `caveat` fields in the return dict itself, not just a
  docstring, so a caller can't miss it.

## Key finding: two different inspection endpoints, two different access rules
The per-permit inspection LIST (entity/inspections/search/search) requires
being a logged-in contact on the record — confirmed against two unrelated
real permits (ELEC-24-00375, 2016-8666), both returned HTTP 200 with
Success=false/StatusCode=412/"You must be a contact on this record to see
this information". The Inspections tab on the permit detail page
(#/permit/{CaseId}) shows this same message and doesn't even call the API.
This is systematic and permanent for v1 (login is explicitly excluded), not
a bug or a fluke on one record.

But a single inspection's own DETAIL page (#/inspectionDetail/inspection/
{CaseId}, backed by inspections/getById/{id}) is fully public — no login
wall, confirmed with a bare unauthenticated fetch(). Its response includes
`LinkTypeName: "Permit"`, `LinkNumber`, and `LinkId` — an exact link back
to the parent permit (LinkId matched a known permit's CaseId GUID exactly
in testing). That's what get_inspection_history is built on now: discover
candidate inspections publicly (address search), confirm each one exactly
(getById + LinkId match), skip the endpoint that needs login entirely.

Also tried the public "Today's Inspections" page as another possible route
to real inspection data before finding getById — it unexpectedly redirects
through Tyler Identity login, so that avenue stayed closed. Not needed in
the end since getById worked directly.

## Correction to a prior assumption: 2022-41675 is not an electrical permit
The task instructions assumed permit "2022-41675" (444 Starlight Village
Loop) was an electrical permit in the older plain year-sequence numbering
format. Checked live: its CaseType is actually "BLD - Residential - Single
Family New Construction". The address does have several
"Electrical Final Inspection" / "Permanent Power-Electric Meter Release
Inspection" etc. records against it, but those are separate Inspection-
module entities, not the permit's own CaseType — this jurisdiction bundles
electrical work for new residential construction under one umbrella
building permit rather than issuing it as a standalone electrical permit,
unlike ELEC-24-00375's case. check_permit_status/get_inspection_history
both correctly return not_found for "2022-41675" given the v1
electrical-only scope — verified this is correct, not a bug. Substituted
"2016-8666" (genuinely CaseType "Electrical (Stand Alone)", plain
year-sequence format, no "ELEC-" prefix) to actually validate that the
CaseType-based match logic doesn't depend on permit-number-prefix
assumptions, which was the real intent behind the test.

## MCP server transport: built and verified (2026-08-14)
- server.py wires up check_permit_status and get_inspection_history from
  tools.py as `@mcp.tool()`-registered tools on an `MCPServer` instance
  (mcp==2.0.0's `mcp.server.mcpserver.MCPServer`), served over stdio via
  `mcp.run(transport="stdio")`. No business logic in server.py — it only
  imports and wraps the already-working tools.py functions, always
  calling them with headless=True (the real functions still take a
  `headless` kwarg for interactive debugging, but that's not exposed as
  part of either tool's MCP-facing parameter schema).
- Tool descriptions are the functions' docstrings (that's how the SDK
  derives them — confirmed by inspection, not assumed). Both are written
  to be self-sufficient for a model that only sees the description, not
  the implementation: what the tool does, what identifier formats it
  accepts, and — critical for get_inspection_history — an explicit
  "results may be incomplete but are never inaccurate" framing, so a
  model doesn't misreport an empty/short list as proof no inspections
  happened.
- Real end-to-end test: test_mcp_client.py (kept in the repo, not
  deleted — useful for future re-verification) launches server.py as an
  actual subprocess and talks real MCP protocol to it over stdio using
  mcp v2's `Client` class + `StdioServerParameters`/`stdio_client`. This
  is a genuine protocol-level test, not a Python function call — the
  client and server communicate only through stdio-framed JSON-RPC, the
  same way a real MCP host (e.g. Claude Desktop) would talk to it.
  Verified: `list_tools()` returns both tools with their descriptions;
  `call_tool("check_permit_status", {"identifier": "ELEC-24-00375"})` and
  `call_tool("get_inspection_history", {"permit_number": "2016-8666"})`
  both returned the same real, correct results already verified via
  direct function calls in earlier sessions.
- (Node.js/npx isn't installed on this machine, so the official
  `@modelcontextprotocol/inspector` CLI wasn't used — the Python SDK's own
  client was used instead, which exercises the identical protocol. If
  Node ever gets installed, the inspector would also work unmodified
  against `python server.py`.)

## How to actually run this server
- Manually, for debugging: `./venv/bin/python3 server.py` (blocks, waiting
  for stdio input — not useful standalone, needs a real MCP client on the
  other end).
- Via the throwaway test client: `./venv/bin/python3 test_mcp_client.py`
  (from the repo root — spawns server.py itself, no separate step needed).
- Via Claude Desktop: **TESTED AND WORKING (2026-08-14).** Config lives at
  `~/Library/Application Support/Claude/claude_desktop_config.json` on
  macOS — this file already existed with unrelated Claude Desktop
  preferences in it; the fix was adding a `"mcpServers"` key alongside
  them, not creating the file from scratch:
  ```json
  {
    "mcpServers": {
      "permit-status-agent": {
        "command": "/Users/antwandon/dev/permit-status-agent/venv/bin/python3",
        "args": ["/Users/antwandon/dev/permit-status-agent/server.py"]
      }
    }
  }
  ```
  Use the venv's python3 directly (not a bare `python3`/`python`), since
  that's the interpreter with playwright/pydantic/mcp actually installed.
  After adding this and fully restarting Claude Desktop (Cmd+Q, not just
  closing the window — MCP servers load at startup), the user confirmed
  via screenshot: permit-status-agent shows connected (green check,
  tagged "Local dev") in the app's connector list.

  **Troubleshooting, if this ever shows disconnected later:** the two
  likely failure points are environmental, not code:
  (a) the venv python path in claude_desktop_config.json no longer points
  to a real interpreter — happens if the venv gets rebuilt/moved/deleted
  and the config isn't updated to match (this project's venv has already
  been rebuilt once this way, see the Python 3.9→3.12 migration above);
  check the path in the config still resolves (`ls -la
  <path-in-config>`) and matches the *current* venv, not a stale one.
  (b) `mcp` is no longer installed in that venv, or got downgraded below
  a version this server.py's API calls are compatible with — check via
  `<venv>/bin/pip show mcp` and compare against "mcp SDK version" noted
  above (2.0.0 as of this writing). Also check
  `~/Library/Logs/Claude/mcp-server-permit-status-agent.log` (or similarly
  named) for the actual error text before guessing.

## Eval harness: built (2026-08-14)
Measures real reliability of both tools against the live portal — success
rate over N real runs, broken down by failure mode — instead of just "it
works on the two examples we already hand-verified."

- eval/build_sample.py — builds a REAL, reproducible sample of electrical
  permits: runs 7 seed queries against the live search endpoint (one
  broad `Keyword="electrical"` net, plus 6 real Leander street names for
  diversity), filters to ModuleName==2 + CaseType containing "electrical",
  dedupes by CaseNumber, then takes a fixed-seed random.sample() of 30 for
  reproducibility. Every query run and its result counts are logged, not
  just the final sample — see the "Sample construction" table in each
  results_*.md for the exact reproducible recipe.
- eval/classify.py — maps each tool response to exactly one of 7
  categories (success, genuinely_not_found, ambiguous_match,
  access_restricted, contract_drift, transient, unexpected_error), per
  PROJECT.md's reliability section. unexpected_error is deliberately a
  catch-all signal, not a bug bucket — if it's ever non-empty, the report
  lists each entry individually rather than just counting it.
- eval/run_eval.py — the runner. Tests both tools against: the sample (30
  random real permits), 2 fixed hand-verified regression cases
  (ELEC-24-00375, 2016-8666), and 3 negative cases (a nonsense
  well-formed-looking permit number, a nonsense address, and the known
  non-electrical permit 2022-41675 — all expected to come back
  not_found). Paces itself (2s between items, 0.5s between the two tool
  calls per item) to avoid hammering a small municipal system. Writes
  three files per run under eval/: `sample_<ts>.json` (full reproducible
  sample-construction log + candidate pool + selected sample),
  `raw_<ts>.jsonl` (one line per call, written incrementally so a crash
  mid-run doesn't lose completed results), and `results_<ts>.md` (the
  human-readable summary — overall/per-tool success rates, per-category
  breakdown, explicit pass/fail on the fixed regression and negative
  cases, every unexpected_error listed individually, and an honest
  "known sample limitations" section computed from that run's actual
  data, not boilerplate).
- Run via: `./venv/bin/python3 -m eval.run_eval` (from repo root).
- **Bug the harness itself caught immediately**, before even running the
  main eval: `RecordAddress.City` in models.py was typed as required
  `str`, but 3 of the 7 seed queries hit real live records (Inspection-
  module entities with incomplete address data) where City is genuinely
  `null`. This killed those 3 queries outright via ValidationError before
  City was made `Optional[str]`. Fixed the model to match reality (same
  discipline as every other nullable field in that file) — this is
  exactly the kind of drift/gap detection the "loud failure over silent
  wrong answer" design is supposed to produce, working as intended on the
  first real run.

## Known reliability profile (first real run, 2026-08-14)
Full results: `eval/results_20260814T223843Z.md` (human-readable summary),
`eval/raw_20260814T223843Z.jsonl` (every call), `eval/sample_20260814T223843Z.json`
(exact sample-construction log). 35 items (30 random real electrical
permits + 2 fixed regression + 3 negative cases) x 2 tools = 70 calls.

- **Overall success rate: 63/70 (90.0%)** — every non-success call was a
  correct `genuinely_not_found` (6, all negative/expected cases + a couple
  of legitimately-not-found sample items) except one.
- **check_permit_status:** 31 success, 3 genuinely_not_found, 1
  unexpected_error. Latency: 5.9s–12.9s, avg 11.0s.
- **get_inspection_history:** 32 success, 3 genuinely_not_found, 0 errors.
  Latency: 10.9s–35.2s, avg 23.8s (roughly 2x check_permit_status's, as
  expected — it opens a second browser session and verifies each
  candidate inspection individually via getById).
- **Fixed regression (ELEC-24-00375, 2016-8666): ALL PASSED**, both tools.
- **Negative cases (nonsense permit number, nonsense address,
  2022-41675): ALL PASSED** — all six calls (3 cases x 2 tools) correctly
  returned not_found.
- **ambiguous_match, access_restricted, contract_drift, transient: all
  zero** in this run. Notable: contract_drift being zero is itself
  informative given the harness caught a real drift-adjacent bug (see
  below) during sample construction, before the main run even started —
  the main run's 70 calls just didn't happen to hit that specific gap
  (RecordAddress.City null) again once it was fixed first.
- **The one unexpected_error** (`check_permit_status('2015-4421')`,
  `TypeError: Failed to fetch`) was investigated immediately: re-running
  that exact call standalone came back `found` cleanly — a real permit,
  no data problem. It was a one-off network hiccup inside the browser's
  fetch() call that the classifier didn't recognize as transient yet.
  Fixed (`eval/classify.py` now treats "failed to fetch" as transient) —
  see the addendum in the results file for the full writeup. This run's
  recorded category for that call was left as observed
  (unexpected_error), not retroactively changed.
- **A real bug the harness caught before the main run even started:**
  `RecordAddress.City` was required `str` but 3 of 7 seed queries hit
  live records where it's genuinely null — see "Eval harness: built"
  above for the fix. Zero code bugs surfaced during the main 70-call run
  itself.
- **Sample honesty:** all 100 candidates in the pool came from the single
  broad `Keyword="electrical"` query — none of the 6 street-name queries
  contributed any (they returned real results, just not electrical-typed
  permits in their first 50). Status distribution: Complete=45,
  Expired=38, Issued=12, Void=4, Cancelled/Withdrawn=1. This is a sample
  of what these 7 specific queries surface against an opaque relevance
  ranking, not a random draw from the full universe of electrical permits
  — see the results file's "Known sample limitations" section for the
  full caveat.
- **Follow-up check (2026-08-14, same day): confirmed real, not a fluke
  of those 6 streets.** Pulled 8 different real Leander street names from
  the candidate pool's own addresses (DEERCREEK LN, OAKWOOD DR, HALSEY DR,
  WILLOW CREEK DR, LAUREL GLEN BLVD, DUBLIN DR, LONDONDERRY DR, GRANITE
  CREEK DR — none overlapping the original 6) and ran the identical
  `ExactMatch=True, PageSize=50` query method against them. Result: 7 of
  8 surfaced ZERO electrical-typed permits, same as before. The one that
  did (DEERCREEK LN) had them ranked at positions 15, 20, 21, 24, 40, 41,
  48 out of 50 — never in the top 15. Combined across all 14 street
  queries tried so far (6 original + 8 new): 1/14 surfaced any electrical
  permits at all, and even that one never ranked them near the top.
  **Conclusion: this portal's address-scoped search relevance ranking
  reliably deprioritizes electrical-type permits relative to other record
  types (inspections, other permit types, plans, licenses) at the same
  address — a broad `Keyword="electrical"` query is the correct and
  necessary way to sample electrical permits specifically; street-name
  search alone is not a reliable path to them even at PageSize=50.** This
  is a real characteristic of the live system, not noise from an unlucky
  street pick, and it's why build_sample.py's actual candidate pool ends
  up 100% sourced from the single broad query in practice, regardless of
  which additional street names get added for diversity.

**Bottom line:** both tools are solid against live data — no code bugs in
the 70-call main run, both negative-case and regression-case handling
100% correct, and the one anomaly was a transient network blip, not a
logic error, caught and explained rather than hand-waved.

## FIXED: bare-street-name address search could silently drop/undercount matches (2026-08-14)
Previously confirmed (see prior session's finding, kept below for the
full backstory) and now fixed, with a real before/after:

**Before** (PageSize=25 for every lookup): `check_permit_status("DEERCREEK LN")`
returned `outcome: "ambiguous"` with only 4 candidates
(ELEC-24-00295, ELEC-24-00386, ELEC-24-00402, ELEC-23-00268) — silently
missing 3 real electrical permits on that same street (2021-36242,
2021-36243, 2020-30304) that existed beyond the PageSize=25 cutoff, with
no indication anything was missing.

**Fix:** `_lookup_electrical_permit` (tools.py) now picks PageSize by
identifier shape: permit-number-looking identifiers keep
`LOOKUP_PAGE_SIZE_PERMIT_NUMBER = 25` (narrow queries, no crowding
problem, unaffected — confirmed no latency regression, still ~11s).
Address-looking identifiers now use `LOOKUP_PAGE_SIZE_ADDRESS = 200`
(config.py). Confirmed live first: search/search has no PageSize cap
observed up to at least 500 — requesting 1000 for a query with
TotalFound=477 just returns all 477, no error, no silent capping. So a
much larger address PageSize is a real fix, not a workaround chasing an
API limit.

Also added an explicit truncation signal, since even PageSize=200 can't
guarantee completeness for a large enough underlying record set:
`_lookup_electrical_permit` now compares `TotalFound` (the grand total
across every module — permits, inspections, plans, etc. — not just
electrical permits) against how many records were actually returned. If
they differ:
  - `not_found` responses gain `"no_match_but_results_truncated": true`
    (the exact field asked for).
  - `ambiguous` responses gain `"candidates_possibly_truncated": true` —
    an extension beyond what was asked (only not_found was specified),
    added because the DEERCREEK LN before-case above proved the
    *candidate list itself* can be incomplete, not just a clean miss —
    the same signal is just as relevant there.

**After:** `check_permit_status("DEERCREEK LN")` now returns `ambiguous`
with **9 candidates** — all 7 previously known ones, PLUS 2 more
(2022-41786, ELEC-26-00772) that weren't even visible in the earlier
PageSize=50 eval check. `candidates_possibly_truncated: true` is present
and CORRECTLY so — TotalFound for this query is 477 across all modules,
still above PageSize=200, so there could be more beyond what was
returned. That's the flag doing its job honestly, not a bug: everything
returned is real and confirmed electrical, the flag just tells the
caller "there might be more we didn't see," which is true.

**Regression-checked:** permit-number lookup (`ELEC-24-00375`) and the
already-verified full address (`"100 DEERCREEK LN LEANDER TX 78641"`)
both still return clean single `found` results, unaffected.
- Disambiguation logic is a simple len()-based branch today; no real
  scoring/ranking for close address matches yet.
- Retry/circuit-breaker layer not yet implemented.
- Statistical drift monitoring (null-rate tracking) not yet implemented —
  right now schema drift is only caught by Pydantic's hard validation
  failure (extra="forbid"), which is a start but not the full design (the
  eval harness above catches it too, but only when actually run, not
  continuously).
- get_inspection_history's candidate search caps at PageSize=100 with no
  pagination beyond that — fine for everything tested so far, but a permit
  at a very high-traffic address could theoretically have more inspection
  candidates than that and miss some. Not hit in practice yet.

## v2 (requires login/auth) — deliberately out of scope, not a bug
The AUTHORITATIVE per-permit inspection list
(entity/inspections/search/search) requires being a logged-in contact on
the record. v1 explicitly excludes login/account creation, so
get_inspection_history uses the address-search-plus-verify design above
instead — correct per-item, best-effort on completeness. If a future
version adds login, entity/inspections/search/search
(EnerGovClient.get_inspections, already implemented) would replace or
supplement it with the real, complete, guaranteed list.

## Immediate next step
v1's originally-planned pieces are all built, verified end-to-end, AND
now have a real measured reliability baseline (90% success over 70 live
calls, zero code bugs in the main run — see "Known reliability profile").
What's left is the rest of the reliability/quality hardening list:
retry/circuit-breaker for transient failures (the harness already found
one real example to design against — the "Failed to fetch" case) and
continuous statistical drift monitoring (today it's only checked when the
eval harness is actually run).
