@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ResourceStudio

set "PYTHON=%~dp0runtime\python.exe"
if not exist "%PYTHON%" set "PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  set "FOUND_PYTHON="
  for /f "delims=" %%P in ('powershell -NoProfile -ExecutionPolicy Bypass -Command "$roots=Get-PSDrive -PSProvider FileSystem | ForEach-Object { $_.Root }; $patterns=foreach($r in $roots){ Join-Path $r 'Python*\python.exe'; Join-Path $r 'Program Files\Python*\python.exe'; Join-Path $r 'Program Files (x86)\Python*\python.exe'; Join-Path $r 'Users\*\AppData\Local\Programs\Python\Python*\python.exe' }; Get-ChildItem -Path $patterns -File -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName"') do if not defined FOUND_PYTHON set "FOUND_PYTHON=%%P"
  if defined FOUND_PYTHON set "PYTHON=%FOUND_PYTHON%"
)
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 (
  set "PYTHON=python"
  "%PYTHON%" --version >nul 2>&1
)
if errorlevel 1 (
  echo Python nao encontrado. A instalar runtime local automaticamente...
  set "PYTHON_INSTALLER=%TEMP%\ResourceStudio-Python-3.12.10.exe"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%PYTHON_INSTALLER%'"
  if not exist "%PYTHON_INSTALLER%" (
    echo Nao foi possivel descarregar o Python.
    pause
    exit /b 1
  )
  start "" /wait "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=0 Include_test=0 Include_pip=1 TargetDir="%~dp0runtime"
  set "PYTHON=%~dp0runtime\python.exe"
  del /q "%PYTHON_INSTALLER%" >nul 2>&1
  "%PYTHON%" --version >nul 2>&1
  if errorlevel 1 (
    echo A instalacao automatica do Python falhou.
    pause
    exit /b 1
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $h=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8777/api/health -TimeoutSec 1; if($h.Content -match 'support_cards.*true' -and $h.Content -match 'fivem_generator.*v2'){ exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  start "" http://127.0.0.1:8777
  endlocal
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$target=[IO.Path]::GetFullPath('%~dp0launcher.py'); Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -and $_.CommandLine.Contains($target) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 1 /nobreak >nul

set "LOCAL_DEPS=%~dp0local_deps"
set "STATE_DIR=%~dp0data"
set "READY_FILE=%STATE_DIR%\first_run_ready"

if exist "%READY_FILE%" goto launch

if not exist "%LOCAL_DEPS%" mkdir "%LOCAL_DEPS%"

"%PYTHON%" -c "import luaparser, antlr4, multimethod" >nul 2>&1
if errorlevel 1 (
  "%PYTHON%" -c "import sys; sys.path.insert(0, r'%LOCAL_DEPS%'); import luaparser, antlr4, multimethod" >nul 2>&1
  if errorlevel 1 (
    echo A instalar dependencias em falta...
    "%PYTHON%" -m pip install --disable-pip-version-check --no-input --target "%LOCAL_DEPS%" -r "%~dp0requirements.txt"
    if errorlevel 1 (
      echo Nao foi possivel instalar as dependencias.
      pause
      exit /b 1
    )
  )
)

if not exist "%STATE_DIR%" mkdir "%STATE_DIR%"
>"%READY_FILE%" echo ResourceStudio dependencies ready

:launch
echo ResourceStudio a iniciar...
start "ResourceStudio" /min "%PYTHON%" "%~dp0launcher.py"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8777
endlocal
