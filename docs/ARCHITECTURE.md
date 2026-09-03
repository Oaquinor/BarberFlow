# KingFlow Barber - Architecture Guide

**NOVENTIA GROUP - Enterprise Architecture Documentation**

---

## 🏗️ Architectural Overview

KingFlow Barber follows **Clean Architecture** principles with a clear separation of concerns across multiple layers.

```
┌─────────────────────────────────────────────────────────────┐
│                     PRESENTATION LAYER                       │
│                  (FastAPI Endpoints / React)                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                        │
│                   (Services / Use Cases)                     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                      DOMAIN LAYER                            │
│                  (Models / Business Logic)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   INFRASTRUCTURE LAYER                       │
│            (Repositories / Database / External APIs)         │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Backend Structure

```
backend/
│
├── app/
│   ├── main.py                      # Application entry point
│   │
│   ├── api/                         # 🌐 Presentation Layer
│   │   ├── __init__.py
│   │   ├── deps.py                  # Shared dependencies
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── auth/                # Authentication endpoints
│   │       ├── appointments/        # Appointment management
│   │       ├── clients/             # Client management
│   │       ├── barbers/             # Barber management
│   │       ├── barbershops/         # Barbershop management
│   │       ├── affiliates/          # Affiliate system
│   │       ├── analytics/           # Analytics & reports
│   │       ├── subscriptions/       # Subscription management
│   │       ├── notifications/       # Notifications
│   │       └── admin/               # Admin panel
│   │
│   ├── services/                    # 🎯 Application Layer
│   │   ├── __init__.py
│   │   ├── appointment_service.py   # Appointment business logic
│   │   ├── client_service.py        # Client business logic
│   │   ├── barber_service.py        # Barber business logic
│   │   ├── affiliate_service.py     # Affiliate business logic
│   │   ├── notification_service.py  # Notification business logic
│   │   ├── analytics_service.py     # Analytics business logic
│   │   └── subscription_service.py  # Subscription business logic
│   │
│   ├── models/                      # 🗃️ Domain Layer
│   │   ├── __init__.py
│   │   ├── base.py                  # Base model
│   │   ├── user.py                  # User entity
│   │   ├── role.py                  # Role entity
│   │   ├── permission.py            # Permission entity
│   │   ├── barbershop.py            # Barbershop entity
│   │   ├── barber.py                # Barber entity
│   │   ├── client.py                # Client entity
│   │   ├── appointment.py           # Appointment entity
│   │   ├── subscription.py          # Subscription entity
│   │   ├── affiliate.py             # Affiliate entity
│   │   ├── commission.py            # Commission entity
│   │   ├── notification.py          # Notification entity
│   │   └── analytics.py             # Analytics entity
│   │
│   ├── repositories/                # 💾 Infrastructure Layer
│   │   ├── __init__.py
│   │   ├── base_repository.py       # Base repository pattern
│   │   ├── user_repository.py
│   │   ├── appointment_repository.py
│   │   ├── client_repository.py
│   │   ├── barber_repository.py
│   │   ├── affiliate_repository.py
│   │   └── notification_repository.py
│   │
│   ├── schemas/                     # 📋 DTOs (Data Transfer Objects)
│   │   ├── __init__.py
│   │   ├── common.py                # Shared schemas
│   │   ├── auth.py                  # Auth DTOs
│   │   ├── appointment.py           # Appointment DTOs
│   │   ├── client.py                # Client DTOs
│   │   ├── barber.py                # Barber DTOs
│   │   ├── affiliate.py             # Affiliate DTOs
│   │   └── notification.py          # Notification DTOs
│   │
│   ├── core/                        # ⚙️ Core Infrastructure
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   └── settings.py          # Application settings
│   │   ├── security/
│   │   │   ├── __init__.py
│   │   │   ├── jwt.py               # JWT handling
│   │   │   ├── password.py          # Password hashing
│   │   │   └── permissions.py       # Permission checks
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── session.py           # Database session
│   │   │   └── base.py              # Base setup
│   │   ├── logging/
│   │   │   ├── __init__.py
│   │   │   └── logger.py            # Logging configuration
│   │   ├── exceptions/
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Base exceptions
│   │   │   └── handlers.py          # Exception handlers
│   │   └── constants/
│   │       ├── __init__.py
│   │       └── enums.py             # Application enums
│   │
│   ├── middleware/                  # 🔧 Middleware
│   │   ├── __init__.py
│   │   ├── auth.py                  # Auth middleware
│   │   ├── logging.py               # Request logging
│   │   └── rate_limit.py            # Rate limiting
│   │
│   ├── websocket/                   # 🔌 Real-time Layer
│   │   ├── __init__.py
│   │   ├── manager.py               # WebSocket manager
│   │   ├── handlers.py              # WebSocket handlers
│   │   └── events.py                # WebSocket events
│   │
│   ├── notifications/               # 🔔 Notification System
│   │   ├── __init__.py
│   │   ├── email.py                 # Email notifications
│   │   ├── push.py                  # Push notifications
│   │   └── templates/               # Notification templates
│   │
│   ├── analytics/                   # 📊 Analytics Engine
│   │   ├── __init__.py
│   │   ├── calculator.py            # Metric calculations
│   │   └── reporter.py              # Report generation
│   │
│   ├── ai/                          # 🤖 AI Module (Future)
│   │   ├── __init__.py
│   │   ├── recommendations.py       # AI recommendations
│   │   └── predictions.py           # Predictive analytics
│   │
│   ├── workers/                     # ⚡ Background Jobs
│   │   ├── __init__.py
│   │   ├── celery_app.py            # Celery configuration
│   │   └── tasks.py                 # Background tasks
│   │
│   ├── utils/                       # 🛠️ Utilities
│   │   ├── __init__.py
│   │   ├── datetime.py              # Datetime helpers
│   │   ├── validators.py            # Custom validators
│   │   └── formatters.py            # Data formatters
│   │
│   └── tests/                       # 🧪 Test Suite
│       ├── __init__.py
│       ├── conftest.py              # Test configuration
│       ├── unit/                    # Unit tests
│       ├── integration/             # Integration tests
│       └── fixtures/                # Test fixtures
│
├── alembic/                         # 📦 Database Migrations
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
│
├── docs/                            # 📚 Documentation
│   ├── ARCHITECTURE.md
│   ├── STANDARDS.md
│   ├── API_GUIDELINES.md
│   └── DATABASE.md
│
├── scripts/                         # 🔨 Utility Scripts
│   ├── seed_db.py                   # Seed database
│   └── create_admin.py              # Create admin user
│
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Python project config
├── Dockerfile                       # Docker image
├── docker-compose.yml               # Docker services
├── .env.example                     # Environment template
├── .gitignore
└── README.md
```

---

## 🎯 Layer Responsibilities

### 1️⃣ Presentation Layer (API)

**Location:** `app/api/`

**Responsibility:**
- Receive HTTP requests
- Validate input (Pydantic)
- Call appropriate service
- Return HTTP responses
- Handle authentication
- Format responses

**NEVER:**
- ❌ Contain business logic
- ❌ Access database directly
- ❌ Perform calculations
- ❌ Make business decisions

**Example:**
```python
@router.post("/appointments")
async def create_appointment(
    data: AppointmentCreate,
    service: AppointmentService = Depends(get_appointment_service),
    current_user: User = Depends(get_current_user)
) -> StandardResponse:
    """Create a new appointment."""
    appointment = await service.create_appointment(data, current_user)
    return StandardResponse(
        success=True,
        message="Appointment created successfully",
        data=appointment
    )
