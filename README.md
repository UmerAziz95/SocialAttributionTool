# Social Attribution Tool

Social Attribution Tool is a FastAPI-based backend that demonstrates a clean, layered
architecture for collecting and exposing marketing analytics data. The service is
structured to separate web routing, domain logic, persistence, and configuration so
each concern can evolve independently.

## Technology stack

- **FastAPI** for the HTTP interface and dependency injection
- **SQLAlchemy 2.0** with async sessions for database access
- **Pydantic v2** for request/response validation and settings management
- **Passlib** for secure password hashing
- **Uvicorn** as the ASGI server during development 

## Getting started   

1. Create and activate a virtual environment.
   -----------venv\Scripts\activate
2. Install dependencies: `pip install -r requirements.txt`.
3. Provide a `.env` file or environment variables with the desired settings (database
   URL, JWT secret, etc.). The defaults allow the API to start against a local SQLite
   database, but you should still copy the committed template and then adjust the
   credentials for your local environment:

   ```bash
   cp .env.example .env               
   ``` 

   Edit `.env` to point to your database instance and supply any other secrets that
   should not live in source control.
4. Apply database migrations (optional when using the default SQLite dev database) and
   launch the application locally:

   ```bash
   alembic upgrade head
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

The API will expose versioned endpoints beneath `/api/v1`, together with health checks
under `/health` for operational monitoring.

### Troubleshooting a refused connection on port 8000

Seeing `127.0.0.1 refused to connect` even though Uvicorn printed that it started
usually means the process exited before it could bind the port. On Windows
machines this often happens because migrations run during start-up cannot reach
the configured database. Try the following checks:

1. **Verify the server is still running** – after the log line `Waiting for
   application startup.` you should see `Application startup complete.`. If the
   process exits, re-run the command in the virtual environment to view the
   full traceback.
2. **Confirm your database settings** – ensure `.env` contains a valid
   `DATABASE_URL` that the device can reach. If the database is temporarily
   unavailable, start the API without applying migrations by setting
   `INIT_DB_ON_STARTUP=false` and manually run `alembic upgrade head` once the
   database is reachable.
3. **Bind to all interfaces** – use the command shown above with
   `--host 0.0.0.0 --port 8000` to avoid Windows loopback quirks and make the
   service reachable from other devices on the network.
4. **Check for port conflicts** – if another process is listening on 8000,
   either stop it or change the port in the command (for example,
   `--port 8080`).

After these steps, open http://127.0.0.1:8000/health/live to confirm the server
is accepting connections.

### Verifying a Postgres connection

If you are using Postgres instead of the default SQLite database, run these checks
from the same device that cannot reach the API:

1. **Ensure Postgres is reachable on the network** – replace the host/port below
   with your server and run:

   ```bash
   # Linux/macOS PowerShell and Windows Command Prompt syntax are the same here
   psql "postgresql://<user>:<password>@<host>:<port>/<database>" -c "\conninfo"
   ```

   A successful response will show the connected database and host; an error like
   `could not connect to server: Connection refused` means Postgres is blocked or
   not running.
2. **Confirm the Postgres service is up** – on the server hosting Postgres, check
   the service status (examples):

   ```bash
   # Systemd-based Linux
   sudo systemctl status postgresql

   # Homebrew on macOS
   brew services list | grep postgres
   ```

3. **Verify the server is listening on the expected port** – run locally on the
   Postgres host:

   ```bash
   # Linux/macOS
   sudo lsof -iTCP:5432 -sTCP:LISTEN

   # Windows PowerShell
   netstat -ano | findstr 5432
   ```

4. **Test credentials and schema access** – run a simple query using the same DSN
   the API uses (again substitute your connection string):

   ```bash
   psql "postgresql://<user>:<password>@<host>:<port>/<database>" -c "SELECT 1;"
   psql "postgresql://<user>:<password>@<host>:<port>/<database>" -c "\dt"
   ```

   These commands validate authentication and that the target database/schema are
   accessible. If they fail, adjust the credentials, network rules, or
   `pg_hba.conf` to permit the connection from your device.

### Configuration reference 

Key settings are provided through environment variables. During local development the
preferred approach is to configure them inside the `.env` file created from the
template: 

- `DATABASE_URL` – SQLAlchemy async connection string. Defaults to a local SQLite
  database at `sqlite+aiosqlite:///./data/app.db` so the server can boot without extra
  services. Point it to your Postgres instance for shared development or production
  usage.
