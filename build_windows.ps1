$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "== Steam Library Tracker: Windows build =="

try {
    python -c "import PyInstaller" | Out-Null
}
catch {
    Write-Host ""
    Write-Host "PyInstaller is not installed in the active Python environment."
    Write-Host "Install the build requirements with:"
    Write-Host "  python -m pip install -r requirements-build.txt"
    exit 1
}

try {
    python -c "import streamlit, pandas, altair, requests, pyarrow, psutil" | Out-Null
}
catch {
    Write-Host ""
    Write-Host "One or more application dependencies are missing."
    Write-Host "Install them with:"
    Write-Host "  python -m pip install -r requirements-build.txt"
    exit 1
}

Write-Host ("Python:      " + (python --version))
Write-Host ("PyInstaller: " + (python -c "import PyInstaller; print(PyInstaller.__version__)"))
Write-Host ("Streamlit:   " + (python -c "import streamlit; print(streamlit.__version__)"))
Write-Host ""

if (Test-Path "build-windows") {
    Remove-Item "build-windows" -Recurse -Force
}
if (Test-Path "dist-windows") {
    Remove-Item "dist-windows" -Recurse -Force
}

python -m PyInstaller `
    --clean `
    --noconfirm `
    --workpath build-windows `
    --distpath dist-windows `
    SteamLibraryTracker.windows.spec

Write-Host ""
Write-Host "Build complete."
Write-Host ""
Write-Host "Run it with:"
Write-Host "  .\dist-windows\SteamLibraryTracker\SteamLibraryTracker.exe"
