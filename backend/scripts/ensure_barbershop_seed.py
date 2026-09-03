import pymysql

conn = pymysql.connect(
    host='localhost',
    user='kingflow',
    password='kingflow123',
    database='kingflow_barber'
)

try:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM barbershops WHERE id=1")
        exists = cur.fetchone()[0]

        if exists == 0:
            cur.execute(
                """
                INSERT INTO barbershops (
                    id, name, slug, email, phone,
                    address_line1, city, state, postal_code, country,
                    timezone, currency, appointment_duration_minutes,
                    is_active, is_verified, is_deleted,
                    primary_color, secondary_color, onboarding_completed
                ) VALUES (
                    1, 'KingFlow Barber', 'kingflow-barber', 'admin@kingflow.com', '0000000000',
                    'Main St', 'City', 'State', '00000', 'USA',
                    'America/New_York', 'USD', 30,
                    1, 0, 0,
                    '#667eea', '#764ba2', 0
                )
                """
            )
            conn.commit()
            print('CREATED')
        else:
            print('EXISTS')
finally:
    conn.close()
