# API de KingFlow Barber

Base local: `http://localhost:8000/api/v1`. La lista siguiente corresponde a las rutas montadas por FastAPI. Los ejemplos usan centavos y la hora ISO 8601.

## Autenticación y SaaS

| Método | Ruta | Acceso |
|---|---|---|
| `POST` | `/auth/login` | Público; aplica límite de intentos |
| `POST` | `/saas/register` | Público; crea owner, barbería y periodo gratuito |
| `GET` | `/saas/registration-status` | Público; indica si el registro está habilitado y los días del periodo gratuito configurado |
| `POST` | `/auth/refresh` | Token refresh vigente |
| `POST` | `/auth/logout` | Token refresh |
| `POST` | `/auth/change-password` | Usuario autenticado |
| `POST` | `/auth/password-reset/request` | Público; responde sin revelar si la cuenta existe y limita solicitudes por correo/IP |
| `POST` | `/auth/password-reset/confirm` | Público; requiere token de un solo uso vigente y contraseña robusta |
| `GET` | `/auth/me` | Usuario autenticado |
| `POST` | `/client-account/register` | Público; crea cuenta global inactiva y envía verificación por correo; requiere SMTP |
| `POST` | `/client-account/resend-verification` | Público; respuesta no enumera cuentas y limita intentos por IP |
| `POST` | `/client-account/verify` | Público; activa una cuenta con token de 30 minutos, de un solo uso |
| `GET` | `/client-account/profile` | Cliente autenticado y verificado; devuelve sus datos editables |
| `PATCH` | `/client-account/profile` | Actualiza nombre y teléfono propios; email no editable; registra auditoría |
| `GET` | `/client-account/export` | Cliente autenticado y verificado; descarga perfil e historial propio en JSON |
| `GET` | `/client-account/appointments` | Cuenta cliente autenticada y correo verificado; hasta 100 citas vinculadas |
| `GET` | `/client-account/favorites` | Cliente verificado; solo favoritos propios activos; no almacena en caché datos privados |
| `POST` | `/client-account/favorites` | Guarda/restaura una barbería, barbero o servicio existente en el tenant indicado; idempotente y auditado |
| `DELETE` | `/client-account/favorites/{favorite_id}` | Eliminación lógica del favorito propio; IDs de otras cuentas responden 404 |
| `POST` | `/client-account/appointments/claim` | Cuenta cliente autenticada y token privado de seguimiento; añade una cita a su historial |
| `POST` | `/client-account/appointments/{appointment_id}/cancel` | Dueño autenticado de la cita mediante enlace CRM; aplica estado, anticipación de cancelación, libera el turno y encola notificaciones |
| `GET` | `/client-account/style-passport` | Cliente verificado; lista hasta 50 registros propios y privados con el plazo de retención vigente de cada barbería |
| `POST` | `/client-account/style-passport` | Guarda preferencias para una cita completada propia; compartir con la barbería es opcional y desactivado por defecto |
| `PATCH` | `/client-account/style-passport/{entry_id}` | Edita preferencias propias y revoca o concede consentimiento para compartir |
| `DELETE` | `/client-account/style-passport/{entry_id}` | Elimina el registro, retira las fotos privadas y limpia los datos de estilo |
| `POST` | `/client-account/style-passport/{entry_id}/photos?photo_kind=reference|result` | Sube JPG/PNG privado (hasta dos por categoría, 5 MB cada uno); se procesa sin EXIF |
| `GET` | `/client-account/style-passport/{entry_id}/photos/{photo_id}` | Entrega una foto propia autenticada, sin caché |
| `DELETE` | `/client-account/style-passport/{entry_id}/photos/{photo_id}` | Retira una foto privada propia |
| `GET` | `/owner/clients/{client_id}/style-passport` | Owner o barbero del tenant; devuelve solo registros compartidos explícitamente por el cliente |
| `PATCH` | `/owner/clients/{client_id}/style-passport/{entry_id}` | El equipo del tenant actualiza notas y recomendaciones en un registro compartido |
| `GET` | `/owner/clients/{client_id}/style-passport/{entry_id}/photos/{photo_id}` | Acceso autenticado del tenant a fotos del registro compartido |
| `PUT` | `/onboarding/business-settings` | Owner configura zona, marca, políticas de reserva y retención Style Passport (`null`, 90, 180, 365 o 730 días); el historial de citas autenticado devuelve el plazo de cada barbería |
| `GET` | `/billing/subscription` | Owner autenticado; devuelve estado del periodo y uso de límites del plan |
| `POST` | `/billing/renewal-request` | Owner autenticado; crea o reutiliza una solicitud abierta en la bandeja de soporte. No cobra ni reactiva la cuenta |

