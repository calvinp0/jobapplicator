"""Deterministic classifier for Gmail application emails (task 084).

This module turns a candidate email's *safe metadata* (subject / from /
date / snippet) into one of the classifier labels pinned by
``docs/contracts/gmail_integration.md``:

    submission_confirmation
    rejection
    interview_request
    recruiter_followup
    assessment
    offer
    application_update
    newsletter_or_unrelated
    unknown

Design goals
------------

* **Conservative.** Each match is a substring check on the lowered
  metadata fields. No model is invoked. The user remains the final
  reviewer for any label that does not carry strong evidence.
* **Evidence-based.** Every non-``unknown`` result lists at least one
  short evidence quote that says exactly which phrase was matched and in
  which field. Full email bodies are never inspected.
* **Precedence handles ambiguity.** When several labels collect evidence
  on the same message, the higher-priority label wins. The order is the
  one pinned by the contract: ``offer`` > ``interview_request`` >
  ``assessment`` > ``rejection`` > ``submission_confirmation`` >
  ``recruiter_followup`` > ``application_update`` >
  ``newsletter_or_unrelated`` > ``unknown``. This is what keeps
  "Unfortunately, we need to reschedule your interview" out of the
  rejection bucket — the ``interview_request`` phrase ("reschedule",
  "interview") fires too and outranks the lone "unfortunately" hit.

This module has zero google / network imports and is safe to load in the
test process. The actual Gmail round-trip lives in :mod:`app.gmail_client`;
classifier callers pass the metadata dict they already have in hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


# The classifier labels. Order matches the contract; tests pin this
# tuple so any reshuffle is a contract-visible change.
CLASSIFIER_LABELS: tuple[str, ...] = (
    "submission_confirmation",
    "rejection",
    "interview_request",
    "recruiter_followup",
    "assessment",
    "offer",
    "application_update",
    "newsletter_or_unrelated",
    "unknown",
)


# Precedence used to break ties when several labels match. The list is
# applied highest-first; the first label with at least one piece of
# evidence wins.
_PRECEDENCE: tuple[str, ...] = (
    "offer",
    "interview_request",
    "assessment",
    "rejection",
    "submission_confirmation",
    "recruiter_followup",
    "application_update",
    "newsletter_or_unrelated",
    "unknown",
)


# Per-label phrase tables. Phrases are matched as lower-case substrings
# against the lowered metadata fields. They are intentionally short and
# unambiguous; richer signals (e.g. "reschedule" excluding "unfortunately"
# from rejection) are handled by the precedence rule above instead of by
# regex magic, so review stays straightforward.
_PHRASES: dict[str, tuple[str, ...]] = {
    "rejection": (
        "not moving forward",
        "will not be moving forward",
        "decided not to proceed",
        "not selected",
        "pursue other candidates",
        "unable to offer",
        "position has been filled",
        "role has been filled",
        "application was unsuccessful",
        "we regret to inform",
        # ``unfortunately`` is a weak signal on its own. The precedence
        # rule above ensures ``interview_request`` / ``assessment`` etc.
        # outrank a lone ``unfortunately`` hit; keeping it in the table
        # lets confidence reflect that some rejection-flavored language
        # is present.
        "unfortunately",
    ),
    "interview_request": (
        "schedule an interview",
        "schedule a call",
        "phone screen",
        "technical interview",
        "interview availability",
        "available for an interview",
        "meet with",
        "next step",
        "speak with",
        "chat with our team",
        "set up a time",
        "reschedule your interview",
        "reschedule the interview",
        "invite you to interview",
    ),
    "assessment": (
        "coding challenge",
        "take-home",
        "take home",
        "technical exercise",
        "assignment",
        "questionnaire",
        "hackerrank",
        "codesignal",
        "complete the assessment",
        "complete an assessment",
        "complete this assessment",
        "submit your assessment",
        # ``assessment`` and ``test`` are kept narrow on purpose — both
        # words are common in unrelated mail (newsletters, marketing).
        # We require the assessment word to appear near a clear verb
        # ("complete", "submit") rather than treating any occurrence as
        # a positive signal.
    ),
    "submission_confirmation": (
        "application received",
        "thank you for applying",
        "we received your application",
        "your application has been submitted",
        "successfully submitted",
        "received your application",
        "thanks for applying",
        "thank you for your application",
    ),
    "offer": (
        "pleased to offer",
        "would like to extend",
        "extend an offer",
        "extend you an offer",
        "selected for the role",
        "selected for this role",
        "congratulations",
        "offer letter",
    ),
    "application_update": (
        "under review",
        "reviewing your application",
        "still reviewing",
        "update on your application",
        "we will be in touch",
        "we'll be in touch",
        "application status",
        "status update",
    ),
    "recruiter_followup": (
        "wanted to follow up",
        "following up on your application",
        "circling back",
        "checking in",
        "touching base",
        "would love to chat",
    ),
    "newsletter_or_unrelated": (
        "unsubscribe",
        "view in browser",
        "newsletter",
        "weekly digest",
        "this week in",
        "marketing preferences",
        "promotional",
    ),
}


# Per-label confidence weights. Picking one strong phrase already pushes
# confidence above the ``needs_review`` threshold; a second hit caps the
# label near the top of the [0, 1] range. The numbers are deliberately
# coarse so a code reviewer can see at a glance how strong a match needs
# to be to flip the application's status.
_BASE_CONFIDENCE = 0.55
_PER_EVIDENCE_BONUS = 0.18
_MAX_CONFIDENCE = 0.95


# Threshold below which an ``unknown`` classification is preferred over
# the lone weak phrase that matched. Surfaces low-signal hits as
# ``needs_review`` instead of, say, a confident rejection on the word
# "unfortunately" alone.
_LOW_CONFIDENCE_FLOOR = 0.55


# Which classifier labels map onto an ``EmailLink.classified_status``.
# ``None`` means "do not persist an EmailLink row" — for
# ``newsletter_or_unrelated`` (clearly off-topic) and ``unknown`` (the
# user must review before the dashboard reacts).
LABEL_TO_EMAIL_LINK_STATUS: dict[str, Optional[str]] = {
    "submission_confirmation": "confirmation",
    "rejection": "rejection",
    "interview_request": "next_step",
    "recruiter_followup": "next_step",
    # Per the contract, assessment maps to ``next_step`` today and will
    # split into its own ``EmailLink.classified_status`` once the
    # manual-entry UI grows the matching choice.
    "assessment": "next_step",
    "offer": "offer",
    "application_update": "other",
    "newsletter_or_unrelated": None,
    "unknown": None,
}


# Which classifier labels map onto an ``email_status`` value to surface
# in the classify response. The persisted ``email_status`` is *derived*
# from the EmailLink the endpoint writes (see
# :mod:`app.routers.applications`); this map is the *response-time*
# surface so the UI / curl user can see the classifier's intent even when
# the EmailLink vocabulary is coarser.
LABEL_TO_EMAIL_STATUS: dict[str, str] = {
    "submission_confirmation": "confirmation_found",
    "rejection": "classified_rejection",
    "interview_request": "classified_interview",
    "recruiter_followup": "classified_interview",
    "assessment": "classified_assessment",
    "offer": "classified_offer",
    "application_update": "classified_neutral",
    "newsletter_or_unrelated": "needs_review",
    "unknown": "needs_review",
}


# Which classifier labels imply an ``Application.status`` target. The
# value is the target main status; ``None`` means "do not propose a
# status change". The endpoint still defers to the existing
# terminal-status protection in ``_EMAIL_SIDE_EFFECTS`` when writing the
# EmailLink, so ``withdrawn`` / ``rejected`` stay sticky even when a
# higher-precedence label fires.
LABEL_TO_APPLICATION_STATUS: dict[str, Optional[str]] = {
    "submission_confirmation": None,
    "rejection": "rejected",
    "interview_request": "interview",
    "recruiter_followup": "interview",
    "assessment": None,
    "offer": "offer",
    "application_update": None,
    "newsletter_or_unrelated": None,
    "unknown": None,
}


@dataclass(frozen=True)
class CandidateEmail:
    """Safe-metadata view of one Gmail message.

    Only the four metadata fields the contract allows are accepted; the
    body / html / attachments are deliberately not part of the dataclass
    so a classifier caller cannot accidentally feed them in.
    """

    subject: Optional[str] = None
    from_: Optional[str] = None
    date: Optional[str] = None
    snippet: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None


@dataclass(frozen=True)
class EvidenceItem:
    """One quote that supported a classification."""

    field: str
    text: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "text": self.text, "reason": self.reason}


@dataclass(frozen=True)
class ClassificationResult:
    """The full classifier output for one candidate."""

    classification: str
    confidence: float
    evidence: tuple[EvidenceItem, ...] = field(default_factory=tuple)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "confidence": round(self.confidence, 4),
            "evidence": [e.to_dict() for e in self.evidence],
            "reason": self.reason,
        }


def _haystacks(candidate: CandidateEmail) -> tuple[tuple[str, str], ...]:
    """Return ``(field_name, lowercase_text)`` pairs for substring search.

    Only metadata fields the contract permits are inspected. Full bodies
    are never searched — they are never on the dataclass to begin with.
    """
    return (
        ("subject", (candidate.subject or "").lower()),
        ("snippet", (candidate.snippet or "").lower()),
        ("from", (candidate.from_ or "").lower()),
    )


def _find_phrase_hits(
    haystacks: Iterable[tuple[str, str]], phrases: Iterable[str]
) -> list[tuple[str, str]]:
    """Return ``(field_name, matched_phrase)`` pairs for every hit."""
    hits: list[tuple[str, str]] = []
    for field_name, text in haystacks:
        if not text:
            continue
        for phrase in phrases:
            if phrase in text:
                hits.append((field_name, phrase))
    return hits


def _shorten_evidence(text: str, phrase: str, *, window: int = 80) -> str:
    """Return a short quote from ``text`` centered on ``phrase``.

    The quote is at most ``window`` chars so the evidence stays compact
    and obviously does not contain a full email body. Returned text is
    case-preserving (the *original* field text is sliced) so the user can
    recognise the phrase when reviewing.
    """
    if not text or not phrase:
        return ""
    lower = text.lower()
    idx = lower.find(phrase)
    if idx < 0:
        return text[:window]
    start = max(0, idx - 15)
    end = min(len(text), idx + len(phrase) + 30)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet[:window]


def classify_candidate(
    candidate: CandidateEmail,
) -> ClassificationResult:
    """Classify ``candidate`` into one of :data:`CLASSIFIER_LABELS`.

    The classification is purely deterministic — no LLM, no network. The
    rules:

    1. Every label whose phrase table matches at least once is a
       *candidate label*.
    2. Confidence per candidate label = base + bonus * (extra evidence).
    3. Precedence (highest first) picks the winner. The runner-up labels'
       evidence is discarded so the response stays focused on the chosen
       label.
    4. If the winner's confidence falls below the low-confidence floor,
       the result downgrades to ``unknown`` with the same evidence
       attached as a reviewer hint.
    """
    haystacks = _haystacks(candidate)
    raw_lookup = {name: text for name, text in (
        ("subject", candidate.subject or ""),
        ("snippet", candidate.snippet or ""),
        ("from", candidate.from_ or ""),
    )}

    matches: dict[str, list[EvidenceItem]] = {}
    for label, phrases in _PHRASES.items():
        hits = _find_phrase_hits(haystacks, phrases)
        if not hits:
            continue
        seen: set[tuple[str, str]] = set()
        evidence: list[EvidenceItem] = []
        for field_name, phrase in hits:
            key = (field_name, phrase)
            if key in seen:
                continue
            seen.add(key)
            original = raw_lookup.get(field_name, "")
            quote = _shorten_evidence(original, phrase) or phrase
            evidence.append(
                EvidenceItem(
                    field=field_name,
                    text=quote,
                    reason=f"contains {label.replace('_', ' ')} phrase",
                )
            )
        matches[label] = evidence

    if not matches:
        return ClassificationResult(
            classification="unknown",
            confidence=0.0,
            evidence=(),
            reason="No known phrases matched the email metadata",
        )

    winner: Optional[str] = None
    for label in _PRECEDENCE:
        if label in matches:
            winner = label
            break

    assert winner is not None  # at least one match exists
    evidence = tuple(matches[winner])
    confidence = min(
        _MAX_CONFIDENCE,
        _BASE_CONFIDENCE + _PER_EVIDENCE_BONUS * max(0, len(evidence) - 1),
    )

    if confidence < _LOW_CONFIDENCE_FLOOR:
        return ClassificationResult(
            classification="unknown",
            confidence=confidence,
            evidence=evidence,
            reason=(
                f"Weak {winner.replace('_', ' ')} signal — "
                "user review required"
            ),
        )

    reason = _build_reason(winner, evidence)
    return ClassificationResult(
        classification=winner,
        confidence=confidence,
        evidence=evidence,
        reason=reason,
    )


def _build_reason(label: str, evidence: tuple[EvidenceItem, ...]) -> str:
    pretty = label.replace("_", " ")
    if not evidence:
        return f"Matched {pretty} pattern"
    field_name = evidence[0].field
    return f"Matched {pretty} phrase in email {field_name}"


# ---------------------------------------------------------------------------
# Convenience: classify_metadata
# ---------------------------------------------------------------------------


_ALLOWED_METADATA_KEYS = frozenset(
    {"subject", "from", "snippet", "date", "message_id", "thread_id"}
)


def candidate_from_metadata(meta: dict[str, Any]) -> CandidateEmail:
    """Build a :class:`CandidateEmail` from a metadata dict.

    Accepts the shape produced by ``app.gmail_application_search`` /
    the search endpoint response. Unknown keys (e.g. ``body``, ``html``)
    are silently dropped so a caller cannot accidentally leak a full
    body into the classifier.
    """
    safe = {k: v for k, v in meta.items() if k in _ALLOWED_METADATA_KEYS}
    return CandidateEmail(
        subject=safe.get("subject"),
        from_=safe.get("from"),
        date=safe.get("date"),
        snippet=safe.get("snippet"),
        message_id=safe.get("message_id"),
        thread_id=safe.get("thread_id"),
    )


# Sanity check that the contract-pinned set above matches the precedence
# list. Catching a typo at import time is friendlier than diagnosing a
# test failure later.
assert set(CLASSIFIER_LABELS) == set(_PRECEDENCE), (
    "CLASSIFIER_LABELS and _PRECEDENCE drifted; update both."
)
assert set(LABEL_TO_EMAIL_LINK_STATUS) == set(CLASSIFIER_LABELS)
assert set(LABEL_TO_EMAIL_STATUS) == set(CLASSIFIER_LABELS)
assert set(LABEL_TO_APPLICATION_STATUS) == set(CLASSIFIER_LABELS)


# Defensive re-export so callers do not need to know the private regex
# helper exists.
__all__ = [
    "CLASSIFIER_LABELS",
    "CandidateEmail",
    "ClassificationResult",
    "EvidenceItem",
    "LABEL_TO_APPLICATION_STATUS",
    "LABEL_TO_EMAIL_LINK_STATUS",
    "LABEL_TO_EMAIL_STATUS",
    "candidate_from_metadata",
    "classify_candidate",
]
