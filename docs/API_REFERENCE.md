# API de KingFlow Barber

Base local: `http://localhost:8000/api/v1`. La lista siguiente corresponde a las rutas montadas por FastAPI. Los ejemplos usan centavos y la hora ISO 8601.

## Autenticación y SaaS

| Método | Ruta | Acceso |
|---|---|---|
| `POST` | `/auth/login` | Público; aplica límite de intentos |
| `POST` | `/saas/register` | Público; crea owner, barbería y periodo gratuito |
| `POST` | `/auth/refresh` | Token refresh vigente |
| `POST` | `/auth/logout` | Token refresh |
| `POST` | `/auth/change-password` | Usuario autenticado |
| `POST` | `/auth/password-reset/request` | Público; responde sin revelar si la cuenta existe y limita solicitudes por correo/IP |
| `POST` | `/auth/password-reset/confirm` | Público; requiere token de un solo uso vigente y contraseña robusta |
| `GET` | `/auth/me` | Usuario autenticado |

El registro de barbería recibe `owner_email`, `owner_password`, `owner_first_name`, `owner_last_name`, `owner_phone`, `barbershop_name`, `barbershop_email`, `barbershop_phone`, `address_line1`, `city`, `state`, `postal_code`, `country`, `timezone`, `currency` y un `affiliate_code` opcional. Un código inválido se rechaza; uno válido registra el referido con el owner, barbería y suscripción en una sola transacción. La contraseña requiere 12 caracteres, una mayúscula y un número. El registro no cobra ni simula un pago.

Usa `Authorization: Bearer <access_token>` en las rutas protegidas. Los tokens refresh son rotativos y revocables; cada access token emitido por login o refresh queda ligado a su sesión, por lo que rotar o cerrar sesión también invalida ese access token. Cambiar o recuperar la contraseña incrementa `auth_version`, invalidando access tokens y sesiones refresh de todos los dispositivos.

La solicitud de recuperación devuelve el mismo mensaje para correos registrados y desconocidos. Limita a cinco solicitudes por correo/IP y treinta por IP en una hora. Si la cuenta está activa y SMTP entrega el mensaje, el enlace vence en 30 minutos y se consume una sola vez. Configura `FRONTEND_BASE_URL` con el origen HTTPS público en producción.

## Portal público del cliente

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/public/{slug}` | Perfil público, moneda y zona horaria |
| `GET` | `/public/{slug}/services` | Catálogo activo |
| `GET` | `/public/{slug}/slots?duration_minutes={minutes}` | Turnos que caben en la duración del servicio y no se solapan con citas ni ausencias |
| `POST` | `/public/{slug}/appointments` | Crea reserva sin cuenta |
| `POST` | `/public/{slug}/track` | Consulta con token privado |
| `POST` | `/public/{slug}/appointments/reschedule` | Cambia turno con token privado |
| `POST` | `/public/{slug}/appointments/cancel` | Cancela turno con token privado |

Reserva:

```json
{
  "client_name": "Ana Cliente",
  "phone": "8095550202",
  "service_id": 12,
  "barber_id": 7,
  "scheduled_time": "2026-11-20T15:00:00-04:00",
  "notes": "Corte clásico"
}
```

`barber_id` es opcional para integraciones anteriores. La página pública permite elegir un barbero entre los que tienen disponibilidad y envía su ID junto con la hora; el backend valida que el turno siga disponible para ese barbero y esa barbería.

Las solicitudes de reserva para barberías con suscripción activa se limitan por IP y barbería a 10 por hora, con un límite adicional de 60 por IP por hora entre todas las barberías. El backend guarda únicamente hashes con clave secreta para aplicar la cuota y responde `429` con `Retry-After` al superarla.

El enlace de seguimiento contiene un token aleatorio; la base de datos guarda su hash. No se acepta un ID de cita como sustituto de autorización. Para reprogramar envía `{"token":"<token privado>","availability_id":45}`; el sistema bloquea el nuevo turno, valida duración y conflictos, libera el anterior y registra el cambio atómicamente. Cancelación acepta `token` y `reason` opcional. Email/WhatsApp depende de configuración real del proveedor.

Las rutas de consulta, servicios, disponibilidad y reserva requieren una suscripción activa. Cancelar una reserva futura no requiere iniciar sesión.

## Bandeja autenticada

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/notifications?limit=50&unread_only=false` | Lista notificaciones del usuario autenticado y su contador de no leídas |
| `POST` | `/notifications/{notification_id}/read` | Marca una notificación propia como leída |