El registro de barbería recibe `owner_email`, `owner_password`, `owner_first_name`, `owner_last_name`, `owner_phone`, `barbershop_name`, `barbershop_email`, `barbershop_phone`, `address_line1`, `city`, `state`, `postal_code`, `country`, `timezone`, `currency` y un `affiliate_code` opcional. Se limita a cinco intentos por IP por hora. Un código inválido se rechaza; uno válido registra el referido con el owner, barbería y suscripción en una sola transacción. Las contraseñas nuevas —registro, cambio y recuperación— requieren al menos 12 caracteres, una mayúscula y un número, y no deben exceder 72 bytes UTF-8 por el límite de bcrypt. El registro no cobra ni simula un pago.

Usa `Authorization: Bearer <access_token>` en las rutas protegidas. Los tokens refresh son rotativos y revocables; cada access token emitido por login o refresh queda ligado a su sesión, por lo que rotar o cerrar sesión también invalida ese access token. Cambiar o recuperar la contraseña incrementa `auth_version`, invalidando access tokens y sesiones refresh de todos los dispositivos.

La solicitud de recuperación devuelve el mismo mensaje para correos registrados y desconocidos. Limita a cinco solicitudes por correo/IP y treinta por IP en una hora. Si la cuenta está activa y SMTP entrega el mensaje, el enlace vence en 30 minutos y se consume una sola vez. Configura `FRONTEND_BASE_URL` con el origen HTTPS público en producción.

