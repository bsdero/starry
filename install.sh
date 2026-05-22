#!/usr/bin/env bash
# install.sh — Install StarryCLI to ~/.local/starry/
#
# Usage:
#   bash install.sh              # fresh install or upgrade
#   bash install.sh --uninstall  # remove everything
#
# What it does:
#   1. Copies the project to ~/.local/starry/
#   2. Creates a dedicated venv at ~/.local/starry/.venv
#   3. Installs the package (all deps via pyproject.toml)
#   4. Writes a launcher to ~/.local/bin/starry_cli
#   5. Sets up .env if missing
#   6. Copies TLS cert if present
#   7. Writes launcher script
#   8. Checks ~/.local/starry/config.toml exists
#   9. Checks ~/.local/bin is on PATH

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { echo -e "${GREEN}✓${RESET}  $*"; }
warn() { echo -e "${YELLOW}!${RESET}  $*"; }
err()  { echo -e "${RED}✗${RESET}  $*"; }
hdr()  { echo -e "\n${BOLD}── $* ──${RESET}"; }

# ── Paths ─────────────────────────────────────────────────────────────
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/starry"
BIN_DIR="$HOME/.local/bin"
VENV="$INSTALL_DIR/.venv"
LAUNCHER="$BIN_DIR/starry_cli"

# ── Uninstall ─────────────────────────────────────────────────────────
if [[ "${1:-}" == "--uninstall" ]]; then
  hdr "Uninstalling StarryCLI"
  if [[ -f "$LAUNCHER" ]]; then
    rm -f "$LAUNCHER"
    ok "Removed launcher: $LAUNCHER"
  fi
  if [[ -d "$INSTALL_DIR" ]]; then
    read -rp "  Remove $INSTALL_DIR ? This deletes config and .env [y/N] " yn
    if [[ "$yn" =~ ^[Yy]$ ]]; then
      rm -rf "$INSTALL_DIR"
      ok "Removed $INSTALL_DIR"
    else
      warn "Kept $INSTALL_DIR"
    fi
  fi
  echo ""
  ok "Uninstall complete."
  exit 0
fi

hdr "StarryCLI installer"
echo "  Source : $SRC"
echo "  Install: $INSTALL_DIR"
echo "  Bin    : $LAUNCHER"

# ── 1. Python ─────────────────────────────────────────────────────────
hdr "Checking Python"

