# PyPI / Wheel Publishing

- **Summary**: Publish IgnoreScope as a pre-built wheel on PyPI (or GitHub Releases) so `pip install ignorescope` works without building from source.
- **Blocked by**: Nothing — pyproject.toml already configured for builds.
- **Estimated scope**: S
- **Current state**: `uv tool install git+...` builds from source on every install. No pre-built wheel exists.
- **Options**: PyPI publishing via GitHub Actions on tag push, or attach .whl to GitHub Releases.
