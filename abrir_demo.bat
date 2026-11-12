@echo off
rem Origami - abre a demonstracao no navegador (clique duplo).
rem Na primeira vez cria um ambiente Python em .venv e instala o minimo (1 a 2 minutos).
setlocal
cd /d "%~dp0"
title Origami - demonstracao

set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo  Nao encontrei o Python 3.10 ou mais novo.
  echo  Instale em https://www.python.org/downloads/ ^(marque "Add python.exe to PATH"^) e abra este arquivo de novo.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  Preparando o ambiente pela primeira vez...
  %PY% -m venv .venv || goto erro
)
if not exist ".venv\.pronto" (
  echo  Instalando o necessario ^(so na primeira vez^)...
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements-demo.txt || goto erro
  echo ok> ".venv\.pronto"
)

echo.
echo  Abrindo o Origami no navegador. Para encerrar, feche esta janela.
echo.
set "ORIGAMI_DEMO=1"
set "ORIGAMI_PORTA=0"
set "ORIGAMI_ABRIR=1"
".venv\Scripts\python.exe" -m motor.cli servidor
exit /b 0

:erro
echo.
echo  Algo deu errado na preparacao. Veja a mensagem acima.
pause
exit /b 1