PYTHON=""
for candidate in python3.12 python3.11 python3; do
  if command -v "$candidate" &>/dev/null; then
    major=$("$candidate" -c 'import sys; print(sys.version_info.major)')
    minor=$("$candidate" -c 'import sys; print(sys.version_info.minor)')
    if [[ $major -ge 3 && $minor -ge 11 ]]; then
      PYTHON="$candidate"
      ver=$("$candidate" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')
      ok "Using $PYTHON ($ver)"
      break
    fi
  fi
done

if [[ -z "$PYTHON" ]]; then
  err "Python 3.11+ not found. Install it and re-run."
  exit 1
fi

# ── 2. Copy source files ───────────────────────────────────────────────
hdr "Copying files to $INSTALL_DIR"

mkdir -p "$INSTALL_DIR"

# rsync preferred; fall back to cp
if command -v rsync &>/dev/null; then
  rsync -a --delete \
    --exclude='.venv/' \
    --exclude='tests/' \
    --exclude='__pycache__/' \
    --exclude='*.egg-info/' \
    --exclude='.git/' \
    --exclude='.env' \
    --exclude='config.toml' \
    --exclude='plan.md' \
    --exclude='install.sh' \
    "$SRC/" "$INSTALL_DIR/"
  ok "Files synced (rsync)"
else
  # cp fallback — copy what we need explicitly
  for item in starry_lib starry_cli config pyproject.toml .env.example; do
    cp -r "$SRC/$item" "$INSTALL_DIR/"
  done
  mkdir -p "$INSTALL_DIR/certs"
  ok "Files copied (cp)"
fi

# Always copy certs dir skeleton (never delete existing certs)
mkdir -p "$INSTALL_DIR/certs"

# ── 3. Virtual environment ─────────────────────────────────────────────
hdr "Virtual environment"

if [[ -d "$VENV" ]]; then
  if "$VENV/bin/pip" --version &>/dev/null 2>&1; then
    ok "venv already exists — reusing"
  else
    warn "Existing venv is broken — recreating"
    rm -rf "$VENV"
    "$PYTHON" -m venv "$VENV"
    ok "Recreated venv at $VENV"
  fi
else
  "$PYTHON" -m venv "$VENV"
  ok "Created venv at $VENV"
fi

PIP="$VENV/bin/pip"
"$PIP" install --upgrade pip -q
ok "pip up to date"

# ── 4. Install package ────────────────────────────────────────────────
hdr "Installing StarryCLI"

# Editable install so _find_project_root() resolves correctly
"$PIP" install -e "$INSTALL_DIR" -q
ok "starry-lib installed (editable)"

# ── 5. .env file ──────────────────────────────────────────────────────
hdr "Environment file"

ENV_FILE="$INSTALL_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  ok ".env already exists — not overwriting"
else
  cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
  warn ".env created — edit $ENV_FILE and set your API keys"
fi

# ── 6. TLS certificate ────────────────────────────────────────────────
hdr "TLS certificate"

CERT="$INSTALL_DIR/certs/davy.labs.lenovo.com.crt"
SRC_CERT="$SRC/certs/davy.labs.lenovo.com.crt"

if [[ -f "$CERT" ]]; then
  ok "Certificate present: $CERT"
elif [[ -f "$SRC_CERT" ]]; then
  cp "$SRC_CERT" "$CERT"
  ok "Certificate copied from source"
else
  warn "Certificate not found."
  warn "Copy davy.labs.lenovo.com.crt to $INSTALL_DIR/certs/"
  warn "Or set ssl_verify = false in $INSTALL_DIR/config/default.toml"
fi

# ── 7. Launcher ───────────────────────────────────────────────────────
hdr "Launcher"

mkdir -p "$BIN_DIR"

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# StarryCLI launcher — auto-generated by install.sh
# Source: $INSTALL_DIR
exec "$VENV/bin/starry_cli" "\$@"
EOF
chmod +x "$LAUNCHER"
ok "Launcher written: $LAUNCHER"

# ── 8. Config check ───────────────────────────────────────────────────
hdr "User config"

USER_CONFIG="$INSTALL_DIR/config.toml"
if [[ -f "$USER_CONFIG" ]]; then
  ok "User config present: $USER_CONFIG"
else
  warn "No user config found at $USER_CONFIG"
  warn "Run starry_cli and use /setup to configure a provider."
  warn "Or copy the template:"
  echo ""
  echo -e "    ${BOLD}cp $SRC/config/default.toml $USER_CONFIG${RESET}"
  echo ""
fi

# ── 9. PATH check ─────────────────────────────────────────────────────
hdr "PATH"

if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  ok "$BIN_DIR is on PATH"
else
  warn "$BIN_DIR is NOT on your PATH."
  warn "Add this to ~/.bashrc or ~/.zshrc and restart your shell:"
  echo ""
  echo -e "    ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
  echo ""
fi

# ── Done ──────────────────────────────────────────────────────────────
hdr "Done"

echo ""
echo -e "  Start StarryCLI:"
echo -e "    ${BOLD}starry_cli${RESET}"
echo ""
echo -e "  With a specific provider or role:"
echo -e "    ${BOLD}starry_cli --provider openai --role coder${RESET}"
echo ""
echo -e "  Manage providers:"
echo -e "    ${BOLD}starry_cli provider list${RESET}"
echo -e "    ${BOLD}starry_cli provider use openai${RESET}"
echo ""
echo -e "  Edit config:"
echo -e "    ${BOLD}\$EDITOR $INSTALL_DIR/config.toml${RESET}"
echo ""
echo -e "  Edit API keys:"
echo -e "    ${BOLD}\$EDITOR $INSTALL_DIR/.env${RESET}"
echo ""
echo -e "  Uninstall:"
echo -e "    ${BOLD}bash $SRC/install.sh --uninstall${RESET}"
echo ""
