# 🚀 KingFlow Barber - Quick Start Guide

> **Guía heredada, no operativa:** algunos comandos, rutas y ejemplos de este documento ya no coinciden con el repositorio. No ejecutes instrucciones de rollback/reset aquí sin una base desechable. Usa el [README vigente](README.md) y la [guía de validación actual](VALIDATION_GUIDE.md); la única base soportada es MySQL.

Get up and running in **5 minutes**!

---

## 📋 Prerequisites

- Python 3.12+
- MySQL 8.0+
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
# Start a local MySQL server, then create the application database and user.
mysql -u root -p
CREATE DATABASE kingflow_barber CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kingflow'@'localhost' IDENTIFIED BY 'choose-a-local-password';
GRANT ALL PRIVILEGES ON kingflow_barber.* TO 'kingflow'@'localhost';
FLUSH PRIVILEGES;
EXIT;
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
# For Docker Compose, MySQL is published to localhost:3307. The backend container uses db:3306.
# DATABASE_URL=mysql+pymysql://USER:PASSWORD@localhost:3307/kingflow_barber

# Run migrations
alembic upgrade head

# Create the first platform administrator interactively
python -m scripts.create_admin

# Start server
uvicorn app.main:app --reload
```

### 4. Access API

Open browser to:
- **API Docs**: http://localhost:8000/docs
- **API**: http://localhost:8000/api/v1

---

## 🔐 Initial administrator

After running migrations, create an administrator interactively:

```bash
cd backend
python -m scripts.create_admin
```

KingFlow does not ship with reusable demo or default login credentials. Disposable demo records can be created only in development with `ENVIRONMENT=development python -m scripts.seed_db --allow-demo-data`; the script asks for confirmation and refuses to alter an existing demo tenant.

---

## 🐳 Quick Start (Docker)

Even faster with Docker Compose:

```bash
# Start all services
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head

# Optional: create disposable demo records; only use on a development database
docker-compose exec backend python -m scripts.seed_db --allow-demo-data

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
   - Public appointment flow: `GET /api/v1/public/{slug}/slots`, then `POST /api/v1/public/{slug}/appointments`

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
# Check MySQL is running
mysqladmin ping -h localhost -u kingflow -p

# Check connection manually
mysql -u kingflow -p kingflow_barber
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
