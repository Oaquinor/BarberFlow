





 


CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);


USE kingflow_barber;

CREATE TABLE subscriptions (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    plan VARCHAR(50) NOT NULL, 
    status VARCHAR(50) NOT NULL, 
    current_period_start DATETIME NOT NULL, 
    current_period_end DATETIME NOT NULL, 
    max_barbers INTEGER, 
    max_appointments_per_month INTEGER, 
    max_clients INTEGER, 
    stripe_subscription_id VARCHAR(255), 
    stripe_customer_id VARCHAR(255), 
    trial_start DATETIME, 
    trial_end DATETIME, 
    is_trial BOOL, 
    auto_renew BOOL, 
    created_at DATETIME, 
    updated_at DATETIME, 
    is_deleted BOOL, 
    deleted_at DATETIME, 
    PRIMARY KEY (id)
);

CREATE TABLE barbershops (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    name VARCHAR(200) NOT NULL, 
    slug VARCHAR(100) NOT NULL, 
    description VARCHAR(1000), 
    email VARCHAR(255) NOT NULL, 
    phone VARCHAR(20) NOT NULL, 
    website VARCHAR(255), 
    address_line1 VARCHAR(255) NOT NULL, 
    address_line2 VARCHAR(255), 
    city VARCHAR(100) NOT NULL, 
    state VARCHAR(100) NOT NULL, 
    postal_code VARCHAR(20) NOT NULL, 
    country VARCHAR(100) NOT NULL, 
    latitude VARCHAR(50), 
    longitude VARCHAR(50), 
    logo_url VARCHAR(500), 
    cover_image_url VARCHAR(500), 
    opening_time TIME, 
    closing_time TIME, 
    timezone VARCHAR(50) NOT NULL, 
    currency VARCHAR(3) NOT NULL, 
    appointment_duration_minutes INTEGER NOT NULL, 
    is_active BOOL, 
    is_verified BOOL, 
    subscription_id INTEGER, 
    created_at DATETIME, 
    updated_at DATETIME, 
    is_deleted BOOL, 
    deleted_at DATETIME, 
    PRIMARY KEY (id), 
    UNIQUE (slug), 
    FOREIGN KEY(subscription_id) REFERENCES subscriptions (id)
);

CREATE INDEX ix_barbershops_slug ON barbershops (slug);

CREATE TABLE users (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    email VARCHAR(255) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    first_name VARCHAR(100) NOT NULL, 
    last_name VARCHAR(100) NOT NULL, 
    phone VARCHAR(20), 
    `role` VARCHAR(50) NOT NULL, 
    is_active BOOL, 
    is_verified BOOL, 
    barbershop_id INTEGER, 
    avatar_url VARCHAR(500), 
    bio VARCHAR(500), 
    created_at DATETIME, 
    updated_at DATETIME, 
    is_deleted BOOL, 
    deleted_at DATETIME, 
    PRIMARY KEY (id), 
    UNIQUE (email), 
    FOREIGN KEY(barbershop_id) REFERENCES barbershops (id)
);

CREATE INDEX ix_users_email ON users (email);

CREATE TABLE appointments (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    barbershop_id INTEGER NOT NULL, 
    client_id INTEGER NOT NULL, 
    barber_id INTEGER NOT NULL, 
    scheduled_time DATETIME NOT NULL, 
    estimated_duration INTEGER NOT NULL, 
    actual_start_time DATETIME, 
    actual_end_time DATETIME, 
    service_type VARCHAR(50) NOT NULL, 
    service_price INTEGER, 
    status VARCHAR(50) NOT NULL, 
    client_notes TEXT, 
    barber_notes TEXT, 
    cancelled_by INTEGER, 
    cancellation_reason TEXT, 
    checked_in_at DATETIME, 
    created_at DATETIME, 
    updated_at DATETIME, 
    is_deleted BOOL, 
    deleted_at DATETIME, 
    PRIMARY KEY (id), 
    FOREIGN KEY(barbershop_id) REFERENCES barbershops (id), 
    FOREIGN KEY(client_id) REFERENCES users (id), 
    FOREIGN KEY(barber_id) REFERENCES users (id), 
    FOREIGN KEY(cancelled_by) REFERENCES users (id)
);

CREATE INDEX ix_appointments_barbershop_id ON appointments (barbershop_id);

CREATE INDEX ix_appointments_client_id ON appointments (client_id);

CREATE INDEX ix_appointments_barber_id ON appointments (barber_id);

CREATE INDEX ix_appointments_scheduled_time ON appointments (scheduled_time);

CREATE INDEX ix_appointments_status ON appointments (status);

INSERT INTO alembic_version (version_num) VALUES ('001_initial');


