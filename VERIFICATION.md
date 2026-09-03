# ✅ KingFlow Barber - Verification & Testing Guide

**How to verify everything is working correctly**

---

## 📋 Pre-Flight Checklist

### 1. File Structure Verification

Run these commands to verify all files exist:

```powershell
# Windows PowerShell
Get-ChildItem -Recurse -Directory | Select-Object Name

# Should see:
# backend, docs, alembic, app, api, core, models, repositories, services, schemas, tests, scripts
```

```bash
# Linux/Mac
find . -type d -maxdepth 3

# Should see all project directories
```

---

## 🔧 Installation Verification

### Step 1: Check Python Version

```bash
python --version
# Should show: Python 3.12.x or higher
```

### Step 2: Create Virtual Environment

```bash
cd backend
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt

# Verify installation
pip list | grep fastapi
pip list | grep sqlalchemy
pip list | grep alembic
```

---

## 🗄️ Database Verification

### Step 1: Check PostgreSQL

```bash
# Check if PostgreSQL is running
# Windows:
Get-Service -Name postgresql*

# Linux:
sudo systemctl status postgresql

# Mac:
brew services list
```

### Step 2: Create Database

```bash
# Using psql
psql -U postgres

CREATE DATABASE kingflow_barber;
CREATE USER kingflow WITH PASSWORD 'kingflow123';
GRANT ALL PRIVILEGES ON DATABASE kingflow_barber TO kingflow;
\q
```

### Step 3: Test Connection

```bash
psql -U kingflow -d kingflow_barber -h localhost

# Should connect successfully
```

---

## ⚙️ Configuration Verification

### Step 1: Environment Variables

```bash
cd backend
cp .env.example .env

# Edit .env
# Update DATABASE_URL with your credentials
```

### Step 2: Verify Configuration

```bash
python -c "from app.core.config import get_settings; print(get_settings())"

# Should print configuration without errors
```

---

## 🔄 Migration Verification

### Step 1: Check Alembic

```bash
alembic current
# Should show: (empty) or (head)
```

### Step 2: Run Migrations

```bash
alembic upgrade head

# Should see:
# INFO  [alembic.runtime.migration] Running upgrade  -> 001_initial
# INFO  [alembic.runtime.migration] Running upgrade 001_initial
```

### Step 3: Verify Tables

```bash
psql -U kingflow -d kingflow_barber

\dt
# Should show tables: users, barbershops, appointments, subscriptions

\d users
# Should show user table structure

\q
```

---

## 🌱 Seeding Verification

### Step 1: Seed Database

```bash
python scripts/seed_db.py

# Should see:
# 🌱 Starting database seeding...
# ✅ Database seeded successfully!
# 📋 Test Accounts:
# (account list)
```

### Step 2: Verify Data

```bash
psql -U kingflow -d kingflow_barber

SELECT email, role FROM users;
# Should show test users

SELECT name FROM barbershops;
# Should show King's Barbershop

\q
```

---

## 🚀 Server Verification

### Step 1: Start Server

```bash
uvicorn app.main:app --reload

# Should see:
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup complete.
```

### Step 2: Test Endpoints

Open browser:

1. **Root endpoint**
   - http://localhost:8000
   - Should see: `{"name":"KingFlow Barber API",...}`

2. **Health check**
   - http://localhost:8000/health
   - Should see: `{"status":"healthy"}`

3. **API Documentation**
   - http://localhost:8000/docs
   - Should see Swagger UI

4. **Alternative docs**
   - http://localhost:8000/redoc
   - Should see ReDoc documentation

---

## 🧪 API Testing

### Test 1: Register User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPass123",
    "first_name": "Test",
    "last_name": "User",
    "phone": "+1234567890"
  }'

# Should return: {"success":true,"message":"User registered successfully",...}
```

### Test 2: Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@kingflow.com",
    "password": "Admin123!"
  }'

# Should return: {"access_token":"...", "refresh_token":"...", ...}
# Save the access_token for next tests
```

### Test 3: Get Current User

```bash
# Replace <TOKEN> with access_token from login
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <TOKEN>"

# Should return: {"success":true,"data":{"id":1,"email":"admin@kingflow.com",...}}
```

### Test 4: Create Appointment

