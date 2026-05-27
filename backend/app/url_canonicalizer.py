"""Deterministic canonicalization of captured job URLs.

The browser extension hands the backend whatever the user's tab URL was at
capture time. LinkedIn renders the same posting at several URL shapes —
``/jobs/collections/recommended/?currentJobId=<id>``,
``/jobs/search/?currentJobId=<id>&keywords=...``,
``/jobs/view/<id>/?trackingId=...`` — and only the last is a clean,
shareable, stable identity for the role.

This module converts any of those shapes (and known tracking-laden general
URLs) into a clean canonical URL without calling an LLM and without doing a
network round-trip. It is consciously not a URL shortener; it strips
tracking-only parameters and rewrites known LinkedIn job paths into the
canonical ``/jobs/view/<id>`` form. The raw URL is preserved by the caller
in a separate column so debugging the original capture is still possible.

See ``docs/contracts/browser_extension_capture.md`` for the contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse


# Tracking params we strip from any URL we don't otherwise rewrite. Limited
# to widely-recognized analytics/click-id parameters so that platform-
# specific query parameters that genuinely identify a job (e.g. a job id
# in the query string of a non-LinkedIn ATS) are preserved untouched.
_GENERIC_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
    }
)

# Additional LinkedIn-only tracking params. These exist in the query string
# of legitimate LinkedIn job URLs but never change which job is being
# referenced; stripping them is safe and keeps the canonical URL short.
_LINKEDIN_TRACKING_PARAMS: frozenset[str] = _GENERIC_TRACKING_PARAMS | frozenset(
    {
        "trackingId",
        "refId",
        "origin",
        "trk",
        "trkInfo",
        "lipi",
        "lici",
        "savedSearchId",
        "alternateChannel",
        "originalSubdomain",
    }
)

_LINKEDIN_HOST_RE = re.compile(r"(?:^|\.)linkedin\.com$", re.IGNORECASE)
_LINKEDIN_VIEW_PATH_RE = re.compile(r"^/jobs/view/(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class CanonicalJobUrl:
    """Result of canonicalizing a captured job URL.

    ``source_url`` is preserved as the caller supplied it so the original
    capture is recoverable. ``canonical_url`` is the clean form that should
    be displayed to the user and used for dedup. ``external_job_id`` is
    populated when the source platform exposes a stable job id in the URL;
    ``None`` otherwise. ``source_platform`` is the platform name in
    lowercase, or ``"unknown"`` when the URL is empty / unparseable.
    """

    source_url: str
    canonical_url: str
    external_job_id: Optional[str]
    source_platform: str


def _is_linkedin_host(host: str) -> bool:
    if not host:
        return False
    return bool(_LINKEDIN_HOST_RE.search(host))


def _infer_platform(host: str) -> str:
    if not host:
        return "unknown"
    host = host.lower()
    if _is_linkedin_host(host):
        return "linkedin"
    if host.startswith("www."):
        host = host[4:]
    head = host.split(".", 1)[0]
    return head or "unknown"


def _strip_params(parsed: ParseResult, drop: frozenset[str]) -> str:
    pairs = parse_qsl(parsed.query, keep_blank_values=False)
    kept = [(k, v) for k, v in pairs if k not in drop]
    new_query = urlencode(kept)
    return urlunparse(parsed._replace(query=new_query, fragment=""))


def _linkedin_job_id(parsed: ParseResult) -> Optional[str]:
    """Pull a LinkedIn job id out of a parsed URL.

    Prefers the path form (``/jobs/view/<id>``) because that is the
    canonical surface. Falls back to ``currentJobId`` query param used by
    LinkedIn's collections/search shells which keep the focused posting in
    the URL alongside their own routing state.
    """
    path_match = _LINKEDIN_VIEW_PATH_RE.match(parsed.path or "")
    if path_match:
        return path_match.group(1)
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key == "currentJobId" and value.isdigit():
            return value
    return None


def canonicalize_job_url(url: Optional[str]) -> CanonicalJobUrl:
    """Normalize a captured job URL into a canonical form.

    Empty / non-string / unparseable input is returned unchanged with
    ``source_platform="unknown"`` and ``external_job_id=None`` so callers
    never have to special-case the no-URL path.
    """
    source_url = url if isinstance(url, str) else ""
    if not source_url or not source_url.strip():
        return CanonicalJobUrl(
            source_url=source_url,
            canonical_url=source_url,
            external_job_id=None,
            source_platform="unknown",
        )

    stripped = source_url.strip()
    try:
        parsed = urlparse(stripped)
    except ValueError:
        return CanonicalJobUrl(
            source_url=source_url,
            canonical_url=source_url,
            external_job_id=None,
            source_platform="unknown",
        )

    host = (parsed.hostname or "").lower()
    platform = _infer_platform(host)

    if platform == "linkedin":
        job_id = _linkedin_job_id(parsed)
        if job_id is not None:
            canonical = f"https://www.linkedin.com/jobs/view/{job_id}"
            return CanonicalJobUrl(
                source_url=source_url,
                canonical_url=canonical,
                external_job_id=job_id,
                source_platform="linkedin",
            )
        # LinkedIn URL we can't pin to a job id — keep the path but strip
        # LinkedIn tracking params and normalize the scheme/host.
        normalized = parsed._replace(
            scheme=parsed.scheme or "https",
            netloc="www.linkedin.com",
        )
        canonical = _strip_params(normalized, _LINKEDIN_TRACKING_PARAMS)
        return CanonicalJobUrl(
            source_url=source_url,
            canonical_url=canonical,
            external_job_id=None,
            source_platform="linkedin",
        )

    # Generic / unknown URL: only drop widely-recognized tracking params so
    # platform-specific job identifiers carried as query strings are not
    # accidentally dropped.
    canonical = _strip_params(parsed, _GENERIC_TRACKING_PARAMS)
    return CanonicalJobUrl(
        source_url=source_url,
        canonical_url=canonical,
        external_job_id=None,
        source_platform=platform,
    )
