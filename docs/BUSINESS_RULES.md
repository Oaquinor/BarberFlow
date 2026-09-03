# 📋 Business Rules - KingFlow Barber

**Reglas de negocio y lógica operativa del sistema**

---

## 🎯 Visión del Producto

### ❌ Lo que NO somos:
- Marketplace de barberos
- Directorio de barberías
- Plataforma de empleo
- Sistema de contratación

### ✅ Lo que SÍ somos:
**Sistema operativo para barberías**

Ayudamos a:
- Propietarios a gestionar su negocio
- Administradores a optimizar operaciones
- Barberos a ser más productivos
- Clientes a recibir mejor servicio

---

## 👥 Roles y Permisos

### Super Admin
**Puede:**
- Acceder a todas las barberías
- Gestionar suscripciones
- Ver métricas globales
- Aprobar afiliados

### Barbershop Owner
**Puede:**
- Gestionar su barbería
- Crear/editar servicios
- Agregar/remover barberos
- Ver reportes completos
- Configurar horarios
- Personalizar colores

### Barber
**Puede:**
- Ver su agenda
- Iniciar/finalizar servicios
- Ver sus métricas
- Ver sus logros
- Gestionar sus citas

### Client
**Puede:**
- Reservar citas
- Ver su historial
- Cancelar citas (con restricciones)

---

## 🔥 Modo En Servicio

### Reglas de Inicio

**Condiciones para iniciar servicio:**
1. La cita debe estar en estado `confirmed` o `pending`
2. El barbero debe ser el asignado a la cita
3. No puede haber otro servicio activo del mismo barbero
4. La hora actual debe estar cerca de la hora programada (±15 min)

**Al iniciar servicio:**
1. Estado cambia a `in_progress`
2. Se registra `actual_start_time`
3. Se inicia temporizador
4. Se muestra próxima cita (si existe)

### Reglas de Finalización

**Condiciones para finalizar servicio:**
1. El servicio debe estar en estado `in_progress`
2. El barbero debe ser el asignado
3. Debe haber transcurrido al menos 5 minutos

**Al finalizar servicio:**
1. Estado cambia a `completed`
2. Se registra `actual_end_time`
3. Se calcula duración real
4. Se compara con duración estimada
5. Se actualiza performance diaria
6. Se verifican logros automáticamente

### Alertas de Tiempo

**Durante el servicio:**
- Al 80% del tiempo estimado: "⏰ 6 minutos restantes"
- Al exceder tiempo: "⚠️ El servicio excede el tiempo estimado por X minutos"
- Si hay cita próxima en 20 min: "⚠️ Próxima cita en 20 minutos"
- Si hay cita próxima en 10 min: "🚨 URGENTE: Próxima cita en 10 minutos"

---

## 📊 Sistema de Rendimiento

### Cálculo de Métricas Diarias

**Se ejecuta:**
- Al finalizar cada cita
- Al final del día (automático)

**Métricas calculadas:**
1. `appointments_completed`: Citas finalizadas
2. `appointments_cancelled`: Citas canceladas
3. `appointments_no_show`: Clientes que no asistieron
4. `total_revenue`: Suma de precios de citas completadas
5. `total_service_time_minutes`: Suma de duraciones reales
6. `average_service_time_minutes`: Promedio de duración
7. `time_efficiency_percentage`: (estimado / real) * 100

### Cálculo de Rachas

**Reglas:**
1. La racha se incrementa si trabajas días consecutivos
2. "Trabajar" = completar al menos 1 cita
3. La racha se reinicia si falta un día
4. `best_streak` guarda el récord histórico

**Ejemplo:**
- Lunes: 3 citas → streak = 1
- Martes: 5 citas → streak = 2
- Miércoles: 0 citas → streak = 0 (se reinicia)
- Jueves: 4 citas → streak = 1 (nueva racha)

### Insights Generados

**Condiciones para insights:**

1. **Racha actual ≥ 7 días:**
   - "🔥 Increíble! Llevas X días consecutivos"

2. **Racha actual ≥ 3 días:**
   - "💪 Llevas X días consecutivos. ¡Sigue así!"

3. **Eficiencia ≥ 90%:**
   - "🎯 Tu eficiencia de tiempo es excelente"

4. **Eficiencia < 70%:**
   - "⏱️ Hay oportunidad de mejorar tu tiempo promedio"

5. **Tasa de cancelación > 20%:**
   - "⚠️ Tu tasa de cancelación es del X%. Considera confirmaciones"

---

## 🎮 Sistema de Gamificación

### Logros Predefinidos

#### **Primer Día** (🎉)
- **Requisito:** Completar 1 cita
- **Puntos:** 10
- **Rareza:** Common

#### **Guerrero Semanal** (🔥)
- **Requisito:** 7 días consecutivos trabajando
- **Puntos:** 50
- **Rareza:** Rare

#### **Maestro del Mes** (👑)
- **Requisito:** 30 días consecutivos trabajando
- **Puntos:** 200
- **Rareza:** Epic

#### **Abeja Ocupada** (🐝)
- **Requisito:** 10 citas en un solo día
- **Puntos:** 30
- **Rareza:** Rare

#### **Super Barbero** (⚡)
- **Requisito:** 15 citas en un solo día
- **Puntos:** 75
- **Rareza:** Epic

