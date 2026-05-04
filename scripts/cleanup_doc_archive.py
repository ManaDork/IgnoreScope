"""Cleanup doc archive — migrate shipped/superseded docs into _archive/done/ subdirs.

Driven by an explicit MOVES manifest. Rewrites backtick-wrapped path references
across all *.md and *.json files under planning/, _workbench/, docs/, plus root
CLAUDE.md / README.md / USAGE.md. Used by Phase B of the IgnoreScope cleanup
(refactor/project-cleanup branch).

Usage:
    python scripts/cleanup_doc_archive.py --phase B.2 --dry-run
    python scripts/cleanup_doc_archive.py --phase B.2 --apply
    python scripts/cleanup_doc_archive.py --phase B.4 --apply
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Force-tracked planning files (per `git ls-files planning/` Phase 1 inventory).
# Anything not in this set under planning/ or _workbench/ is gitignored.
TRACKED_PATHS: set[str] = {
    "planning/backlog/fusion-custom-title-bar.md",
    "planning/features/config-panel-collapse-fix/scope.md",
    "planning/features/config-panel-collapse-fix/spec.md",
    "planning/features/config-panel-collapse-fix/technical-design.md",
    "planning/tasks/unify-l4-task-1-1-owner-field.md",
    "planning/tasks/unify-l4-task-1-5-delete-collect-isolation.md",
    "planning/tasks/virtual-mount-phase-3.md",
}

# Phase B.2 — planning/ doc archive moves
B2_MOVES: list[tuple[str, str]] = [
    # 24 unify-l4-task-* -> planning/tasks/done/
    ("planning/tasks/unify-l4-task-1-1-owner-field.md", "planning/tasks/done/unify-l4-task-1-1-owner-field.md"),
    ("planning/tasks/unify-l4-task-1-3-hierarchy-extensions.md", "planning/tasks/done/unify-l4-task-1-3-hierarchy-extensions.md"),
    ("planning/tasks/unify-l4-task-1-4-volume-naming.md", "planning/tasks/done/unify-l4-task-1-4-volume-naming.md"),
    ("planning/tasks/unify-l4-task-1-5-delete-collect-isolation.md", "planning/tasks/done/unify-l4-task-1-5-delete-collect-isolation.md"),
    ("planning/tasks/unify-l4-task-1-6-compose-signature-collapse.md", "planning/tasks/done/unify-l4-task-1-6-compose-signature-collapse.md"),
    ("planning/tasks/unify-l4-task-1-7-claude-auth-removal.md", "planning/tasks/done/unify-l4-task-1-7-claude-auth-removal.md"),
    ("planning/tasks/unify-l4-task-1-8-orphan-diff.md", "planning/tasks/done/unify-l4-task-1-8-orphan-diff.md"),
    ("planning/tasks/unify-l4-task-1-9-gui-synth-retirement.md", "planning/tasks/done/unify-l4-task-1-9-gui-synth-retirement.md"),
    ("planning/tasks/unify-l4-task-1-10-rmb-guard-rekey.md", "planning/tasks/done/unify-l4-task-1-10-rmb-guard-rekey.md"),
    ("planning/tasks/unify-l4-task-1-11-set-extensions-retire.md", "planning/tasks/done/unify-l4-task-1-11-set-extensions-retire.md"),
    ("planning/tasks/unify-l4-task-1-12-test-integration-fixtures.md", "planning/tasks/done/unify-l4-task-1-12-test-integration-fixtures.md"),
    ("planning/tasks/unify-l4-task-1-13-no-iso-claude-auth.md", "planning/tasks/done/unify-l4-task-1-13-no-iso-claude-auth.md"),
    ("planning/tasks/unify-l4-task-1-14-doc-update.md", "planning/tasks/done/unify-l4-task-1-14-doc-update.md"),
    ("planning/tasks/unify-l4-task-1-15-retire-backlog.md", "planning/tasks/done/unify-l4-task-1-15-retire-backlog.md"),
    ("planning/tasks/unify-l4-task-2-1-isolation-compound-glossary.md", "planning/tasks/done/unify-l4-task-2-1-isolation-compound-glossary.md"),
    ("planning/tasks/unify-l4-task-2-2-isolation-audit.md", "planning/tasks/done/unify-l4-task-2-2-isolation-audit.md"),
    ("planning/tasks/unify-l4-task-2-5-test-config-fixture-cleanup.md", "planning/tasks/done/unify-l4-task-2-5-test-config-fixture-cleanup.md"),
    ("planning/tasks/unify-l4-task-2-6-test-zone-cleanup.md", "planning/tasks/done/unify-l4-task-2-6-test-zone-cleanup.md"),
    ("planning/tasks/unify-l4-task-2-7-blueprint-polish.md", "planning/tasks/done/unify-l4-task-2-7-blueprint-polish.md"),
    ("planning/tasks/unify-l4-task-3-1-scope-header-signals-dataclass.md", "planning/tasks/done/unify-l4-task-3-1-scope-header-signals-dataclass.md"),
    ("planning/tasks/unify-l4-task-3-2-wire-container-running.md", "planning/tasks/done/unify-l4-task-3-2-wire-container-running.md"),
    ("planning/tasks/unify-l4-task-3-3-3-4-scope-header-render.md", "planning/tasks/done/unify-l4-task-3-3-3-4-scope-header-render.md"),
    ("planning/tasks/unify-l4-task-3-5-retire-delivery-tint.md", "planning/tasks/done/unify-l4-task-3-5-retire-delivery-tint.md"),
    ("planning/tasks/unify-l4-task-3-6-3-7-3-8-3-9-doc-closure.md", "planning/tasks/done/unify-l4-task-3-6-3-7-3-8-3-9-doc-closure.md"),

    # 4 virtual-mount-phase-* -> planning/tasks/done/
    ("planning/tasks/virtual-mount-phase-1.md", "planning/tasks/done/virtual-mount-phase-1.md"),
    ("planning/tasks/virtual-mount-phase-2.md", "planning/tasks/done/virtual-mount-phase-2.md"),
    ("planning/tasks/virtual-mount-phase-3.md", "planning/tasks/done/virtual-mount-phase-3.md"),
    ("planning/tasks/virtual-mount-phase-3-deferred.md", "planning/tasks/done/virtual-mount-phase-3-deferred.md"),

    # 8 shipped feature dirs -> planning/features/_archive/
    ("planning/features/config-panel-collapse-fix/", "planning/features/_archive/config-panel-collapse-fix/"),
    ("planning/features/consolidated-theme-file/", "planning/features/_archive/consolidated-theme-file/"),
    ("planning/features/fix-highlight-node/", "planning/features/_archive/fix-highlight-node/"),
    ("planning/features/house-cleaning/", "planning/features/_archive/house-cleaning/"),
    ("planning/features/menu-reorganization-extensions-framework/", "planning/features/_archive/menu-reorganization-extensions-framework/"),
    ("planning/features/nodedstate-mask-reveal-exclusivity/", "planning/features/_archive/nodedstate-mask-reveal-exclusivity/"),
    ("planning/features/undo-redo-session-history/", "planning/features/_archive/undo-redo-session-history/"),
    ("planning/features/unify-l4-reclaim-isolation-term/", "planning/features/_archive/unify-l4-reclaim-isolation-term/"),

    # Isolation pre-pivot bundle -> _archive/
    ("planning/tasks/isolation-container-mode-phase-1.md", "planning/tasks/_archive/isolation-container-mode-phase-1.md"),
    ("planning/features/isolation-container-mode/", "planning/features/_archive/isolation-container-mode/"),
    ("planning/backlog/isolation-container-mode-archive.md", "planning/backlog/_archive/isolation-container-mode-archive.md"),
    ("planning/backlog/isolation-empty-mount-specs-cue.md", "planning/backlog/_archive/isolation-empty-mount-specs-cue.md"),
    ("planning/backlog/isolation-symlink-skip-cue.md", "planning/backlog/_archive/isolation-symlink-skip-cue.md"),

    # Done backlog item
    ("planning/backlog/unify-l4-reclaim-isolation-term.md", "planning/backlog/done/unify-l4-reclaim-isolation-term.md"),
]

# Phase B.2 — explicit deletes (per audit Wave 1D — phases never started)
B2_DELETES: list[str] = [
    "planning/tasks/isolation-container-mode-phase-2.md",
    "planning/tasks/isolation-container-mode-phase-3.md",
]

# Phase B.4 — workbench archive moves (filesystem-only, gitignored)
B4_MOVES: list[tuple[str, str]] = [
    ("_workbench/_bugs/config-panel-collapse-expand-cycle.md", "_workbench/_bugs/_archive/config-panel-collapse-expand-cycle.md"),
    ("_workbench/_bugs/header-rmb-undo-redo.md", "_workbench/_bugs/_archive/header-rmb-undo-redo.md"),
    ("_workbench/_bugs/inconsistent_mask_reveal_recursion.md", "_workbench/_bugs/_archive/inconsistent_mask_reveal_recursion.md"),
    ("_workbench/_bugs/integration-test-docker-name-mismatch.md", "_workbench/_bugs/_archive/integration-test-docker-name-mismatch.md"),
    ("_workbench/_bugs/localhostview-header-rmb-silent-noop.md", "_workbench/_bugs/_archive/localhostview-header-rmb-silent-noop.md"),
    ("_workbench/_bugs/scroll-bar-bg-color.md", "_workbench/_bugs/_archive/scroll-bar-bg-color.md"),
    ("_workbench/_evaluations/wave_review/", "_workbench/_evaluations/_archive/wave_review/"),
    ("_workbench/_feedback/zev-feedback-2026-04-03-postmortem-skill-monitoring.md", "_workbench/_feedback/_archive/zev-feedback-2026-04-03-postmortem-skill-monitoring.md"),
]

PHASES: dict[str, tuple[list[tuple[str, str]], list[str]]] = {
    "B.2": (B2_MOVES, B2_DELETES),
    "B.4": (B4_MOVES, []),
}

# Backtick-wrapped ref pattern. Matches both file refs (`.md`/`.json`) and dir refs (trailing `/`).
REF_PATTERN = re.compile(r"`((?:planning|_workbench)/[^`]+(?:\.(?:md|json)|/))`")

SCAN_EXTS = {".md", ".json"}
SCAN_ROOTS = ["planning", "_workbench", "docs"]
SCAN_ROOT_FILES = ["CLAUDE.md", "README.md", "USAGE.md"]


def expand_moves(moves: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Expand directory moves (trailing /) to per-file moves."""
    expanded: list[tuple[str, str]] = []
    for src, dst in moves:
        if src.endswith("/"):
            src_path = PROJECT_ROOT / src
            if not src_path.is_dir():
                print(f"  WARN: dir not found: {src}")
                continue
            for sub in sorted(src_path.rglob("*")):
                if sub.is_file():
                    rel = sub.relative_to(src_path).as_posix()
                    expanded.append((f"{src}{rel}", f"{dst}{rel}"))
        else:
            expanded.append((src, dst))
    return expanded


