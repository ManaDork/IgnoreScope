# IgnoreScope Usage Guide

IgnoreScope manages Docker containers with volume layering — selectively hiding directories while allowing specific files to be pushed or pulled at runtime. This guide walks through the full workflow.

For installation and prerequisites, see [README.md](README.md).

---

## GUI Overview

```
 _____________________________________________________________________________
| File  Edit  + New Scope  Container  Extensions  View                       |
|_____________________________________________________________________________|
|  A  MENU BAR                                                                |
|                                                                             |
|  File: Open Location, Export                                               |
|  Edit: Add Sibling, Container Root Name, Terminal Preference               |
|  + New Scope: Quick scope creation                                         |
|  Container: Create, Update, Recreate, Launch Container in Terminal, Remove |
|  Extensions: Claude (Install, Launch, Clipboard), Git (Install)            |
|  View: Panels, Themes, Options                                             |
|____________________________________._______________________________________ |
|                                    |                                        |
|  B  LOCAL HOST CONFIGURATION       |  C  SCOPE CONFIGURATION                |
|     (Left Panel - Host View)       |     (Right Panel - Container View)     |
|                                    |                                        |
|  Your host filesystem.             |  Container's perspective.              |
|  Configure what goes into          |  Shows what's visible inside           |
|  the container.                    |  the container.                        |
|                                    |                                        |
|  Columns:                          |  Header RMB: Start / Stop Container    |
|  [Name] [Mount] [Mask] [Reveal]    |                                        |
|                        [Pushed]    |  Columns:                              |
|                                    |  [Name] [Pushed]                       |
|                                    |                                        |
|  ~/MyProject/                      |  /MyProject/                           |
|  +-- src/          [x][ ][ ]       |  +-- src/                              |
|  |   +-- vendor/   [x][x][ ]       |  |   +-- fork/       (revealed)        |
|  |   |   +-- fork/ [x][x][x]       |  |   +-- app/                          |
|  |   +-- app/      [x][ ][ ]       |  +-- docs/                             |
|  +-- docs/         [x][ ][ ]       |  +-- config.ini      [o] pushed        |
|  +-- config.ini     .  .  . [o]    |                                        |
|                                    |                                        |
|____________________________________|________________________________________|
|                                    |                                        |
|  D  RMB CONTEXT MENUS              |  E  CONTAINER ROOT / JSON VIEWER       |
|                                    |                                        |
|  Files:   Push, Sync, Pull         |  Container Root: /../MyProject         |
|  Folders: Expand, Collapse         |                                        |
|                                    |  { "version": "0.1.4",                 |
|                                    |    "scope_name": "dev",                |
|                                    |    "local": { "mounts": [...] } }      |
|                                    |                                        |
|____________________________________|________________________________________|
|                                                                             |
|  F  STATUS BAR                    Project: MyProject  |  Scope: dev         |
|_____________________________________________________________________________|

 REGION KEY
 ----------
  A   Menu Bar ............. Open project, manage scopes, container ops, extensions
  B   Local Host Config .... Host filesystem tree with Mount/Mask/Reveal/Push columns
  C   Scope Config ......... Container view - what's visible inside, push status
  D   Context Menus ........ RMB actions on files and folders
  E   JSON Viewer .......... Live config preview, container root path
  F   Status Bar ........... Current project and active scope name
```

### Column Legend

| Column | Panel | Target | Purpose |
|--------|-------|--------|---------|
| **Mount** | Local Host | Folders | Bind-mount host directory into container |
| **Mask** | Local Host | Folders | Hide mounted directory with empty volume overlay |
| **Reveal** | Local Host | Folders | Punch through mask to re-expose subdirectory |
| **Pushed** | Both | Files | Track file for push/pull workflow (`●` = pushed) |

---

## 1. Open a Project Location

A project is any directory on your host machine that you want to manage with IgnoreScope.

**GUI:**
- `File > Open Project Location` (`Ctrl+O`)
- Select the root folder of your project
- The project appears in the Local Host Configuration panel (left)

**CLI:**
```bash
# Most CLI commands default to the current directory
cd E:\MyProject
ignorescope-docker create

# Or specify explicitly
ignorescope-docker create --project E:\MyProject
```

---

## 2. Create a Scope

A scope is a named container configuration. One project can have multiple scopes (e.g., `dev`, `prod`, `test`).

**GUI:**
- Click the `+ New Scope` menu button in the menu bar
- Enter a name (e.g., `dev`)
- The scope is created and becomes active immediately

**CLI:**
```bash
ignorescope-docker create --project E:\MyProject
# Follow the interactive prompts to name the scope
```

**Config location:** `.ignore_scope/{scope_name}/scope_docker_desktop.json`

---

## 3. Mount Folders

Mounting makes a host directory visible inside the container via a bind mount.

**GUI:**
- In the Local Host Configuration tree (left panel), right-click a folder
- Select **Mount** (shows only when folder is not yet mounted)
- To mount the project root, RMB on the top-level folder and select **Mount**

**What happens:** The host directory is bind-mounted at the corresponding path inside the container (e.g., `E:\MyProject\src` maps to `/{container_root}/MyProject/src`).

---

## 4. Mask Directories

Masking hides a mounted directory from the container using an empty named Docker volume overlay.

**GUI:**
- Right-click a mounted folder in the Local Host Configuration tree
- Select **Mask** (shows only for mounted folders without existing masks)
- The folder and its contents become hidden inside the container
- The mask volume starts empty — original content is invisible