## Portal público del cliente

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/public/{slug}` | Perfil público, moneda y zona horaria |
| `GET` | `/public/{slug}/services` | Catálogo activo |
| `GET` | `/public/{slug}/slots?duration_minutes={minutes}` | Turnos que caben en la duración del servicio y no se solapan con citas ni ausencias |
| `POST` | `/public/{slug}/appointments` | Crea una reserva como invitado con nombre/teléfono o autenticada con una cuenta de cliente verificada; esta última se guarda en el historial |
| `POST` | `/public/{slug}/waitlist` | Registra una solicitud sin compromiso para que la barbería contacte al cliente; limita por negocio/IP y conserva snapshots del servicio/profesional en MySQL |
| `GET` | `/public/{slug}/waitlist-offers/{token}` | Muestra al titular del enlace el detalle mínimo de una oferta privada y su vencimiento; respuesta `no-store` |
| `POST` | `/public/{slug}/waitlist-offers/{token}/accept` | Acepta una oferta vigente una sola vez; reclama el turno y crea cita pendiente en una transacción MySQL; reintentos devuelven la misma cita y la respuesta es `no-store` |
| `POST` | `/public/{slug}/track` | Consulta con token privado; la espera aproximada se omite durante el descanso del barbero |
| `POST` | `/public/{slug}/appointments/check-in` | Confirma llegada con token privado desde 60 min antes hasta 30 min después de la cita |
| `POST` | `/public/{slug}/appointments/reschedule` | Cambia turno con token privado o sesión autenticada de la cuenta propietaria |
| `POST` | `/public/{slug}/appointments/cancel` | Cancela turno con token privado |

Reserva:

La reserva autenticada acepta `Authorization: Bearer <access_token>` y no requiere repetir `client_name` ni `phone`; la identidad se toma de la cuenta y se vincula a un perfil CRM separado de la barbería. Sin token, ambos campos siguen siendo obligatorios para una reserva de invitado. La respuesta incluye `saved_to_account`.

El seguimiento privado informa si el check-in está abierto, la hora de llegada y una posición/espera aproximadas para el cliente que ya confirmó su llegada. La estimación solo considera citas confirmadas que también hicieron check-in y citas en curso del mismo barbero; no revela nombres ni datos de otros clientes y se recalcula al volver a consultar. Reprogramar elimina el check-in anterior. No equivale a seguimiento en vivo ni envía notificaciones push.

La cuenta cliente puede actualizar nombre/teléfono, descargar perfil e historial en JSON, cancelar y reprogramar sus citas futuras `pending` o `confirmed` desde el historial. El correo se mantiene verificado y no se cambia desde este formulario. Las respuestas de perfil, historial y exportación usan `Cache-Control: no-store`. El API verifica el enlace de propiedad CRM y aplica la política de anticipación. Cancelar actualiza estado y libera el turno; reprogramar requiere `appointment_id` junto con `availability_id` y un `Authorization: Bearer <access_token>` de cliente verificado. El ID por sí solo nunca autoriza el acceso. El flujo confirma el nuevo turno y libera el anterior dentro de la misma transacción, con validación de disponibilidad, conflictos, notificación y auditoría.

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

La solicitud de lista de espera admite `client_name`, `phone`, `service_id`, un `idempotency_key` UUID y opciones `barber_id`, `preferred_date_start`, `preferred_date_end` y `notes`. La clave se conserva únicamente como hash, tiene unicidad por barbería y permite reintentar una solicitud si se pierde la respuesta. El teléfono se guarda solo con dígitos; las fechas deben formar un rango dentro del límite de anticipación de reservas configurado. Recibir una solicitud no crea una cita ni reserva un turno. El owner puede convertir una coincidencia revisada en una oferta que se entrega por el outbox WhatsApp y vence; el cliente acepta desde enlace privado. Al aceptar, se valida nuevamente el estado del negocio/plan, límites, servicio, turno, barbero, bloqueos, citas y caja; se reclama el horario con compare-and-set y se crea una cita pendiente dentro de la misma transacción. El token se conserva como hash, las ofertas hermanas se cancelan y el reintento devuelve la misma cita. La aceptación aplica límite anónimo por IP.

Las solicitudes de reserva para barberías con suscripción activa se limitan por IP y barbería a 10 por hora, con un límite adicional de 60 por IP por hora entre todas las barberías. El backend guarda únicamente hashes con clave secreta para aplicar la cuota y responde `429` con `Retry-After` al superarla.

El enlace de seguimiento contiene un token aleatorio; la base de datos guarda su hash. No se acepta un ID de cita como sustituto de autorización. Para reprogramar envía `{"token":"<token privado>","availability_id":45}`; el sistema bloquea el nuevo turno, valida duración y conflictos, libera el anterior y registra el cambio atómicamente. Cancelación acepta `token` y `reason` opcional. Email/WhatsApp depende de configuración real del proveedor.

La reserva pública acepta `booking_answers` como un mapa de las preguntas estándar de estilo y las preguntas actualmente configuradas por la barbería. El backend rechaza claves ajenas o desactualizadas; conserva las respuestas como JSON en MySQL y las devuelve solo en las agendas autorizadas del owner/barbero. Las respuestas se escapan al mostrarse. El campo `notes` permanece compatible para las notas libres históricas.

Las rutas de consulta, servicios, disponibilidad y reserva requieren una suscripción activa. Cancelar una reserva futura no requiere iniciar sesión.

Las cuentas de cliente son identidades globales (`role=client`, sin `barbershop_id`) y no sustituyen los registros tenant-scoped del CRM. El email debe verificarse antes de iniciar sesión. Las citas existentes se importan presentando el token privado de seguimiento; no se enlazan registros por teléfono. Al reclamar se crea un perfil CRM separado para ese cliente y barbería, y una cita ya vinculada a otra cuenta no se puede transferir con el mismo token. El endpoint de reprogramación también acepta el token privado sin sesión para conservar el flujo existente; alternativamente, permite `appointment_id` solo si una cuenta cliente verificada autenticada tiene el enlace CRM correspondiente.

## Bandeja autenticada

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/notifications?limit=50&unread_only=false` | Lista notificaciones del usuario autenticado y su contador de no leídas |
| `GET` | `/notifications/unread-count` | Devuelve solo el contador de no leídas para actualizar el indicador sin descargar la bandeja |
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
| `GET` | `/owner/live-chair` | Estado operativo por barbero para el propietario; devuelve atención activa, cantidad de check-ins, próxima cita y estimación aproximada, sin nombres/notas de clientes |
| `GET` | `/barber/live-status` | Estado disponible/descanso del barbero autenticado |
| `PUT` | `/barber/live-status` | Actualiza disponibilidad o descanso; no permite iniciar descanso con servicio activo |
| `GET` | `/barber/appointments?target_date=YYYY-MM-DD` | Agenda local del negocio; al equipo incluye el ID del perfil CRM para consultar únicamente el Style Passport compartido |
| `GET` | `/barber/appointments/calendar?view=week&anchor_date=YYYY-MM-DD` | Citas por día para una semana o mes local; el barbero solo recibe sus citas y el ID CRM necesario para revisar registros compartidos |
| `PUT` | `/barber/appointments/{appointment_id}/status` | Confirma, inicia, cancela o marca no presentado |
| `POST` | `/barber/appointments/{appointment_id}/payment` | Registra el pago y finaliza el servicio |
| `POST` | `/barber/appointments/walk-in` | Inicia una atención presencial sin reserva |
| `GET` | `/barber/commissions` | El barbero consulta sus comisiones y saldos por moneda |
| `GET` | `/barber/cash/today` | Cobros, comisiones pagadas y movimiento neto de efectivo del día local; owner incluye gastos |
| `POST` | `/barber/cash/close` | Concilia cierre diario con fondo inicial, efectivo contado y egresos |
| `GET` | `/barber/share-link` | Enlace público del negocio |

