# KingFlow Barber - Database Schema

**Database Design Documentation**

---

## Overview

KingFlow Barber uses **MySQL 8** with a **multi-tenant architecture** where each barbershop is isolated by `barbershop_id`. The application uses SQLAlchemy's synchronous `mysql+pymysql` driver for the currently mounted API.

---

## Entity Relationship Diagram

```
┌─────────────────┐
│  Subscriptions  │
└────────┬────────┘
         │
         │ 1:1
         ↓
┌─────────────────┐        ┌──────────────┐
│   Barbershops   │←──────→│    Users     │
└────────┬────────┘   1:N  └──────┬───────┘
         │                         │
         │ 1:N                     │ 1:N
         ↓                         ↓
┌─────────────────────────────────┐
│         Appointments            │
└─────────────────────────────────┘
```

---

## Tables

### barber_availability_blocks

La migración `018_barber_availability_blocks` guarda los rangos futuros en los que un barbero no acepta citas. Cada fila referencia su tenant y barbero, almacena inicio/fin UTC, motivo opcional y metadatos de soft delete. Se indexa por barbero y rango para filtrar turnos públicos existentes y rechazar turnos que se intenten generar durante la ausencia. El endpoint serializa la operación con creación y reserva de turnos y rechaza el cambio si hay citas activas en el rango. Cancelar una ausencia restaura la disponibilidad anterior sin modificar las filas de turnos.

### client_account_verifications

La migración `033_client_accounts` guarda hashes SHA-256 de enlaces de verificación de correo, su fecha de vencimiento y uso/revocación. Los tokens originales solo se envían por correo; expiran en 30 minutos y son de un solo uso. El limpiador de registros de autenticación elimina tokens expirados.

### client_account_shop_links

La migración `033_client_accounts` vincula una identidad global de cliente verificada con un registro CRM independiente por barbería. Hay unicidad por `(account_user_id, barbershop_id)` y por `crm_client_user_id`. No se deduce pertenencia a partir del teléfono; las citas antiguas se añaden mediante su token privado de seguimiento.

### 1. subscriptions

Barbershop subscription plans.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| plan | VARCHAR(50) | Plan type (free, basic, professional, enterprise) |
| status | VARCHAR(50) | Status (active, inactive, cancelled, expired) |
| current_period_start | TIMESTAMP | Current billing period start |
| current_period_end | TIMESTAMP | Current billing period end |
| max_barbers | INTEGER | Maximum barbers allowed |
| max_appointments_per_month | INTEGER | Maximum appointments per month |
| max_clients | INTEGER | Maximum clients |
| stripe_subscription_id | VARCHAR(255) | Legacy compatibility column; unused, with no Stripe integration |
| stripe_customer_id | VARCHAR(255) | Legacy compatibility column; unused, with no Stripe integration |
| trial_start | TIMESTAMP | Trial period start |
| trial_end | TIMESTAMP | Trial period end |
| is_trial | BOOLEAN | Is in trial period |
| auto_renew | BOOLEAN | Administrative indicator only; automatic charges are not processed or scheduled |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |
| is_deleted | BOOLEAN | Soft delete flag |
| deleted_at | TIMESTAMP | Deletion timestamp |

**Indexes:**
- PRIMARY KEY (id)

---

### 2. barbershops

Barbershop entities (tenants in multi-tenant architecture).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| name | VARCHAR(200) | Barbershop name |
| slug | VARCHAR(100) | URL-friendly slug (unique) |
| description | VARCHAR(1000) | Description |
| email | VARCHAR(255) | Contact email |
| phone | VARCHAR(20) | Contact phone |
| website | VARCHAR(255) | Website URL |
| address_line1 | VARCHAR(255) | Address line 1 |
| address_line2 | VARCHAR(255) | Address line 2 |
| city | VARCHAR(100) | City |
| state | VARCHAR(100) | State/Province |
| postal_code | VARCHAR(20) | Postal/ZIP code |
| country | VARCHAR(100) | Country |
| latitude | VARCHAR(50) | GPS latitude |
| longitude | VARCHAR(50) | GPS longitude |
| logo_url | VARCHAR(500) | Logo image URL |
| cover_image_url | VARCHAR(500) | Cover image URL |
| opening_time | TIME | Default opening time |
| closing_time | TIME | Default closing time |
| timezone | VARCHAR(50) | Timezone |
| currency | VARCHAR(3) | Currency code (USD, EUR, etc.) |
| appointment_duration_minutes | INTEGER | Default appointment duration |
| cancellation_window_hours | INTEGER NOT NULL DEFAULT 0 | Minimum notice for public cancellation/rescheduling; 0 preserves unrestricted pre-start changes |
| is_active | BOOLEAN | Is active |
| is_verified | BOOLEAN | Is verified |
| subscription_id | INTEGER | Foreign key to subscriptions |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |
| is_deleted | BOOLEAN | Soft delete flag |
| deleted_at | TIMESTAMP | Deletion timestamp |

