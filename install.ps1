# Installs video-to-skill on Windows. All the work is done by scripts/bootstrap.py.
#   .\install.ps1                 -> everything (packages, ffmpeg, JS runtime, Whisper small, self-test, skill)
#   .\install.ps1 --check         -> diagnostics only
#   .\install.ps1 --whisper-model medium
# If PowerShell blocks the script: powershell -ExecutionPolicy Bypass -File .\install.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$candidates = @(@('py', '-3'), @('python'), @('python3'))
$py = $null
foreach ($c in $candidates) {
    $exe = $c[0]
    $pre = @($c | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    # the fake Microsoft Store "python3" returns an error code: skip it
    & $exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if ($null -eq $py) {
    Write-Host "Python 3.9+ not found. Install it: winget install -e --id Python.Python.3.12"
    exit 1
}
$exe = $py[0]
$pre = @($py | Select-Object -Skip 1)
& $exe @pre (Join-Path $here 'scripts\bootstrap.py') @args
exit $LASTEXITCODE
