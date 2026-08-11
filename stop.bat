@echo off
setlocal
title ResourceStudio - Desligar
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8777 .*LISTENING"') do (
    taskkill /PID %%P /F >nul 2>&1
    echo ResourceStudio encerrado. PID %%P
)
echo.
echo Os projetos, licencas e pacotes exportados permanecem no dispositivo.
pause
endlocal
