# Lista de espera digital, backend

API de una lista de espera para restaurantes. El comensal se une con un QR y sigue su puesto en vivo; el anfitrión
ve la cola en una tablet y llama a quien le toca.

**Stack:** FastAPI · SQLAlchemy 2 (async) · MySQL 8 · Alembic · Server-Sent Events · argon2.

## Levantarlo en 5 minutos

**Requisitos:** Python 3.11 a 3.13, [Poetry](https://python-poetry.org/docs/#installation) y MySQL 8 corriendo en
local (en macOS: `brew install mysql@8.0 && brew services start mysql@8.0`).

> Si tu Python por defecto es más nuevo (3.14, por ejemplo), Poetry usa el 3.11 a 3.13 que encuentre en tu `PATH`.
> Si no encuentra ninguno: `poetry env use /ruta/a/python3.11` antes del paso 1.

```bash
cd backend

# 1. Dependencias (crea el entorno virtual en .venv)
poetry install

# 2. Configuración
cp .env.example .env          # ajusta MYSQL_USER / MYSQL_PASSWORD si tu MySQL los usa

# 3. Base de datos + datos de demostración (3 locales, un usuario por local y la cola de ejemplo)
./scripts/setup_demo_data.sh --demo-queue

# 4. Servidor
poetry run uvicorn app.main:app --reload
```

- API: <http://127.0.0.1:8000> · documentación interactiva: <http://127.0.0.1:8000/docs> · salud: `GET /health`.
- El script crea la base, migra, siembra y **abre los 3 locales las 24 horas** (para no depender de la hora real).
  Es idempotente: repetirlo no cambia nada de lo que ya exista. La contraseña de los tres usuarios es `demo1234`
  (fija, pensada para quien revisa la prueba); para poner otra: `SEED_PASSWORD=miclave ./scripts/setup_demo_data.sh`.
- Sin el paso 3 (a mano, sin el script): `mysql -uroot -e "CREATE DATABASE waiting_list ..."`, luego
  `poetry run alembic upgrade head` y `poetry run python -m app.seed --demo-queue` — misma contraseña fija
  `demo1234` (el default vive en el propio script, no depende de ninguna variable de entorno), pero sin
  tocar el horario real (11:00 a 01:00, ver abajo): eso solo lo hace `--open-24h` o el script de arriba.

| Local | Usuario | Zona horaria |
|---|---|---|
| La Terraza Azul (`la-terraza-azul`) | `terraza-azul` | America/Lima |
| Cuatro Vientos (`cuatro-vientos`) | `cuatro-vientos` | America/Lima |
| Casa Mediterránea (`casa-mediterranea`) | `casa-mediterranea` | America/Santiago |

El horario de negocio por defecto es de 11:00 a 01:00 todos los días (el script de arriba lo deja en 24 horas
solo para revisar cómodo). Fuera de horario nadie puede unirse; se cambia desde la tablet (botón **Horario**)
o con `PUT /api/v1/venues/{slug}/host/schedule`.

## Variables de entorno (`.env`)

| Variable | Por defecto | Para qué |
|---|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` | `127.0.0.1` / `3306` | Servidor MySQL |
| `MYSQL_USER` / `MYSQL_PASSWORD` | `root` / vacío | Credenciales |
| `MYSQL_DATABASE` | `waiting_list` | Base de datos |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Orígenes del front (JSON). Solo hace falta si el front llama al back en otro origen |
| `RATE_LIMIT_ENABLED` | `true` | Límite de intentos en login, unirse y buscar ticket |
| `SSE_HEARTBEAT_SECONDS` | `15` | Cada cuánto se envía un latido por los streams en vivo |
| `DEBUG` | `false` | |

## Probarlo

```bash
poetry run pytest                        # todo: 386 tests, unos 10 segundos
poetry run pytest -m "not integration"   # 303 tests que no necesitan MySQL, menos de 1 segundo
poetry run ruff check .                  # lint
```

> Las pruebas de integración **borran y recrean** la base `waiting_list_test` en cada ejecución (nunca tocan
> `waiting_list`). Si MySQL no está disponible, se saltan solas.

Cubren, entre otras cosas: transiciones de estado válidas e inválidas, cálculo de posición y ETA, horario (incluida la
ventana que cruza la medianoche y el cambio de horario de Santiago), un teléfono con una sola entrada activa,
ticket con teléfono, y concurrencia real contra MySQL (dos anfitriones a la vez, 25 "Unirme" simultáneos).

## Arquitectura

Hexagonal, por módulos. Cada módulo tiene sus cuatro capas y **las dependencias solo apuntan hacia el dominio**:

```
app/
├── config.py · database.py · main.py · seed.py
├── shared/          errores base, puertos comunes (reloj, bus de eventos), tipos SQL
├── auth/            login de la tablet, sesiones sin caducidad por tiempo
├── venues/          locales, horario (con ventanas que cruzan la medianoche), pausa
└── waitlist/        la cola: unirse, turno, llamar/sentar/no vino/quitar, historial
    ├── domain/          reglas puras (sin frameworks): máquina de estados, posición, ETA, teléfono
    ├── application/     casos de uso + puertos (interfaces de repositorio, reloj, bus...)
    ├── infrastructure/  adaptadores SQLAlchemy, argon2, bus en memoria
    ├── presentation/    routers FastAPI, esquemas Pydantic, streams SSE
    └── dependencies.py  raíz de composición: arma los casos de uso con sus adaptadores
```

`tests/architecture/test_layers.py` **hace cumplir** esas reglas: `domain` no importa FastAPI ni SQLAlchemy,
`application` no importa infraestructura, `presentation` no llega a la base de datos, y un módulo no usa la
infraestructura de otro.

### Rutas

Todas cuelgan de `/api/v1/venues/{slug}` y dicen a quién sirven: `/diner` (comensal, sin login) o `/host`
(anfitrión, con `Authorization: Bearer`).

| Comensal | |
|---|---|
| `GET  /venues/{slug}/diner/status` | Estado de la lista: abierta, en pausa o cerrada y cuándo abre |
| `POST /venues/{slug}/diner/join` | Unirse. 201 si crea la entrada; 200 con `already_in_queue` si el teléfono ya estaba |
| `POST /venues/{slug}/diner/tickets/lookup` | Recuperar el turno con ticket **y** teléfono |
| `GET  /venues/{slug}/diner/entries/{token}` | Mi turno: puesto, ETA, plazo |
| `POST /venues/{slug}/diner/entries/{token}/cancel` | "Ya no voy" |
| `POST /venues/{slug}/diner/entries/{token}/on-the-way` | "Voy en camino" (solo avisa, no extiende el plazo) |
| `GET  /venues/{slug}/diner/entries/{token}/stream` | Mi turno en vivo (SSE) |

| Anfitrión | |
|---|---|
| `GET  /venues/{slug}/host/queue` | La cola completa |
| `POST /venues/{slug}/host/entries/{id}/call · seat · no-show · remove` | Acciones sobre una fila; devuelven la cola actualizada |
| `POST /venues/{slug}/host/pause · resume` | Pausar y reanudar la lista |
| `PUT  /venues/{slug}/host/schedule` | Guardar el horario de los 7 días |
| `GET  /venues/{slug}/host/stream` | La cola en vivo (SSE): eventos `queue` y `feed` |

| Sesión | |
|---|---|
| `POST /auth/login · /auth/logout` · `GET /auth/me` | Sesión de la tablet |

Los errores tienen siempre el mismo formato: `{"error": {"code": "invalid_phone", "message": "...", "field": "phone"}}`.

## Docker

Para un servidor de pruebas (no para desarrollo local, donde `uvicorn --reload` es más rápido de iterar).
La base de datos vive en este compose, junto con las migraciones que la crean.

```bash
docker network create waitlist-net   # una sola vez: la comparte el contenedor del frontend
cp .env.example .env
echo "MYSQL_ROOT_PASSWORD=cambia-esto" >> .env   # obligatoria, sin valor por defecto a propósito
docker compose up -d --build
```

Al arrancar, el contenedor `api` aplica las migraciones y siembra los 3 locales solo (ver
`docker-entrypoint.sh`) — igual que `./scripts/setup_demo_data.sh`, pero cada vez que se levanta el
contenedor, no una vez a mano. Por defecto queda abierto **24 horas** (es un servidor de pruebas: no
depende de la hora real). Si algún día este mismo contenedor sirve datos reales, `SEED_ON_START=false`
evita tocar nada al arrancar.

| Variable en `.env` | Por defecto | Para qué |
|---|---|---|
| `MYSQL_ROOT_PASSWORD` | *(obligatoria)* | Contraseña de MySQL dentro del contenedor |
| `API_PORT` | `8000` | Puerto publicado en el host |
| `SEED_ON_START` | `true` | `false` para no tocar nada al arrancar (servidor con datos reales) |
| `SEED_DEMO_QUEUE` | `true` | Incluir la cola de ejemplo de La Terraza Azul |
| `SEED_OPEN_24H` | `true` | `false` para respetar el horario real (11:00 a 01:00) en vez de 24h |
| `SEED_PASSWORD` | `demo1234` | Contraseña de los 3 usuarios, solo si son nuevos |
| `WAITLIST_NETWORK` | `waitlist-net` | Nombre de la red compartida con el frontend |

La base de datos **no** se publica al host (`db` no tiene `ports:`): solo el backend puede alcanzarla,
por la red interna que crea el propio compose. La API sí queda publicada en `API_PORT` (por defecto
8000); si el servidor mira a internet, decide tú si conviene cerrarla en el firewall y dejar solo el
frontend expuesto — el front igual la alcanza por dentro, por la red compartida, sin depender de este puerto.

```bash
docker compose logs -f api          # ver los logs
docker compose up -d --build api    # reconstruir tras un cambio de código (la base no se toca)
docker compose down                 # detener (con -v además borra los datos)
```

## Migraciones

```bash
poetry run alembic revision --autogenerate -m "descripcion"   # generar (revisar el archivo antes de aplicar)
poetry run alembic upgrade head                               # aplicar
poetry run alembic downgrade -1                               # deshacer la última
poetry run alembic check                                      # ¿el modelo y las migraciones coinciden?
```

## Notas de operación

- **Un solo worker.** El límite de intentos y el bus de tiempo real viven en la memoria del proceso: alcanzan para el
  piloto. Con varios workers hay que moverlos a un almacén compartido (Redis); los puertos ya están separados.
- **Detrás de nginx:** arrancar uvicorn con `--proxy-headers` (para ver la IP real en el límite de intentos) y desactivar
  el buffering en la ruta de los streams (`proxy_buffering off;`). El back ya envía `X-Accel-Buffering: no`.
- **Sesiones de la tablet:** no vencen por tiempo ni se cierran al iniciar sesión en otra tablet (dos tablets pueden
  compartir la cuenta del local). Solo se cierran con `POST /auth/logout`. Del token solo se guarda su hash.
- **Fechas:** todo se guarda en UTC; el horario y la jornada de servicio se calculan en la zona horaria del local.
  El ticket se reinicia por **jornada de servicio**, no a medianoche.
- **Historial:** cada cambio de estado queda en `entry_event` (quién, cuándo, desde qué estado) para el reporte futuro.

## Problemas comunes

| Síntoma | Causa |
|---|---|
| `Can't connect to MySQL server` | MySQL apagado o `MYSQL_*` mal configurado en `.env` |
| `Unknown database 'waiting_list'` | Falta el paso 3 (crear la base) |
| `Access denied for user 'root'` | Tu MySQL tiene contraseña: ponla en `MYSQL_PASSWORD` |
| Login responde 429 | Demasiados intentos (5 por minuto y por usuario); esperar o `RATE_LIMIT_ENABLED=false` en desarrollo |
| `POST .../join` responde 409 `list_closed` | Fuera del horario del local: abrirlo desde **Horario** o cambiar el horario |
