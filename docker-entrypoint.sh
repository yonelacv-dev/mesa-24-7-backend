#!/usr/bin/env bash
# Al iniciar el contenedor: aplica las migraciones y, si se pide, siembra los datos de demostración.
# docker-compose ya espera a que MySQL esté healthy antes de arrancar este contenedor (depends_on).
#
# SEED_ON_START=false      para no tocar nada al arrancar (un servidor con datos reales)
# SEED_DEMO_QUEUE=false    para sembrar los 3 locales pero sin la cola de ejemplo del brief
# SEED_OPEN_24H=false      para respetar el horario real (11:00 a 01:00) en vez de dejarlo 24h
set -euo pipefail

alembic upgrade head

if [ "${SEED_ON_START:-true}" = "true" ]; then
  SEED_ARGS=()
  if [ "${SEED_DEMO_QUEUE:-true}" = "true" ]; then
    SEED_ARGS+=(--demo-queue)
  fi
  if [ "${SEED_OPEN_24H:-true}" = "true" ]; then
    SEED_ARGS+=(--open-24h)
  fi
  python -m app.seed "${SEED_ARGS[@]}"
fi

exec "$@"