#### **Club de los 100** (💯)
- **Requisito:** 100 citas totales
- **Puntos:** 100
- **Rareza:** Rare

#### **Quinientos** (🌟)
- **Requisito:** 500 citas totales
- **Puntos:** 500
- **Rareza:** Epic

#### **Leyenda** (🏆)
- **Requisito:** 1000 citas totales
- **Puntos:** 1000
- **Rareza:** Legendary

### Detección de Logros

**Se verifica en:**
1. Al completar una cita
2. Al calcular performance diaria
3. Al finalizar la semana

**Reglas:**
- Un logro solo se otorga una vez
- No se puede perder un logro ganado
- Los logros son por barbero y por barbería
- Se notifica inmediatamente al desbloquear

---

## 👥 Sistema de Afiliados

### Registro de Afiliado

**Datos requeridos:**
- Nombre completo
- Email (único)
- Teléfono
- Información bancaria

**Al registrar:**
- Se genera código único (8 caracteres)
- Tasa de comisión: 15% (default)
- Estado inicial: `pending`
- Requiere verificación del admin

### Referidos

**Proceso:**
1. Cliente usa código de afiliado al registrar barbería
2. Se vincula barbería con afiliado
3. Se incrementa `total_referrals`
4. Se incrementa `active_referrals` si barbería se activa

### Comisiones

**Cálculo:**
- Comisión = Precio de suscripción × Tasa de comisión
- Se genera comisión mensual por cada referido activo

**Estados:**
1. **Pending:** Generada, esperando aprobación
2. **Approved:** Aprobada, lista para pago
3. **Paid:** Pagada al afiliado
4. **Rejected:** Rechazada (caso excepcional)

**Pago:**
- Requiere aprobación manual del admin
- Se registra método, referencia y notas
- Se actualiza balance del afiliado

---

## 🛠️ Servicios de Barbería

### Catálogo de Servicios

**Campos obligatorios:**
- `name`: Nombre del servicio
- `duration_minutes`: Duración estimada
- `price`: Precio en centavos
- `category`: Categoría (haircut, beard, combo, etc.)

**Categorías predefinidas:**
- `haircut`: Corte de cabello
- `beard_trim`: Arreglo de barba
- `shave`: Afeitado clásico
- `combo`: Servicios combinados
- `hair_color`: Tinte y color
- `facial`: Tratamientos faciales

### Gestión

**Reglas:**
- Solo owner puede crear/editar servicios
- Los servicios se pueden desactivar (no eliminar físicamente)
- Los precios se guardan en centavos (ej: $15.00 = 1500)
- Se pueden ordenar con `display_order`

---

## 📅 Gestión de Citas

### Estados de Cita

1. **Pending:** Creada, esperando confirmación
2. **Confirmed:** Confirmada por barbería
3. **In Progress:** Servicio activo
4. **Completed:** Finalizada exitosamente
5. **Cancelled:** Cancelada
6. **No Show:** Cliente no asistió

### Reglas de Creación

**Validaciones:**
1. La fecha debe ser futura
2. El barbero debe estar disponible
3. El horario debe estar dentro del horario laboral
4. No puede haber superposición con otras citas

**Duración estimada:**
- Se usa la duración del servicio seleccionado
- Default: 30 minutos

### Cancelación

**Reglas:**
- Cliente puede cancelar hasta 2 horas antes
- Barbero puede cancelar en cualquier momento
- Owner puede cancelar en cualquier momento
- Se registra quién canceló y el motivo

### No Show

**Detección:**
- Si pasan 15 minutos después de la hora programada
- Y el estado sigue en `confirmed`
- El sistema puede marcar automáticamente como `no_show`

---

## 💰 Planes de Suscripción

### Plan Básico - RD$300/mes
- Max 3 barberos
- Max 200 citas/mes
- Max 500 clientes
- Métricas básicas
- Soporte por email

### Plan Pro - RD$500/mes
- Max 10 barberos
- Max 1000 citas/mes
- Max 2000 clientes
- Métricas avanzadas
- Gamificación
- Insights automáticos
- Soporte prioritario

### Límites

**Al exceder límites:**
1. Se notifica al owner
2. Se sugiere upgrade
3. No se bloquea inmediatamente (período de gracia de 7 días)
4. Después de 7 días, no se pueden crear nuevas citas

---

## 🔒 Reglas de Seguridad

### Autenticación
- Tokens JWT con expiración de 30 minutos
- Refresh tokens válidos por 7 días
- Passwords hasheados con Bcrypt (10 rounds)

### Permisos
- Multi-tenant: cada barbería es aislada
- Barberos solo ven su propia data
- Owners ven toda la data de su barbería
- Super admin ve todo

### Rate Limiting
- 100 requests por minuto por IP
- 1000 requests por hora por IP

---

## 📝 Reglas de Negocio Generales

### Horarios
- Se usan zones horarias configurables
- Default: America/New_York
- Horario laboral default: 9:00 AM - 6:00 PM

### Moneda
- Todo se guarda en centavos (evita problemas de decimales)
- Currency default: USD
- Formato de display: $X.XX

### Soft Delete
- Nada se elimina físicamente
- Se marca con `is_deleted = true`
- Se registra `deleted_at`

### Timestamps
- Todos los registros tienen `created_at` y `updated_at`
- Se actualizan automáticamente

---

**Última actualización:** 2024-05-30
