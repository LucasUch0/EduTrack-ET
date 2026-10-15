@echo off
REM EduTrack-GNN - duplo clique para abrir a aplicacao no navegador (Windows).
REM Procura um Python 3.10 ou mais novo e passa o trabalho para o iniciar.py, que cria o
REM ambiente em %USERPROFILE%\.edutrack-gnn, instala o que faltar e abre o navegador
REM quando o servico responder. Opcoes: iniciar.bat --reinstalar  ou  iniciar.bat --porta 8123
setlocal
title EduTrack-GNN
cd /d "%~dp0"

set "PY="
for %%V in (3.13 3.12 3.14 3.11 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo Nao encontrei o Python 3.10 ou mais novo neste computador.
  echo Instale o Python 3.13 em https://www.python.org/downloads/
  echo marcando a opcao "Add python.exe to PATH" e rode este arquivo de novo.
  echo.
  pause
  exit /b 1
)

%PY% iniciar.py %*
if errorlevel 1 (
  echo.
  pause
)
endlocal
