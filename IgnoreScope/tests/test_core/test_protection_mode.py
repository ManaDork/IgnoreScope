"""Tests for the protection_mode feature.

protection_mode (default True) force-hides the `.ignore_scope/` config
directory (and everything beneath it) at EVERY mirrored root — the primary
project root plus each sibling root — and suppresses any user `!` reveal that
would re-expose content beneath it. The protection is absolute: a deliberate
reveal carve-out cannot win against the force-hide.

Two surfaces under test:
  - core/config.py     — ScopeDockerConfig.protection_mode serialization
  - core/hierarchy.py  — compute_container_hierarchy(protection_mode=...) masking

Core tests only — tmp_path, NO Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from IgnoreScope.core.config import ScopeDockerConfig, IGSC_DIR_NAME
from IgnoreScope.core.hierarchy import compute_container_hierarchy
from IgnoreScope.core.mount_spec_path import MountSpecPath


def _make_mount_specs(
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
) -> list[MountSpecPath]:
    """Convert old-style flat sets to mount_specs list (mirrors test_hierarchy)."""
    specs = []
    for mount_root in sorted(mounts or set()):
        patterns = []
        for m in sorted(masked or set()):
            try:
                rel = str(m.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"{rel}/")
            except ValueError:
                pass
        for r in sorted(revealed or set()):
            try:
                rel = str(r.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"!{rel}/")
            except ValueError:
                pass
        specs.append(MountSpecPath(mount_root=mount_root, patterns=patterns))
    return specs


def _make_sibling(
    host_path: Path,
    container_path: str,
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
    pushed_files: set[Path] | None = None,
):
    """Build SiblingMount from old-style set kwargs (mirrors test_hierarchy)."""
    from IgnoreScope.core.config import SiblingMount

    mount_specs = []
    for mount_root in sorted(mounts or set()):
        patterns = []
        for m in sorted(masked or set()):
            try:
                rel = str(m.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"{rel}/")
            except ValueError:
                pass
        for r in sorted(revealed or set()):
            try:
                rel = str(r.relative_to(mount_root)).replace("\\", "/")
                patterns.append(f"!{rel}/")
            except ValueError:
                pass
        mount_specs.append(MountSpecPath(mount_root=mount_root, patterns=patterns))
    return SiblingMount(
        host_path=host_path,
        container_path=container_path,
        mount_specs=mount_specs,
        pushed_files=pushed_files or set(),
    )


def _make_scope_config(
    host_project_root: Path,
    mounts: set[Path] | None = None,
    masked: set[Path] | None = None,
    revealed: set[Path] | None = None,
    pushed_files: set[Path] | None = None,
    **kwargs,
) -> ScopeDockerConfig:
    """Build ScopeDockerConfig from old-style set kwargs (mirrors test_config)."""
    mount_specs = _make_mount_specs(mounts, masked, revealed)
    return ScopeDockerConfig(
        mount_specs=mount_specs,
        pushed_files=pushed_files or set(),
        host_project_root=host_project_root,
        **kwargs,
    )


class TestProtectionMode:
    """Acceptance criteria for the protection_mode feature (AC1-AC7)."""

    # --- AC1: protection masks .ignore_scope at the primary root ---

    def test_ac1_protection_masks_ignore_scope(self, tmp_path: Path):
        """protection_mode=True with mount={project_root} ⇒ the `.ignore_scope`
        container path is force-hidden (in masked_paths, NOT in visible_paths).
        """
        igsc = tmp_path / IGSC_DIR_NAME

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            protection_mode=True,
        )

        igsc_cpath = "/workspace/" + IGSC_DIR_NAME
        assert igsc_cpath in hierarchy.masked_paths, (
            f"{igsc_cpath} must be force-hidden; masked={hierarchy.masked_paths}"
        )
        assert igsc_cpath not in hierarchy.visible_paths, (
            f"{igsc_cpath} must NOT be visible; visible={hierarchy.visible_paths}"
        )

    # --- AC2: no-leak round-trip — protection never leaks into patterns ---

    def test_ac2_no_leak_round_trip(self, tmp_path: Path):
        """to_dict serializes protection_mode as a top-level boolean only — the
        injected `.ignore_scope` hide must NEVER appear in any mount_spec
        pattern. from_dict restores the boolean.
        """
        config = _make_scope_config(
            host_project_root=tmp_path,
            mounts={tmp_path / "src"},
            masked={tmp_path / "src" / "api"},
            scope_name="leak-check",
            protection_mode=True,
        )

        data = config.to_dict()

        # Top-level boolean present.
        assert data["protection_mode"] is True

        # No serialized mount_spec pattern (or mount_root) mentions .ignore_scope.
        for spec in data["local"]["mount_specs"]:
            for pattern in spec.get("patterns", []):
                assert IGSC_DIR_NAME not in pattern, (
                    f"Protection leaked into pattern: {pattern!r}"
                )
            assert IGSC_DIR_NAME not in spec.get("mount_root", ""), (
                f"Protection leaked into mount_root: {spec['mount_root']!r}"
            )

        # Round-trip restores the boolean.
        restored = ScopeDockerConfig.from_dict(data, tmp_path)
        assert restored.protection_mode is True

    # --- AC3 (ABSOLUTE): reveal beneath .ignore_scope does NOT re-expose ---

    def test_ac3_reveal_cannot_reexpose_protected(self, tmp_path: Path):
        """A reveal targeting beneath `.ignore_scope` is suppressed: with
        protection_mode=True the secret path stays masked (the `!` carve-out
        did NOT win against the force-hide).
        """
        igsc = tmp_path / IGSC_DIR_NAME
        secret = igsc / "secret"

        # mask .ignore_scope/ then attempt to reveal .ignore_scope/secret/.
        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs(
                {tmp_path}, masked={igsc}, revealed={secret},
            ),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            protection_mode=True,
        )

        igsc_cpath = "/workspace/" + IGSC_DIR_NAME
        secret_cpath = igsc_cpath + "/secret"

        # The protected dir itself is masked.
        assert igsc_cpath in hierarchy.masked_paths

        # CRUX: the reveal did NOT re-expose the secret.
        assert secret_cpath not in hierarchy.visible_paths, (
            f"Reveal re-exposed protected content: {secret_cpath} leaked into "
            f"visible_paths={hierarchy.visible_paths}"
        )

        # Suppression happens before validation — no orphan-reveal error and
        # no L3 punch-through bind for the secret.
        assert hierarchy.validation_errors == []
        assert not any(secret_cpath in v for v in hierarchy.ordered_volumes), (
            f"A punch-through volume leaked for the suppressed reveal: "
            f"{hierarchy.ordered_volumes}"
        )

    # --- AC4: default-on when key absent from serialized dict ---

    def test_ac4_from_dict_defaults_on(self, tmp_path: Path):
        """ScopeDockerConfig.from_dict with no protection_mode key ⇒ True."""
        data = {
            "version": "0.7.0",
            "scope_name": "legacy",
            "dev_mode": True,
            "local": {"mount_specs": []},
        }
        config = ScopeDockerConfig.from_dict(data, tmp_path)
        assert config.protection_mode is True

    # --- AC5: sibling root with its own .ignore_scope is also masked ---

    def test_ac5_sibling_ignore_scope_masked(self, tmp_path: Path):
        """A sibling root containing `.ignore_scope` ⇒ that sibling's
        `.ignore_scope` is force-hidden when protection_mode=True.
        """
        sibling_host = Path("C:/Libs")
        sibling_common = sibling_host / "common"
        sibling = _make_sibling(
            host_path=sibling_host,
            container_path="/libs",
            mounts={sibling_common},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path / "src"}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
            protection_mode=True,
        )

        # Sibling force-hide is computed at the sibling mount_root:
        # C:/Libs/common → /libs/common, so .ignore_scope → /libs/common/.ignore_scope
        sibling_igsc = "/libs/common/" + IGSC_DIR_NAME
        assert sibling_igsc in hierarchy.masked_paths, (
            f"Sibling .ignore_scope must be masked; masked={hierarchy.masked_paths}"
        )
        assert sibling_igsc not in hierarchy.visible_paths

        # The primary root is still protected too.
        primary_igsc = "/workspace/src/" + IGSC_DIR_NAME
        assert primary_igsc in hierarchy.masked_paths

    # --- AC6: opt-out restores prior behavior ---

    def test_ac6_opt_out_disables_protection(self, tmp_path: Path):
        """protection_mode=False ⇒ `.ignore_scope` is NOT force-hidden, and a
        reveal beneath it works as before (re-exposes the content).
        """
        igsc = tmp_path / IGSC_DIR_NAME
        secret = igsc / "secret"

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs(
                {tmp_path}, masked={igsc}, revealed={secret},
            ),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            protection_mode=False,
        )

        igsc_cpath = "/workspace/" + IGSC_DIR_NAME
        secret_cpath = igsc_cpath + "/secret"

        # The mask is honored (user asked for it) but NOT force-injected —
        # here it exists only because the test config masked it explicitly.
        assert igsc_cpath in hierarchy.masked_paths
        # Prior behavior: the reveal re-exposes the secret.
        assert secret_cpath in hierarchy.visible_paths, (
            f"With protection off, reveal should re-expose {secret_cpath}; "
            f"visible={hierarchy.visible_paths}"
        )

    def test_ac6_opt_out_no_forced_hide_without_user_mask(self, tmp_path: Path):
        """protection_mode=False with a bare mount ⇒ `.ignore_scope` is not
        injected into masked_paths at all (no force-hide).
        """
        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            protection_mode=False,
        )

        igsc_cpath = "/workspace/" + IGSC_DIR_NAME
        assert igsc_cpath not in hierarchy.masked_paths, (
            f"Protection off must not inject a force-hide; "
            f"masked={hierarchy.masked_paths}"
        )

    # --- AC7: show_hidden guard — masking independent of show_hidden ---

    def test_ac7_show_hidden_does_not_affect_masking(self, tmp_path: Path):
        """Toggling show_hidden (True vs False) does NOT change whether
        `.ignore_scope` is in masked_paths — container masking is independent
        of the show_hidden display flag.

        show_hidden is a ScopeDockerConfig display flag, not a parameter of
        compute_container_hierarchy; container masking is computed without it.
        The hierarchy call is identical regardless of the config's show_hidden,
        so the masked set is byte-identical across the toggle.
        """
        igsc_cpath = "/workspace/" + IGSC_DIR_NAME

        def _masked_for(show_hidden: bool) -> set[str]:
            config = _make_scope_config(
                host_project_root=tmp_path,
                mounts={tmp_path},
                scope_name="guard",
                show_hidden=show_hidden,
                protection_mode=True,
            )
            assert config.show_hidden is show_hidden
            hierarchy = compute_container_hierarchy(
                container_root="/workspace",
                mount_specs=config.mount_specs,
                pushed_files=config.pushed_files,
                host_project_root=tmp_path,
                host_container_root=tmp_path,
                protection_mode=config.protection_mode,
            )
            return hierarchy.masked_paths

        masked_shown = _masked_for(True)
        masked_hidden = _masked_for(False)

        assert igsc_cpath in masked_shown
        assert igsc_cpath in masked_hidden
        assert masked_shown == masked_hidden, (
            "show_hidden must not change container masking"
        )