El inbox guarda eventos operativos de cita para el barbero asignado y los propietarios activos de la barbería. La consulta y lectura requieren identidad autenticada y filtran por destinatario y tenant. Las filas se crean junto con la operación de negocio; claves únicas por evento y destinatario evitan duplicados.

## Agenda, servicio, cobros y caja

| Método | Ruta | Función |
|---|---|---|
| `POST` | `/barber/slots` | El barbero configura sus turnos |
| `GET` | `/barber/absences` | Lista las ausencias futuras del barbero autenticado |
| `POST` | `/barber/absences` | Bloquea un rango futuro propio; rechaza rangos con citas activas |
| `DELETE` | `/barber/absences/{absence_id}` | Cancela una ausencia propia y vuelve a publicar los turnos originales |
| `GET` | `/barber/dashboard` | Agenda del día y métricas operativas |
| `GET` | `/barber/appointments?target_date=YYYY-MM-DD` | Citas de un día local del negocio |
| `GET` | `/barber/appointments/calendar?view=week&anchor_date=YYYY-MM-DD` | Citas por día para una semana o mes local |
| `PUT` | `/barber/appointments/{appointment_id}/status` | Confirma, inicia, cancela o marca no presentado |
| `POST` | `/barber/appointments/{appointment_id}/payment` | Registra el pago y finaliza el servicio |
| `POST` | `/barber/appointments/walk-in` | Inicia una atención presencial sin reserva |
| `GET` | `/barber/commissions` | El barbero consulta sus comisiones y saldos por moneda |
| `GET` | `/barber/cash/today` | Cobros del día local y conciliación |
| `POST` | `/barber/cash/close` | Registra cierre diario |
| `GET` | `/barber/share-link` | Enlace público del negocio |

## Gestión del negocio (owner)

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/owner/barbers` | Lista los barberos de la barbería |
| `POST` | `/owner/barbers` | Crea acceso con contraseña inicial y aplica el límite del plan |
| `PUT` | `/owner/barbers/{barber_id}` | Actualiza nombre y teléfono de un barbero del tenant, con auditoría |
| `PUT` | `/owner/barbers/{barber_id}/status` | Activa o desactiva un barbero del mismo tenant |
| `GET` | `/owner/clients?limit=50&offset=0` | Lista clientes con citas y total efectivamente pagado |
| `POST` | `/owner/clients` | Registra un cliente manual en el tenant, aplica el límite del plan y audita el alta |
| `PUT` | `/owner/clients/{client_id}` | Actualiza nombre y teléfono de un cliente del tenant, con auditoría |
| `PUT` | `/owner/clients/{client_id}/status` | Activa o desactiva el acceso del cliente sin borrar su historial |

El alta manual requiere nombre, apellido y teléfono; normaliza el teléfono y rechaza duplicados del mismo tenant. Crea una ficha sin acceso de cuenta ni cita asociada.
| `GET` | `/onboarding/profile` | Lee el perfil, horario y zona horaria de la barbería autenticada |
| `PUT` | `/onboarding/business-settings` | Actualiza nombre, horario, zona horaria y colores; registra auditoría |

La actualización de configuración requiere rol owner, valida horas y zona horaria IANA, y deriva el tenant del usuario autenticado. Un administrador general debe indicar explícitamente la barbería autorizada.

`GET /billing/subscription` devuelve al owner el estado efectivo del periodo y el uso de límites del plan para su tenant. Una suscripción marcada activa cuyo periodo ya terminó se informa como vencida sin mutar datos al leer. El campo histórico `auto_renew` es solo un indicador administrativo: no inicia renovaciones ni programa cobros. Cada periodo requiere registrar manualmente un pago externo recibido.

## Analítica de demanda

| Método | Ruta | Acceso | Función |
|---|---|---|---|
| `GET` | `/analytics/demand-forecast` | Owner autenticado | Estima el volumen de servicios por día y hora para los próximos siete días |
| `GET` | `/analytics/financial-report?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | Owner autenticado | Resume pagos realmente recibidos, separados por día comercial, método y barbero |

