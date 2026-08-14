"""
MCP server entrypoint. Registers check_permit_status and
get_inspection_history (permit_status_agent/tools.py) as MCP tools and
serves them over stdio transport.

Built against mcp==2.0.0 (the Python MCP SDK's v2), which requires Python
3.10+ — this project's venv was rebuilt on Python 3.12 for that reason
(the original venv was 3.9.6). v2 is a breaking rework of v1: there is no
`mcp.server.fastmcp.FastMCP` in this version. The equivalent class is
`mcp.server.mcpserver.MCPServer`, used below. If a future session finds an
older `mcp` installed, that's v1 and this file's imports won't match —
check `pip show mcp` before assuming this code is still correct.

No business logic lives here — this file only wires the already-working
functions in tools.py up to MCP's tool-calling protocol. See tools.py for
how check_permit_status and get_inspection_history actually work, and
PROJECT.md for the empirical findings behind their design.
"""
from mcp.server.mcpserver import MCPServer

from permit_status_agent import config
from permit_status_agent.tools import check_permit_status as _check_permit_status
from permit_status_agent.tools import get_inspection_history as _get_inspection_history

mcp = MCPServer(name="permit-status-agent")


@mcp.tool()
async def check_permit_status(identifier: str) -> dict:
    """Look up the status of an electrical permit on the City of Leander,
    TX EnerGov citizen self-service portal.

    Accepts either a permit number (e.g. "ELEC-24-00375" or "2016-8666")
    or a street address (e.g. "1303 LEANDER DR"). Scope is electrical
    permits only: a real, valid permit number for a non-electrical permit
    (e.g. a residential new-construction building permit) will come back
    not_found by design, not as an error — that's this tool correctly
    staying in scope, not a lookup failure.

    Returns one of:
    - {"outcome": "found", "permit_number", "case_type", "work_class",
       "status", "description", "address", "apply_date", "issue_date",
       "expire_date", "final_date"}
    - {"outcome": "not_found", "identifier"} — no confident electrical
      permit match for this identifier.
    - {"outcome": "ambiguous", "identifier", "message", "candidates"} —
      multiple electrical permits matched with no way to pick one
      confidently. Do not guess which one the user means; show them the
      candidates (permit_number, case_type, status, address each) and ask.
    - {"outcome": "error", "identifier", "message"} — a transient failure
      or an unexpected response shape from the live portal (possible API
      drift). Safe to retry once; if it persists, say so rather than
      guessing at a result.
    """
    return await _check_permit_status(identifier, headless=config.DEFAULT_HEADLESS)


@mcp.tool()
async def get_inspection_history(permit_number: str) -> dict:
    """Get the inspection history for an electrical permit on the City of
    Leander, TX EnerGov citizen self-service portal.

    IMPORTANT — results can be INCOMPLETE, but never inaccurate. Every
    inspection this tool returns is individually verified to belong to the
    given permit (an exact ID match against the portal's own linking data,
    not a guess or an address coincidence), so anything returned can be
    trusted as real and correctly attributed. But finding candidates in
    the first place relies on a public address search, which is not
    guaranteed to surface every inspection tied to the permit — the
    portal's authoritative, complete inspection list requires being a
    logged-in contact on the record, which this tool deliberately does not
    do. So an empty or short list means "no inspections found via public
    search," not "no inspections exist" — say that distinction explicitly
    if you relay this to a user, rather than stating a definitive count or
    "no inspections have occurred."

    Accepts a permit number (e.g. "ELEC-24-00375" or "2016-8666"), not an
    address. Uses the same permit-matching logic as check_permit_status, so
    not_found/ambiguous/error outcomes below mean the same thing they do
    there — call check_permit_status first if you need to resolve an
    address to a permit number.

    Returns one of:
    - {"outcome": "found", "permit_number", "inspections": [{"type",
       "date", "result"}, ...] in chronological order, "no_inspections_yet"
       (bool), "data_source", "caveat" (the recall-limitation wording
       above, always included in the result itself)}
    - {"outcome": "not_found", "identifier"}
    - {"outcome": "ambiguous", "identifier", "message", "candidates"}
    - {"outcome": "error", "permit_number" or "identifier", "message"}
    """
    return await _get_inspection_history(permit_number, headless=config.DEFAULT_HEADLESS)


if __name__ == "__main__":
    mcp.run(transport="stdio")
