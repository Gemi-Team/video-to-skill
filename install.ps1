# Installe video-to-skill sous Windows. Tout le travail est fait par scripts/bootstrap.py.
#   .\install.ps1                 -> tout (paquets, ffmpeg, runtime JS, Whisper small, autotest, skill)
#   .\install.ps1 --check         -> diagnostic seul
#   .\install.ps1 --whisper-model medium
# Si PowerShell bloque le script : powershell -ExecutionPolicy Bypass -File .\install.ps1
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$candidates = @(@('py', '-3'), @('python'), @('python3'))
$py = $null
foreach ($c in $candidates) {
    $exe = $c[0]
    $pre = @($c | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    # le faux "python3" du Microsoft Store renvoie un code d'erreur : on l'ignore
    & $exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $c; break }
}
if ($null -eq $py) {
    Write-Host "Python 3.9+ introuvable. Installe-le : winget install -e --id Python.Python.3.12"
    exit 1
}
$exe = $py[0]
$pre = @($py | Select-Object -Skip 1)
& $exe @pre (Join-Path $here 'scripts\bootstrap.py') @args
exit $LASTEXITCODE
