"""Config migration functions for schema version transitions.

Each migration transforms the raw JSON data dict in-place from one
version schema to the next. Called by check_version_mismatch() in
_version.py before from_dict() parses the data.
"""

from __future__ import annotations


def _migrate_local_section(section: dict) -> dict:
    """Migrate a local/sibling/extension section from flat sets to mount_specs.

    Converts:
        mounts: ["src"], masked: ["src/vendor"], revealed: ["src/vendor/public"]
    To:
        mount_specs: [{"mount_root": "src", "patterns": ["vendor/", "!vendor/public/"]}]
    """
    if 'mount_specs' in section:
        return section  # Already migrated

    mounts = section.pop('mounts', [])
    masked = section.pop('masked', [])
    revealed = section.pop('revealed', [])

    # Handle legacy exception_files → pushed_files
    if 'exception_files' in section:
        section['pushed_files'] = section.pop('exception_files')

    mount_specs = []
    for mount_rel in sorted(mounts):
        patterns = []
        # Add mask patterns for paths under this mount
        for m in sorted(masked):
            if m.startswith(mount_rel + '/') or m == mount_rel:
                # Relative to mount root
                if m == mount_rel:
                    continue  # Can't mask the mount root itself as a pattern
                rel = m[len(mount_rel) + 1:]  # Strip mount prefix + /
                if rel:
                    patterns.append(f"{rel}/")
            elif '/' not in m:
                # Top-level mask, mount is also top-level
                if mount_rel == m:
                    continue
                # Mask is a sibling, not under this mount
        # Add reveal patterns for paths under this mount
        for r in sorted(revealed):
            if r.startswith(mount_rel + '/'):
                rel = r[len(mount_rel) + 1:]
                if rel:
                    patterns.append(f"!{rel}/")

        mount_specs.append({
            'mount_root': mount_rel,
            'patterns': patterns,
        })

    section['mount_specs'] = mount_specs
    return section


def migrate_to_0_2_0(data: dict) -> dict:
    """Migrate config data from pre-0.2.0 (flat sets) to 0.2.0 (mount_specs).

    Transforms the raw JSON data dict in-place:
    - local section: mounts/masked/revealed → mount_specs
    - Each sibling: same transformation
    - Each extension: same transformation
    - exception_files → pushed_files

    Args:
        data: Raw dict from scope_docker_desktop.json

    Returns:
        Transformed data dict (same object, modified in-place)
    """
    # Migrate local section
    if 'local' in data:
        data['local'] = _migrate_local_section(data['local'])

    # Migrate siblings
    for sibling in data.get('siblings', []):
        _migrate_local_section(sibling)

    # Migrate extensions
    for extension in data.get('extensions', []):
        _migrate_local_section(extension)

    # Handle top-level pushed_files (some old formats had this at top level)
    if 'pushed_files' in data and 'local' in data:
        local_pushed = data['local'].get('pushed_files', [])
        top_pushed = data.pop('pushed_files')
        # Merge into local section
        combined = list(set(local_pushed) | set(top_pushed))
        if combined:
            data['local']['pushed_files'] = combined

    data['version'] = '0.2.0'
    return data
