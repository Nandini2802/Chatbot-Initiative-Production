"""
Which walkthrough does the user mean?

Hybrid resolution for "how to" questions:
  1. Candidates from the router's pick (LLM), the alias list below, and a
     typo-tolerant ("wildcard") match of the user's words against every
     walkthrough name and alias.
  2. Each candidate is checked against the user's feature keys.
  3. Decide:
       one accessible        -> show it
       several accessible    -> ask which one (only accessible options)
       none accessible       -> say the user has no access to it
       nothing matched       -> ask which feature

Deterministic: the same message and keys always give the same result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from rapidfuzz import fuzz


# Distinctive fragment of a walkthrough name -> what users call it.
# Multi-word aliases may match with small typos; single-word aliases must
# match exactly and only count when they point to one walkthrough.
FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    # Plain "DAR" questions mean the Daily Activity Report (create / view).
    "daily activity report": (
        "dar", "my dar", "dar report", "dar reports", "dar dashboard",
        "dar create", "dar view", "new dar", "create dar", "add dar", "log dar",
        "daily activity report", "daily activity", "activity report",
    ),
    # DAR Analytics only when the user explicitly asks for it.
    "dar analytics": (
        "dar analytics", "dar analytic", "dar stats", "dar statistics",
        "dar stories", "dar story",
    ),
    "unit details page": ("unit details", "unit detail", "unit page"),
    "add a unit to compare": ("compare units", "compare unit", "unit comparison", "comparison"),
    "create lead": ("create lead", "add lead", "new lead", "create a lead", "leads"),
    "opportunities": ("opportunity", "opportunities"),
    "sales order": ("sales order", "booking", "bookings", "book a unit"),
    "add or remove agent": ("add agent", "remove agent", "agents", "referral", "add referral"),
    "my profile": ("my profile",),
    "company profile": ("company profile", "agency profile"),
    "change password": ("change password", "reset password", "password"),
    "log out": ("log out", "logout", "sign out"),
    "bank details for projects": ("bank details", "bank account", "escrow account", "iban"),
    "download availability": ("download availability", "availability report", "availability"),
    "marketing materials": ("marketing materials", "marketing material", "marketing", "collateral"),
    "support ticket": ("support ticket", "raise a ticket", "raise ticket", "report an issue", "report issue"),
    "eoi": ("eoi", "expression of interest", "eoi request"),
    "how-to videos": ("how to videos", "training videos", "tutorial videos", "tutorials", "videos"),
    "3d tour": ("3d tour", "virtual tour", "3d"),
    "download project brochure": ("project brochure", "download brochure", "brochure"),
    "share project": ("share project", "share unit", "share"),
    "download sales offer": ("download sales offer", "sales offer", "generate sales offer"),
}

# Walkthroughs answered by another one (none at the moment: Daily Activity
# Report and DAR Analytics are separate walkthroughs).
FEATURE_REDIRECTS: dict[str, str] = {}

# Walkthroughs that are only chosen when the user explicitly asks for them.
# feature -> (walkthrough used otherwise, words that make the ask explicit).
# A router pick of DAR Analytics for a plain "DAR" question becomes the
# Daily Activity Report; the user's own "analytics" wording wins over the
# router picking the Daily Activity Report.
EXPLICIT_ONLY: dict[str, tuple[str, frozenset[str]]] = {
    "dar analytics": (
        "daily activity report",
        frozenset({"analytics", "analytic", "stats", "statistics", "stories", "story"}),
    ),
}

# Words that never identify a feature on their own.
FILLER_WORDS = {
    "how", "to", "do", "does", "i", "we", "you", "can", "could", "use", "using",
    "the", "a", "an", "in", "on", "for", "of", "my", "me", "is", "it", "app",
    "feature", "please", "tell", "about", "what", "where", "find", "open",
    "access", "show", "help", "with", "guide", "steps", "step", "work", "works",
    "danube", "one", "and", "or", "page", "view", "see", "get",
}

FUZZY_THRESHOLD = 88
MIN_FUZZY_PHRASE_LENGTH = 5
MAX_OPTIONS = 5


def _clean(text) -> str:
    text = str(text or "").replace("�", " ").casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def display_name(name: str) -> str:
    """Walkthrough name as shown to users (fixes the Excel's broken dash)."""
    return str(name or "").replace("�", "–").strip()


def _find_name(fragment: str, names: list[str]) -> str | None:
    key = _clean(fragment)
    matches = [name for name in names if key in _clean(name)]
    return matches[0] if len(matches) == 1 else None


def redirect(name: str | None, names: list[str]) -> str | None:
    """Apply FEATURE_REDIRECTS; returns a real walkthrough name or None."""
    if not name:
        return None

    clean = _clean(name)
    exact = next((n for n in names if _clean(n) == clean), None)

    if exact is None:
        return None

    for source, target in FEATURE_REDIRECTS.items():
        if _clean(source) == clean:
            return _find_name(target, names) or exact

    return exact


def _phrases(names: list[str]) -> list[tuple[str, str]]:
    """(phrase, walkthrough name) for every alias and name part."""
    pairs: list[tuple[str, str]] = []

    for fragment, aliases in FEATURE_ALIASES.items():
        name = _find_name(fragment, names)
        if name:
            pairs.extend((_clean(alias), name) for alias in aliases)

    for name in names:
        pairs.append((_clean(name), name))
        # "3D Tour / Virtual Tour", "Support Ticket (Report an Issue)"
        for part in re.split(r"[/()]", name):
            part = _clean(part)
            if len(part.split()) >= 2:
                pairs.append((part, name))

    return pairs


def _match_span(phrase: str, words: list[str]) -> tuple[int, int] | None:
    """(start, end) word positions where the phrase matches, or None."""
    size = len(phrase.split())

    if size == 0 or size > len(words):
        return None

    windows = [
        (i, " ".join(words[i:i + size]))
        for i in range(len(words) - size + 1)
    ]

    for i, window in windows:
        if window == phrase:
            return i, i + size

    if len(phrase.replace(" ", "")) < MIN_FUZZY_PHRASE_LENGTH:
        return None

    for i, window in windows:
        if fuzz.ratio(phrase, window) >= FUZZY_THRESHOLD:
            return i, i + size

    return None


def _matches(phrase: str, words: list[str]) -> bool:
    return _match_span(phrase, words) is not None


def _apply_explicit_only(
    router: str | None,
    strong: list[str],
    words: list[str],
    names: list[str],
) -> str | None:
    """Keep explicit-only walkthroughs (DAR Analytics) for explicit asks."""
    for source_fragment, (fallback_fragment, trigger_words) in EXPLICIT_ONLY.items():
        source = _find_name(source_fragment, names)
        fallback = _find_name(fallback_fragment, names)

        if not source or not fallback:
            continue

        explicit = source in strong or any(w in trigger_words for w in words)

        if router == source and not explicit:
            return fallback
        if router == fallback and source in strong:
            return source

    return router


def find_walkthrough_candidates(
    message: str | None,
    router_feature: str | None,
    names: Iterable[str],
) -> list[str]:
    """Walkthrough names the user may mean, most likely first."""

    names = list(names)
    words = _clean(message).split()
    router = redirect(router_feature, names)

    strong: list[str] = []
    single_word_targets: dict[str, set[str]] = {}

    pairs = _phrases(names)
    for phrase, name in pairs:
        if len(phrase.split()) == 1:
            single_word_targets.setdefault(phrase, set()).add(redirect(name, names) or name)

    matched: list[tuple[str, str, tuple[int, int]]] = []

    for phrase, name in pairs:
        target = redirect(name, names) or name
        if len(phrase.split()) == 1 and len(single_word_targets.get(phrase, ())) > 1:
            continue
        span = _match_span(phrase, words)
        if span:
            matched.append((phrase, target, span))

    explicit_targets = {
        _find_name(fragment, names) for fragment in EXPLICIT_ONLY
    }

    def priority(item):
        phrase, target, _ = item
        return len(phrase.split()), target in explicit_targets

    def overlaps(a, b):
        return a[0] < b[1] and b[0] < a[1]

    for item in matched:
        phrase, target, span = item
        # Overlapping words that point to different walkthroughs: the longer
        # phrase wins ("dar analytics" over "dar"); on a tie an explicit-only
        # walkthrough wins ("dar stats" over "my dar").
        if any(
            other[1] != target
            and overlaps(span, other[2])
            and priority(other) > priority(item)
            for other in matched
        ):
            continue
        if target not in strong:
            strong.append(target)

    router = _apply_explicit_only(router, strong, words, names)

    candidates: list[str] = []

    if router:
        candidates.append(router)

    if strong:
        candidates.extend(name for name in strong if name not in candidates)
        return candidates

    # Only generic words matched: every walkthrough sharing such a word.
    meaningful = [w for w in words if w not in FILLER_WORDS and len(w) >= 4]
    weak = []
    for name in names:
        name_words = set(_clean(name).split())
        if any(word in name_words for word in meaningful):
            target = redirect(name, names) or name
            if target not in weak:
                weak.append(target)

    if router and len(weak) > 1 and router in weak:
        return weak
    if router:
        return candidates
    return weak


@dataclass
class WalkthroughDecision:
    kind: str                      # "show" | "ask" | "denied" | "none"
    feature: str | None = None
    options: list[str] = field(default_factory=list)
    message: str | None = None


def _join(items: list[str], word: str) -> str:
    items = [display_name(i) for i in items]
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" {word} " + items[-1]


def decide_walkthrough(
    candidates: list[str],
    is_allowed: Callable[[str], bool],
) -> WalkthroughDecision:
    """Pick the walkthrough using the user's access."""

    if not candidates:
        return WalkthroughDecision(
            "none",
            message="Which Danube One feature would you like help with?",
        )

    accessible = [name for name in candidates if is_allowed(name)]

    if len(accessible) == 1:
        return WalkthroughDecision("show", feature=accessible[0])

    if len(accessible) > 1:
        options = accessible[:MAX_OPTIONS]
        return WalkthroughDecision(
            "ask",
            options=options,
            message=f"Which one do you need help with: {_join(options, 'or')}?",
        )

    denied = candidates[:2]
    return WalkthroughDecision(
        "denied",
        feature=candidates[0],
        options=denied,
        message=(
            f"You don't currently have access to {_join(denied, 'or')} "
            "in your account."
        ),
    )