## Gestión del negocio (owner)

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/owner/barbers` | Lista los barberos de la barbería |
| `POST` | `/owner/barbers` | Crea acceso con contraseña inicial y aplica el límite del plan |
| `PUT` | `/owner/barbers/{barber_id}` | Actualiza nombre y teléfono de un barbero del tenant, con auditoría |
| `PUT` | `/owner/barbers/{barber_id}/status` | Activa o desactiva un barbero del mismo tenant |
| `GET` | `/owner/clients?limit=50&offset=0&search=` | Lista y pagina clientes del tenant por nombre, teléfono o correo, con citas y total efectivamente pagado |
| `GET` | `/owner/clients/{client_id}/appointments?limit=20&offset=0` | Historial paginado de citas y pagos del cliente dentro del tenant autenticado |
| `POST` | `/owner/clients` | Registra un cliente manual en el tenant, aplica el límite del plan y audita el alta |
| `PUT` | `/owner/clients/{client_id}` | Actualiza nombre y teléfono de un cliente del tenant, con auditoría |
| `PUT` | `/owner/clients/{client_id}/status` | Activa o desactiva el acceso del cliente sin borrar su historial |
| `GET` | `/owner/waitlist?status=new&limit=50&offset=0` | Consulta solicitudes de espera del tenant autenticado; permite filtrar `new`, `contacted` o `closed` |
| `GET` | `/owner/waitlist/{entry_id}/matches` | Busca hasta ocho turnos abiertos según servicio, duración, profesional, bloqueos, citas y fechas; devuelve IDs para emitir una oferta |
| `POST` | `/owner/waitlist/{entry_id}/offers` | Emite oferta WhatsApp por un turno compatible; vencimiento entre 15 y 1440 minutos (120 por defecto), token aleatorio guardado como hash y entrega en outbox |
| `PUT` | `/owner/waitlist/{entry_id}/status` | Marca la solicitud `new`, `contacted` o `closed`; cerrar revoca ofertas pendientes, registra hora de contacto y auditoría |

El alta manual requiere nombre, apellido y teléfono; normaliza el teléfono y rechaza duplicados del mismo tenant. Crea una ficha sin acceso de cuenta ni cita asociada.

La cola de espera solo la consulta el owner del negocio correspondiente; barberos y otros tenants no tienen acceso. Incluye el teléfono necesario para el seguimiento comercial, pero no devuelve ningún contacto a la API pública.
| `GET` | `/onboarding/profile` | Lee el perfil, horario y zona horaria de la barbería autenticada |
| `PUT` | `/onboarding/business-settings` | Actualiza perfil público, horario, zona, tema, preguntas y anticipación de cancelación; registra auditoría |
| `PUT` | `/onboarding/brand-colors` | Guarda los colores de marca del tenant |
| `POST` | `/onboarding/upload-logo` | Valida y guarda un logo PNG/JPG de hasta 5 MB |
| `POST` | `/onboarding/upload-cover` | Valida y guarda la imagen de portada PNG/JPG del tenant |
| `DELETE` | `/onboarding/cover-image` | Quita la portada personalizada y vuelve a la portada editorial predeterminada |
| `POST` | `/onboarding/upload-gallery-image` | Valida, guarda y registra una imagen de galería para el perfil público |
| `DELETE` | `/onboarding/gallery-image` | Quita una imagen de la galería, desvincula la imagen del servicio y registra auditoría |
| `POST` | `/onboarding/step/1` | Guarda el nombre de la barbería |
| `POST` | `/onboarding/step/3` | Guarda los colores de marca |
| `POST` | `/onboarding/step/4` | Guarda el estilo elegido |
| `POST` | `/onboarding/step/5` | Guarda el objetivo principal |
| `POST` | `/onboarding/step/6` | Guarda el tamaño del equipo |
| `POST` | `/onboarding/step/7` | Guarda la duración promedio del servicio |
| `POST` | `/onboarding/step/8` | Guarda el horario comercial |
| `POST` | `/onboarding/step/9` | Guarda la personalidad del negocio |
| `POST` | `/onboarding/complete` | Valida, guarda y audita la configuración final |
| `GET` | `/onboarding/dashboard-layout` | Devuelve consejos según el objetivo del negocio; no declara widgets ni métricas que el panel no ofrezca |
| `GET` | `/onboarding/greeting` | Devuelve saludo contextual por hora local del tenant |
| `POST` | `/onboarding/motivational-message` | Devuelve mensaje según el logro indicado y datos del negocio |

Las rutas de escritura requieren rol owner; las que admiten `super_admin` exigen además `barbershop_id`. Para owner/barbero, el tenant se deriva de la identidad autenticada. Las rutas de perfil y contenido del panel permiten owner o barbero. Los pasos 1 y 3–9 guardan el progreso en MySQL y permiten reanudar el onboarding. El paso 2 carga el logo por `/upload-logo` y el último paso aplica los datos por `/complete`. La actualización de configuración valida horas, zona IANA y `cancellation_window_hours` entero entre 0 y 168. Cero permite cambios públicos antes del inicio; un valor mayor exige esa anticipación para cancelar o reprogramar. El perfil público informa la política antes de confirmar la cita. La migración `032_cancellation_window` preserva las barberías existentes con valor cero.

`GET /billing/subscription` devuelve al owner el estado efectivo del periodo y el uso de límites del plan para su tenant. Las citas consumidas se cuentan por mes calendario en la zona horaria del negocio, igual que el límite mensual aplicado al reservar o crear turnos presenciales. Una suscripción marcada activa cuyo periodo ya terminó se informa como vencida sin mutar datos al leer. `POST /billing/renewal-request` registra una solicitud tenant-scoped y auditada en soporte; solicitudes abiertas se reutilizan para evitar duplicados. La solicitud no cobra ni reactiva la cuenta. El campo de respuesta histórico `auto_renew` se conserva solo por compatibilidad; no activa cargos y no puede habilitarse desde el formulario de administración. Cada periodo requiere registrar manualmente un pago externo recibido.

## Analítica de demanda

| Método | Ruta | Acceso | Función |
|---|---|---|---|
| `GET` | `/analytics/demand-forecast` | Owner autenticado | Estima el volumen de servicios por día y hora para los próximos siete días |
| `GET` | `/analytics/financial-report?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | Owner autenticado | Resume pagos cobrados y gastos registrados por día comercial, método y categoría; por barbero muestra servicios |

