# GUI Container Recreate Warning Dialog

- **Summary**: When any action requires container recreate, prompt user and warn that runtime-deployed extensions will be lost. Offer auto-re-deploy after recreate.
- **Blocked by**: Nothing — Phase 3 reconciliation handles auto-re-deploy. This is the GUI warning layer on top.
- **Estimated scope**: S
- **Partially addressed**: Phase 3 `reconcile_extensions()` auto-re-deploys after recreate. Remaining work is the pre-recreate warning dialog in GUI.
- **Full spec**: `.claude/TODOs/container-recreate-prompt.md`
