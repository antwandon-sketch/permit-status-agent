"""
Failure-mode classification for eval results, per PROJECT.md's
reliability section.

Categories:
  success              — outcome == "found"
  genuinely_not_found  — outcome == "not_found"
  ambiguous_match      — outcome == "ambiguous"
  access_restricted    — the known per-permit inspection-list login wall
                          (kept even though get_inspection_history's
                          current design routes around it — see
                          PROJECT.md; this exists so the classifier still
                          recognizes it if that ever resurfaces)
  contract_drift       — outcome == "error" from a Pydantic validation
                          failure (the API's response shape changed)
  transient            — timeout / 5xx / network-level failure, whether
                          it surfaced as a caught EnerGovSearchError or an
                          uncaught exception (e.g. Playwright timeout)
  unexpected_error     — anything not fitting the above. This bucket
                          having ANY entries is itself a signal that a
                          new category is needed, not that the harness is
                          broken — see each one individually in the report.
"""
from __future__ import annotations

CATEGORIES = [
    "success",
    "genuinely_not_found",
    "ambiguous_match",
    "access_restricted",
    "contract_drift",
    "transient",
    "unexpected_error",
]

_TRANSIENT_MARKERS = (
    "timeout", "timed out", "network", "err_", "econn", "http 5", "failed to fetch",
)
_DRIFT_MARKERS = ("schema validation", "api drift")
_RESTRICTED_MARKERS = ("must be a contact",)


def classify(response: dict | None, exception: BaseException | None) -> str:
    if exception is not None:
        msg = str(exception).lower()
        name = type(exception).__name__.lower()
        if any(m in name or m in msg for m in _TRANSIENT_MARKERS):
            return "transient"
        return "unexpected_error"

    if not isinstance(response, dict):
        return "unexpected_error"

    outcome = response.get("outcome")
    message = (response.get("message") or "").lower()

    if outcome == "found":
        return "success"
    if outcome == "not_found":
        return "genuinely_not_found"
    if outcome == "ambiguous":
        return "ambiguous_match"
    if outcome == "restricted":
        return "access_restricted"
    if outcome == "error":
        if any(m in message for m in _DRIFT_MARKERS):
            return "contract_drift"
        if any(m in message for m in _RESTRICTED_MARKERS):
            return "access_restricted"
        if any(m in message for m in _TRANSIENT_MARKERS):
            return "transient"
        return "unexpected_error"

    return "unexpected_error"