El pronóstico usa el promedio histórico de citas completadas por día de la semana y hora durante las 12 semanas anteriores, y lo combina con las reservas próximas conocidas. Es una referencia estadística explicable, no un modelo de aprendizaje automático. La respuesta incluye el periodo y tamaño de la muestra, reservas conocidas, horas pico y nivel de confianza; con poco historial se indica esa limitación y solo sirven de referencia las reservas existentes. Todos los datos se filtran por la barbería del owner autenticado.

El reporte financiero exige un rango de fechas de hasta 366 días y lo interpreta en la zona horaria IANA del negocio. Se basa en cobros y egresos realmente guardados, separa servicios, productos, propinas y gastos, y expresa todos los importes en centavos y la moneda del tenant. El saldo se llama «cobros menos gastos registrados» y no es utilidad neta: no necesariamente incluye todos los costos, impuestos ni obligaciones. Las ventas minoristas y gastos no se asignan a un barbero. No estima ingresos de citas aún no cobradas.

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
{"business_date":"2026-11-19","opening_cash_cents":10000,"declared_cash_cents":30000,"notes":"Conteo revisado"}
```

Un barbero ve sus cobros; el owner ve los del negocio y sus gastos. Antes del cierre, «movimiento neto de efectivo» son las entradas en efectivo menos comisiones en efectivo y gastos en efectivo, excluido el fondo inicial. El cierre lo suma al fondo inicial para obtener el efectivo esperado, conserva fondo, esperado, declarado y diferencia. Una segunda conciliación de la misma fecha y usuario se rechaza. El cierre del owner también cierra la fecha para los barberos del negocio. Antes de cerrar, se deben resolver las citas pendientes o confirmadas y finalizar los servicios en curso de esa fecha, también cuando se cierra un día anterior.

## Catálogo de servicios

| Método | Ruta | Acceso |
|---|---|---|
| `GET` | `/services/` | Roles autenticados de la barbería |
| `GET` | `/services/{service_id}` | Tenant propietario del registro |
| `POST` | `/services/` | Owner |
| `PUT` | `/services/{service_id}` | Owner |
| `DELETE` | `/services/{service_id}` | Owner; baja lógica |

`name` admite hasta 100 caracteres y se conserva como snapshot en la cita; `price` es entero en centavos. Todos los registros se restringen al tenant autenticado.

## Productos e inventario

Todas estas rutas requieren sesión de propietario y derivan la barbería del usuario autenticado. Los precios y costos se reciben como enteros en unidades monetarias menores (por ejemplo, 550 para RD$5.50). Las cantidades solo cambian mediante el libro de movimientos; las entradas son inmutables desde la API.

| Método | Ruta | Acceso |
|---|---|---|
| `GET` | `/owner/inventory/products?q=&low_stock=false&include_inactive=false&limit=50&offset=0` | Owner de su tenant; búsqueda y paginación |
| `POST` | `/owner/inventory/products` | Owner; crea producto sin existencias iniciales |
| `PATCH` | `/owner/inventory/products/{product_id}` | Owner del tenant del producto |
| `POST` | `/owner/inventory/products/{product_id}/movements` | Owner; registra recepción, devolución, consumo o ajuste idempotente y evita stock negativo |
| `GET` | `/owner/inventory/movements?product_id=&limit=50&offset=0` | Owner; consulta historial de su tenant |
| `POST` | `/owner/inventory/sales` | Owner; cobra líneas de productos sin cita y descuenta existencias en una operación idempotente |
| `GET` | `/owner/inventory/sales?limit=50&offset=0` | Owner; lista ventas de su tenant |

Cada movimiento conserva su costo unitario, actor, razón y nota; la idempotencia usa hash de clave y payload. La creación del movimiento, el saldo actualizado y la auditoría se confirman en una sola transacción MySQL. La venta guarda snapshots de precio/costo, bloquea el tenant y los productos, impide existencias negativas y se refleja en efectivo esperado y reporte financiero. El panel owner prepara un carrito de hasta 50 productos distintos, admite reintentos seguros y muestra las últimas diez ventas. El POS actual no aplica impuestos/descuentos, no procesa reembolsos, compras/proveedores, transferencias entre sucursales ni comisiones de producto.

## Gastos del negocio

| Método | Ruta | Acceso | Función |
|---|---|---|---|
| `POST` | `/owner/expenses` | Owner; solo su tenant | Registra un gasto pagado con categoría, método, importe en centavos, UUID idempotente y auditoría |
| `GET` | `/owner/expenses?start_date=&end_date=&limit=50` | Owner; solo su tenant | Lista hasta 100 egresos por fecha local; el rango de fechas debe enviarse completo |

Los gastos son append-only desde la API: no hay edición ni eliminación que cambie registros financieros ya asentados. La clave UUID y el payload se almacenan como hashes; el mismo reintento devuelve el registro y reutilizar la clave con otros datos responde `409`. Registrar un gasto tras el cierre del día también responde `409`. Solo el método en efectivo afecta el movimiento neto y la conciliación; tarjeta/transferencia se muestran en el reporte por método. Las categorías no sustituyen cuentas contables. En esta etapa no se guardan comprobantes ni proveedores y no hay gastos recurrentes.

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

La fecha predeterminada de rendimiento usa la zona horaria de la barbería. En `/performance/monthly/{barber_id}`, `year` y `month` son opcionales solo como pareja: si se omiten ambos se usa el mes comercial actual; si se envía uno solo, la API responde `422`. Ingresos se derivan de pagos efectivamente registrados. Los logros disponibles se insertan con la migración MySQL `011_seed_achievements`; el pago completado actualiza el rendimiento y evalúa logros compatibles.

## Onboarding y personalización

Rutas protegidas bajo `/onboarding`: `GET /profile`, `GET /dashboard-layout`, `GET /greeting`; `POST /complete`, `/motivational-message`, `/step/1`, `/step/3` a `/step/9`, `/upload-logo`, `/upload-cover`, `/upload-gallery-image`; `DELETE /cover-image`, `/gallery-image`; `PUT /brand-colors`. El tenant se deriva del usuario autenticado. `/dashboard-layout` devuelve `layout_type`, `greeting_message` e `insights` para orientar el uso del panel existente; no anuncia widgets o métricas inexistentes. El mensaje motivacional calcula el conteo de citas de los últimos 30 días y no confía en el contexto enviado por el cliente.

## Equipo y clientes del negocio

| Método | Ruta | Acceso |
|---|---|---|
| `GET` / `POST` | `/owner/barbers` | Owner del tenant; listado y alta con límites del plan |
| `PUT` | `/owner/barbers/{barber_id}` | Actualiza nombre y teléfono de un barbero del tenant, con auditoría |
| `PUT` | `/owner/barbers/{barber_id}/status` | Owner del tenant; activar o desactivar |
| `PUT` | `/owner/barbers/{barber_id}/commission-rate` | Configurar tasa del barbero (puntos base; 0 a 10 000) |
| `GET` | `/owner/barber-commissions` | Consultar comisiones generadas por cobros del tenant |
| `POST` | `/owner/barber-commissions/{commission_id}/pay` | Registrar liquidación de comisión con método y referencia |
| `GET` | `/owner/clients` | Owner del tenant; historial agregado, búsqueda por nombre/teléfono/correo y paginación |
| `GET` | `/owner/clients/{client_id}/appointments` | Owner del tenant; historial y pagos de su cliente, paginado y tenant-scoped |
| `POST` | `/owner/clients` | Registrar cliente manualmente, con límite del plan y auditoría |
| `PUT` | `/owner/clients/{client_id}` | Editar nombre y teléfono, con auditoría |
| `PUT` | `/owner/clients/{client_id}/status` | Activar o desactivar acceso conservando citas y cobros |
| `POST` | `/barber/slots` | Barbero propio; turnos dentro del horario configurado |
| `GET` | `/barber/dashboard` | Barbero propio u owner; agenda operativa del día |

La gestión de clientes permite alta manual, edición de nombre y teléfono, y desactivar el acceso conservando citas y cobros. La gestión de barberos permite alta, edición de nombre y teléfono, activación y tasa de comisión; no hay eliminación de perfiles. Los turnos creados se serializan por barbero en MySQL para evitar solapamientos concurrentes.

El portal público envía la duración seleccionada al consultar turnos. Si no se indica `duration_minutes`, el endpoint usa la duración del servicio activo más corto. El servidor vuelve a validar el turno al reservar y reprogramar.

El propietario define la tasa porcentual por barbero. Al registrar un pago de cita, el backend crea la comisión pendiente en la misma transacción usando el importe del servicio, sin incluir propina. El barbero solo ve sus registros; el propietario solo puede consultar y liquidar los de su barbería. La liquidación queda auditada y no se puede repetir. Los pagos de comisión en efectivo se registran como salidas en el efectivo esperado del cierre diario del propietario; no se aceptan después de cerrar esa caja.

La ruta de calendario acepta `view=week` o `view=month`. Sus límites de fecha se calculan en la zona horaria del tenant; los resultados quedan filtrados por barbería y, para el rol barbero, por su usuario. La vista de día conserva operaciones para iniciar, cancelar y cobrar citas; las vistas agrupadas permiten abrir el día seleccionado.

La agenda del día y el dashboard incluyen `booking_answers`; las preguntas y respuestas que un cliente envió al reservar aparecen separadas de las notas libres de citas anteriores.

## Administración de plataforma

Todas las rutas `/admin/*` requieren rol `super_admin`.

| Método | Ruta | Función |
|---|---|---|
| `GET` | `/admin/overview` | Métricas globales de tenants, usuarios, suscripciones, citas y cobros por moneda |
| `GET` | `/admin/tenants` | Barberías y suscripciones |
| `PUT` | `/admin/tenants/{barbershop_id}/status` | Activar o suspender barbería |
| `GET` | `/admin/tenants/{barbershop_id}/subscription` | Consultar suscripción |
| `PUT` | `/admin/tenants/{barbershop_id}/subscription` | Administrar plan y periodo |
| `POST` | `/admin/tenants/{barbershop_id}/subscription/payments` | Registrar pago SaaS externo ya recibido |
| `GET` | `/admin/users?barbershop_id=1&search=ana&limit=50&offset=0` | Buscar usuarios con filtro tenant y paginación |
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

Al cambiar el estado de una barbería, se revocan sus sesiones de renovación y se invalida la versión de sesión de sus usuarios; al reactivarla todos deben iniciar sesión de nuevo. Suspender o reactivar un usuario individual también invalida sus tokens y sesiones de renovación. El último superadministrador no se puede desactivar. El historial guarda eventos sensibles junto con la operación y omite tokens y contraseñas. El resumen global cuenta cobros de citas por separado para cada moneda; no suma monedas distintas. El registro SaaS de cobro requiere importe positivo, periodo vigente y confirmación administrativa de un pago ya recibido; no se conecta a una pasarela ni procesa tarjetas. Las comisiones guardan la moneda de origen. El pago de afiliados requiere aprobar la comisión y registrar método y referencia externa.

El listado de usuarios acepta `barbershop_id`, `search` (nombre o correo), `limit` (1–100, por defecto 50) y `offset` (por defecto 0); la respuesta incluye `total`, `offset` y `limit` para recorrer resultados sin cargar todos los usuarios en el navegador.

`GET /admin/tenants` incluye el código ISO de moneda de cada barbería. La administración lo muestra al registrar cobros externos para evitar interpretar el importe en una moneda distinta de la que se guarda en MySQL. La ruta `PUT /admin/tenants/{barbershop_id}/subscription` no puede activar, cambiar ni extender un plan de pago activo sin un pago registrado para el periodo; prepara el plan en estado inactivo y usa la ruta `/subscription/payments` después de confirmar el cobro. Esa ruta registra el pago y activa el periodo en una sola operación.

`GET /saas/registration-status` expone si el registro está habilitado y `free_period_days`, que el formulario de alta muestra según la configuración vigente. Si se desactiva, el formulario de alta se bloquea y el endpoint de registro lo rechaza de nuevo en servidor. Los cambios de estos parámetros se guardan en MySQL y generan auditoría; los secretos siguen en variables de entorno.

La bandera disponible `branding_auto` controla si el portal autenticado aplica los colores de marca de la barbería. Solo se activa para un usuario owner/barbero con onboarding completado; su estado forma parte de `/auth/me` y del listado de usuarios. Los cambios se reflejan al volver a iniciar sesión.

## Soporte y errores

| Método | Ruta | Acceso | Función |
|---|---|---|---|
| `POST` | `/support/contact` | Público; limitado por IP | Persiste una solicitud y encola un aviso por correo |
| `GET` | `/admin/support/tickets?status=open&limit=50&offset=0` | `super_admin` | Consulta y pagina solicitudes de soporte |
| `PUT` | `/admin/support/tickets/{ticket_id}/status` | `super_admin` | Cambia estado y audita la solicitud |
| `GET` | `/health` | Público | Verifica la conexión real a MySQL |
| `GET` | `/` | Público | Sirve la aplicación web |

`POST /support/contact` recibe nombre, email o teléfono, mensaje y slug opcional. Cada solicitud se conserva en MySQL aunque SMTP esté caído; la respuesta incluye `ticket_id` y `notification_sent`. El formulario limita a cinco solicitudes por IP y hora y persiste solo un hash de la dirección.

El superadministrador puede consultar `GET /admin/support/tickets?status=open&limit=50&offset=0` (incluye total para paginar) y cambiar su estado con `PUT /admin/support/tickets/{ticket_id}/status` (`open`, `in_progress`, `resolved` o `closed`). Solo el rol `super_admin` puede ver o gestionar la bandeja; cada cambio de estado genera auditoría.

Errores usan JSON `{"detail":"..."}`. Códigos usados: `401` autenticación, `403` permiso, `404` recurso del tenant, `409` conflicto/transición, `422` validación y `402` límite o suscripción inactiva.

Las respuestas incluyen `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, una CSP que limita los scripts al mismo origen, restringe las URL base y formularios al mismo origen y bloquea objetos y marcos, y una `Permissions-Policy` que bloquea cámara, micrófono y geolocalización. La CSP se omite solo en Swagger/ReDoc cuando se habilitan explícitamente como documentación de desarrollo. En producción también se incluye HSTS. Las rutas bajo `/api/` añaden `Cache-Control: no-store` y `Pragma: no-cache` para impedir que el navegador almacene respuestas operativas o datos personales.

La API no implementa actualmente cobro automatizado de suscripciones ni notificaciones push. El owner puede registrar, editar y desactivar clientes; no hay eliminación de clientes para conservar su historial. El owner puede registrar y editar los datos básicos de barberos, activarlos y configurar su comisión, pero no eliminarlos. Los recordatorios se encolan y procesan mediante el worker MySQL configurado.