**Constraint:** A directory must be mounted before it can be masked. Masking without a mount has no effect.

**Use case:** Mount your entire `src/` folder, then mask `src/vendor/` or `src/node_modules/` to hide large dependency trees from the container.

---

## 5. Punch Through (Reveal) Directories

Revealing creates a bind mount that re-exposes a specific subdirectory within a masked area.

**GUI:**
- Right-click a folder inside a masked directory in the Local Host Configuration tree
- Select **Reveal** (shows only for masked folders without existing reveals)
- That folder's host content becomes visible again in the container

**Use case:** Mask `src/vendor/`, then reveal `src/vendor/my-fork/` to expose only your custom fork while hiding third-party packages.

---

## 6. Create the Container

Once your mount/mask/reveal configuration is set, create the Docker container.

**GUI:**
- `Container > Create Container`
- Wait for the build to complete (first build may take a minute)
- Status bar and Scope Configuration panel update to show the running container

**CLI:**
```bash
ignorescope-docker create --project E:\MyProject
```

---

## 7. Deploy Claude CLI

Install the Claude Code CLI inside the running container.

**GUI:**
- `Extensions > Claude > Install Claude CLI`
- Confirm the installation
- Wait for download and installation (installs via `curl`, requires internet)

**CLI:**
```bash
# No dedicated CLI command — use the GUI or docker exec directly:
docker exec -it <container_name> bash -c "curl -fsSL https://claude.ai/install.sh | bash"
```

---

## 8. Install Git

Install Git inside the running container.

**GUI:**
- `Extensions > Git > Install Git`
- Confirm the installation

**CLI:**
```bash
ignorescope-docker install-git --container dev
```

**Note:** Runtime installs (Claude, Git) are ephemeral — they live in the container filesystem layer and are lost on container recreate.

---

## 9. Recreate / Update Container

**Update** applies configuration changes (new mounts, masks, reveals) while retaining existing volume data.

**Recreate** destroys everything (container + volumes) and rebuilds from scratch. All runtime installs and mask volume data are lost.

**GUI:**
- `Container > Update Container` — safe, retains data
- `Container > Recreate Container` — destructive, confirms before proceeding

**Note:** After a recreate, you will need to re-install extensions (Claude CLI, Git).

---

## 10. Run Container in Terminal

Launch an interactive shell inside the container.

**GUI:**
- `Container > Launch Container in Terminal` — opens a terminal window with `docker exec`
- `Extensions > Claude > Launch Claude CLI` — opens Claude Code inside the container
- `Extensions > Claude > Clipboard: Launch Claude CLI` — copies the launch command to clipboard

**Terminal preference:** `Edit > Terminal:` submenu lets you choose CMD, PowerShell, or pwsh.

---

## 11. Push Files

Push transfers tracked files from the host into the container via `docker cp`. Pushed files can be modified during transfer via filters.

**GUI:**
- In the Local Host Configuration tree, right-click a file
- Select **Push to Container** (shows only when file is not yet pushed)
- The file is immediately pushed to the container
- Pushed files are tracked in the configuration for repeat push/pull operations

**CLI:**
```bash
# Push all tracked files
ignorescope-docker push --container dev

# Push specific files
ignorescope-docker push --container dev config.ini src/settings.json
```

**Raw copy (no tracking):**
```bash
# Copy a file or directory without tracking
ignorescope-docker cp --container dev C:\tools\my-binary /usr/local/bin/my-binary
ignorescope-docker cp --container dev C:\tools\my-dir /opt/my-dir
```

---

## 12. Pull Files

Pull transfers files from the container back to the host.

**GUI:**
- Right-click a pushed file in the Scope Configuration tree (right panel)
- Select **Pull**

**CLI:**
```bash
# Pull all tracked files
ignorescope-docker pull --container dev

# Pull specific files
ignorescope-docker pull --container dev config.ini
```

**Pull modes:**
- **Safe mode** (dev_mode=True): Files pulled to `./Pulled/{timestamp}/` — never overwrites originals
- **Production mode** (dev_mode=False): Files overwrite the host originals

---

## 13. Remove Container

Remove the Docker container and its volumes. Configuration files on disk are preserved.

**GUI:**
- `Container > Remove Container`
- Confirm when prompted

**CLI:**
```bash
ignorescope-docker remove --container dev
ignorescope-docker remove --container dev --yes  # skip confirmation
```

---

## 14. Remove Scope

Remove the scope's configuration files from disk. The Docker container must be removed first.

**GUI:**
- Right-click the scope name in the scope menu or status bar
- Select **Remove Scope Config**
- Only available when the Docker container has been removed

**Note:** This deletes `.ignore_scope/{scope_name}/` and its configuration JSON.

---

## Quick Reference

### CLI Commands

| Command | Purpose |
|---------|---------|
| `gui` | Launch GUI editor |
| `create` | Interactive scope setup |
| `list` | List containers with status |
| `status` | Detailed container info |
| `push` | Push tracked files (workflow) |
| `pull` | Pull tracked files |
| `cp` | Raw file/directory copy (no tracking) |
| `remove` | Remove container and volumes |
| `install-git` | Install Git in container |

### Global Options

| Option | Description |
|--------|-------------|
| `--project PATH` | Project root (default: current directory) |
| `--container NAME` | Scope name (default: `default`) |
| `--yes` / `-y` | Skip confirmation prompts |

### Config Location

```
{project_root}/.ignore_scope/{scope_name}/scope_docker_desktop.json
```
