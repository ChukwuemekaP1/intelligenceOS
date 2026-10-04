# IntelligenceOS - Phase 1: Foundation & Identity Layer

IntelligenceOS is a production-grade AI platform backend built with FastAPI, PostgreSQL, Redis, and Google Gemini.

Phases establishes the core foundation:
- **FastAPI Modular Monolith** architecture
- **PostgreSQL Persistence** with SQLAlchemy 2.0 (asyncpg)
- **Redis Connection** for caching and state management
- **Alembic Migrations** for declarative database schema evolution
- **Authentication & Security** with bcrypt password hashing and JWT access tokens
- **Workspace Multi-tenancy & RBAC** (OWNER, ADMIN, MEMBER roles)
- **Gemini LLM Provider Abstraction** with normalized error handling
- **Health & Readiness Endpoints** with independent dependency probing
- **Structured JSON Logging** with request correlation ID tracking and credential redaction
- **Automated Tests & Ruff Linting**

---

## Architecture Overview

```
Intelligence-OS/
├── alembic/                # Database migrations (asyncpg)
│   ├── env.py
│   └── versions/
│       └── 0001_initial_identity_schema.py
├── app/
│   ├── api/                # Route handlers and centralized dependencies
│   │   ├── deps.py         # Authentication & RBAC dependencies
│   │   ├── router.py       # API routing aggregator
│   │   └── v1/             # Endpoints (auth, workspaces, health)
│   ├── core/               # Configuration, security, logging, exceptions
│   │   ├── config.py       # Pydantic v2 settings
│   │   ├── exceptions.py   # Domain error hierarchy & HTTP handlers
│   │   ├── logging.py      # Structured JSON logger & redactor
│   │   └── security.py     # bcrypt & JWT utilities
│   ├── database/           # Engine, sessions, redis client
│   │   ├── base.py         # Declarative Base
│   │   ├── session.py      # Async sessionmaker & get_db dependency
│   │   └── redis.py        # Redis client & ping check
│   ├── models/             # SQLAlchemy ORM models (User, Workspace, Membership)
│   ├── providers/          # External service integrations
│   │   └── llm/            # LLM provider abstraction & Gemini implementation
│   ├── schemas/            # Pydantic request/response models
│   ├── services/           # Business logic (AuthService, WorkspaceService)
│   └── main.py             # FastAPI application factory & lifespan
├── tests/                  # Pytest test suite (health, auth, workspaces, LLM)
├── Dockerfile              # Container definition (python:3.12-slim)
├── docker-compose.yml      # Local orchestration (FastAPI + Postgres + Redis)
├── pyproject.toml          # Project configuration, dependencies, ruff, pytest
└── .env.example            # Environment template without real secrets
```

---

## Getting Started

### 1. Environment Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Ensure `SECRET_KEY` has at least 32 characters.

### 2. Running with Docker Compose

Start the full platform stack (Postgres, Redis, and API):

```bash
docker compose up --build -d
```

Check logs:

```bash
docker compose logs -f api
```

The database migrations run automatically on container startup via `entrypoint.sh`.

### 3. API Documentation

Interactive Swagger documentation is available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## API Endpoints

### Health & Readiness
- `GET /healthz` (or `/api/v1/health/live`): Process liveness probe.
- `GET /readyz` (or `/api/v1/health/ready`): Readiness probe validating PostgreSQL and Redis connectivity.

### Authentication
- `POST /api/v1/auth/register`: Register a new user (`email`, `password`).
- `POST /api/v1/auth/login`: Authenticate and receive a Bearer JWT access token.
- `GET /api/v1/auth/me`: Retrieve current authenticated user profile.

### Workspaces & RBAC
- `POST /api/v1/workspaces`: Create a workspace (creator automatically becomes `OWNER`).
- `GET /api/v1/workspaces`: List workspaces the user belongs to.
- `GET /api/v1/workspaces/{id}`: View workspace details (requires membership).
- `GET /api/v1/workspaces/{id}/members`: List workspace members.
- `POST /api/v1/workspaces/{id}/members`: Add a member (`OWNER` or `ADMIN`).
- `PATCH /api/v1/workspaces/{id}/members/{user_id}`: Update member role (`OWNER` or `ADMIN`).
- `DELETE /api/v1/workspaces/{id}/members/{user_id}`: Remove member (`OWNER`, `ADMIN`, or self-leave).

---

## Testing & Linting

Run tests with pytest:

```bash
docker compose exec api pytest -v
```

Or locally:

```bash
pytest -v
```

Run linting with Ruff:

```bash
docker compose exec api ruff check .
```