```

---

### 2️⃣ Application Layer (Services)

**Location:** `app/services/`

**Responsibility:**
- Business logic implementation
- Use case orchestration
- Business rule validation
- Transaction coordination
- Error handling

**NEVER:**
- ❌ Access database directly (use repositories)
- ❌ Know about HTTP (status codes, headers)
- ❌ Format responses

**Example:**
```python
class AppointmentService:
    """Handles appointment business logic."""

    def __init__(self, repository: AppointmentRepository):
        self.repository = repository

    async def create_appointment(
        self,
        data: AppointmentCreate,
        user: User
    ) -> Appointment:
        """
        Create appointment with business validations.

        Business Rules:
        - Check barber availability
        - Validate time slot
        - Check client has no overlapping appointments
        - Send notification
        """
        await self._validate_time_slot(data)
        await self._check_barber_availability(data)

        appointment = await self.repository.create(data)
        await self._notify_participants(appointment)

        return appointment
```

---

### 3️⃣ Domain Layer (Models)

**Location:** `app/models/`

**Responsibility:**
- Define entities
- Represent business concepts
- Database schema
- Relationships

**Example:**
```python
class Appointment(Base):
    """Appointment entity - represents a booking."""

    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    barber_id = Column(Integer, ForeignKey("barbers.id"), nullable=False)
    scheduled_time = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="pending")

    # Relationships
    client = relationship("Client", back_populates="appointments")
    barber = relationship("Barber", back_populates="appointments")