**Indexes:**
- PRIMARY KEY (id)
- UNIQUE INDEX (slug)
- FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)

---

### 3. users

System users (super admin, barbershop owners, barbers, clients).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| email | VARCHAR(255) | Email address (unique) |
| password_hash | VARCHAR(255) | Hashed password |
| first_name | VARCHAR(100) | First name |
| last_name | VARCHAR(100) | Last name |
| phone | VARCHAR(20) | Phone number |
| role | VARCHAR(50) | User role (super_admin, barbershop_owner, barber, client) |
| is_active | BOOLEAN | Is account active |
| is_verified | BOOLEAN | Is email verified |
| barbershop_id | INTEGER | Foreign key to barbershops (null for super admin) |
| avatar_url | VARCHAR(500) | Avatar image URL |
| bio | VARCHAR(500) | Biography |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |
| is_deleted | BOOLEAN | Soft delete flag |
| deleted_at | TIMESTAMP | Deletion timestamp |

**Indexes:**
- PRIMARY KEY (id)
- UNIQUE INDEX (email)
- INDEX (barbershop_id)
- INDEX (`barbershop_id`, `role`, `is_deleted`, `id`) para listados y conteos paginados por tenant
- FOREIGN KEY (barbershop_id) REFERENCES barbershops(id)

La migración `026_users_client_listing` añade el índice compuesto sin cambiar ni eliminar registros. Al revertirla, se elimina ese índice; si MySQL lo estaba usando como soporte de la clave foránea, se conserva un índice sencillo sobre `barbershop_id` para mantener la integridad referencial.

---

### 4. appointments

Appointment bookings between clients and barbers.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| barbershop_id | INTEGER | Foreign key to barbershops (tenant isolation) |
| client_id | INTEGER | Foreign key to users (client) |
| barber_id | INTEGER | Foreign key to users (barber) |
| scheduled_time | TIMESTAMP | Scheduled appointment time |
| estimated_duration | INTEGER | Estimated duration in minutes |
| actual_start_time | TIMESTAMP | Actual start time |
| actual_end_time | TIMESTAMP | Actual end time |
| service_type | VARCHAR(100) | Service name snapshot captured when the appointment is created |
| service_price | INTEGER | Price in cents |
| status | VARCHAR(50) | Status (pending, confirmed, in_progress, completed, cancelled, no_show) |
| client_notes | TEXT | Notes from client |
| barber_notes | TEXT | Notes from barber |
| cancelled_by | INTEGER | User ID who cancelled |
| cancellation_reason | TEXT | Cancellation reason |
| checked_in_at | TIMESTAMP | Client check-in time |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |
| is_deleted | BOOLEAN | Soft delete flag |
| deleted_at | TIMESTAMP | Deletion timestamp |

**Indexes:**
- PRIMARY KEY (id)
- INDEX (barbershop_id)
- INDEX (client_id)
- INDEX (barber_id)
- INDEX (scheduled_time)
- INDEX (status)
- INDEX (barbershop_id, created_at) for tenant-scoped monthly appointment usage
- FOREIGN KEY (barbershop_id) REFERENCES barbershops(id)
- FOREIGN KEY (client_id) REFERENCES users(id)
- FOREIGN KEY (barber_id) REFERENCES users(id)
- FOREIGN KEY (cancelled_by) REFERENCES users(id)

---

## Multi-Tenant Isolation

All tenant-specific tables include `barbershop_id` for data isolation:

```sql
-- Example query with tenant isolation
SELECT * FROM appointments
WHERE barbershop_id = :current_barbershop_id
AND is_deleted = FALSE;
```

---

## Soft Delete Pattern

All tables implement soft delete:
- `is_deleted` (BOOLEAN): Flag for deleted records
- `deleted_at` (TIMESTAMP): When record was deleted

```sql
-- Soft delete
UPDATE appointments
SET is_deleted = TRUE, deleted_at = NOW()
WHERE id = :appointment_id;

-- Restore
UPDATE appointments
SET is_deleted = FALSE, deleted_at = NULL
WHERE id = :appointment_id;
```

