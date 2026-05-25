"""Application-aware Gmail search helpers (task 083).

This module is the *only* place that knows how to turn an
``Application`` + ``Job`` pair into a Gmail-search query and how to score
the messages that come back.

It is intentionally a pure-Python module with no Gmail/Google library
imports. The actual network round-trip lives in
:mod:`app.gmail_client`; this module produces the query string and
classifies the returned metadata.

Scope
-----
- Build a deterministic Gmail-search query for an application.
- Score returned messages against the application's signals.
- Return only the safe metadata fields the contract allows (no full
  bodies, no HTML, no attachments).

Out of scope (per ``docs/contracts/gmail_integration.md``):

- Final classification (rejection/interview/offer/etc.).
- Application main-status transitions.
- Any Gmail write/modify/archive/delete/label operation.
- Background polling — search is strictly user-triggered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional


# Known ATS / hiring-platform sender domains. The list is intentionally a
# *query aid*, not an authoritative classifier — Gmail will return any
# message that mentions the company or job title regardless of sender. A
# match on one of these domains is a positive signal for scoring.
ATS_DOMAINS: tuple[str, ...] = (
    "greenhouse.io",
    "lever.co",
    "workday.com",
    "myworkdayjobs.com",
    "ashbyhq.com",
    "smartrecruiters.com",
    "icims.com",
    "bamboohr.com",
    "jobvite.com",
    "recruitee.com",
    "successfactors.com",
)


# Recency window applied when ``submitted_at`` is unknown. Mirrors the
# default mentioned in the task description ("180d") and the contract's
# example query window.
DEFAULT_NEWER_THAN_DAYS = 180

# One-day buffer applied to ``submitted_at`` so an email sent in the
# minutes before the user marked the application submitted still falls
# inside the window.
SUBMITTED_BUFFER_DAYS = 1

# Hard cap on the number of candidates a single search response returns.
# Mirrors the spirit of :data:`gmail_client.MAX_TEST_SEARCH_RESULTS` but
# is intentionally separate so the application-search surface can be
# tuned without changing the test-search surface.
MAX_APPLICATION_SEARCH_RESULTS = 25


@dataclass(frozen=True)
class ApplicationQueryInputs:
    """Inputs the query builder needs.

    Kept as a dataclass (rather than a pile of positional args) so future
    tasks can grow the input set — ``sender_domain``, ``location``,
    etc. — without breaking existing callers.
    """

    company: Optional[str]
    job_title: Optional[str]
    submitted_at: Optional[datetime]
    extra_terms: tuple[str, ...] = ()
    include_ats_terms: bool = True


def _quote_phrase(value: str) -> str:
    """Wrap ``value`` for use inside a Gmail-search query.

    Empty / whitespace-only strings produce an empty token. Embedded
    double quotes are stripped because Gmail's parser does not support
    escaping inside quoted phrases.
    """
    cleaned = value.strip().replace('"', "")
    if not cleaned:
        return ""
    return f'"{cleaned}"'


def _format_gmail_date(value: datetime) -> str:
    """Format a datetime as Gmail's ``YYYY/M/D`` after-clause value."""
    return f"{value.year}/{value.month}/{value.day}"


def _ats_sender_clause(domains: Iterable[str]) -> str:
    parts = [f"from:{d}" for d in domains if d]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "(" + " OR ".join(parts) + ")"


def build_application_query(inputs: ApplicationQueryInputs) -> str:
    """Build a Gmail-search query for an application.

    The shape is::

        (<term> OR <term> ...) <date-clause> [<ats-from-clause>]

    where ``<date-clause>`` is ``after:YYYY/M/D`` when ``submitted_at`` is
    set, and ``newer_than:180d`` otherwise.
    """
    primary_terms: list[str] = []
    company_token = _quote_phrase(inputs.company or "")
    if company_token:
        primary_terms.append(company_token)
    title_token = _quote_phrase(inputs.job_title or "")
    if title_token:
        primary_terms.append(title_token)
    for term in inputs.extra_terms:
        token = _quote_phrase(term)
        if token and token not in primary_terms:
            primary_terms.append(token)

    primary_clause = ""
    if len(primary_terms) == 1:
        primary_clause = primary_terms[0]
    elif primary_terms:
        primary_clause = "(" + " OR ".join(primary_terms) + ")"

    if inputs.submitted_at is not None:
        cutoff = inputs.submitted_at - timedelta(days=SUBMITTED_BUFFER_DAYS)
        date_clause = f"after:{_format_gmail_date(cutoff)}"
    else:
        date_clause = f"newer_than:{DEFAULT_NEWER_THAN_DAYS}d"

    ats_clause = ""
    if inputs.include_ats_terms:
        ats_clause = _ats_sender_clause(ATS_DOMAINS)

    pieces = [p for p in (primary_clause, date_clause, ats_clause) if p]
    return " ".join(pieces).strip()


