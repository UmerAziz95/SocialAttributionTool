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
   URL, JWT secret, etc.). Start by copying the committed template and then adjust the
   credentials for your local environment:                           

   ```bash
   cp .env.example .env               
   ``` 

   Edit `.env` to point to your database instance and supply any other secrets that
   should not live in source control.
4. Apply database migrations and launch the application locally:

   ```bash
   alembic upgrade head
   uvicorn app.main:app --reload                  
   ```

The API will expose versioned endpoints beneath `/api/v1`, together with health checks
under `/health` for operational monitoring.

### Configuration reference 

Key settings are provided through environment variables. During local development the
preferred approach is to configure them inside the `.env` file created from the
template: 

- `DATABASE_URL` – SQLAlchemy async connection string. Ensure the username/password in
  the URL correspond to an existing database account; authentication failures during
  start-up usually mean these credentials do not match the target instance. This value
  must be supplied via `.env` (or the environment) before the app or Alembic commands
  can run.
- `INIT_DB_ON_STARTUP` – when `true` (default) the application will apply Alembic
  migrations on start. Set it to `false` if schema management happens elsewhere or when
  you want the server to boot without touching the database (for example, while pointing
  the API to a remote staging database that is temporarily unavailable).
- `JWT_SECRET`, `JWT_ALG`, `ACCESS_TOKEN_EXPIRE_MIN` – security-related knobs for token
  generation. Define `JWT_SECRET` in `.env` to keep it out of source control.
- `CORS_ORIGINS` – list of origins allowed to call the API in browsers.

## Database migrations              

Alembic manages schema changes for the project. The start-up hook in
`app/db/init_db.py` automatically upgrades the database to the latest revision when
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
