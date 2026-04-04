# Claude Code CLI — Container Install Modes

Two methods for installing Claude Code CLI inside IgnoreScope containers.

## Validated Findings (2026-03-15)

Tested against `ruminatepy__dev` container (`python:3.11-slim` base).

| Finding | Result |
|---------|--------|
| Standalone installer bundles Node runtime | **Yes** — no pre-install needed |
| Requires host-side Claude Code | **No** — fully independent |
| Requires outbound internet | **Yes** — download + API |
| `curl` / `ca-certificates` in slim image | Already present (Debian Trixie) |
| Install location | `/root/.local/bin/claude` |
| Installed version | 2.1.76 |

---

## Mode 1: Runtime Install

> Active code path. This is how IgnoreScope installs Claude Code today.

**What**: Install Claude Code CLI into a **running** container via `docker exec` + `curl | bash`.

**How**:
```bash
docker exec -it <container> bash -c "curl -fsSL https://claude.ai/install.sh | bash"
```

**Characteristics**:
- Binary lands at `/root/.local/bin/claude`
- Installation is **not permanent** — binary lost on container recreation (`docker compose down && up`)
- Auth tokens persist via named volume (`{scope}-claude-auth:/root/.claude`) — separate concern from install
- Fast iteration — no image rebuild required
- Suitable for development / experimentation

**IgnoreScope code path**:
- `docker/compose.py` → `generate_dockerfile()` — builds a basic image (no CLI)
- `container_ext/install_extension.py` → `deploy_runtime()` — orchestrates install into running container
- `docker/container_ops.py` → `exec_in_container()` — low-level `docker exec` wrapper

**Persistence gap**: Binary lives outside any named volume. Options:
- Re-run installer after each container recreation (automated via deployer)
- Add a named volume for `/root/.local/bin` (risk: stale binary across image changes)

---

## Mode 2: Image Bake

> Currently SHELVED in code. Not used in production.

**What**: Install Claude Code CLI during `docker build` via a `RUN` directive. Binary is **baked into the image layer**.

**How** (Dockerfile):
```dockerfile
FROM python:3.11-slim

RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/root/.local/bin:$PATH"
ENV CLAUDE_CODE_DISABLE_AUTO_UPDATE=1

CMD ["sleep", "infinity"]
```

**Characteristics**:
- Binary is **permanent** — survives container recreation
- Requires image rebuild to update CLI version
- Increases image size (bundled Node runtime, ~100MB)
- `CLAUDE_CODE_DISABLE_AUTO_UPDATE=1` prevents unexpected mutation of baked layer
- Auth still uses named volume at `/root/.claude` (separate concern)

**IgnoreScope code path**:
- `docker/compose.py` → `generate_dockerfile_with_llm()` — generates Dockerfile with `RUN` install + `ENV` layers
- Not called from production code; kept for future reference

---

## Comparison

| Concern | Runtime Install | Image Bake |
|---------|----------------|------------|
| Survives container recreation | No | **Yes** |
| Requires image rebuild | No | Yes |
| Update CLI version | Re-run installer | Rebuild image |
| Image size impact | None (installed after) | +~100MB |
| Dev iteration speed | **Fast** | Slower |
| Production suitability | Fragile | **Reliable** |
| IgnoreScope status | **Active** | Shelved |
| IgnoreScope code path | `deploy_runtime()` | `generate_dockerfile_with_llm()` |

---

## Resolved — Code Drift Cleanup (2026-03-16)

The `container_ext/` module naming inconsistencies have been resolved:

| Old | New | Reason |
|-----|-----|--------|
| `DeployMethod.BUILD_TIME` | `DeployMethod.MINIMAL` | Single curl command, assumes deps present |
| `DeployMethod.RUNTIME` | `DeployMethod.FULL` | Provisions deps first, then curl |
| `deploy_claude_npm()` | `deploy_claude()` | No npm involved |
| `deploy_claude_native()` | Removed | Dead code, zero callers |
| `NPM_PACKAGE` constant | Removed | Zero references |
| `generate_dockerfile()` | Added `ENV PATH` | `/root/.local/bin` now in PATH for new containers |

---

## Open Questions

### Auth in headless containers
- OAuth flow requires a browser — not available in headless containers
- Options: `--api-key` flag, or pre-seed auth token into the `/root/.claude` named volume
- The auth volume (`{scope}-claude-auth:/root/.claude`) is already wired in compose generation

### PATH configuration
- Installer warns `/root/.local/bin` is not in PATH
- **Resolved**: `generate_dockerfile()` now includes `ENV PATH="/root/.local/bin:$PATH"` — all new containers have it
- **Existing containers**: Require `Recreate Container` to pick up the new Dockerfile
- IgnoreScope's `get_llm_command()` also uses full binary path as a belt-and-suspenders approach

### Auto-update behavior
- Default: Claude Code auto-updates itself
- In **Image Bake** mode, this mutates baked layers — set `CLAUDE_CODE_DISABLE_AUTO_UPDATE=1`
- In **Runtime Install** mode, auto-update is acceptable (installation is not permanent anyway)
