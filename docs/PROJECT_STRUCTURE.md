# Project architecture and folder responsibilities

This document dives deeper into the moving pieces of the Social Attribution Tool
codebase so you can quickly identify where a change should live and how requests
flow through the system.

## Request lifecycle overview

1. **Entry point (`app/main.py`)** – FastAPI boots the application, loads
   settings, attaches middleware, and registers routers during startup.
2. **Routing layer (`app/api`)** – Requests hit the top-level `api_router`,
   which dispatches to the appropriate versioned router (currently `v1`). Each
   feature-specific router lives under `app/api/v1/routes`.
3. **Schema validation (`app/schemas`)** – Incoming payloads are parsed into
   Pydantic models, guaranteeing type safety and enforcing validation rules
   before business logic executes.
4. **Service layer (`app/services`)** – Services coordinate domain operations,
   cross-cutting policies, and repository calls.
5. **Persistence (`app/repositories` and `app/models`)** – Repositories wrap
   database interaction while SQLAlchemy models define the database schema.
6. **Database session management (`app/db`)** – Async sessions are provided to
   the request via dependency injection and cleaned up automatically once the
   request finishes.

Understanding this flow ensures new endpoints are implemented consistently and
leverage the existing abstractions.

## Directory catalogue

| Path | Purpose | What to keep here |
| --- | --- | --- |
| `app/api/` | HTTP entry points (routers, dependencies, error handlers). | Router declarations, dependency functions scoped to the web layer, exception mappers. |
| `app/api/v1/routes/` | Versioned endpoint implementations grouped by feature. | `APIRouter` instances, endpoint functions, response models specific to the feature. |
| `app/core/` | Cross-cutting concerns and application configuration. | Settings management, security helpers, constants, feature flags. |
| `app/db/` | Database bootstrapping and session utilities. | SQLAlchemy engine/session factories, Alembic helpers, seed scripts. |
| `app/middlewares/` | FastAPI middleware registration logic. | CORS, logging, rate limiting, or custom middleware functions. |
| `app/models/` | ORM models describing persistence schema. | SQLAlchemy declarative models, association tables, mixins. |
| `app/repositories/` | Data-access layer encapsulating queries. | CRUD classes, query helpers, database-facing abstractions. |
| `app/schemas/` | Pydantic models exchanged over the API. | Request/response DTOs, shared validation utilities. |
| `app/services/` | Domain services orchestrating business rules. | Classes/functions that combine repositories, external integrations, and core policies. |
| `app/main.py` | FastAPI application factory. | Application creation, router registration, health endpoints. |
| `docs/` | Living documentation for contributors. | Architectural guides, onboarding notes, ADRs, API usage examples. |

## Layer-specific guidance

### API layer (`app/api`)

- Use small, focused routers per feature area (e.g. `user`, `dashboard`).
- Declare dependencies (`Depends(...)`) close to where they are used to keep
  coupling explicit.
- Perform request/response validation with models from `app/schemas` and keep
  transformation logic minimal.

### Domain layer (`app/services` and `app/schemas`)

- Services encapsulate business invariants and should be the only layer that
  interacts with repositories directly.
- Schemas define the contract exposed to API consumers. Add new models or
  fields here before touching routers.

### Persistence layer (`app/repositories`, `app/models`, `app/db`)

- Repositories should expose task-focused methods (`get_by_email`, `create`)
  rather than low-level SQL, making them easy to mock and test.
- Models stay free of business logic; they describe tables and relationships
  only.
- Centralise session/engine creation in `app/db/session.py` so deployments can
  tweak configuration in one place.
- Toggle the `INIT_DB_ON_STARTUP` setting when deployments manage schema via
  migrations and should skip the automatic `create_all` call during application
  startup.

## Extending the project

When adding a new feature, follow this checklist:

1. Create or update Pydantic schemas describing the request and response data.
2. Extend or build a service that enforces business rules for the feature.
3. Add repository methods (and new models if necessary) to persist/fetch data.
4. Create a router module under `app/api/v1/routes/` that exposes the feature
   through HTTP endpoints, delegating to the service.
5. Register the router inside `app/api/v1/router.py` so it becomes part of the
   public API surface.
6. Update documentation (README or `docs/`) with any important decisions.

This layered approach keeps the project maintainable and clarifies where each
piece of logic belongs.
