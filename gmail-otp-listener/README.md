# FastAPI Template

Python project template with FastAPI, SQLAlchemy (postgres) and alembic.

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

2. Clone the repo

   ```bash
   git clone git@github.com:PuntPartners/fastapi-template.git
   cd fastapi-template
   ```

3. Sync and install dependencies

   ```bash
   uv sync
   source .venv/bin/activate
   ```

4. Start local postgres service (Optional)

   ```bash
   docker compose up -d
   ```

5. Start the server

   ```bash
   uvicorn api.main:server --reload --port=8001
   ```

## Testing

This project uses pytest with testcontainers to provide isolated testing with a real PostgreSQL database.

### Prerequisites

Ensure you have Docker running on your system, as testcontainers will spin up PostgreSQL containers for testing.

### Running Tests

1. **Run all tests without Docker (recommended for quick feedback)**:
   ```bash
   uv run pytest -m "not docker"
   ```

2. **Run all tests including Docker-based integration tests**:
   ```bash
   uv run pytest
   ```

3. **Run tests with verbose output**:
   ```bash
   uv run pytest -v
   ```

4. **Run specific test file**:
   ```bash
   uv run pytest tests/test_database.py
   ```

5. **Run specific test function**:
   ```bash
   uv run pytest tests/test_database.py::TestDatabase::test_database_connection
   ```

6. **Run tests with coverage report**:
   ```bash
   uv run pytest --cov-report=html
   ```
   This generates an HTML coverage report in `htmlcov/index.html`

### Test Configuration

- **Coverage threshold**: Set to 70% with comprehensive test suite
- **Test database**: Automatic PostgreSQL container with migrations (Docker tests only)
- **Test isolation**: Each test runs in a transaction that's rolled back (Docker tests)
- **Async support**: Full async/await support for database operations
- **Docker markers**: Tests requiring Docker are marked with `@pytest.mark.docker`

### Coverage

This boilerplate template maintains 100% test coverage and will fail if coverage drops below 70%.
All code paths including error handling are thoroughly tested with both unit and integration tests.
