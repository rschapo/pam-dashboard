@echo off
REM Executador da Etapa 1 (Agrocore) - um clique. Usa o venv local.
cd /d "%~dp0"
set PYTHONUTF8=1
chcp 65001 >nul
set LOG=..\..\data\etapa1_run.log
echo ===== Etapa 1 iniciada %DATE% %TIME% ===== >> "%LOG%"
".venv\Scripts\python.exe" -u run_pipeline.py --stage 1 %* 2>&1 | powershell -Command "$input | Tee-Object -Append -FilePath '%LOG%'"
echo ===== Etapa 1 fim %DATE% %TIME% ===== >> "%LOG%"
echo.
echo Log completo em data\etapa1_run.log
pause