def build_rewrite_map(moves: list[tuple[str, str]], expanded: list[tuple[str, str]]) -> dict[str, str]:
    """Rewrite map covers both per-file refs and dir-level refs (with and without trailing /)."""
    rmap: dict[str, str] = dict(expanded)
    for src, dst in moves:
        if src.endswith("/"):
            rmap[src] = dst
            rmap[src.rstrip("/")] = dst.rstrip("/")
    return rmap


def is_tracked(rel: str) -> bool:
    return rel in TRACKED_PATHS


def do_move(src: str, dst: str, apply: bool) -> bool:
    src_path = PROJECT_ROOT / src
    dst_path = PROJECT_ROOT / dst
    if not src_path.exists():
        print(f"  SKIP (missing): {src}")
        return False
    if dst_path.exists():
        print(f"  SKIP (target exists): {dst}")
        return False
    marker = "git" if is_tracked(src) else "fs"
    if apply:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if is_tracked(src):
            result = subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "mv", src, dst],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"  ERROR (git mv): {src} -> {dst}: {result.stderr.strip()}")
                return False
        else:
            src_path.rename(dst_path)
        print(f"  MOVE ({marker}): {src} -> {dst}")
    else:
        print(f"  PLAN ({marker}): {src} -> {dst}")
    return True


