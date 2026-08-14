# permit-status-agent

An MCP server that checks electrical permit status and inspection history
on the City of Leander, TX EnerGov citizen self-service portal — a real,
live government system, not a demo API.

## Why this isn't trivial

Leander doesn't publish a public API for this. The server talks to the
portal's actual internal JSON API, reverse-engineered by driving the site
in a real browser and reading its own network traffic and JS bundle — not
guessed.

Real constraints found along the way:

- The search endpoint requires four undocumented tenant headers on every
  request (`tenantid`, `tenantname`, `tyler-tenanturl`,
  `tyler-tenant-culture`). The site's own Angular app injects them via an
  interceptor; a request without them 500s.
- It also requires the full multi-module criteria payload shape (permit,
  plan, inspection, license, project criteria all present at once), not
  just the fields relevant to permits.
- `ExactMatch=true` turned out to be a relevance boost, not a
  literal-match filter — using it wrong swamps results with tens of
  thousands of loosely-related noise records instead of the real match.
- The *authoritative* per-permit inspection list requires being a
  logged-in "contact" on the record. Rather than add login (deliberately
  out of scope — see below), this project found a second, genuinely
  public endpoint — a single inspection's own detail page — that includes
  an exact link back to its parent permit, and builds inspection history
  from that instead, with no login involved.

## The two tools

- **`check_permit_status(identifier)`** — look up an electrical permit by
  permit number (`ELEC-24-00375`, or older `2016-8666`-style formats) or
  street address. Returns status, dates, and description. Ambiguous or
  not-found results say so explicitly rather than guessing at a match.
- **`get_inspection_history(permit_number)`** — inspection history for a
  known permit: type, date, and result, in chronological order.
  Best-effort, not authoritative — see Scope below for why.

## Reliability, measured — not claimed

This is the part most projects like this skip. There's a real eval
harness (`eval/`) that pulls a random sample of real permits live from
the portal, runs both tools against it plus fixed regression cases and
negative cases, and classifies every result into one of seven failure
categories.

Latest real run — **70 calls against live data, 90.0% success rate**:

| category | count |
|---|---|
| success | 63 |
| genuinely_not_found (correctly) | 6 |
| unexpected_error | 1 |

The one `unexpected_error` was investigated, not just counted: a one-off
network blip that resolved cleanly on retry — which exposed a real gap in
the classifier itself, since fixed.

The eval process also surfaced two real, since-fixed bugs:

- A Pydantic response model was stricter than reality — a live record had
  a `null` address field the schema didn't allow, silently killing 3 of
  the eval's own seed queries before it was caught and fixed.
- Address searches using a bare street name (no house number) could rank
  real electrical permits past the default result-page cutoff and miss
  them entirely. Confirmed live — one street's search went from finding 4
  of 9 real matches to all 9 — then fixed by widening the page size for
  address-shaped queries and adding an explicit "results may be
  truncated" signal directly in the response.

Full raw results and reproducible sample-construction logs live in
`eval/`.

## Setup

```bash
python3 -m venv venv          # Python 3.10+ required (mcp SDK)
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
```

Run it:

```bash
# via the included test client (spawns the server itself)
./venv/bin/python3 test_mcp_client.py

# or point Claude Desktop / any MCP host at it directly
{
  "mcpServers": {
    "permit-status-agent": {
      "command": "/path/to/venv/bin/python3",
      "args": ["/path/to/server.py"]
    }
  }
}
```

## Scope, by design

- **Electrical permits only.** Not a general permit lookup tool.
- **Read-only.** No submissions, no account actions.
- **No login.** Deliberately excluded — see below for how inspection
  history works without it.
- **Inspection history is recall-limited, not accuracy-limited.** Every
  inspection returned is individually verified to belong to the permit
  (an exact ID match, not a guess). What isn't guaranteed is finding
  *every* inspection that exists — the complete authoritative list
  requires login, which this project doesn't do. The tool says so in its
  own response, not just in the docs.

## Stack

Python · Playwright (a real browser context, not a bare HTTP client —
required by this portal's fingerprinting) · Pydantic (strict response
contracts, `extra="forbid"`, so API drift is a hard failure, not a silent
one) · MCP (Model Context Protocol, stdio transport)
