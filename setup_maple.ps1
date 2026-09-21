$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
$Ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source

if (-not $Python) { throw 'Python을 찾지 못했어.' }
if (-not $Ollama) { throw 'Ollama를 찾지 못했어. https://ollama.com/download/windows 에서 설치해줘.' }

$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$VoiceDir = Join-Path $Root 'voices'
$VoiceModel = Join-Path $VoiceDir 'ko_KR-kss-medium.onnx'
$EspeakData = Join-Path $env:USERPROFILE 'maple_espeak'
$Config = Get-Content (Join-Path $Root 'config.json') -Raw | ConvertFrom-Json

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $Python -m venv $Venv
}

& $VenvPython -m pip install --disable-pip-version-check --upgrade 'piper-tts==1.4.1'
if (-not (Test-Path -LiteralPath $VoiceModel)) {
    New-Item -ItemType Directory -Path $VoiceDir -Force | Out-Null
    & $VenvPython -m piper.download_voices --download-dir $VoiceDir $Config.piper_voice
}

# Piper Windows wheels can fail on Korean/Unicode paths. Keep only its data folder
# at an ASCII path under the user's profile; no drive mapping or background server is used.
$PackageEspeak = Join-Path $Venv 'Lib\site-packages\piper\espeak-ng-data'
New-Item -ItemType Directory -Path $EspeakData -Force | Out-Null
Copy-Item -Path (Join-Path $PackageEspeak '*') -Destination $EspeakData -Recurse -Force

$modelNames = (& $Ollama list | Out-String)
if ($modelNames -notmatch [regex]::Escape($Config.model)) {
    & $Ollama pull $Config.model
}

Write-Host ''
Write-Host '설정이 끝났어. 이제 start_maple.bat을 실행하면 돼.' -ForegroundColor Green
