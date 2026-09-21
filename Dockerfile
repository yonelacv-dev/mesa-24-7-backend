# Imagen del back para un servidor de pruebas. Un solo proceso (ver "Notas de operación" del README):
# el límite de intentos y el bus de tiempo real viven en memoria, así que no se escala con --workers
# dentro del mismo contenedor; para más carga se levantan varias réplicas detrás de un balanceador.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

RUN pip install --no-cache-dir poetry==2.2.1

# Capa de dependencias por separado: cambiar el código no vuelve a instalar los paquetes.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
