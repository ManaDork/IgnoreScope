"""Tests for CLI interactive create flow.

Exercises _interactive_create() with mocked input() to catch
method-name crashes (add_masked→add_mask, add_revealed→add_reveal)
and verify the interactive flow produces valid configs.

No Docker required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from IgnoreScope.cli.interactive import _interactive_create
from IgnoreScope.core.config import ScopeDockerConfig


@pytest.fixture
def project_with_structure(tmp_path):
    """Project dir with subdirs for mount/mask/reveal flow.

    Structure:
        MyProject/
            Content/
                texture.png
            src/
                main.py
                api/
                    routes.py
                    public/
                        index.html
    """
    project = tmp_path / "MyProject"
    project.mkdir()
    src = project / "src"
    src.mkdir()
    (src / "main.py").touch()
    api = src / "api"
    api.mkdir()
    (api / "routes.py").touch()
    public = api / "public"
    public.mkdir()
    (public / "index.html").touch()
    content = project / "Content"
    content.mkdir()
    (content / "texture.png").touch()
    return project


class TestInteractiveCreate:
    """Tests for _interactive_create() prompt flow."""

    def test_mount_only_no_crash(self, project_with_structure):
        """Mount src/, skip masking, skip siblings, name scope.

        Verifies basic flow produces config with mount and scope_name.
        """
        project = project_with_structure
        # Prompt sequence:
        #   1. Container root path → accept default
        #   2. Mount 'Content'? → no
        #   3. Mount 'src'? → yes
        #   4. Mask 'src/api'? → no  (api is only subdir of src)
        #   5. Add sibling? → no
        #   6. Scope name → "test_scope"
        #   7. Safe mode → accept default (yes)
        #   8. Proceed? → accept default (yes)
        inputs = ["", "n", "y", "n", "n", "test_scope", "", ""]

        with patch("builtins.input", side_effect=inputs):
            config = _interactive_create(project)

        assert isinstance(config, ScopeDockerConfig)
        assert config.scope_name == "test_scope"
        assert project / "src" in config.mounts
        assert len(config.masked) == 0
        assert len(config.revealed) == 0

    def test_mount_and_mask_no_crash(self, project_with_structure):
        """Mount src/, mask api/, skip reveals and siblings.

        Crash-detection test for F-1: add_masked() → add_mask().
        Before fix, this raised AttributeError on config.add_masked().
        """
        project = project_with_structure
        # Prompt sequence:
        #   1. Container root → default
        #   2. Mount 'Content'? → no
        #   3. Mount 'src'? → yes
        #   4. Mask 'src/api'? → yes  ← exercises add_mask()
        #   5. Unmask 'src/api/public'? → no  (public is subdir of api)
        #   6. Add sibling? → no
        #   7. Scope name → "test_scope"
        #   8. Safe mode → default
        #   9. Proceed? → default
        inputs = ["", "n", "y", "y", "n", "n", "test_scope", "", ""]

        with patch("builtins.input", side_effect=inputs):
            config = _interactive_create(project)

        assert isinstance(config, ScopeDockerConfig)
        assert project / "src" / "api" in config.masked
        assert len(config.revealed) == 0

    def test_mount_mask_reveal_no_crash(self, project_with_structure):
        """Mount src/, mask api/, reveal public/, skip siblings.

        Crash-detection test for F-1: add_revealed() → add_reveal().
        Before fix, this raised AttributeError on config.add_revealed().
        """
        project = project_with_structure
        # Prompt sequence:
        #   1. Container root → default
        #   2. Mount 'Content'? → no
        #   3. Mount 'src'? → yes
        #   4. Mask 'src/api'? → yes
        #   5. Unmask 'src/api/public'? → yes  ← exercises add_reveal()
        #   6. Add sibling? → no
        #   7. Scope name → "test_scope"
        #   8. Safe mode → default
        #   9. Proceed? → default
        inputs = ["", "n", "y", "y", "y", "n", "test_scope", "", ""]

        with patch("builtins.input", side_effect=inputs):
            config = _interactive_create(project)

        assert isinstance(config, ScopeDockerConfig)
        assert project / "src" / "api" in config.masked
        assert project / "src" / "api" / "public" in config.revealed

    def test_full_flow_with_sibling(self, project_with_structure, tmp_path):
        """Mount, mask, reveal, add one sibling, name scope.

        Verifies siblings list populated with correct host_path.
        """
        project = project_with_structure
        # Create sibling dir with one subfolder (needs a mount to be truthy)
        sibling_dir = tmp_path / "SharedLibs"
        sibling_dir.mkdir()
        (sibling_dir / "utils").mkdir()

        # Prompt sequence:
        #   1.  Container root → default
        #   2.  Mount 'Content'? → no
        #   3.  Mount 'src'? → yes
        #   4.  Mask 'src/api'? → yes
        #   5.  Unmask 'src/api/public'? → yes
        #   6.  Add sibling? → yes
        #       _configure_sibling(1):
        #   7.    Host path → sibling_dir
        #   8.    Container path → default (/SharedLibs)
        #         folders: utils/
        #   9.    Mount 'utils'? → yes (makes sibling truthy)
        #         (utils has no subdirs → no mask prompts)
        #   10. Add another sibling? → no
        #   11. Scope name → "test_scope"
        #   12. Safe mode → default
        #   13. Proceed? → default
        inputs = [
            "", "n", "y", "y", "y",
            "y", str(sibling_dir), "", "y",
            "n", "test_scope", "", "",
        ]

        with patch("builtins.input", side_effect=inputs):
            config = _interactive_create(project)

        assert isinstance(config, ScopeDockerConfig)
        assert config.scope_name == "test_scope"
        assert len(config.siblings) == 1
        assert config.siblings[0].host_path == sibling_dir
        assert config.siblings[0].container_path == "/SharedLibs"
