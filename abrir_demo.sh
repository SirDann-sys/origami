#!/usr/bin/env bash
# Origami: abre a demonstração no navegador (Linux/macOS).
# Na primeira vez cria um ambiente Python em .venv e instala o mínimo (1 a 2 minutos).
set -e
cd "$(dirname "$0")"

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Não encontrei o Python 3.10 ou mais novo. Instale em https://www.python.org/downloads/ e rode de novo."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Preparando o ambiente pela primeira vez..."
  "$PY" -m venv .venv
fi
if [ ! -f .venv/.pronto ]; then
  echo "Instalando o necessário (só na primeira vez)..."
  .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements-demo.txt
  touch .venv/.pronto
fi

echo "Abrindo o Origami no navegador. Ctrl+C para encerrar."
ORIGAMI_DEMO=1 ORIGAMI_PORTA=0 ORIGAMI_ABRIR=1 exec .venv/bin/python -m motor.cli servidor