```

---

### 4️⃣ Infrastructure Layer (Repositories)

**Location:** `app/repositories/`

**Responsibility:**
- Data access only
- CRUD operations
- Query building
- Data persistence

**NEVER:**
- ❌ Contain business logic
- ❌ Validate business rules
- ❌ Send notifications

**Example:**
```python
class AppointmentRepository:
    """Handles appointment data access."""

    def __init__(self, db: Session):
        self.db = db

    async def create(self, data: AppointmentCreate) -> Appointment:
        """Create appointment in database."""
        appointment = Appointment(**data.dict())
        self.db.add(appointment)
        await self.db.commit()
        await self.db.refresh(appointment)
        return appointment

    async def get_by_id(self, appointment_id: int) -> Appointment | None:
        """Retrieve appointment by ID."""
        return await self.db.get(Appointment, appointment_id)
```

---

## 🔄 Request Flow

```
1. HTTP Request
   ↓
2. FastAPI Endpoint (API Layer)
   ↓
3. Pydantic Validation (Schema)
   ↓
4. Authentication Check (Middleware/Dependency)
   ↓
5. Service Call (Application Layer)
   ↓
6. Business Logic Execution (Service)
   ↓
7. Repository Call (Infrastructure Layer)
   ↓
8. Database Operation
   ↓
9. Return to Service
   ↓
10. Additional Operations (Notifications, Events)
    ↓
11. Return to Endpoint
    ↓
12. Format Response (Schema)
    ↓
13. HTTP Response
```

---

## 🔐 Authentication Flow

```
1. User sends credentials (POST /auth/login)
   ↓
2. Auth endpoint receives request
   ↓
3. Auth service validates credentials
   ↓
4. Generate JWT access token + refresh token
   ↓
5. Return tokens to user
   ↓
6. User includes access token in subsequent requests
   ↓
7. Middleware validates token
   ↓
8. Extract user from token
   ↓
9. Inject user into endpoint
```

---

## 🏢 Multi-Tenant Architecture

### Tenant Isolation

Each barbershop is a separate tenant with:
- Isolated data
- Separate subscriptions
- Independent configurations

### Implementation

```python
class Appointment(Base):
    """All entities include tenant_id for isolation."""

    id = Column(Integer, primary_key=True)
    barbershop_id = Column(Integer, ForeignKey("barbershops.id"))  # Tenant
    # ... other fields
```

### Query Filtering

```python
async def get_appointments(self, barbershop_id: int):
    """Always filter by tenant."""
    return await self.db.query(Appointment)\
        .filter(Appointment.barbershop_id == barbershop_id)\
        .all()
```

---

## ⚡ Real-Time Architecture

### WebSocket Manager

```python
class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: dict[int, WebSocket] = {}

    async def connect(self, barbershop_id: int, websocket: WebSocket):
        """Connect client to barbershop room."""
        await websocket.accept()
        self.active_connections[barbershop_id] = websocket

    async def broadcast(self, barbershop_id: int, message: dict):
        """Broadcast to all connected clients."""
        websocket = self.active_connections.get(barbershop_id)
        if websocket:
            await websocket.send_json(message)
