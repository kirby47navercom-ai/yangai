# Build with the official Umamo 0.3.0-dev libraries already downloaded locally.
$ErrorActionPreference = 'Stop'
$taskRepo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$taskLocal = Join-Path $taskRepo '.local-tools/live2d'
$taskApp = Join-Path $taskLocal 'umamo-portable/umamo/app'
$taskClasses = Join-Path $taskLocal 'hana-rig-classes'
$taskSource = Join-Path $PSScriptRoot 'UmamoHana.kt'
$taskOutput = Join-Path $taskRepo 'assets/live2d/hana-v7-rig'
$taskJars = (Get-ChildItem -LiteralPath $taskApp -Filter '*.jar' | ForEach-Object { $_.FullName }) -join ';'
$taskCompiler = @('kotlin-compiler-embeddable-2.4.10.jar','kotlin-build-tools-api-2.4.10.jar','kotlin-script-runtime-2.4.10.jar') | ForEach-Object {
    $taskFile = Join-Path $taskLocal $_
    if (-not (Test-Path -LiteralPath $taskFile)) { throw "Missing local compiler dependency: $_" }
    $taskFile
}
$taskCompilerClasspath = (($taskCompiler -join ';') + ';' + (Join-Path $taskApp '*'))
& java -cp $taskCompilerClasspath org.jetbrains.kotlin.cli.jvm.K2JVMCompiler -no-stdlib -no-reflect -jvm-target 21 -classpath $taskJars -d $taskClasses $taskSource
if ($LASTEXITCODE -ne 0) { throw 'Kotlin compilation failed' }
& java -Xmx4g -cp ($taskClasses + ';' + (Join-Path $taskApp '*')) UmamoHanaKt $taskOutput
if ($LASTEXITCODE -ne 0) { throw 'Rig export or its self-check failed' }
