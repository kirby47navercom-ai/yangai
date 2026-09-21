$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$VoiceModel = Join-Path $Root 'voices\ko_KR-kss-medium.onnx'
$EspeakData = Join-Path $env:USERPROFILE 'hana_espeak'
$Ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source

if (-not (Test-Path -LiteralPath $VenvPython) -or -not (Test-Path -LiteralPath $VoiceModel) -or -not (Test-Path -LiteralPath $EspeakData)) {
    & (Join-Path $Root 'setup_hana.ps1')
}

if ($Ollama) { & $Ollama list | Out-Null }

# Piper는 하나 프로세스 안에서 직접 실행한다. 별도 서버와 드라이브 매핑이 없다.
& $VenvPython (Join-Path $Root 'hana_app.py')