---

## Timestamp Tracking

All tables include:
- `created_at`: When record was created
- `updated_at`: When record was last modified (auto-updated)

---

## Operación MySQL agregada por migraciones

La cadena vigente termina en `025_perf_day_unique` y todas las conexiones de la aplicación usan `mysql+pymysql`.

| Revisión | Cambio |
|---|---|
| `006_appointment_tracking_token` | Hash único para seguimiento privado de cita |
| `007_refresh_sessions` | Sesiones refresh con expiración y revocación |
| `008_payments_cash_register` | Pagos únicos por cita y cierre de caja por barbería, usuario y fecha |
| `009_login_attempt_limits` | Contadores hash de intentos fallidos y bloqueos temporales |
| `010_audit_logs` | Eventos sensibles con actor, tenant, objeto y detalles |
| `011_seed_achievements` | Catálogo persistente de logros calculables |
| `012_subscription_payments` | Registro de cobros SaaS externos efectivamente recibidos |
| `013_commission_currency` | Moneda de origen y backfill en cada comisión |
| `014_align_mysql_schema` | Alinea nulabilidad, claves foráneas e índices con los modelos SQLAlchemy preservando datos existentes |
| `015_barber_commissions` | Añade tasas configurables por barbero y comisiones vinculadas de forma única a pagos de citas |
| `016_in_app_notifications` | Bandeja persistente de eventos operativos con destinatario, tenant, idempotencia y estado de lectura |
| `017_notification_delivery_outbox` | Cola MySQL idempotente para SMTP/WhatsApp con reintentos y programación de recordatorios |
| `018_barber_availability_blocks` | Bloqueos de disponibilidad del barbero con reversión protegida ante rangos con citas activas |
| `019_platform_settings` | Parámetros no secretos para habilitar el registro y definir los días iniciales de suscripción free |
| `020_password_reset_tokens` | Tokens hash de recuperación de un solo uso con expiración y revocación |
| `021_user_auth_version` | Versión de credenciales para invalidar access tokens tras cambio/recuperación de contraseña |
| `022_auth_record_retention_index` | Índice para depurar en lotes acotados los buckets de autenticación vencidos |
| `023_persist_support_tickets` | Bandeja MySQL de solicitudes de soporte, estado y vínculo opcional a barbería; downgrade protegido si existen tickets |
| `024_service_name_100` | Amplía a 100 caracteres el snapshot del servicio de una cita; el downgrade rechaza snapshots más largos |
| `025_perf_day_unique` | Garantiza una fila diaria por barbería/barbero/fecha; aborta sin borrar ni fusionar datos si detecta duplicados existentes |
| `026_users_client_listing` | Índice compuesto para listados y conteos de usuarios por barbería, rol y estado de eliminación |
| `027_appointment_monthly_usage` | Índice compuesto de barbería y fecha de creación para aplicar y mostrar los límites mensuales de citas |

`support_tickets` conserva el mensaje y los datos de contacto para que el equipo los consulte aunque falle SMTP. `notification_sent` indica si se notificó por correo; los cambios de estado requieren `super_admin` y se guardan en auditoría.

Los importes operativos se guardan en centavos enteros. Las fechas de cita y pago se guardan como UTC sin zona en MySQL; el negocio las convierte usando su zona IANA para presentación y cierres diarios. Las migraciones son aditivas y no borran datos operativos al actualizar.

CI valida el avance desde una base vacía hasta `head`, el retroceso de la base descartable de migraciones hasta `base` y una nueva aplicación hasta `head`, usando MySQL 8.4. Los downgrades que eliminarían datos de negocio, auditoría, autenticación, preferencias, notificaciones, pagos, logros o soporte se niegan intencionalmente; las revisiones con semillas solo eliminan valores originales no utilizados. Realiza una reversión de producción solo después de respaldar y revisar los datos afectados.

Los modelos `affiliates` y `commissions` registran el programa de referidos SaaS. `barber_commissions` es independiente: se origina en pagos de servicios, se guarda en la moneda del tenant y se liquida por su propietario. Los cobros SaaS externos se registran en `subscription_payments` y solo después se calculan comisiones de afiliados. `in_app_notifications` es la bandeja del usuario; `notification_deliveries` conserva entregas SMTP/WhatsApp pendientes, enviadas o fallidas, con clave idempotente y reintentos.

---

**© 2024 NOVENTIA GROUP - Database Documentation**