```

### Event Broadcasting

```python
# When appointment status changes
await websocket_manager.broadcast(
    barbershop_id=appointment.barbershop_id,
    message={
        "event": "appointment_updated",
        "data": appointment.dict()
    }
)
```

---

## 📊 Analytics Architecture

### Metric Calculation

```python
class AnalyticsCalculator:
    """Calculate business metrics."""

    async def calculate_average_service_time(
        self,
        barbershop_id: int,
        start_date: date,
        end_date: date
    ) -> float:
        """Calculate average service time."""
        appointments = await self.repository.get_completed_appointments(
            barbershop_id, start_date, end_date
        )

        total_time = sum(a.actual_duration for a in appointments)
        return total_time / len(appointments) if appointments else 0
```

---

## 🤝 Affiliate System Architecture

### Commission Calculation

```python
class AffiliateService:
    """Handles affiliate business logic."""

    async def calculate_commission(
        self,
        affiliate_id: int,
        sale_amount: float
    ) -> Commission:
        """
        Calculate commission based on affiliate tier.

        Business Rules:
        - Basic tier: 10%
        - Silver tier: 15%
        - Gold tier: 20%
        """
        affiliate = await self.repository.get_by_id(affiliate_id)
        rate = self._get_commission_rate(affiliate.tier)

        commission = Commission(
            affiliate_id=affiliate_id,
            amount=sale_amount * rate,
            status="pending"
        )

        return await self.repository.create_commission(commission)
```

---

## 🔔 Notification Architecture

### Notification Strategy Pattern

```python
class NotificationService:
    """Orchestrates notifications across channels."""

    def __init__(
        self,
        email_notifier: EmailNotifier,
        push_notifier: PushNotifier
    ):
        self.email_notifier = email_notifier
        self.push_notifier = push_notifier

    async def notify_appointment_created(self, appointment: Appointment):
        """Send notifications for new appointment."""
        await self.email_notifier.send(appointment.client.email, template="new_appointment")
        await self.push_notifier.send(appointment.client.device_token, message="Appointment confirmed")
```

---

## 🤖 AI Module Architecture (Future)

### Modular Design

```python
class RecommendationEngine:
    """AI recommendations - pluggable architecture."""

    async def recommend_barber(self, client_id: int) -> list[Barber]:
        """
        Recommend barbers based on:
        - Client history
        - Barber ratings
        - Availability
        - Service preferences
        """
        # AI logic here
        pass
```

---

## 🚀 Scalability Considerations

### Horizontal Scaling
- Stateless API servers
- Load balancer ready
- Session stored in Redis

### Database Optimization
- Indexes on foreign keys
- Query optimization
- Connection pooling

### Caching Strategy
- Redis for session storage
- Cache frequently accessed data
- Invalidation on updates

### Background Jobs
- Celery for async tasks
- Email sending
- Report generation
- Analytics calculation

---

## 🔒 Security Architecture

### Authentication
- JWT tokens
- Refresh token rotation
- Token expiration

### Authorization
- Role-based access control (RBAC)
- Permission checking
- Tenant isolation

### Data Protection
- Password hashing (bcrypt)
- SQL injection prevention (SQLAlchemy)
- Input validation (Pydantic)
- CORS configuration

---

## 📈 Monitoring & Logging

### Structured Logging

```python
logger.info(
    "Appointment created",
    extra={
        "appointment_id": appointment.id,
        "barbershop_id": appointment.barbershop_id,
        "user_id": current_user.id
    }
)
```

### Performance Tracking
- API response times
- Database query times
- Background job duration

---

## 🎯 Design Patterns Used

1. **Repository Pattern** - Data access abstraction
2. **Service Layer Pattern** - Business logic encapsulation
3. **Dependency Injection** - Loose coupling
4. **Strategy Pattern** - Notification channels
5. **Observer Pattern** - WebSocket events
6. **Factory Pattern** - Object creation
7. **Singleton Pattern** - Configuration management

---

**© 2024 NOVENTIA GROUP - Enterprise Architecture**
