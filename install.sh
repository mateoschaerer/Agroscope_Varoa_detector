#!/usr/bin/env bash
#
# ==========================
# Varroa Detector Installer (Linux)
# - Creates/updates conda env from env_linux.yaml
# - Creates a launcher script and a .desktop entry to launch the app
# ==========================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/env_linux.yaml"

info() { echo "[INFO] $*"; }
err()  { echo "[ERR ] $*" >&2; }
ok()   { echo "[OK  ] $*"; }

fail() {
  echo
  err "Installation failed. See messages above."
  exit 1
}

info "Repository: $SCRIPT_DIR"
if [ ! -f "$ENV_FILE" ]; then
  err "env_linux.yaml not found at $ENV_FILE"
  fail
fi

# ---- Locate conda ----
CONDA_BIN=""
if command -v conda >/dev/null 2>&1; then
  CONDA_BIN="$(command -v conda)"
else
  for c in \
    "$HOME/miniforge3/bin/conda" \
    "$HOME/miniconda3/bin/conda" \
    "$HOME/anaconda3/bin/conda" \
    "/opt/miniforge3/bin/conda" \
    "/opt/miniconda3/bin/conda" \
    "/opt/anaconda3/bin/conda" \
    "/opt/conda/bin/conda"
  do
    if [ -x "$c" ]; then
      CONDA_BIN="$c"
      break
    fi
  done
fi

if [ -z "$CONDA_BIN" ]; then
  err "Conda not found. Install Miniforge/Miniconda/Anaconda and add it to PATH:"
  err "  https://conda-forge.org/miniforge/"
  fail
fi
info "Using conda at: $CONDA_BIN"

CONDA_BASE="$(cd "$(dirname "$CONDA_BIN")/.." && pwd)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"

# ---- Extract env name from env_linux.yaml (fallback varroa-env) ----
ENV_NAME="$(grep -m1 '^[[:space:]]*name:' "$ENV_FILE" | sed -E 's/^[[:space:]]*name:[[:space:]]*//' | tr -d '\r')"
if [ -z "$ENV_NAME" ]; then
  ENV_NAME="varroa-env"
fi
info "Target conda environment: $ENV_NAME"

# ---- Create or update the environment ----
info "Creating/updating environment from env_linux.yaml (this can take a while)..."
if ! conda env create -f "$ENV_FILE"; then
  echo "[WARN] Create failed (likely exists). Updating..."
  if ! conda env update -f "$ENV_FILE" --prune; then
    err "Update failed."
    fail
  fi
fi

# ---- Choose app script ----
APP_SCRIPT=""
if [ -f "$SCRIPT_DIR/modern_ui_app.py" ]; then
  APP_SCRIPT="$SCRIPT_DIR/modern_ui_app.py"
elif [ -f "$SCRIPT_DIR/modern_gui_app.py" ]; then
  APP_SCRIPT="$SCRIPT_DIR/modern_gui_app.py"
else
  err "Neither modern_ui_app.py nor modern_gui_app.py found in repo root."
  fail
fi
info "App script: $APP_SCRIPT"

# ---- Create launcher script ----
LAUNCHER="$SCRIPT_DIR/run_varroa_detector.sh"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
cd "$SCRIPT_DIR"
exec python "$APP_SCRIPT"
EOF
chmod +x "$LAUNCHER"
info "Launcher script created: $LAUNCHER"

# ---- Resolve an icon for the desktop entry ----
ICON_PATH="$SCRIPT_DIR/app/icons/icon.png.png"
if [ ! -f "$ICON_PATH" ]; then
  ICON_PATH="$SCRIPT_DIR/app/icons/honeycomb_logo_transparent.ico"
fi
if [ ! -f "$ICON_PATH" ]; then
  ICON_PATH="applications-science"
fi

# ---- Create .desktop entry ----
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
DESKTOP_FILE="$APPS_DIR/varroa-detector.desktop"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Varroa Detector
Comment=Launch Varroa Detector
Exec=$LAUNCHER
Path=$SCRIPT_DIR
Icon=$ICON_PATH
Terminal=false
Categories=Science;Education;
EOF
chmod +x "$DESKTOP_FILE"
info "Desktop entry created: $DESKTOP_FILE"

# ---- Also drop a copy on the Desktop, if it exists ----
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESKTOP_DIR" ]; then
  cp -f "$DESKTOP_FILE" "$DESKTOP_DIR/Varroa Detector.desktop"
  chmod +x "$DESKTOP_DIR/Varroa Detector.desktop"
  info "Desktop shortcut created: $DESKTOP_DIR/Varroa Detector.desktop"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

echo
ok "All set!"
ok "- Conda environment: $ENV_NAME"
ok "- Application menu entry: $DESKTOP_FILE"
echo
echo "You can now launch 'Varroa Detector' from your application menu,"
echo "double-click the desktop shortcut (if your file manager allows launching .desktop files),"
echo "or run: $LAUNCHER"
