# KingFlow Barber - Coding Standards

**NOVENTIA GROUP - Enterprise Development Standards**

> Estas son convenciones generales. Para la arquitectura implementada, consulta `docs/ARCHITECTURE.md`. KingFlow usa frontend JavaScript/PWA, FastAPI, SQLAlchemy síncrono y MySQL 8 mediante PyMySQL. No copies ejemplos que dependan de `AsyncSession`, SQLite o módulos no conectados.

---

## 🎯 Philosophy

This project prioritizes:

1. **Simplicity** over complexity
2. **Readability** over cleverness
3. **Maintainability** over quick hacks
4. **Modularity** over monolithic code
5. **Clarity** over brevity

---

## ⚠️ CRITICAL RULES

### Rule #1: Simplicity First

**IF** there's a simpler way to do something:
→ **ALWAYS** use the simpler way.

**NEVER:**
- ❌ Write complex code to look smart
- ❌ Use advanced features unnecessarily
- ❌ Create abstractions prematurely
- ❌ Optimize before measuring

**ALWAYS:**
- ✅ Write clear, readable code
- ✅ Use simple solutions first
- ✅ Refactor when needed
- ✅ Think about future maintainers

---

### Rule #2: Single Responsibility

Every function, class, and module should do **ONE THING** well.

**Bad:**
```python
def process_appointment(appointment_id):
    # Validates
    # Sends notifications
    # Updates database
    # Logs events
    # Calculates commissions
    # Updates analytics
    pass  # 200 lines of mixed responsibilities
```

**Good:**
```python
def process_appointment(appointment_id: int) -> Appointment:
    """Process a single appointment."""
    appointment = _validate_appointment(appointment_id)
    _update_appointment_status(appointment)
    _notify_participants(appointment)
    _calculate_commissions(appointment)
    _track_analytics(appointment)
    return appointment
```

---

### Rule #3: Keep request handlers focused

Handlers authenticate and validate the request, enforce role and tenant access,
orchestrate the use case, and return the endpoint's documented response. Put
shared or substantial business rules in an existing service; do not add a
service/repository layer only to satisfy a template. Related database writes
must use the transaction boundary required by the flow. Active handlers use
synchronous SQLAlchemy sessions; do not `await` database calls.

---

## 📝 Naming Conventions

### Variables & Functions: `snake_case`

```python
# Variables
current_client = get_current_client()
appointment_time = calculate_time()
commission_amount = 0.0

# Functions
def calculate_commission(amount: float) -> float:
    pass

def send_notification(user_id: int) -> None:
    pass
```

### Classes: `PascalCase`

```python
class AppointmentService:
    pass

class ClientRepository:
    pass

class NotificationManager:
    pass
```

### Constants: `UPPER_CASE`

```python
MAX_APPOINTMENTS = 50
DEFAULT_TIMEOUT = 30
API_VERSION = "v1"
```

### Files: `snake_case`

```
appointment_service.py
client_repository.py
notification_manager.py
```

### Endpoints: resource-oriented paths

Follow the existing versioned API and resource naming. Use HTTP methods to
express operations and preserve established contracts, for example
`GET /owner/clients` and `POST /public/{slug}/appointments`. Check
`docs/API_REFERENCE.md` before adding or renaming a route; do not introduce
action-style paths just to force a naming convention.

---

## 🏗️ Architecture Layers

Follow the structure that exists in the repository; do not add layers only to match a sample architecture.

- `models/`: SQLAlchemy entities and relationships.
- `schemas/`: Pydantic request and response validation.
- `api/v1/`: FastAPI routes registered in `app/api/v1/__init__.py`. Enforce authentication, role, and tenant checks on the server.
- `services/`: use case logic when shared or substantial orchestration warrants it. Active API handlers are split between `api/v1/endpoints/platform.py` (authentication, registration, public booking, agenda and checkout), `api/v1/endpoints/owner.py` (team, commissions and clients), and `api/v1/endpoints/admin.py` (platform administration).
- `core/database/`: synchronous SQLAlchemy sessions backed only by MySQL 8 through `mysql+pymysql://`.
- `alembic/`: all schema changes must be versioned migrations.

Do not assume a file is active because it exists. Verify router registration and actual imports. The former unmounted async appointment and service-mode modules were removed; the active operational flow is synchronous SQLAlchemy over MySQL and is documented in `docs/API_REFERENCE.md`.

Active request handlers use synchronous database operations (`Session.query`, `Session.execute`, `commit`, `rollback`). FastAPI endpoints may be declared `async` for async I/O, but synchronous SQLAlchemy calls must not be awaited. Prefer ordinary `def` handlers for database-bound synchronous work where appropriate.

---

## 🎯 Function Standards

### Keep Functions Small

Keep functions focused and easy to review. Line counts are a prompt to inspect
responsibility, not a hard limit; split code when it improves cohesion without
adding layers that obscure the actual flow.

### One Level of Abstraction

```python
# Good - Same abstraction level
def process_appointment(appointment_id: int) -> None:
    appointment = fetch_appointment(appointment_id)
    validate_appointment(appointment)
    update_status(appointment)
    notify_participants(appointment)

# Bad - Mixed abstraction levels
def process_appointment(appointment_id: int) -> None:
    appointment = db.query(Appointment).filter_by(id=appointment_id).first()
    if appointment.status == "pending":
        appointment.status = "confirmed"
        send_email(appointment.client.email)
        db.commit()
```

### Clear Function Names

Function names should clearly state what they do:

```python
# Good
def calculate_total_commission(sales: list[Sale]) -> float:
    pass

def send_appointment_reminder(appointment: Appointment) -> None:
    pass

# Bad
def process(data):
    pass

def do_stuff(x, y):
    pass
```

