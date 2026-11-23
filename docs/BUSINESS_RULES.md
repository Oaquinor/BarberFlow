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
4. Debe registrarse el cobro con un método de pago válido

**Al registrar el cobro:**
1. Se crea un pago inmutable con el precio del servicio, propina, método y moneda del negocio.
2. En la misma transacción, la cita cambia a `completed` y se registra `actual_end_time`.
3. Se actualizan comisión, rendimiento, logros y notificaciones.
4. Si no se pueden persistir las consecuencias operativas, se revierte el cobro y la finalización.

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
- Al finalizar una cita con su pago
- Al cancelar o marcar una cita como no presentada, para recalcular esas métricas
- No hay un proceso automático al cierre del día; el worker activo se ocupa de notificaciones y recordatorios

**Métricas calculadas:**
1. `appointments_completed`: Citas finalizadas
2. `appointments_cancelled`: Citas canceladas
3. `appointments_no_show`: Clientes que no asistieron
4. `total_revenue`: Suma de pagos registrados para citas completadas, incluida la propina
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

**Se verifica:** al registrar el pago que completa una cita. No existe una tarea automática diaria o semanal para evaluar logros.

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
- Teléfono opcional

**Al registrar:**
- Se genera código único (8 caracteres)
- Tasa de comisión configurable (15% por defecto)
- Estado inicial: activo y pendiente de verificación
- Los datos bancarios no se solicitan en el formulario actual

### Referidos

**Proceso:**
1. Owner usa el código al registrar una barbería
2. Se vincula barbería con afiliado
3. Se incrementa `total_referrals`
4. Se incrementa `active_referrals` si barbería se activa

### Comisiones

**Cálculo:**
- Se calcula al registrar manualmente un pago externo de suscripción
- Comisión = importe efectivamente recibido × tasa del afiliado
- Un pago referido no puede registrarse dos veces para el mismo periodo de facturación

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
3. Si la barbería configuró horario laboral, la cita debe quedar dentro de ese horario
4. No puede haber superposición con otras citas

**Duración estimada:**
- Se usa la duración del servicio seleccionado
- El catálogo acepta servicios de 10 a 180 minutos; 30 minutos es solo el valor de respaldo del modelo de barbería, no reemplaza la duración del servicio

### Cancelación

**Reglas:**
- El cliente puede cancelar una cita futura pendiente o confirmada mediante su token privado de seguimiento; no hay una ventana mínima de dos horas
- Barbero puede cancelar en cualquier momento
- Owner puede cancelar en cualquier momento
- Se registra quién canceló y el motivo

### No Show

**Registro:**
- Un propietario o el barbero asignado puede marcar manualmente una cita `pending` o `confirmed` como `no_show` cuando haya pasado la hora programada más la duración estimada del servicio.
- La agenda habilita la acción al cumplirse ese plazo; el backend vuelve a validar el tiempo y el estado antes de guardar.
- El cambio actualiza las métricas de rendimiento y queda registrado en auditoría. No hay detección automática.

---

## 💰 Planes de Suscripción

Los planes disponibles en el código son `free`, `basic`, `professional` y `enterprise`:

| Plan | Barberos activos | Citas creadas por mes | Clientes |
|---|---:|---:|---:|
| `free` | 1 | 50 | 100 |
| `basic` | 3 | 200 | 500 |
| `professional` | 10 | 1,000 | 2,000 |
| `enterprise` | Sin límite | Sin límite | Sin límite |

Los precios y prestaciones comerciales no están configurados como catálogo en la aplicación. La pasarela y los precios permanecen pendientes de definición; la plataforma solo registra manualmente pagos externos ya recibidos.

### Límites

Al alcanzar el límite, el backend rechaza con `402` la operación que crearía otra cita, cliente o barbero según corresponda. La interfaz no implementa un periodo de gracia de siete días ni una compra o mejora automática. La consulta de uso de citas se calcula por mes calendario en la zona horaria del negocio.

---

## 🔒 Reglas de Seguridad

### Autenticación
- Tokens JWT con expiración de 30 minutos
- Refresh tokens válidos por 7 días
- Contraseñas hasheadas con bcrypt a costo 12

### Permisos
- Multi-tenant: cada barbería es aislada
- Barberos solo ven su propia data
- Owners ven toda la data de su barbería
- Super admin ve todo

### Rate Limiting
- No hay un límite global activo de 100 solicitudes por minuto; esos valores de configuración no se aplican actualmente
- Sí hay límites específicos para login, recuperación de contraseña, registro SaaS (5 por IP por hora), soporte, reservas públicas y cambios/seguimiento con token, persistidos en MySQL

---

## 📝 Reglas de Negocio Generales

### Horarios
- Las citas y cierres se agrupan usando la zona IANA de la barbería
- El registro SaaS requiere que se elija una zona horaria y propone `America/Santo_Domingo` en el formulario
- El onboarding guarda el horario comercial; si no se configuró, ese rango no restringe las citas. Los turnos explícitos publicados por barberos y la duración del servicio siguen determinando disponibilidad

### Moneda
- Los importes de pagos y comisiones se guardan como enteros en centavos
- El formulario de registro propone DOP y permite elegir DOP, USD o EUR; la moneda queda asociada a la barbería (el modelo conserva USD como valor de respaldo para altas internas antiguas)
- Los informes separan monedas y no suman importes de monedas distintas

### Soft Delete
- Las entidades de negocio se conservan mediante borrado lógico (`is_deleted` y `deleted_at`)
- Los registros temporales de autenticación vencidos se purgan físicamente por la política de retención

### Timestamps
- Todos los registros tienen `created_at` y `updated_at`
- Se actualizan automáticamente

---

**Última actualización:** 2026-11-23
