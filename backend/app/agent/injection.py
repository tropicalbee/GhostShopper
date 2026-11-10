"""Instructions aimed at AI agents, found in text a shopper reads. Pure and deterministic: no browser, no LLM.

A page can carry text meant for an agent instead of a customer: "ignore your instructions", "use coupon X",
"enter the customer's email at ...". This module only finds such text, from a small explicit pattern list, so the
run can show it as evidence. What the agent may do is decided by the guards in loop.py and browser.py, not here.
The result never changes the readiness score.
"""

import re
from dataclasses import dataclass
from typing import Iterable

EXCERPT_CHARS = 200
CONTEXT_CHARS = 60  # kept before the match

PATTERNS: dict[str, re.Pattern[str]] = {
    "ignore_instructions": re.compile(
        r"\bignore\s+(?:(?:all|any|your)\s+(?:(?:previous|prior|earlier|above)\s+)?|(?:previous|prior|earlier|above)\s+)"
        r"instructions\b", re.I),
    "addresses_an_ai": re.compile(
        r"\byou\s+are\s+an?\s+(?:ai|llm|language\s+model)\b|\bas\s+an\s+ai\b"
        r"|\bai\s+(?:shopping\s+)?(?:agents?|assistants?)\s*(?::|must\b|should\b|need\s+to\b)", re.I),
    "system_prompt": re.compile(r"\b(?:system|developer)\s+prompt\b", re.I),
    "install_skill": re.compile(r"\bSKILL\.md\b|\binstall\b[^.\n]{0,40}\b(?:skill|plugin|extension)\b", re.I),
    "send_customer_data": re.compile(
        r"\b(?:send|enter|give|share|reveal)\s+(?:the\s+)?(?:buyer|user|customer)(?:'s|’s)", re.I),
}


@dataclass(frozen=True)
class Segment:
    """A piece of text from a page or file: where it came from, and whether a person looking at it would see it."""

    text: str
    where: str
    hidden: bool


@dataclass(frozen=True)
class Hit:
    pattern: str
    where: str
    excerpt: str
    hidden: bool


def _excerpt(text: str, start: int) -> str:
    return " ".join(text[max(0, start - CONTEXT_CHARS):][:EXCERPT_CHARS].split())


def find_instructions(segments: Iterable[Segment]) -> list[Hit]:
    """The instructions in the segments, one hit per stretch of text: a sentence that matches several patterns is
    reported once, under the pattern that appears first. Hidden segments are read first, so a text that is both
    hidden and part of the page's visible text is reported as hidden."""
    hits: list[Hit] = []
    seen: set[str] = set()
    for segment in sorted(segments, key=lambda s: not s.hidden):
        matches = sorted((m.start(), name, " ".join(m.group(0).lower().split()))
                         for name, pattern in PATTERNS.items() for m in pattern.finditer(segment.text))
        shown_until = 0
        for start, name, matched in matches:
            repeated = matched in seen
            seen.add(matched)
            if start < shown_until or repeated:
                continue
            shown_until = max(0, start - CONTEXT_CHARS) + EXCERPT_CHARS
            hits.append(Hit(name, segment.where, _excerpt(segment.text, start), segment.hidden))
    return hits
