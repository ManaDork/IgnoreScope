# IgnoreScope — Architecture Principles

## Core Architecture
Detailed architecture docs live in `docs/architecture/`:
- `ARCHITECTUREGLOSSARY.md` — Key concepts including MatrixState
- `COREFLOWCHART.md` — Core logic flow
- `DATAFLOWCHART.md` — Data flow through the system
- `GUI_LAYOUT_SPECS.md`, `GUI_STATE_STYLES.md`, `GUI_STRUCTURE.md` — GUI architecture
- `MIRRORED_ALGORITHM.md` — Mirrored directory algorithm

## Guiding Principles
1. **Correctness and readability over premature optimization**
2. **MatrixState**: Truth table evaluation over gated conditional chains
3. **DRY Audit**: Scan for duplicated logic, classify clones, extract shared functions

## Module Boundaries

```
IgnoreScope/
├── core/           — Config, hierarchy, node state. No Docker/GUI imports.
├── docker/         — Container lifecycle, ops, compose, file ops. Depends on core/.
├── cli/            — CLI commands, interactive mode. Depends on core/, docker/.
├── gui/            — PyQt6 UI. Depends on core/, docker/.
├── container_ext/  — Extensions (claude, git, install, workflow). Depends on core/, docker/.
├── utils/          — Shared helpers. No internal imports.
└── migration/      — Schema/config migration (future).
```

## External Dependencies
- **Docker Engine** — Container runtime, accessed via subprocess (`docker` CLI)
- **PyQt6** — GUI framework
- **pathspec** — Gitignore-style pattern matching