El pronóstico usa el promedio histórico de citas completadas por día de la semana y hora durante las 12 semanas anteriores, y lo combina con las reservas próximas conocidas. Es una referencia estadística explicable, no un modelo de aprendizaje automático. La respuesta incluye el periodo y tamaño de la muestra, reservas conocidas, horas pico y nivel de confianza; con poco historial se indica esa limitación y solo sirven de referencia las reservas existentes. Todos los datos se filtran por la barbería del owner autenticado.

El reporte financiero exige un rango de fechas de hasta 366 días y lo interpreta en la zona horaria IANA del negocio. Se basa en cobros guardados, separa precio del servicio y propina, y expresa todos los importes en centavos y la moneda del tenant. No estima ingresos de citas aún no cobradas.

Para iniciar servicio:

```json
{"status":"in_progress"}
```

El inicio solo se acepta dentro de los 15 minutos anteriores o posteriores al turno, y el barbero no puede tener otro servicio en curso. El temporizador usa la hora inicial guardada y sigue visible en el modo de servicio aunque la cita activa quede fuera de la agenda del día actual. Para registrar el cobro y terminar la atención deben haber transcurrido al menos cinco minutos.

Una cita completada exige el endpoint de pago. Ejemplo:

```json
{"method":"cash","tip_cents":5000}
```

Métodos aceptados: `cash`, `card`, `transfer`, `other`. Cada cita admite un solo pago. La operación guarda el pago y completa la cita dentro de la misma transacción. No se confunde el precio de lista con ingresos cobrados.

Cierre:

```json
{"business_date":"2026-11-19","declared_cash_cents":30000,"notes":"Conteo revisado"}
```

Un barbero ve sus cobros; el owner ve los del negocio. El cierre conserva esperado, declarado y diferencia. Una segunda conciliación de la misma fecha y usuario se rechaza. El cierre del owner también cierra la fecha para los barberos del negocio. Antes de cerrar, se deben resolver las citas pendientes o confirmadas y finalizar los servicios en curso de esa fecha, también cuando se cierra un día anterior.

## Catálogo de servicios

| Método | Ruta | Acceso |
|---|---|---|
| `GET` | `/services/` | Roles autenticados de la barbería |
| `GET` | `/services/{service_id}` | Tenant propietario del registro |
| `POST` | `/services/` | Owner |
| `PUT` | `/services/{service_id}` | Owner |
| `DELETE` | `/services/{service_id}` | Owner; baja lógica |

`name` admite hasta 100 caracteres y se conserva como snapshot en la cita; `price` es entero en centavos. Todos los registros se restringen al tenant autenticado.

## Rendimiento y logros

| Método | Ruta | Acceso |
|---|---|---|
| `GET` | `/performance/daily/{barber_id}` | Barbero propio u owner del mismo tenant |
| `GET` | `/performance/weekly/{barber_id}` | Barbero propio u owner del mismo tenant |
| `GET` | `/performance/monthly/{barber_id}` | Barbero propio u owner del mismo tenant |
| `GET` | `/performance/insights/{barber_id}` | Barbero propio u owner del mismo tenant |
| `GET` | `/achievements/` | Barbero autenticado |
| `POST` | `/achievements/check` | Barbero autenticado |
| `POST` | `/achievements/mark-viewed/{achievement_id}` | Dueño del logro |

