"""Tests for the protection_mode feature.

protection_mode (default True) force-hides the `.ignore_scope/` config
directory (and everything beneath it) at EVERY mirrored root — the primary
project root plus each sibling root — and suppresses any user `!` reveal that
would re-expose content beneath it. The protection is absolute: a deliberate
reveal carve-out cannot win against the force-hide.

Real masking is materialized as a Docker MASK VOLUME: when a root has an
`.ignore_scope` directory on disk, protection injects a synthetic non-negated
`.ignore_scope/` mask pattern so the existing mask-emission path produces a
`mask_volume_names` entry + an `ordered_volumes` mount line. Assertions target
that REAL output — not the UI/debug `masked_paths` set, which alone never
hides anything in-container. Existence-gating: a root with NO `.ignore_scope`
on disk is a true no-op (no mask volume materialized).

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


def _mask_vol_name_for(rel_path: str) -> str:
    """Mirror hierarchy._compute_volume_entries mask-name derivation.

    Lets a test assert the EXACT mask volume name the pipeline emits for a
    given path relative to host_container_root (e.g. ``.ignore_scope`` →
    ``mask__ignore_scope``).
    """
    from IgnoreScope.utils.strings import sanitize_volume_name

    return f"mask_{sanitize_volume_name(rel_path.replace('/', '_'))}"


class TestProtectionMode:
    """Acceptance criteria for the protection_mode feature (AC1-AC7).

    Assertions target the REAL masking output (``mask_volume_names`` /
    ``ordered_volumes``), not the UI/debug ``masked_paths`` set.
    """

    # --- AC1: protection emits a real .ignore_scope mask VOLUME ---

    def test_ac1_protection_emits_ignore_scope_mask_volume(self, tmp_path: Path):
        """protection_mode=True with mount={project_root} that has an
        `.ignore_scope` dir on disk ⇒ a real mask VOLUME is emitted for it
        (in mask_volume_names AND ordered_volumes), and the path is force-hidden.
        """
        (tmp_path / IGSC_DIR_NAME).mkdir()  # on disk → existence gate passes

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            protection_mode=True,
        )

        igsc_cpath = "/workspace/" + IGSC_DIR_NAME
        expected_mask = _mask_vol_name_for(IGSC_DIR_NAME)

        # CRUX: a real mask volume is materialized — not merely masked_paths.
        assert expected_mask in hierarchy.mask_volume_names, (
            f"{expected_mask} must be a mask volume; "
            f"mask_volume_names={hierarchy.mask_volume_names}"
        )
        assert any(
            v == f"{expected_mask}:{igsc_cpath}" for v in hierarchy.ordered_volumes
        ), (
            f"Mask volume must mount at {igsc_cpath}; "
            f"ordered_volumes={hierarchy.ordered_volumes}"
        )
        # And it is force-hidden (UI/debug surface still correct).
        assert igsc_cpath in hierarchy.masked_paths
        assert igsc_cpath not in hierarchy.visible_paths

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
        protection_mode=True the `.ignore_scope` mask VOLUME is still emitted
        and NO punch-through volume leaks for the secret (the `!` carve-out
        did NOT win against the force-hide).
        """
        igsc = tmp_path / IGSC_DIR_NAME
        secret = igsc / "secret"
        secret.mkdir(parents=True)  # on disk

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
        expected_mask = _mask_vol_name_for(IGSC_DIR_NAME)

        # The protected dir is masked by a real volume (user's own mask here;
        # the synthetic inject is skipped to avoid a duplicate).
        assert expected_mask in hierarchy.mask_volume_names, (
            f"{expected_mask} must be a mask volume; "
            f"mask_volume_names={hierarchy.mask_volume_names}"
        )

        # Suppression happens before validation — no orphan-reveal error and
        # no L3 punch-through bind for the secret.
        assert hierarchy.validation_errors == []
        assert not any(secret_cpath in v for v in hierarchy.ordered_volumes), (
            f"A punch-through volume leaked for the suppressed reveal: "
            f"{hierarchy.ordered_volumes}"
        )
        # CRUX (UI/debug surface): the reveal did NOT re-expose the secret.
        assert secret_cpath not in hierarchy.visible_paths

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
        `.ignore_scope` is masked by a REAL mask VOLUME when protection_mode=True
        (existence-gated on the sibling's own on-disk `.ignore_scope`).
        """
        # Primary root with .ignore_scope on disk.
        src = tmp_path / "src"
        (src / IGSC_DIR_NAME).mkdir(parents=True)

        # Sibling host laid out on disk so the existence gate passes.
        sibling_host = tmp_path / "Libs"
        sibling_common = sibling_host / "common"
        (sibling_common / IGSC_DIR_NAME).mkdir(parents=True)
        sibling = _make_sibling(
            host_path=sibling_host,
            container_path="/libs",
            mounts={sibling_common},
        )

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({src}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            siblings=[sibling],
            protection_mode=True,
        )

        # Sibling mask volume: sibling root is Libs/common → /libs/common, so
        # the mask name derives from "common/.ignore_scope" (relative to the
        # sibling's host_container_root = sibling_host).
        sibling_mask = _mask_vol_name_for("common/" + IGSC_DIR_NAME)
        sibling_igsc = "/libs/common/" + IGSC_DIR_NAME
        assert sibling_mask in hierarchy.mask_volume_names, (
            f"Sibling .ignore_scope must be a mask volume; "
            f"mask_volume_names={hierarchy.mask_volume_names}"
        )
        assert any(
            v == f"{sibling_mask}:{sibling_igsc}" for v in hierarchy.ordered_volumes
        ), f"Sibling mask must mount at {sibling_igsc}; {hierarchy.ordered_volumes}"

        # The primary root is masked by a real volume too.
        primary_mask = _mask_vol_name_for("src/" + IGSC_DIR_NAME)
        assert primary_mask in hierarchy.mask_volume_names

    # --- AC6: opt-out restores prior behavior ---

    def test_ac6_opt_out_disables_protection(self, tmp_path: Path):
        """protection_mode=False ⇒ no synthetic mask injected, and a user
        reveal beneath `.ignore_scope` works as before — its L3 punch-through
        volume IS emitted (re-exposes the content).
        """
        igsc = tmp_path / IGSC_DIR_NAME
        secret = igsc / "secret"
        secret.mkdir(parents=True)

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

        # The mask volume is honored (user asked for it) — but only because the
        # test config masked it explicitly, not via a force-inject.
        assert _mask_vol_name_for(IGSC_DIR_NAME) in hierarchy.mask_volume_names
        # Prior behavior: the reveal's L3 punch-through volume IS emitted.
        assert any(
            v == f"{secret}:{secret_cpath}".replace("\\", "/")
            or v.endswith(f":{secret_cpath}")
            for v in hierarchy.ordered_volumes
        ), (
            f"With protection off, reveal should emit a punch-through for "
            f"{secret_cpath}; ordered_volumes={hierarchy.ordered_volumes}"
        )
        assert secret_cpath in hierarchy.visible_paths

    def test_ac6_opt_out_no_forced_hide_without_user_mask(self, tmp_path: Path):
        """protection_mode=False with a bare mount (even with `.ignore_scope` on
        disk) ⇒ no `.ignore_scope` mask volume is emitted (no force-hide).
        """
        (tmp_path / IGSC_DIR_NAME).mkdir()  # on disk, but protection is OFF

        hierarchy = compute_container_hierarchy(
            container_root="/workspace",
            mount_specs=_make_mount_specs({tmp_path}),
            pushed_files=set(),
            host_project_root=tmp_path,
            host_container_root=tmp_path,
            protection_mode=False,
        )

        igsc_cpath = "/workspace/" + IGSC_DIR_NAME
        assert _mask_vol_name_for(IGSC_DIR_NAME) not in hierarchy.mask_volume_names, (
            f"Protection off must not inject a mask volume; "
            f"mask_volume_names={hierarchy.mask_volume_names}"
        )
        assert igsc_cpath not in hierarchy.masked_paths

    # --- AC7: show_hidden guard — masking independent of show_hidden ---

    def test_ac7_show_hidden_does_not_affect_masking(self, tmp_path: Path):
        """Toggling show_hidden (True vs False) does NOT change the emitted
        `.ignore_scope` mask VOLUME — container masking is independent of the
        show_hidden display flag.

        show_hidden is a ScopeDockerConfig display flag, not a parameter of
        compute_container_hierarchy; container masking is computed without it.
        The hierarchy call is identical regardless of the config's show_hidden,
        so the emitted mask volumes are byte-identical across the toggle.
        """
        (tmp_path / IGSC_DIR_NAME).mkdir()  # on disk → mask volume materializes
        expected_mask = _mask_vol_name_for(IGSC_DIR_NAME)

        def _mask_vols_for(show_hidden: bool) -> list[str]:
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
            return hierarchy.mask_volume_names

        masks_shown = _mask_vols_for(True)
        masks_hidden = _mask_vols_for(False)

        assert expected_mask in masks_shown
        assert expected_mask in masks_hidden
        assert masks_shown == masks_hidden, (
            "show_hidden must not change container masking"
        )