def do_delete(src: str, apply: bool) -> bool:
    src_path = PROJECT_ROOT / src
    if not src_path.exists():
        print(f"  SKIP (missing): {src}")
        return False
    marker = "git" if is_tracked(src) else "fs"
    if apply:
        if is_tracked(src):
            result = subprocess.run(
                ["git", "-C", str(PROJECT_ROOT), "rm", src],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"  ERROR (git rm): {src}: {result.stderr.strip()}")
                return False
        else:
            src_path.unlink()
        print(f"  DELETE ({marker}): {src}")
    else:
        print(f"  PLAN-DELETE ({marker}): {src}")
    return True


def cleanup_empty_dirs(moves: list[tuple[str, str]]) -> None:
    """Remove source directories that are now empty after their files moved."""
    for src, _ in moves:
        if src.endswith("/"):
            src_path = PROJECT_ROOT / src
            if src_path.is_dir() and not any(src_path.iterdir()):
                src_path.rmdir()
                print(f"  CLEAN: removed empty dir {src}")


def find_scan_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        root_path = PROJECT_ROOT / root
        if root_path.is_dir():
            for ext in SCAN_EXTS:
                files.extend(root_path.rglob(f"*{ext}"))
    for fname in SCAN_ROOT_FILES:
        p = PROJECT_ROOT / fname
        if p.is_file():
            files.append(p)
    return files