La fecha predeterminada de rendimiento usa la zona horaria de la barbería. Ingresos se derivan de pagos efectivamente registrados. Los logros disponibles se insertan con la migración MySQL `011_seed_achievements`; el pago completado actualiza el rendimiento y evalúa logros compatibles.

## Onboarding y personalización

Rutas protegidas bajo `/onboarding`: `GET /profile`, `GET /dashboard-layout`, `GET /greeting`; `POST /complete`, `/motivational-message`, `/step/1`, `/step/3` a `/step/9`, `/upload-logo`; `PUT /brand-colors`. El tenant se deriva del usuario autenticado. Las recomendaciones del layout son consejos generales; el mensaje motivacional calcula el conteo de citas de los últimos 30 días y no confía en el contexto enviado por el cliente.

## Equipo y clientes del negocio

| Método | Ruta | Acceso |
|---|---|---|
| `GET` / `POST` | `/owner/barbers` | Owner del tenant; listado y alta con límites del plan |
| `PUT` | `/owner/barbers/{barber_id}/status` | Owner del tenant; activar o desactivar |
| `PUT` | `/owner/barbers/{barber_id}/commission-rate` | Configurar tasa del barbero (puntos base; 0 a 10 000) |
| `GET` | `/owner/barber-commissions` | Consultar comisiones generadas por cobros del tenant |
| `POST` | `/owner/barber-commissions/{commission_id}/pay` | Registrar liquidación de comisión con método y referencia |
| `GET` | `/owner/clients` | Owner del tenant; historial agregado, paginado y de solo lectura |
| `POST` | `/barber/slots` | Barbero propio; turnos dentro del horario configurado |
| `GET` | `/barber/dashboard` | Barbero propio u owner; agenda operativa del día |

La gestión de clientes permite editar nombre y teléfono y desactivar el acceso conservando citas y cobros. La gestión de barberos permite alta, activación y tasa de comisión, pero no edición de perfil ni eliminación. Los turnos creados se serializan por barbero en MySQL para evitar solapamientos concurrentes.

El portal público envía la duración seleccionada al consultar turnos. Si no se indica `duration_minutes`, el endpoint usa la duración del servicio activo más corto. El servidor vuelve a validar el turno al reservar y reprogramar.

El propietario define la tasa porcentual por barbero. Al registrar un pago de cita, el backend crea la comisión pendiente en la misma transacción usando el importe del servicio, sin incluir propina. El barbero solo ve sus registros; el propietario solo puede consultar y liquidar los de su barbería. La liquidación queda auditada y no se puede repetir. Los pagos de comisión en efectivo se registran como salidas en el efectivo esperado del cierre diario del propietario; no se aceptan después de cerrar esa caja.

La ruta de calendario acepta `view=week` o `view=month`. Sus límites de fecha se calculan en la zona horaria del tenant; los resultados quedan filtrados por barbería y, para el rol barbero, por su usuario. La vista de día conserva operaciones para iniciar, cancelar y cobrar citas; las vistas agrupadas permiten abrir el día seleccionado.

## Administración de plataforma

