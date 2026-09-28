# Rebuild the exe files into dist\ and zip the folder build.
#   .\build.ps1                    build only
#   .\build.ps1 -Release v0.2.0    build, tag, push, and publish a GitHub release
# Keep this file ASCII-only: Windows PowerShell 5.1 misreads BOM-less UTF-8.
param(
    [string]$Release = "",
    [string]$Notes = ""
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pyi = Join-Path $PSScriptRoot ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $pyi)) {
    throw "PyInstaller not found. Run: .venv\Scripts\python.exe -m pip install -r requirements-dev.txt"
}

if ($Release) {
    if (git status --porcelain) { throw "Uncommitted changes. Commit before releasing." }
    if (git tag --list $Release) { throw "Tag $Release already exists." }
}

Write-Host "== build $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') @ $(git rev-parse --short HEAD)"
& $pyi --noconfirm --log-level WARN Filer.spec
if ($LASTEXITCODE) { throw "Filer.spec build failed" }
& $pyi --noconfirm --log-level WARN Filer-portable.spec
if ($LASTEXITCODE) { throw "Filer-portable.spec build failed" }
Compress-Archive -Path dist\Filer -DestinationPath dist\Filer.zip -Force
Write-Host "== done: dist\Filer-portable.exe, dist\Filer.zip, dist\Filer\Filer.exe"

if ($Release) {
    $gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
    if (-not $gh) { $gh = "C:\Program Files\GitHub CLI\gh.exe" }
    if (-not $Notes) { $Notes = "Filer $Release" }
    git tag $Release
    git push origin HEAD $Release
    & $gh release create $Release dist\Filer-portable.exe dist\Filer.zip --title "Filer $Release" --notes $Notes
    if ($LASTEXITCODE) { throw "gh release create failed" }
}
