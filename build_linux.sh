#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "== Steam Library Tracker: Linux build =="

if ! python -c "import PyInstaller" >/dev/null 2>&1; then
    echo
    echo "PyInstaller is not installed in the active Python environment."
    echo "Install it with:"
    echo "  python -m pip install -r requirements-build.txt"
    exit 1
fi

if ! python -c "import streamlit, pandas, altair, requests, pyarrow, psutil" >/dev/null 2>&1; then
    echo
    echo "One or more application dependencies are missing from the active environment."
    echo "Install them with:"
    echo "  python -m pip install -r requirements-build.txt"
    exit 1
fi

echo "Python:      $(python --version 2>&1)"
echo "PyInstaller: $(python -c 'import PyInstaller; print(PyInstaller.__version__)')"
echo "Streamlit:   $(python -c 'import streamlit; print(streamlit.__version__)')"
echo

rm -rf build dist

python -m PyInstaller \
    --clean \
    --noconfirm \
    SteamLibraryTracker.spec

echo
echo "Build complete."
echo
echo "Run it with:"
echo "  ./dist/SteamLibraryTracker/SteamLibraryTracker"