Todas las rutas `/admin/*` requieren rol `super_admin`.

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/admin/overview` | Métricas globales de tenants, usuarios, suscripciones, citas y cobros por moneda |
| `GET` | `/admin/tenants` | Barberías y suscripciones |
| `PUT` | `/admin/tenants/{barbershop_id}/status` | Activar o suspender barbería |
| `GET` | `/admin/tenants/{barbershop_id}/subscription` | Consultar suscripción |
| `PUT` | `/admin/tenants/{barbershop_id}/subscription` | Administrar plan y periodo |
| `GET` | `/admin/users` | Buscar usuarios |
| `PUT` | `/admin/users/{user_id}/status` | Activar o suspender usuario |
| `PUT` | `/admin/users/{user_id}/support` | Configurar contacto de soporte |
| `PUT` | `/admin/users/{user_id}/features` | Cambiar feature flag |
| `GET` | `/admin/audit-logs` | Leer historial paginado y filtrable |
| `GET` / `PUT` | `/admin/settings` | Consultar y cambiar estado de registro y duración inicial del periodo gratuito |
| `GET` / `POST` | `/admin/affiliates` | Consultar o crear afiliados y sus códigos |
| `PUT` | `/admin/affiliates/{affiliate_id}/status` | Activar o desactivar un código para nuevos referidos |
| `GET` | `/admin/affiliates/{affiliate_id}/commissions` | Consultar comisiones por moneda |
| `POST` | `/admin/commissions/{commission_id}/approve` | Aprobar una comisión pendiente |
| `POST` | `/admin/commissions/{commission_id}/pay` | Registrar el pago externo de una comisión aprobada |
| `POST` | `/admin/tenants/{barbershop_id}/subscription/payments` | Registrar un cobro SaaS externo ya recibido y crear su comisión afiliada |

Al cambiar el estado de una barbería, se revocan sus sesiones de renovación y se invalida la versión de sesión de sus usuarios; al reactivarla todos deben iniciar sesión de nuevo. Suspender o reactivar un usuario individual también invalida sus tokens y sesiones de renovación. El último superadministrador no se puede desactivar. El historial guarda eventos sensibles junto con la operación y omite tokens y contraseñas. El resumen global cuenta cobros de citas por separado para cada moneda; no suma monedas distintas. El registro SaaS de cobro requiere importe positivo, periodo vigente y confirmación administrativa de un pago ya recibido; no se conecta a una pasarela ni procesa tarjetas. Las comisiones guardan la moneda de origen. El pago de afiliados requiere aprobar la comisión y registrar método y referencia externa.

`GET /saas/registration-status` expone solo si el registro está habilitado. Si se desactiva, el formulario de alta se bloquea y el endpoint de registro lo rechaza de nuevo en servidor. Los cambios de estos parámetros se guardan en MySQL y generan auditoría; los secretos siguen en variables de entorno.

La bandera disponible `branding_auto` controla si el portal autenticado aplica los colores de marca de la barbería. Solo se activa para un usuario owner/barbero con onboarding completado; su estado forma parte de `/auth/me` y del listado de usuarios. Los cambios se reflejan al volver a iniciar sesión.

## Soporte y errores

`POST /support/contact` recibe nombre, email o teléfono, mensaje y slug opcional. Cada solicitud se conserva en MySQL aunque SMTP esté caído; la respuesta incluye `ticket_id` y `notification_sent`. El formulario limita a cinco solicitudes por IP y hora y persiste solo un hash de la dirección.

El superadministrador puede consultar `GET /admin/support/tickets?status=open&limit=50&offset=0` (incluye total para paginar) y cambiar su estado con `PUT /admin/support/tickets/{ticket_id}/status` (`open`, `in_progress`, `resolved` o `closed`). Solo el rol `super_admin` puede ver o gestionar la bandeja; cada cambio de estado genera auditoría.

Errores usan JSON `{"detail":"..."}`. Códigos usados: `401` autenticación, `403` permiso, `404` recurso del tenant, `409` conflicto/transición, `422` validación y `402` límite o suscripción inactiva.

Las respuestas incluyen `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, una CSP que restringe las URL base y formularios al mismo origen y bloquea objetos y marcos, y una `Permissions-Policy` que bloquea cámara, micrófono y geolocalización. En producción también incluyen HSTS. Las rutas bajo `/api/` añaden `Cache-Control: no-store` y `Pragma: no-cache` para impedir que el navegador almacene respuestas operativas o datos personales.

La API no implementa actualmente cobro automatizado de suscripciones, creación/eliminación manual de clientes o edición/eliminación de perfil de barberos, ni notificaciones push. Los recordatorios se encolan y procesan mediante el worker MySQL configurado.
