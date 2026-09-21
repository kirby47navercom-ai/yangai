$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Dist = Join-Path $Root 'dist\Hana'
$BuildDist = Join-Path $Root '.hana_build_dist'
$Data = Join-Path $Dist 'data'
$DataBackup = Join-Path $Root '.hana_data_backup'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw '먼저 setup_hana.bat을 실행해줘.'
}

if (Test-Path -LiteralPath $BuildDist) {
    Remove-Item -LiteralPath $BuildDist -Recurse -Force
}
if (Test-Path -LiteralPath $DataBackup) {
    throw "임시 기억 백업 폴더가 남아 있어. 먼저 확인해줘: $DataBackup"
}
if (Test-Path -LiteralPath $Data) {
    Move-Item -LiteralPath $Data -Destination $DataBackup
}

try {
    & $VenvPython -m PyInstaller --noconfirm --clean --onedir --windowed --name Hana `
        --distpath $BuildDist `
        --collect-all piper `
        --collect-all faster_whisper `
        --collect-all ctranslate2 `
        --hidden-import sounddevice `
        (Join-Path $Root 'hana_app.py')

    $BuiltDist = Join-Path $BuildDist 'Hana'
    Copy-Item (Join-Path $Root 'config.json') $BuiltDist -Force
    Copy-Item (Join-Path $Root 'hana_prompt.txt') $BuiltDist -Force
    Copy-Item (Join-Path $Root 'voices') (Join-Path $BuiltDist 'voices') -Recurse -Force
    Copy-Item (Join-Path $Root 'assets') (Join-Path $BuiltDist 'assets') -Recurse -Force

    if (Test-Path -LiteralPath $Dist) {
        Remove-Item -LiteralPath $Dist -Recurse -Force
    }
    Move-Item -LiteralPath $BuiltDist -Destination $Dist
}
finally {
    if ((Test-Path -LiteralPath $DataBackup) -and -not (Test-Path -LiteralPath $Data)) {
        New-Item -ItemType Directory -Path $Dist -Force | Out-Null
        Move-Item -LiteralPath $DataBackup -Destination $Data
    }
    if (Test-Path -LiteralPath $BuildDist) {
        Remove-Item -LiteralPath $BuildDist -Recurse -Force
    }
}

Write-Host ''
Write-Host "완료: $Dist\Hana.exe" -ForegroundColor Green
