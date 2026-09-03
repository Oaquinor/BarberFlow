# 🚀 KingFlow Barber - Quick Start Guide

Get up and running in **5 minutes**!

---

## 📋 Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Git

---

## ⚡ Quick Start (Development)

### 1. Clone Repository

```bash
git clone <repository-url>
cd kingflow-barber
```

### 2. Setup Database

```bash
# Start PostgreSQL and create database
createdb kingflow_barber

# Or using PostgreSQL shell:
psql postgres
CREATE DATABASE kingflow_barber;
\q
```

### 3. Setup Backend

```bash
cd backend

# Create virtual environment
python3.12 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env

# Edit .env with your database URL
# DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/kingflow_barber

# Run migrations
alembic upgrade head

# Seed database with test data
python scripts/seed_db.py

# Start server
uvicorn app.main:app --reload
```

### 4. Access API

Open browser to:
- **API Docs**: http://localhost:8000/docs
- **API**: http://localhost:8000/api/v1

---

## 🎯 Test Accounts (After Seeding)

| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@kingflow.com | Admin123! |
| Owner | owner@kingsbarbershop.com | Owner123! |
| Barber | mike@kingsbarbershop.com | Barber123! |
| Client | client1@example.com | Client123! |

---

## 🐳 Quick Start (Docker)

Even faster with Docker Compose:

```bash
# Start all services
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head

# Seed database
docker-compose exec backend python scripts/seed_db.py

# View logs
docker-compose logs -f backend
```

Access:
- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs

---

## 📚 Next Steps

1. **Read Documentation**
   - [Architecture Guide](docs/ARCHITECTURE.md)
   - [Coding Standards](docs/STANDARDS.md)
   - [API Guidelines](docs/API_GUIDELINES.md)
   - [Database Schema](docs/DATABASE.md)

2. **Try API Endpoints**
   - Login: `POST /api/v1/auth/login`
   - Get Profile: `GET /api/v1/auth/me`
   - Create Appointment: `POST /api/v1/appointments`

3. **Run Tests**
   ```bash
   cd backend
   pytest
   ```

4. **Code Formatting**
   ```bash
   black app/
   isort app/
   ```

---

## 🔧 Common Commands

### Database

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# Reset database
alembic downgrade base
alembic upgrade head
```

### Development

```bash
# Run server with auto-reload
uvicorn app.main:app --reload

# Run tests
pytest

# Run tests with coverage
pytest --cov=app

# Format code
black app/
isort app/

# Type checking
mypy app/
```

### Docker

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f

# Rebuild
docker-compose build --no-cache

# Execute command in container
docker-compose exec backend bash
```

---

## 🐛 Troubleshooting

### Database Connection Error

```bash
# Check PostgreSQL is running
pg_isready

# Check connection manually
psql -U postgres -d kingflow_barber
```

### Module Not Found

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Port Already in Use

```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use different port
uvicorn app.main:app --port 8001
```

---

## 📞 Need Help?

- **Documentation**: Check `/docs` folder
- **Issues**: Create GitHub issue
- **Email**: support@noventiagroup.com

---

**Happy Coding! 💈**

**© 2024 NOVENTIA GROUP**
