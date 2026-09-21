#!/usr/bin/env bash
# Deja la base lista para revisar la prueba: crea la base si no existe, aplica las migraciones y
# siembra los 3 locales, abiertos 24 horas (quien revisa no debe depender de la hora real), con una
# contraseña fija y conocida (no una al azar que solo se ve una vez).
#
# Uso:
#   ./scripts/setup_demo_data.sh                 # los 3 locales, sin comensales
#   ./scripts/setup_demo_data.sh --demo-queue     # además, la cola de ejemplo del brief en La Terraza Azul
#
# Es seguro correrlo varias veces: no toca lo que ya existe (usuarios, contraseñas, comensales, horario).
set -euo pipefail
cd "$(dirname "$0")/.."

DB="${MYSQL_DATABASE:-waiting_list}"
export SEED_PASSWORD="${SEED_PASSWORD:-demo1234}"

echo "Base de datos: ${DB}"
mysql -uroot -e "CREATE DATABASE IF NOT EXISTS \`${DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
poetry run alembic upgrade head
poetry run python -m app.seed --open-24h "$@"

cat <<EOF

Listo. Si los usuarios son nuevos, la contraseña de los tres es: ${SEED_PASSWORD}
Local a probar como comensal: http://localhost:5173/venues/la-terraza-azul/diner
Tablet del anfitrión:         http://localhost:5173/venues/la-terraza-azul/host/login
EOF
