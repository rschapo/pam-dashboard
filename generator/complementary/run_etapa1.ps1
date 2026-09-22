# Executador da Etapa 1 (Agrocore). Uso: powershell -ExecutionPolicy Bypass -File run_etapa1.ps1 [--no-download]
Set-Location $PSScriptRoot
$env:PYTHONUTF8="1"
$log = Join-Path $PSScriptRoot "..\..\data\etapa1_run.log"
"===== Etapa 1 iniciada $(Get-Date -Format s) =====" | Add-Content $log
& ".\.venv\Scripts\python.exe" -u run_pipeline.py --stage 1 @args 2>&1 | Tee-Object -Append -FilePath $log
"===== Etapa 1 fim $(Get-Date -Format s) =====" | Add-Content $log
Write-Host "Log em data\etapa1_run.log"
