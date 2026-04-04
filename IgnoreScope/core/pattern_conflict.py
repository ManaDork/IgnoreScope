"""Pattern ordering conflict detection for gitignore-style patterns.

Detects when exception patterns (!) appear BEFORE the deny patterns they
should override. In gitignore semantics, later patterns win — so an exception
must come AFTER its corresponding deny pattern to be effective.

Ported from: E:/SANS/SansMachinatia/_workbench/archive/IgnoreScope/utils/pattern_conflict.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PatternConflict:
    """Represents a pattern ordering conflict."""

    exception_idx: int
    exception_pattern: str
    deny_idx: int
    deny_pattern: str
    severity: str  # 'high', 'medium', 'low'
    description: str

    def __str__(self) -> str:
        return (
            f"Line {self.exception_idx + 1}: '{self.exception_pattern}' "
            f"overridden by line {self.deny_idx + 1}: '{self.deny_pattern}'"
        )


def _pattern_to_regex(pattern: str) -> str:
    """Convert gitignore pattern to regex for overlap detection.

    Handles: ** (any path segments), * (non-slash), ? (single char), trailing /
    """
    p = pattern.lstrip("!")
    p = re.escape(p)
    p = p.replace(r"\*\*/", ".*")
    p = p.replace(r"\*\*", ".*")
    p = p.replace(r"\*", "[^/]*")
    p = p.replace(r"\?", ".")
    if p.endswith("/"):
        p = p.rstrip("/") + "(/.*)?"
    return p


def _patterns_could_overlap(pattern1: str, pattern2: str) -> bool:
    """Check if two patterns could match overlapping paths.

    Uses case-insensitive comparison for Windows compatibility.
    """
    p1 = pattern1.lstrip("!").lower()
    p2 = pattern2.lstrip("!").lower()

    if p1 == p2:
        return True

    if p1.startswith(p2.rstrip("/")) or p2.startswith(p1.rstrip("/")):
        return True

    p1_base = p1.replace("**/", "").replace("/**", "").rstrip("/")
    p2_base = p2.replace("**/", "").replace("/**", "").rstrip("/")
    if p1_base == p2_base:
        return True

    try:
        regex1 = _pattern_to_regex(pattern1)
        regex2 = _pattern_to_regex(pattern2)
        p1_literal = p1.replace("*", "x").replace("?", "x")
        p2_literal = p2.replace("*", "x").replace("?", "x")
        if re.match(regex1, p2_literal, re.IGNORECASE):
            return True
        if re.match(regex2, p1_literal, re.IGNORECASE):
            return True
    except re.error:
        pass

    return False


def find_ordering_conflicts(patterns: list[str]) -> list[PatternConflict]:
    """Find exception patterns that are overridden by later deny patterns.

    In gitignore, later patterns win. An exception pattern like '!Config/'
    is ineffective if a deny pattern like '**/config/**' appears after it.

    Args:
        patterns: List of gitignore-style patterns in order.

    Returns:
        List of PatternConflict objects describing each conflict.
    """
    conflicts = []
    exceptions = [(i, p) for i, p in enumerate(patterns) if p.startswith("!")]

    for exc_idx, exc_pattern in exceptions:
        for deny_idx in range(exc_idx + 1, len(patterns)):
            deny_pattern = patterns[deny_idx]
            if deny_pattern.startswith("!"):
                continue

            if _patterns_could_overlap(exc_pattern, deny_pattern):
                exc_specificity = exc_pattern.count("/") + exc_pattern.count("*")
                deny_specificity = deny_pattern.count("/") + deny_pattern.count("*")

                if "**" in deny_pattern and "**" not in exc_pattern:
                    severity = "high"
                elif exc_specificity < deny_specificity:
                    severity = "medium"
                else:
                    severity = "low"

                conflicts.append(
                    PatternConflict(
                        exception_idx=exc_idx,
                        exception_pattern=exc_pattern,
                        deny_idx=deny_idx,
                        deny_pattern=deny_pattern,
                        severity=severity,
                        description=(
                            f"Exception '{exc_pattern}' (line {exc_idx + 1}) may be "
                            f"overridden by '{deny_pattern}' (line {deny_idx + 1})"
                        ),
                    )
                )

    return conflicts


def get_ineffective_exception_indices(patterns: list[str]) -> set[int]:
    """Get indices of exception patterns that may be ineffective.

    Convenience function for UI highlighting.
    """
    conflicts = find_ordering_conflicts(patterns)
    return {c.exception_idx for c in conflicts}


def get_conflict_summary(patterns: list[str]) -> str:
    """Get a summary message about ordering conflicts.

    Returns human-readable summary, or empty string if no conflicts.
    """
    conflicts = find_ordering_conflicts(patterns)
    if not conflicts:
        return ""

    high_count = sum(1 for c in conflicts if c.severity == "high")

    if len(conflicts) == 1:
        return str(conflicts[0])

    msg = f"{len(conflicts)} pattern ordering conflicts"
    if high_count:
        msg += f" ({high_count} high severity)"
    return msg


def format_conflict_report(patterns: list[str]) -> str:
    """Generate a detailed report of all ordering conflicts."""
    conflicts = find_ordering_conflicts(patterns)

    if not conflicts:
        return (
            "No pattern ordering conflicts detected.\n\n"
            "All exception patterns appear after their corresponding deny patterns."
        )

    lines = [
        f"Found {len(conflicts)} pattern ordering conflict(s):",
        "",
        "In gitignore, later patterns override earlier ones.",
        "Exception patterns (!) must come AFTER the deny patterns they override.",
        "",
        "=" * 60,
    ]

    by_severity: dict[str, list[PatternConflict]] = {
        "high": [],
        "medium": [],
        "low": [],
    }
    for c in conflicts:
        by_severity[c.severity].append(c)

    for severity in ["high", "medium", "low"]:
        if by_severity[severity]:
            lines.append(f"\n{severity.upper()} SEVERITY:")
            lines.append("-" * 40)
            for c in by_severity[severity]:
                lines.append(f"\n  Line {c.exception_idx + 1}: {c.exception_pattern}")
                lines.append(
                    f"    -> Overridden by line {c.deny_idx + 1}: {c.deny_pattern}"
                )
                lines.append(f"    Fix: Move exception after line {c.deny_idx + 1}")

    lines.append("\n" + "=" * 60)
    lines.append(
        "\nTo fix: Move exception patterns AFTER the deny patterns they override."
    )

    return "\n".join(lines)