def rewrite_refs_in_file(path: Path, rmap: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    text = path.read_text(encoding="utf-8")
    rewrites: list[tuple[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        old = match.group(1)
        if old in rmap:
            new = rmap[old]
            rewrites.append((old, new))
            return f"`{new}`"
        return match.group(0)

    new_text = REF_PATTERN.sub(repl, text)
    return new_text, rewrites


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--phase", choices=list(PHASES.keys()), required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    moves, deletes = PHASES[args.phase]
    apply = args.apply

    print(f"Phase {args.phase} — {'APPLY' if apply else 'DRY-RUN'}")
    print(f"Project root: {PROJECT_ROOT}")
    print()

    expanded = expand_moves(moves)
    rmap = build_rewrite_map(moves, expanded)

    print("=== Move plan ===")
    move_count = 0
    for src, dst in expanded:
        if do_move(src, dst, apply):
            move_count += 1
    print(f"  Total moves: {move_count}")
    print()

    if deletes:
        print("=== Delete plan ===")
        delete_count = 0
        for src in deletes:
            if do_delete(src, apply):
                delete_count += 1
        print(f"  Total deletes: {delete_count}")
        print()

    if apply:
        cleanup_empty_dirs(moves)
        print()

    print("=== Ref rewrite plan ===")
    scan_files = find_scan_files()
    rewrite_count = 0
    file_rewrite_count = 0
    for fpath in scan_files:
        new_text, rewrites = rewrite_refs_in_file(fpath, rmap)
        if rewrites:
            rel = fpath.relative_to(PROJECT_ROOT).as_posix()
            print(f"  {rel}: {len(rewrites)} refs")
            for old, new in rewrites:
                print(f"    `{old}` -> `{new}`")
            if apply:
                fpath.write_text(new_text, encoding="utf-8")
            rewrite_count += len(rewrites)
            file_rewrite_count += 1
    print(f"  Total: {rewrite_count} refs across {file_rewrite_count} files")
    print()

    print("Done." if apply else "Dry-run complete. Re-run with --apply to execute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
