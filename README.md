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
2. Install dependencies: `pip install -r requirements.txt`.
3. Provide a `.env` file or environment variables with the desired settings (database
   URL, JWT secret, etc.).
4. Launch the application locally:

   ```bash
   uvicorn app.main:app --reload
   ```

The API will expose versioned endpoints beneath `/api/v1`, together with health checks
under `/health` for operational monitoring.

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
