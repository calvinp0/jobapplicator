from __future__ import annotations

from app.url_canonicalizer import canonicalize_job_url


# ---- LinkedIn rules --------------------------------------------------------


def test_linkedin_currentjobid_in_collections_url_canonicalizes():
    src = (
        "https://www.linkedin.com/jobs/collections/recommended/"
        "?currentJobId=4415730750&origin=JOB_SEARCH_PAGE_JOB_FILTER"
    )
    result = canonicalize_job_url(src)
    assert result.canonical_url == "https://www.linkedin.com/jobs/view/4415730750"
    assert result.external_job_id == "4415730750"
    assert result.source_platform == "linkedin"
    assert result.source_url == src


def test_linkedin_jobs_view_strips_tracking_params():
    src = "https://www.linkedin.com/jobs/view/4415730750/?trackingId=abc&refId=xyz"
    result = canonicalize_job_url(src)
    assert result.canonical_url == "https://www.linkedin.com/jobs/view/4415730750"
    assert result.external_job_id == "4415730750"
    assert result.source_platform == "linkedin"


def test_linkedin_jobs_search_with_currentjobid_canonicalizes():
    src = (
        "https://www.linkedin.com/jobs/search/"
        "?currentJobId=4415730750&keywords=machine%20learning&geoId=92000000"
    )
    result = canonicalize_job_url(src)
    assert result.canonical_url == "https://www.linkedin.com/jobs/view/4415730750"
    assert result.external_job_id == "4415730750"


def test_linkedin_url_without_job_id_preserves_path_strips_tracking():
    src = (
        "https://www.linkedin.com/jobs/collections/recommended/"
        "?trackingId=abc&utm_source=newsletter"
    )
    result = canonicalize_job_url(src)
    # No job id resolvable — keep the path, drop tracking params, normalize host.
    assert result.canonical_url.startswith(
        "https://www.linkedin.com/jobs/collections/recommended/"
    )
    assert "trackingId" not in result.canonical_url
    assert "utm_source" not in result.canonical_url
    assert result.external_job_id is None
    assert result.source_platform == "linkedin"


def test_linkedin_subdomain_is_still_linkedin():
    src = "https://uk.linkedin.com/jobs/view/4415730750/?trackingId=abc"
    result = canonicalize_job_url(src)
    assert result.canonical_url == "https://www.linkedin.com/jobs/view/4415730750"
    assert result.source_platform == "linkedin"


# ---- General / unknown URLs -----------------------------------------------


def test_unknown_url_preserves_meaningful_path():
    src = "https://example.com/jobs/foo?id=42&utm_source=newsletter"
    result = canonicalize_job_url(src)
    assert result.canonical_url == "https://example.com/jobs/foo?id=42"
    assert result.external_job_id is None
    assert result.source_platform == "example"


def test_unknown_url_strips_common_tracking_params():
    src = "https://greenhouse.io/jobs/123?utm_medium=x&fbclid=y&gclid=z&mc_cid=q"
    result = canonicalize_job_url(src)
    assert result.canonical_url == "https://greenhouse.io/jobs/123"
    assert result.source_platform == "greenhouse"


def test_unknown_url_keeps_non_tracking_query():
    src = "https://boards.greenhouse.io/example/jobs/42?gh_src=mailer"
    result = canonicalize_job_url(src)
    # ``gh_src`` is platform-specific and not in the generic tracking list —
    # the canonicalizer preserves it because it might be meaningful.
    assert "gh_src=mailer" in result.canonical_url


# ---- Edge cases ------------------------------------------------------------


def test_empty_string_returns_unknown():
    result = canonicalize_job_url("")
    assert result.canonical_url == ""
    assert result.external_job_id is None
    assert result.source_platform == "unknown"


def test_whitespace_only_returns_unknown():
    result = canonicalize_job_url("   ")
    assert result.external_job_id is None
    assert result.source_platform == "unknown"


def test_none_returns_unknown():
    result = canonicalize_job_url(None)  # type: ignore[arg-type]
    assert result.canonical_url == ""
    assert result.source_platform == "unknown"


def test_malformed_url_does_not_raise():
    # ``urlparse`` is famously lenient and rarely raises, but the canonicalizer
    # must never let an unexpected input crash the capture endpoint.
    result = canonicalize_job_url("not a url at all")
    assert result.external_job_id is None
    # No host means no recognized platform.
    assert result.source_platform == "unknown"


def test_does_not_call_llm_or_network():
    # Marker test: the canonicalizer is deterministic and pure. If a future
    # change adds an HTTP client / LLM dependency here, this import will
    # fail to introduce one silently — we only depend on stdlib.
    import app.url_canonicalizer as mod

    assert "requests" not in dir(mod)
    assert "openai" not in dir(mod)
    assert "anthropic" not in dir(mod)