# ---- Matching / scoring ------------------------------------------------


_SAFE_METADATA_KEYS = ("id", "thread_id", "subject", "from", "date", "snippet")


@dataclass(frozen=True)
class MatchInputs:
    company: Optional[str]
    job_title: Optional[str]
    submitted_at: Optional[datetime]
    extra_terms: tuple[str, ...] = ()


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _sender_domain(sender: str) -> str:
    """Return the lower-case domain of a Gmail ``From:`` header."""
    if not sender:
        return ""
    match = re.search(r"<([^>]+)>", sender)
    address = match.group(1) if match else sender
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].strip().lower()


def _company_domain_root(company: str) -> str:
    """Best-effort ``ascii-lower`` slug for the company name.

    A real email might be ``talent@exampleaero.com``; the company is
    ``"Example Aero Labs"``. This collapses the company down to its
    alphanumeric core so a substring check has a fighting chance.
    """
    if not company:
        return ""
    return re.sub(r"[^a-z0-9]", "", company.lower())


def _parse_gmail_date(value: str) -> Optional[datetime]:
    """Parse a Gmail ``Date:`` header to an aware UTC datetime.

    Returns ``None`` if the header is missing or unparseable; date-based
    scoring then falls back to "no information" rather than failing the
    whole search.
    """
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime  # stdlib

        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# Per-signal weights. Kept as module constants so tests can pin them and
# the scoring stays explainable in code review — there is no learned
# component here.
_SIGNAL_WEIGHTS: dict[str, float] = {
    "company_name": 0.45,
    "job_title": 0.35,
    "company_sender_domain": 0.20,
    "ats_sender_domain": 0.15,
    "after_submitted_at": 0.10,
    "manual_term": 0.15,
}


def score_candidate(
    message: dict[str, Any], inputs: MatchInputs
) -> tuple[float, list[str]]:
    """Return ``(score, signals)`` for a single Gmail message.

    ``score`` is clamped to ``[0.0, 1.0]``. ``signals`` is the list of
    contributing signal names in the order they were evaluated, so a
    consumer can render an explanation for each candidate.
    """
    subject = _lower(message.get("subject"))
    snippet = _lower(message.get("snippet"))
    sender = str(message.get("from") or "")
    sender_l = sender.lower()

    haystacks = (subject, snippet, sender_l)
    signals: list[str] = []
    score = 0.0

    company = (inputs.company or "").strip()
    if company and any(company.lower() in h for h in haystacks):
        signals.append("company_name")
        score += _SIGNAL_WEIGHTS["company_name"]

    title = (inputs.job_title or "").strip()
    if title and any(title.lower() in h for h in (subject, snippet)):
        signals.append("job_title")
        score += _SIGNAL_WEIGHTS["job_title"]

    domain = _sender_domain(sender)
    if domain:
        company_slug = _company_domain_root(company)
        if company_slug and company_slug in domain.replace(".", ""):
            signals.append("company_sender_domain")
            score += _SIGNAL_WEIGHTS["company_sender_domain"]
        if any(domain == d or domain.endswith("." + d) for d in ATS_DOMAINS):
            signals.append("ats_sender_domain")
            score += _SIGNAL_WEIGHTS["ats_sender_domain"]

    if inputs.submitted_at is not None:
        received = _parse_gmail_date(str(message.get("date") or ""))
        submitted = inputs.submitted_at
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=timezone.utc)
        if received is not None and received >= (
            submitted - timedelta(days=SUBMITTED_BUFFER_DAYS)
        ):
            signals.append("after_submitted_at")
            score += _SIGNAL_WEIGHTS["after_submitted_at"]

    for term in inputs.extra_terms:
        token = term.strip().lower()
        if token and any(token in h for h in haystacks):
            if "manual_term" not in signals:
                signals.append("manual_term")
                score += _SIGNAL_WEIGHTS["manual_term"]
            break

    if score > 1.0:
        score = 1.0
    if score < 0.0:
        score = 0.0
    return score, signals


def safe_metadata(message: dict[str, Any]) -> dict[str, Any]:
    """Project ``message`` down to the safe-to-return metadata fields."""
    return {key: message.get(key) for key in _SAFE_METADATA_KEYS}
