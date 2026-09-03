# KingFlow Barber - Coding Standards

**NOVENTIA GROUP - Enterprise Development Standards**

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

### Rule #3: No Business Logic in Endpoints

**Endpoints ONLY:**
- ✅ Receive requests
- ✅ Validate input
- ✅ Call services
- ✅ Return responses

**Bad:**
```python
@router.post("/appointments")
async def create_appointment(data: dict):
    # 50 lines of business logic here
    pass
```

**Good:**
```python
@router.post("/appointments")
async def create_appointment(
    data: AppointmentCreate,
    service: AppointmentService = Depends()
) -> AppointmentResponse:
    """Create a new appointment."""
    appointment = await service.create_appointment(data)
    return AppointmentResponse(
        success=True,
        message="Appointment created successfully",
        data=appointment
    )
```

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

### Endpoints: `kebab-case`

```python
@router.post("/create-appointment")
@router.put("/finish-appointment")
@router.get("/client-history")
```

---

## 🏗️ Architecture Layers

### 1. Models (`models/`)
**Responsibility:** Database entities

```python
class Appointment(Base):
    """Database model for appointments."""
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    barber_id = Column(Integer, ForeignKey("barbers.id"))
```

### 2. Schemas (`schemas/`)
**Responsibility:** Input/output validation (DTOs)

```python
class AppointmentCreate(BaseModel):
    """Schema for creating appointments."""
    client_id: int
    barber_id: int
    scheduled_time: datetime
```

### 3. Repositories (`repositories/`)
**Responsibility:** Data access only

```python
class AppointmentRepository:
    """Handles appointment data access."""

    async def create(self, data: AppointmentCreate) -> Appointment:
        """Create appointment in database."""
        pass

    async def get_by_id(self, appointment_id: int) -> Appointment:
        """Retrieve appointment by ID."""
        pass
```

### 4. Services (`services/`)
**Responsibility:** Business logic ONLY

```python
class AppointmentService:
    """Handles appointment business logic."""

    async def create_appointment(self, data: AppointmentCreate) -> Appointment:
        """Create appointment with business validations."""
        # Business rules
        # Validations
        # Orchestration
        pass
```

### 5. API (`api/`)
**Responsibility:** HTTP layer only

```python
@router.post("/appointments")
async def create_appointment(
    data: AppointmentCreate,
    service: AppointmentService = Depends()
) -> StandardResponse:
    """Endpoint to create appointment."""
    result = await service.create_appointment(data)
    return StandardResponse(success=True, data=result)
```

---

## 🎯 Function Standards

### Keep Functions Small

**Target:** 10-20 lines per function
**Maximum:** 50 lines (then refactor)

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

async def get_user(user_id: int) -> User | None:
    return await repository.get_by_id(user_id)

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
```
tests/
├── unit/
│   ├── test_services.py
│   └── test_repositories.py
├── integration/
│   └── test_api.py
└── conftest.py
```

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
async def create_appointment(data: AppointmentCreate):  # Pydantic validates
    pass
```

### Use Parameterized Queries
```python
# SQLAlchemy handles this automatically
query = select(User).where(User.id == user_id)
```

---

## 📊 API Response Standards

### Standard Response Format

```python
class StandardResponse(BaseModel):
    success: bool
    message: str
    data: Any = None
    errors: list[str] = []

# Usage
return StandardResponse(
    success=True,
    message="Operation successful",
    data=result
)
```

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
```python
# For I/O operations
async def get_user(user_id: int) -> User:
    return await repository.get_by_id(user_id)

# Not for CPU operations
def calculate_complex_math(data: list) -> float:
    return sum(data) / len(data)
```

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
