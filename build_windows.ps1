$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "== Steam Library Tracker: Windows build =="

function Assert-CommandSuccess {
    param(
        [string]$Message
    )

    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host $Message
        exit $LASTEXITCODE
    }
}

python -c "import PyInstaller" | Out-Null
Assert-CommandSuccess "PyInstaller is not installed in the active Python environment. Run: python -m pip install -r requirements-build.txt"

python -c "import streamlit, pandas, altair, requests, pyarrow, psutil, webview" | Out-Null
Assert-CommandSuccess "One or more application dependencies are missing. Run: python -m pip install -r requirements-build.txt"

Write-Host ("Python:      " + (python --version))
Write-Host ("PyInstaller: " + (python -c "import PyInstaller; print(PyInstaller.__version__)"))
Write-Host ("Streamlit:   " + (python -c "import streamlit; print(streamlit.__version__)"))
Write-Host ("pywebview:   " + (python -c "import importlib.metadata; print(importlib.metadata.version('pywebview'))"))
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

Assert-CommandSuccess "PyInstaller build failed."

Write-Host ""
Write-Host "Build complete."
Write-Host ""
Write-Host "Run it with:"
Write-Host "  .\dist-windows\SteamLibraryTracker\SteamLibraryTracker.exe"
