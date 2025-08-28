# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

This project uses `uv` for dependency management. Key commands:

- **Install dependencies**: `uv sync`
- **Activate virtual environment**: `source .venv/bin/activate`
- **Start development server**: `uvicorn api.main:server --reload --port=8001`
- **Start local PostgreSQL**: `docker compose up -d`
- **Add pip package**: `uv add <package>`

### Code Quality Commands

- **Lint code**: `ruff check fastapi_template/`
- **Format code**: `ruff format fastapi_template/`
- **Type check**: `mypy fastapi_template/`
- **Run pre-commit hooks**: `pre-commit run --all-files`
- **Run uvx ruff format and check with fix**: `uvx ruff format && uvx ruff check --fix`

### Database Commands

- **Create migration**: `alembic revision --autogenerate -m "description"`
- **Run migrations**: `alembic upgrade head`
- **Downgrade migration**: `alembic downgrade -1`

### Testing Commands

- **Run tests without Docker (quick)**: `uv run pytest -m "not docker"`
- **Run all tests (including Docker)**: `uv run pytest`
- **Run tests with verbose output**: `uv run pytest -v`
- **Run specific test file**: `uv run pytest tests/test_database.py`
- **Run tests with coverage report**: `uv run pytest --cov-report=html`
- **Run tests with 100% coverage requirement**: `uv run pytest --cov-fail-under=100`

## Architecture Overview

### Project Structure
- `api/main.py`: FastAPI application entry point with server instance
- `api/config.py`: Pydantic settings with environment configuration
- `api/database/`: Database layer with async SQLAlchemy
- `migration/`: Alembic migration files and configuration
- `tests/`: Test suite with testcontainers for database integration

### Database Architecture
- Uses async SQLAlchemy with PostgreSQL via asyncpg
- `DatabaseSessionManager` in `database/__init__.py` handles connection pooling and session management
- Database dependency injection via `DBSession` annotation in `main.py`
- Models should inherit from `Base` in `database/models/__init__.py`

### Configuration System
- Environment-based configuration using Pydantic Settings
- Loads from `.env.local` (preferred) or `.env` files
- Automatically constructs PostgreSQL URI from individual components
- Supports `local`, `stag`, and `prod` environments

### API Structure
- FastAPI app configured with `/api` root path
- API docs available at `/docs` and `/redoc`
- Database sessions injected using `DBSession` type annotation
- Basic health check endpoints at `/` and `/hello`

### Testing Architecture
- Uses pytest with testcontainers for isolated database testing
- Two test categories: unit tests (no Docker) and integration tests (Docker required)
- Docker tests marked with `@pytest.mark.docker` for conditional execution
- Automatic PostgreSQL container setup with migration execution (Docker tests)
- Each Docker test runs in a rolled-back transaction for isolation
- Maintains 100% test coverage including all error paths
- Comprehensive test suite covering database operations, API endpoints, and error handling
- Async test support with pytest-asyncio

## Important Notes

- Migration scripts exclude ruff linting (configured in pyproject.toml)
- Uses line length of 100 characters for code formatting
- Database URI construction happens automatically in config validation
- Docker Compose provides local PostgreSQL with default credentials
- Docker tests require Docker to be running for testcontainers
- Unit tests can run without Docker using `pytest -m "not docker"`
- Maintains 100% test coverage with comprehensive error handling tests
- Use `uv run pytest` for all pytest commands (not direct pytest)