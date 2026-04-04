# Install Git into a Docker Container (Python CLI)

> **COMPLETED** — Implemented as `IgnoreScope/container_ext/git_extension.py` (`GitInstaller`).
> CLI: `python -m IgnoreScope install-git --container <name>`
> GUI: Container Extensions → Install Git
> Original procedure below kept as reference for volume persistence notes.

A simple Python CLI to install Git into a running Docker Desktop container,
with notes on volume configuration for persistence.

---

## Usage

```bash
python install_git.py --container <container_name>
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--container` | required | Name or ID of the running container |
| `--distro` | `debian` | Base distro: `debian` or `alpine` |
| `--configure` | false | Also write global git user config |
| `--name` | `""` | Git user.name (requires `--configure`) |
| `--email` | `""` | Git user.email (requires `--configure`) |

### Examples

```bash
# Basic install into a Debian-based container
python install_git.py --container my_dev_box

# Alpine-based container
python install_git.py --container my_dev_box --distro alpine

# Install and configure git identity
python install_git.py --container my_dev_box --configure --name "Ira" --email "ira@example.com"
```

---

## Script

```python
# install_git.py

import argparse
import subprocess
import sys


INSTALL_COMMANDS = {
    "debian": "apt-get update && apt-get install -y git",
    "alpine": "apk add --no-cache git",
}


def run_in_container(container: str, command: str) -> int:
    result = subprocess.run(
        ["docker", "exec", container, "sh", "-c", command],
        text=True,
    )
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Install Git into a running Docker container.")
    parser.add_argument("--container", required=True, help="Container name or ID")
    parser.add_argument("--distro", choices=["debian", "alpine"], default="debian")
    parser.add_argument("--configure", action="store_true", help="Write global git config")
    parser.add_argument("--name", default="", help="Git user.name")
    parser.add_argument("--email", default="", help="Git user.email")
    args = parser.parse_args()

    print(f"[+] Installing git ({args.distro}) into container: {args.container}")
    code = run_in_container(args.container, INSTALL_COMMANDS[args.distro])
    if code != 0:
        print("[-] Install failed.")
        sys.exit(code)

    print("[+] Git installed successfully.")

    if args.configure:
        if not args.name or not args.email:
            print("[-] --name and --email are required with --configure.")
            sys.exit(1)
        run_in_container(args.container, f'git config --global user.name "{args.name}"')
        run_in_container(args.container, f'git config --global user.email "{args.email}"')
        print(f"[+] Git configured: {args.name} <{args.email}>")

    # Verify
    code = run_in_container(args.container, "git --version")
    if code == 0:
        print("[+] Verification passed.")
    else:
        print("[-] Verification failed — git not found on PATH.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## Persistence — Required Volume Additions

A Git install via this CLI will **not survive container recreation** unless the
filesystem state is persisted. The following volumes cover the relevant paths.

### 1. Git binary and config persistence

If you want the install itself to persist without rebuilding the image,
mount the relevant system paths as named volumes:

```yaml
# docker-compose.yml
volumes:
  git_usr_bin:
  git_config:

services:
  dev:
    image: your_base_image
    volumes:
      - git_usr_bin:/usr/lib/git-core     # git internals (Debian)
      - git_usr_bin:/usr/bin/git          # git binary
      - git_config:/etc/gitconfig         # system-level git config
```

> **Note:** Persisting binaries this way is fragile. The clean alternative
> is to add `RUN apt-get install -y git` to your Dockerfile so it is baked
> into the image and always present on startup.

---

### 2. Git global user config (per-user)

Global git config lives in the container user's home directory:

```
/root/.gitconfig          # if running as root
/home/<user>/.gitconfig   # if running as a named user
```

Mount your host `.gitconfig` to carry identity in automatically:

```yaml
volumes:
  - ${USERPROFILE}/.gitconfig:/root/.gitconfig:ro
```

On Windows with Docker Desktop, `${USERPROFILE}` resolves to `C:\Users\<you>`.

---

### 3. SSH keys (for git over SSH)

If cloning private repos over SSH, mount your host SSH keys:

```yaml
volumes:
  - ${USERPROFILE}/.ssh:/root/.ssh:ro
```

Ensure permissions are correct inside the container:

```bash
docker exec <container> chmod 600 /root/.ssh/id_rsa
```

---

### 4. Git credential store (for HTTPS)

If authenticating over HTTPS with a credential helper, the credential cache
lives at:

```
/root/.git-credentials       # credential store file
/root/.config/git/           # credential helper config
```

Mount as a named volume to persist between container restarts:

```yaml
volumes:
  git_credentials:

services:
  dev:
    volumes:
      - git_credentials:/root/.git-credentials
```

---

### Full docker-compose.yml example

```yaml
version: "3.9"

volumes:
  git_credentials:

services:
  dev:
    image: your_base_image
    container_name: my_dev_box
    volumes:
      # Source code (bind mount — shared with host)
      - C:\dev\project:/workspace

      # Git identity from host (read-only)
      - ${USERPROFILE}/.gitconfig:/root/.gitconfig:ro

      # SSH keys from host (read-only)
      - ${USERPROFILE}/.ssh:/root/.ssh:ro

      # HTTPS credential persistence (named volume)
      - git_credentials:/root/.git-credentials
```

---

## Recommended Approach

For a stable setup, install Git in the **Dockerfile** rather than at runtime,
and use volume mounts only for user config and credentials:

```dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
```

The CLI tool above is best used for quick one-off installs into an already-running
container where rebuilding the image isn't practical.
