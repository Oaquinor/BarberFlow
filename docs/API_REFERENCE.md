# 📖 API Reference - KingFlow Barber

**Documentación completa de endpoints REST API**

Base URL: `http://127.0.0.1:8000/api/v1`

---

## 🔐 Autenticación

Todos los endpoints (excepto login/register) requieren autenticación JWT.

**Header requerido:**
```
Authorization: Bearer <token>
```

### Endpoints

#### `POST /auth/register`
Registrar nuevo usuario.

**Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword",
  "first_name": "John",
  "last_name": "Doe",
  "role": "barber"
}
```

#### `POST /auth/login`
Iniciar sesión.

**Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## 🔥 Modo En Servicio (CRÍTICO)

### `POST /service-mode/start`

Inicia el modo de servicio para una cita.

**Body:**
```json
{
  "appointment_id": 123
}
```

**Response:**
```json
{
  "appointment": {
    "id": 123,
    "client_name": "Juan Pérez",
    "service_type": "haircut",
    "estimated_duration": 30,
    "actual_start_time": "2024-05-30T14:30:00",
    "status": "in_progress"
  },
  "timer": {
    "started_at": "2024-05-30T14:30:00",
    "estimated_duration_minutes": 30
  },
  "next_appointment": {
    "id": 124,
    "client_name": "María González",
    "scheduled_time": "2024-05-30T15:00:00",
    "minutes_until": 30
  },
  "alerts": [
    "📅 Próxima cita en 30 minutos"
  ]
}
```

### `POST /service-mode/finish`

Finaliza el servicio activo.

**Body:**
```json
{
  "appointment_id": 123,
  "barber_notes": "Cliente satisfecho"
}
```

**Response:**
```json
{
  "appointment": {
    "id": 123,
    "status": "completed",
    "actual_start_time": "2024-05-30T14:30:00",
    "actual_end_time": "2024-05-30T14:55:00",
    "actual_duration_minutes": 25
  },
  "performance": {
    "estimated_duration": 30,
    "actual_duration": 25,
    "time_difference": -5,
    "efficiency_percentage": 120.0,
    "status": "on_time"
  },
  "achievements": [
    {
      "name": "Primer Día",
      "icon": "🎉",
      "description": "Completa tu primera jornada"
    }
  ],
  "message": "🎯 ¡Excelente! Completaste el servicio antes del tiempo estimado."
}
```

### `GET /service-mode/active`

Obtiene el servicio activo actual.

**Response:**
```json
{
  "active": true,
  "appointment": {
    "id": 123,
    "client_name": "Juan Pérez",
    "service_type": "haircut",
    "estimated_duration": 30
  },
  "timer": {
    "elapsed_minutes": 15,
    "remaining_minutes": 15,
    "is_exceeded": false,
    "exceeded_by_minutes": 0,
    "progress_percentage": 50.0
  },
  "alerts": []
}
```

### `GET /service-mode/next`

Obtiene la próxima cita programada.

### `GET /service-mode/schedule/today`

Obtiene la agenda completa del día.

**Response:**
```json
{
  "date": "2024-05-30",
  "summary": {
    "total": 8,
    "completed": 3,
    "in_progress": 1,
    "upcoming": 4,
    "cancelled": 0
  },
  "appointments": [...]
}
```

---

## 📊 Rendimiento

### `GET /performance/daily/{barber_id}`

Métricas diarias de un barbero.

**Query params:**
- `target_date` (opcional): YYYY-MM-DD

**Response:**
```json
{
  "date": "2024-05-30",
  "appointments_completed": 8,
  "appointments_cancelled": 1,
  "appointments_no_show": 0,
  "total_revenue": 24000,
  "total_service_time_minutes": 240,
  "average_service_time_minutes": 30.0,
  "time_efficiency_percentage": 95.5,
  "current_streak": 5,
  "best_streak": 12
}
```

### `GET /performance/weekly/{barber_id}`

Resumen semanal.

**Query params:**
- `start_date` (opcional): YYYY-MM-DD

### `GET /performance/monthly/{barber_id}`

Resumen mensual.

**Query params:**
- `year` (opcional)
- `month` (opcional)

### `GET /performance/insights/{barber_id}`

Insights y recomendaciones.

**Response:**
```json
{
  "insights": [
    "🔥 Llevas 5 días consecutivos trabajando.",
    "⭐ Tu mejor día fue el 28/05: 10 citas completadas.",
    "🎯 Tu eficiencia de tiempo es excelente.",
    "💰 Has generado $720.00 en los últimos 30 días."
  ]
}
```

---

## 🎮 Logros

### `GET /achievements/`

Obtiene todos los logros del usuario.

**Response:**
```json
{
  "total_achievements": 10,
  "earned_achievements": 3,
  "total_points": 90,
  "earned": [
    {
      "achievement": {
        "code": "FIRST_DAY",
        "name": "Primer Día",
        "description": "Completa tu primera jornada",
        "icon": "🎉",
        "rarity": "common",
        "points": 10
      },
      "earned_at": "2024-05-25T18:30:00",
      "is_viewed": true
    }
  ],
  "available": [...]
}
```

### `POST /achievements/check`

Verifica y otorga nuevos logros.

### `POST /achievements/mark-viewed/{achievement_id}`

Marca un logro como visto.

---

## 🛠️ Servicios

### `GET /services/`

Lista todos los servicios activos.

**Query params:**
- `category` (opcional): filtrar por categoría

**Response:**
```json
{
  "total": 6,
  "services": [
    {
      "id": 1,
      "name": "Corte de Cabello",
      "description": "Corte moderno y profesional",
      "duration_minutes": 30,
      "price": 1500,
      "price_formatted": "$15.00",
      "category": "haircut",
      "icon": "✂️",
      "is_active": true
    }
  ]
}
```

### `POST /services/`

Crea un nuevo servicio.

**Body:**
```json
{
  "name": "Corte Premium",
  "description": "Corte + Lavado + Styling",
  "duration_minutes": 45,
  "price": 2500,
  "category": "combo",
  "icon": "👑"
}
```

### `PUT /services/{id}`

Actualiza un servicio.

### `DELETE /services/{id}`

Elimina un servicio (soft delete).

---

## 📅 Citas

### `GET /appointments/`

Lista citas.

**Query params:**
- `status`: filtrar por estado
- `barber_id`: filtrar por barbero
- `date`: filtrar por fecha

### `POST /appointments/`

Crea una cita.

**Body:**
```json
{
  "client_id": 10,
  "barber_id": 5,
  "scheduled_time": "2024-05-30T15:00:00",
  "service_type": "haircut",
  "estimated_duration": 30,
  "client_notes": "Corte bajo en los lados"
}
```

### `GET /appointments/{id}`

Obtiene una cita específica.

### `PUT /appointments/{id}`

Actualiza una cita.

### `DELETE /appointments/{id}`

Cancela una cita.

---

## 🔴 Códigos de Error

- `400` - Bad Request (validación fallida)
- `401` - Unauthorized (token inválido o expirado)
- `403` - Forbidden (permisos insuficientes)
- `404` - Not Found (recurso no encontrado)
- `500` - Internal Server Error

**Formato de error:**
```json
{
  "detail": "Descripción del error"
}
```

---

## 📝 Notas

- Todas las fechas están en formato ISO 8601
- Los precios están en centavos (ej: 1500 = $15.00)
- Los tiempos están en minutos
- Las respuestas incluyen códigos HTTP estándar

---

**Última actualización:** 2024-05-30