```bash
# Use token from login
curl -X POST http://localhost:8000/api/v1/appointments \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": 6,
    "barber_id": 3,
    "scheduled_time": "2024-12-25T10:00:00Z",
    "service_type": "haircut",
    "estimated_duration": 30
  }'

# Should return: {"success":true,"message":"Appointment created successfully",...}
```

---

## 🔬 Test Suite Verification

### Run All Tests

```bash
pytest

# Should see:
# ====== test session starts ======
# collected X items
# tests/test_auth.py::test_register_user PASSED
# tests/test_auth.py::test_login_success PASSED
# ...
# ====== X passed in X.XXs ======
```

### Run Specific Test

```bash
pytest tests/test_auth.py::test_login_success -v

# Should show detailed test execution
```

### Run with Coverage

```bash
pytest --cov=app

# Should show coverage report
```

---

## 🐳 Docker Verification

### Test Docker Compose

```bash
docker-compose up -d

# Should start:
# - kingflow_db (PostgreSQL)
# - kingflow_redis (Redis)
# - kingflow_backend (FastAPI)
```

### Check Containers

```bash
docker ps

# Should show 3 running containers
```

### Test Backend Container

```bash
docker-compose exec backend alembic upgrade head
docker-compose exec backend python scripts/seed_db.py

# Then test API at http://localhost:8000
```

### View Logs

```bash
docker-compose logs -f backend

# Should show server logs
```

---

## 🔍 Code Quality Verification

### Check Formatting

```bash
# Check if code needs formatting
black app/ --check

# Format code
black app/
```

### Check Imports

```bash
# Check import order
isort app/ --check

# Fix imports
isort app/
```

### Type Checking

```bash
mypy app/

# Should show no type errors (or acceptable warnings)
```

---

## ✅ Final Verification Checklist

Run through this checklist:

- [ ] Python 3.12+ installed
- [ ] Virtual environment created and activated
- [ ] All dependencies installed (`pip list` shows packages)
- [ ] PostgreSQL running
- [ ] Database created (`kingflow_barber`)
- [ ] .env file configured
- [ ] Migrations run successfully
- [ ] Database seeded with test data
- [ ] Server starts without errors
- [ ] API documentation accessible (http://localhost:8000/docs)
- [ ] Health endpoint working (http://localhost:8000/health)
- [ ] Registration endpoint working
- [ ] Login endpoint working
- [ ] Protected endpoint working (with token)
- [ ] Tests passing (`pytest`)
- [ ] Docker setup working (optional)

---

## 🐛 Common Issues & Solutions

### Issue: Database connection error

**Solution:**
```bash
# Check PostgreSQL is running
sudo systemctl start postgresql

# Verify credentials in .env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/kingflow_barber
```

### Issue: Module not found

**Solution:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue: Port 8000 already in use

**Solution:**
```bash
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac:
lsof -ti:8000 | xargs kill -9

# Or use different port:
uvicorn app.main:app --port 8001
```

### Issue: Alembic migration fails

**Solution:**
```bash
# Reset migrations
alembic downgrade base
alembic upgrade head

# Or recreate database
dropdb kingflow_barber
createdb kingflow_barber
alembic upgrade head
```

### Issue: Tests fail

**Solution:**
```bash
# Create test database
createdb kingflow_barber_test

# Update test configuration if needed
# Run tests with verbose output
pytest -v
```

---

## 📊 Performance Verification

### Test API Response Time

```bash
# Using curl with timing
time curl http://localhost:8000/health

# Should respond in < 100ms
```

### Load Testing (Optional)

```bash
# Install Apache Bench
# Then:
ab -n 1000 -c 10 http://localhost:8000/health

# Should handle 1000 requests without errors
```

---

## 📞 Need Help?

If verification fails:

1. Check this guide step-by-step
2. Review logs for error messages
3. Check documentation in `/docs`
4. Ensure all prerequisites are met
5. Try Docker setup as alternative

---

## ✨ Success Indicators

You know everything is working when:

- ✅ Server starts without errors
- ✅ API docs load at /docs
- ✅ Health endpoint returns {"status":"healthy"}
- ✅ Login returns valid tokens
- ✅ Protected endpoints work with token
- ✅ All tests pass
- ✅ Database has test data
- ✅ No Python errors in logs

---

**🎉 Congratulations! KingFlow Barber is ready for development!**

**Next Steps:**
1. Explore API documentation
2. Try creating appointments
3. Read architecture docs
4. Start building features

---

**© 2024 NOVENTIA GROUP - Verification Guide**