---

## 📊 Type Hints (MANDATORY)

**ALL** functions must have type hints:

```python
# Required
def calculate_commission(amount: float, rate: float) -> float:
    return amount * rate

def get_user(user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()

def process_batch(items: list[Item]) -> dict[str, Any]:
    return {"processed": len(items)}
```

---

## 📋 Documentation Standards

### Docstrings for Public Functions

```python
def calculate_commission(amount: float, rate: float) -> float:
    """
    Calculate commission based on amount and rate.

    Args:
        amount: Total sale amount
        rate: Commission rate (0.0 to 1.0)

    Returns:
        Calculated commission amount

    Raises:
        ValueError: If rate is invalid
    """
    if not 0 <= rate <= 1:
        raise ValueError("Rate must be between 0 and 1")
    return amount * rate
```

### Comments Only When Needed

**Comment:**
- ✅ Complex algorithms
- ✅ Important business rules
- ✅ Non-obvious decisions

**Don't comment:**
- ❌ Obvious code
- ❌ What code does (code should be self-documenting)

```python
# Bad
# Increment counter by 1
counter += 1

# Good
# Reset counter at midnight for daily statistics
if is_midnight():
    counter = 0
```

---

## 🔄 DRY (Don't Repeat Yourself)

### Extract Repeated Logic

**Bad:**
```python
# In multiple places
if user.role == "admin" and user.is_active and not user.is_deleted:
    # Do something
```

**Good:**
```python
def can_access_admin(user: User) -> bool:
    """Check if user has admin access."""
    return user.role == "admin" and user.is_active and not user.is_deleted

if can_access_admin(user):
    # Do something
```

---

## 🧩 SOLID Principles

### Single Responsibility
Each class has one reason to change.

### Open/Closed
Open for extension, closed for modification.

### Liskov Substitution
Subtypes must be substitutable for base types.

### Interface Segregation
Many specific interfaces over one general.

### Dependency Inversion
Depend on abstractions, not concretions.

---

## 🚨 Error Handling

### Use Custom Exceptions

```python
# Define custom exceptions
class AppointmentNotFoundError(Exception):
    """Raised when appointment doesn't exist."""
    pass

class InvalidTimeSlotError(Exception):
    """Raised when time slot is invalid."""
    pass

# Use them
def get_appointment(appointment_id: int) -> Appointment:
    appointment = repository.get_by_id(appointment_id)
    if not appointment:
        raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")
    return appointment
```

### Never Silent Failures

```python
# Bad
try:
    do_something()
except:
    pass

# Good
try:
    do_something()
except SpecificException as e:
    logger.error(f"Failed to do something: {e}")
    raise
```

---

## 📦 Module Organization

### File Size
- **Target:** 100-300 lines
- **Maximum:** 500 lines (then split)

### Imports Order
1. Standard library
2. Third-party packages
3. Local application

```python
# Standard library
from datetime import datetime
from typing import Optional

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# Local
from app.models import Appointment
from app.services import AppointmentService
```

---

## 🧪 Testing Standards

### Test File Structure

Follow the current layout: backend MySQL integration/API tests live in
`backend/tests/`; frontend unit tests live in `frontend/tests/`, and Chromium
browser tests live in `frontend/browser-tests/`. Keep tests near the suite
that owns their fixtures and run the MySQL suite only against a dedicated
disposable database ending in `_test`.

### Test Naming
```python
def test_create_appointment_with_valid_data():
    pass

def test_create_appointment_with_invalid_time_raises_error():
    pass
```

---

## 🔒 Security Standards

### Never Hardcode Secrets
```python
# Bad
API_KEY = "abc123"

# Good
API_KEY = os.getenv("API_KEY")
```

### Always Validate Input
```python
@router.post("/appointments")
def create_appointment(data: AppointmentCreate):  # Pydantic valida la entrada
    pass
```

### Use Parameterized Queries
```python
# SQLAlchemy handles this automatically
query = select(User).where(User.id == user_id)
```

---

## 📊 API Response Standards

Keep each route's established response schema and error semantics. Do not
wrap all endpoints in a new generic envelope: active routes intentionally
return resource-specific objects, paginated collections, or FastAPI error
responses. Document contract changes in `docs/API_REFERENCE.md` and cover
success, validation, authorization, and not-found cases in tests.

---

## 🎨 Code Formatting

### Use Black
```bash
black app/
```

### Use isort
```bash
isort app/
```

### Use flake8
```bash
flake8 app/
```

---

## 🚀 Performance Guidelines

### Don't Optimize Prematurely
1. Write clean code first
2. Measure performance
3. Optimize bottlenecks only

### Use Async Properly

The active API uses synchronous SQLAlchemy and PyMySQL. Prefer ordinary `def`
handlers for database-bound requests. Use `async def` only when the awaited
I/O path is genuinely asynchronous; never await synchronous `Session` calls.
Do not add an async database driver or `AsyncSession` without an explicit
architecture decision and MySQL integration coverage.

---

## ✅ Code Review Checklist

Before committing, verify:

- [ ] Code follows naming conventions
- [ ] Functions are small and focused
- [ ] Type hints are present
- [ ] No business logic in endpoints
- [ ] No repeated code
- [ ] Proper error handling
- [ ] Tests are written
- [ ] Documentation is updated
- [ ] No secrets in code
- [ ] Imports are organized

---

## 🎯 Remember

> "Code is read 10x more than it's written. Write for the reader, not the writer."

> "Simple is better than complex. Complex is better than complicated."

> "If you can't explain it simply, you don't understand it well enough."

---

**© 2024 NOVENTIA GROUP - Enterprise Standards**
