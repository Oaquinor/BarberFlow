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
│   ├── middleware/                  # HTTP security headers; CORS is in app.main
│   │   └── security_headers.py      # Browser headers and no-store API responses
│   ├── websocket/                   # Manager prototype; no mounted route
│   │   └── manager.py               # Not connected to appointment events
│   │
│   ├── services/                    # Business logic and delivery
│   │   ├── performance_service.py
│   │   ├── notification_service.py
│   │   └── notification_outbox.py   # MySQL outbox and reminder scheduling
│   ├── analytics/                   # Analytics service exports
│   ├── ai/demand_forecast.py        # Explainable tenant demand baseline
│   ├── notifications/               # Exports MySQL-backed notification services
│   ├── workers/                     # Worker package marker
│   │
│   ├── utils/                       # 🛠️ Utilities
│   │   ├── __init__.py
│   │   ├── datetime.py              # Datetime helpers
│   │   ├── validators.py            # Custom validators
│   │   └── formatters.py            # Data formatters
│   │
│   └── tests/                       # MySQL integration and unit coverage
│
├── alembic/                         # 📦 Database Migrations
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
├── scripts/notification_worker.py  # MySQL notification outbox worker
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

## 🔔 Actualizaciones operativas

El backend persiste notificaciones para los usuarios de la barbería y el frontend consulta su bandeja cada 60 segundos mientras la sesión está abierta. No hay servidor WebSocket ni eventos en tiempo real configurados.

---

## 📊 Analítica

`PerformanceService` calcula métricas del barbero a partir de citas y pagos de la barbería. `DemandForecastService` calcula el promedio histórico semanal por día/hora y lo combina con reservas próximas. La ruta de pronóstico está protegida para owners y deriva el tenant de la sesión autenticada. Ambos servicios usan datos MySQL existentes; no hay almacenamiento de analítica separado.

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

Operaciones de reservas y cobros escriben notificaciones internas y entregas email/WhatsApp en MySQL dentro de su transacción. `notification-worker` procesa la outbox con idempotencia, leases y reintentos. No hay servicio push configurado; el paquete WebSocket existente es un prototipo sin ruta ni emisiones conectado a los flujos.

---

## 🤖 Inteligencia y pronóstico

El módulo `app.ai.demand_forecast` calcula una referencia estadística por tenant: promedio de servicios completados por día de semana y hora en las 12 semanas anteriores, más las reservas ya confirmadas en el periodo previsto. No envía datos a proveedores externos ni presenta esta heurística como un modelo de aprendizaje automático. La ruta `GET /api/v1/analytics/demand-forecast` es exclusiva del owner autenticado. Incluye tamaño de muestra y confianza para que el panel no oculte la incertidumbre cuando hay pocos datos.

El sistema todavía no ofrece recomendaciones generativas, predicción entrenada ni análisis de cohortes. Esas funciones requieren criterios de negocio y datos suficientes antes de prometerlas.

La extensión de este módulo debe comenzar con objetivos de producto verificables, muestras suficientes y métricas de calidad. Hasta entonces, la API expone solo este pronóstico histórico transparente.

---

## 🚀 Scalability Considerations

### Horizontal Scaling
- La API no guarda sesión en memoria; los refresh tokens se persisten en MySQL.
- Ejecutar varias instancias requiere una base MySQL compartida y configuración de conexión/pool adecuada.

### Database Optimization
- Indexes on foreign keys
- Query optimization
- Connection pooling

### Caching Strategy
- No hay caché Redis activa; las lecturas van a MySQL.

### Background Jobs
- `scripts/notification_worker.py` procesa la outbox MySQL y programa recordatorios.
- Entrega SMTP/WhatsApp con reintentos persistidos; no se usa Celery.

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
5. **Transactional outbox** - MySQL records operational email and WhatsApp deliveries
6. **Factory Pattern** - Object creation
7. **Singleton Pattern** - Configuration management

---

**© 2024 NOVENTIA GROUP - Enterprise Architecture**
