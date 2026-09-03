# KingFlow Barber - Database Schema

**Database Design Documentation**

---

## Overview

KingFlow Barber uses **PostgreSQL** as the primary database with a **multi-tenant architecture** where each barbershop is isolated by `barbershop_id`.

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
| stripe_subscription_id | VARCHAR(255) | Stripe subscription ID |
| stripe_customer_id | VARCHAR(255) | Stripe customer ID |
| trial_start | TIMESTAMP | Trial period start |
| trial_end | TIMESTAMP | Trial period end |
| is_trial | BOOLEAN | Is in trial period |
| auto_renew | BOOLEAN | Auto-renewal enabled |
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
- FOREIGN KEY (barbershop_id) REFERENCES barbershops(id)

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
| service_type | VARCHAR(50) | Service type (haircut, beard_trim, etc.) |
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

## Future Tables (Not Yet Implemented)

### notifications
```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    type VARCHAR(50),
    title VARCHAR(200),
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP,
    created_at TIMESTAMP,
    ...
);
```

### affiliates
```sql
CREATE TABLE affiliates (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    referral_code VARCHAR(50) UNIQUE,
    tier VARCHAR(50),
    total_referrals INTEGER,
    total_earnings INTEGER,
    created_at TIMESTAMP,
    ...
);
```

### commissions
```sql
CREATE TABLE commissions (
    id INTEGER PRIMARY KEY,
    affiliate_id INTEGER REFERENCES affiliates(id),
    barbershop_id INTEGER REFERENCES barbershops(id),
    amount INTEGER,
    status VARCHAR(50),
    paid_at TIMESTAMP,
    created_at TIMESTAMP,
    ...
);
```

---

**© 2024 NOVENTIA GROUP - Database Documentation**
