#!/bin/bash
# ============================================================
#  Build macOS distributable for ThousandEyes QA Automator
#  Produces: dist/TE Questionnaire Automator.app
#            dist/TE_QA_Automator_mac.dmg  (if create-dmg available)
#
#  Run this on a Mac. Output can be sent to any macOS user.
# ============================================================

set -e
cd "$(dirname "$0")"

echo "============================================================"
echo " Building ThousandEyes QA Automator — macOS"
echo "============================================================"
echo ""

# ---- Prerequisites ----
# ---- Install uv if needed (handles Python version management, no sudo) ----
if ! command -v uv &>/dev/null && ! [ -f "$HOME/.local/bin/uv" ]; then
    echo "📥 Installing uv (Python manager)…"
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="${HOME}/.local/bin/uv"
[ ! -f "$UV" ] && UV="$(command -v uv)"

# ---- Ensure Python 3.12 is available (bundles Tcl/Tk 9.0, not broken macOS 8.5) ----
echo "🐍 Ensuring Python 3.12 is available…"
"$UV" python install 3.12 --quiet 2>&1 | grep -v "^$" || true

# ---- Create venv with Python 3.12 ----
if [ ! -d ".venv" ] || ! .venv/bin/python --version 2>&1 | grep -q "3.12"; then
    echo "📦 Creating Python 3.12 virtual environment…"
    rm -rf .venv
    "$UV" venv .venv --python 3.12
fi

echo "📥 Installing dependencies…"
"$UV" pip install -r requirements.txt -r build_requirements.txt --quiet

# ---- Clean previous builds ----
rm -rf build/ dist/

# ---- Build ----
echo ""
echo "🔨 Building .app bundle (this takes 1–3 minutes)…"
.venv/bin/python -m PyInstaller te_qa.spec --clean --noconfirm

echo ""
echo "✅ Build complete!"
echo "   App: dist/TE Questionnaire Automator.app"
echo ""

# ---- Optional: create .dmg ----
if command -v create-dmg &>/dev/null; then
    echo "📀 Creating .dmg installer…"
    DMG_NAME="TE_QA_Automator_mac"
    create-dmg \
        --volname "TE QA Automator" \
        --volicon "dist/TE Questionnaire Automator.app/Contents/Resources/icon-windowed.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 128 \
        --icon "TE Questionnaire Automator.app" 150 185 \
        --hide-extension "TE Questionnaire Automator.app" \
        --app-drop-link 450 185 \
        "dist/${DMG_NAME}.dmg" \
        "dist/TE Questionnaire Automator.app" \
    && echo "✅ DMG created: dist/${DMG_NAME}.dmg" \
    || echo "⚠️  DMG creation failed — distribute the .app folder directly."
else
    # Zip as fallback
    echo "📦 Zipping .app for distribution…"
    cd dist
    zip -r "TE_QA_Automator_mac.zip" "TE Questionnaire Automator.app" --quiet
    cd ..
    echo "✅ ZIP created: dist/TE_QA_Automator_mac.zip"
    echo ""
    echo "   (Install create-dmg for a nicer .dmg:  brew install create-dmg)"
fi

echo ""
echo "============================================================"
echo " How to distribute:"
echo "   Send the .dmg or .zip to the recipient."
echo "   They open it, run the app, and the wizard sets up Ollama."
echo "============================================================"