- `INIT_DB_ON_STARTUP` – when `true` the application will apply Alembic migrations on
  start. Defaults to `false` to avoid blocking start-up when a database is unreachable;
  enable it once the configured database is available.
- `JWT_SECRET`, `JWT_ALG`, `ACCESS_TOKEN_EXPIRE_MIN` – security-related knobs for token
  generation. Defaults include a development secret; override it in `.env` for any real
  environment.
- `CORS_ORIGINS` – list of origins allowed to call the API in browsers.

## Database migrations              

Alembic manages schema changes for the project. The start-up hook in
`app/db/init_db.py` can automatically upgrade the database to the latest revision when
`INIT_DB_ON_STARTUP=true`, but you can also run migrations manually from the command
line.

### Creating a new model and migration

1. Add or update SQLAlchemy models under `app/models/` and expose them from
   `app/models/__init__.py` so Alembic's autogeneration can discover them.
2. Create a new revision with the detected changes:

   ```bash
   alembic revision --autogenerate -m "describe your change"
   ```   

   Alembic compares the models to the current database state and writes a migration
   script under `alembic/versions/`. Review the generated file to confirm it matches the
   intended schema changes.
3. Apply the migration:      

   ```bash  
   alembic upgrade head
   ```

   The command upgrades the database to the latest revision. Subsequent deployments only
   need to run `alembic upgrade head` to bring the schema up to date.

To revert a migration (for example, during development), run

```bash   
alembic downgrade -1
```

See the [Alembic documentation](https://alembic.sqlalchemy.org/) for more advanced
workflows such as branching, seeding data, or programmatic migration execution.
 
## Project structure

```
app/     
├── api/
│   ├── __init__.py          # Public entry point exposing the assembled router
│   ├── router.py            # Root router that wires all API versions together
│   └── v1/
│       ├── __init__.py
│       ├── router.py        # Version 1 router assembling feature-specific routes
│       └── routes/
│           ├── __init__.py
│           ├── dashboard.py # Dashboard analytics endpoints
│           ├── hello.py     # Simple demo endpoint
│           └── user.py      # User management endpoints
├── core/                    # Configuration and security helpers
├── db/                      # Database engine, session and initialisation helpers
├── middlewares/             # FastAPI middleware registration
├── models/                  # SQLAlchemy ORM models
├── repositories/            # Data-access layer wrapping raw queries
├── schemas/                 # Pydantic models shared across the API boundary
├── services/                # Domain/business logic orchestrating repositories
└── main.py                  # FastAPI application factory and health checks

docs/                        # Extended architecture and contributor guides
requirements.txt             # Python dependency lock-in for reproducible installs
```

## Architectural overview

- **Routing layer (`app/api`)** keeps HTTP concerns such as path definitions and
  response models isolated from the rest of the application. The new `app/api/router.py`
  composes all versioned routers so additional API versions can be introduced without
  touching the application factory.
- **Domain layer (`app/services`, `app/schemas`)** contains business logic and
  validated data contracts that shield the API from persistence details.
- **Persistence layer (`app/models`, `app/repositories`, `app/db`)** encapsulates the
  SQLAlchemy models, repositories, and engine/session configuration, making database
  swaps or migrations straightforward.
- **Cross-cutting concerns (`app/core`, `app/middlewares`)** hold reusable utilities
  such as configuration loading, security helpers, and middleware registration.

This structure keeps responsibilities well separated, making the codebase easier to
maintain, test, and extend (for example by adding background workers or additional API
versions).

## Need a deeper tour?

For a step-by-step walkthrough of the request lifecycle, folder responsibilities,
and a checklist for adding new features, see
[`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md).
