$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$Dist = Join-Path $Root 'dist\Hana'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw '먼저 setup_hana.bat을 실행해줘.'
}

& $VenvPython -m PyInstaller --noconfirm --clean --onedir --windowed --name Hana `
    --collect-all piper `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --hidden-import sounddevice `
    (Join-Path $Root 'hana_app.py')

Copy-Item (Join-Path $Root 'config.json') $Dist -Force
Copy-Item (Join-Path $Root 'hana_prompt.txt') $Dist -Force
Copy-Item (Join-Path $Root 'voices') (Join-Path $Dist 'voices') -Recurse -Force
Copy-Item (Join-Path $Root 'assets') (Join-Path $Dist 'assets') -Recurse -Force

Write-Host ''
Write-Host "완료: $Dist\Hana.exe" -ForegroundColor Green
