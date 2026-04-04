"""Case conflict detection for gitignore-style patterns.

Detects patterns that conflict only due to case differences, which matters
on case-insensitive filesystems (Windows). For example, 'Config/' and
'config/' would match the same directories on Windows.

Ported from: E:/SANS/SansMachinatia/_workbench/archive/IgnoreScope/utils/case_conflict.py
"""

from __future__ import annotations


def normalize_pattern_for_comparison(pattern: str) -> str:
    """Normalize pattern for case comparison.

    Strips negation prefix and converts to lowercase.
    """
    p = pattern.lstrip("!")
    return p.lower()


def find_case_conflicts(patterns: list[str]) -> list[tuple[int, int, str]]:
    """Find patterns that conflict only due to case differences.

    Detects patterns like 'Config/' vs 'config/' that would match the
    same paths on case-insensitive filesystems (Windows).

    Returns:
        List of (index1, index2, reason) tuples.
    """
    conflicts = []
    seen_normalized: dict[str, int] = {}

    for i, pattern in enumerate(patterns):
        normalized = normalize_pattern_for_comparison(pattern)

        if normalized in seen_normalized:
            first_idx = seen_normalized[normalized]
            if patterns[first_idx] != pattern:
                conflicts.append((
                    first_idx,
                    i,
                    f"Case conflict: '{patterns[first_idx]}' vs '{pattern}'",
                ))
        else:
            seen_normalized[normalized] = i

    return conflicts


def get_conflicting_indices(patterns: list[str]) -> set[int]:
    """Get set of all pattern indices involved in case conflicts.

    Convenience function for UI highlighting.
    """
    conflicts = find_case_conflicts(patterns)
    indices = set()
    for idx1, idx2, _ in conflicts:
        indices.add(idx1)
        indices.add(idx2)
    return indices
