@echo off
cd /d "%~dp0"
echo ================================================================
echo Executando RMV-FINAL-PROCV-4.0
echo ================================================================
python RMV_FINAL_PROCV_202607.py --ref 202607 --nao-consultar-ibge --excel-visivel
pause
