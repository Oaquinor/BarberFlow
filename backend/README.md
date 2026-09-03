# KingFlow Barber - Backend

FastAPI backend for KingFlow Barber SaaS platform.

## Quick Start

### 1. Install Dependencies

```bash
# Using pip
pip install -r requirements.txt

# Or using poetry
poetry install
```

### 2. Setup Environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Initialize Database

```bash
# Run migrations
alembic upgrade head

# Optional: Seed database
python scripts/seed_db.py
```

### 4. Run Server

```bash
# Development
uvicorn app.main:app --reload

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5. Access API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
backend/
├── app/
│   ├── api/              # API endpoints
│   ├── core/             # Core functionality
│   ├── models/           # Database models
│   ├── repositories/     # Data access layer
│   ├── services/         # Business logic
│   ├── schemas/          # Pydantic schemas
│   └── main.py           # Application entry
├── alembic/              # Database migrations
├── tests/                # Test suite
└── requirements.txt      # Dependencies
```

## Development

### Run Tests

```bash
pytest
```

### Code Formatting

```bash
black app/
isort app/
```

### Type Checking

```bash
mypy app/
```

## Documentation

See [docs/](../docs/) for complete documentation:
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md)
- [STANDARDS.md](../docs/STANDARDS.md)
- [API_GUIDELINES.md](../docs/API_GUIDELINES.md)
