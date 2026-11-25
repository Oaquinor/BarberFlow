# Matriz de permisos

Esta matriz resume el código y las rutas montadas; `docs/API_REFERENCE.md` es la referencia canónica de endpoints. Toda operación autenticada deriva el tenant de la identidad y restringe cada lectura/escritura al ámbito autorizado.

| Función | Público/visitante | Owner | Barber | Cuenta cliente | Super admin |
|---|---|---|---|---|---|
| Registro/login/reset | Sí | Sí | Sí | Sí | Sí |
| Ver perfil, catálogo y disponibilidad pública | Sí | Sí | Sí | Sí | Sí |
| Crear reserva como invitado | Sí | Sí | Sí | Sí; además se guarda en su historial | Sí |
| Lista de espera y ofertas de turnos | Solicita contacto; solo acepta con token privado, oferta vigente y un solo uso | Administra solicitudes del tenant y ofrece slots válidos; cerrar revoca ofertas pendientes | No | Crea cita pendiente únicamente si la oferta sigue vigente y puede reclamar el slot | No por defecto |
| Filtrar, contactar y cambiar estado de solicitudes de espera | No | Solo su tenant | No | No | No por defecto |
| Buscar horarios y emitir oferta de espera | No | Solo solicitudes y turnos disponibles de su tenant; emite oferta con vencimiento, sin apartar hasta que el cliente acepte | No | No | No por defecto |
| Administrar catálogo, costos, precios y umbrales de inventario | No | Solo su tenant | No | No | No por defecto |
| Cobrar venta de productos y consultar ventas POS | No | Solo su tenant | No | No | No por defecto |
| Registrar y consultar gastos del negocio | No | Solo su tenant; idempotente y auditado; sin edición/borrado financiero | No | No | No por defecto |
| Registrar o consultar movimientos de existencias | No | Solo productos y movimientos de su tenant; deja auditoría | No | No | No por defecto |
| Consultar/cancelar/reprogramar reserva guest con token privado | Token de esa reserva | Token de esa reserva | Token de esa reserva | Token de esa reserva | Token de esa reserva |
| Check-in y estimación privada de cola | Solo con token de esa reserva; sin revelar otros clientes; ETA aproximada durante descanso solo si el barbero indicó regreso futuro, y se omite si no existe o ya venció | Consulta su tenant en agenda; recibe aviso | Consulta según su agenda; recibe aviso si es barbero asignado | Solo su cita con token de seguimiento | No por defecto |
| Agenda/estado/cobro/caja | No | Su negocio | Solo operaciones propias permitidas | No | Según endpoint administrativo explícito |
| Panel Live Chair del equipo | No | Solo barberos/agenda del tenant; sin datos identificables de clientes | No | No | No por defecto |
| Marcar disponibilidad/descanso en Live Chair | No | No modifica estado del equipo | Solo su perfil; descanso bloqueado mientras atiende, regreso previsto de 5–120 min y reanudación manual | No | No por defecto |
| Consultar conciliación del día | No | Su negocio, incluye egresos operativos | Sus cobros y cierres permitidos; no ve el detalle de gastos del negocio | No | Solo conforme al tenant de su cuenta |
| Crear/editar barberos, clientes y comisiones | No | Su tenant | No; consulta permitida de sus comisiones | No | Según endpoints administrativos explícitos |
| Configurar negocio, horarios y branding | No | Su tenant | Lectura o acceso limitado según ruta | No | No por defecto |
| Configurar retención de Style Passport | No | Elige o desactiva el plazo para su tenant; cambio auditado y confirmado si aplica retroactivamente | No | Consulta el plazo antes de guardar y en su historial | No por defecto |
| Métricas de negocio | No | Su tenant | Sus métricas | No | Métricas globales/operación explícita |
| Tenants, suscripciones, soporte/auditoría plataforma | No | No | No | No | Sí |
| Cobro de suscripción SaaS | No | Solicitud manual; no carga fondos | No | No | Registro de pago externo ya recibido |
| Crear cuenta cliente y verificar correo | Sí | No | No | Reenvío solo durante verificación | No |
| Consultar historial | No | No | No | Solo sus citas vinculadas; máximo 100 | No por defecto |
| Consultar/editar perfil de cliente | No | No | No | Solo su nombre y teléfono; correo requiere verificación independiente | No por defecto |
| Exportar sus datos | No | No | No | Solo perfil y citas vinculadas a su cuenta; descarga JSON y deja auditoría | No por defecto |
| Reclamar cita guest en el historial | No sin autenticación + token privado | No | No | Sí, únicamente con su token privado | No por defecto |
| Cancelar desde la cuenta cliente | No | No | No | Solo cita CRM vinculada a su cuenta; respeta anticipación y libera turno | No por defecto |
| Reprogramar desde la cuenta cliente | No | No | No | Solo cita CRM vinculada a su cuenta verificada; respeta anticipación y disponibilidad | No por defecto |
| Guardar/quitar favoritos | No | No | No | Puede guardar barberías activas y sus servicios/barberos; solo administra sus registros | No por defecto |
| Style Passport: crear/leer/editar/eliminar sus registros | No | No | No | Solo sus registros ligados a citas completadas propias | No por defecto |
| Fotos privadas del Style Passport | No | No | No | Gestiona y consulta sus fotos; almacenamiento privado y sin caché | No por defecto |
| Leer fotos/notas compartidas del Style Passport | No | Solo si el cliente lo comparte y el CRM pertenece al tenant | Igual, limitado a su tenant activo | Puede revocar en cualquier momento | No por defecto |
| Actualizar notas compartidas del Style Passport | No | Solo en registros compartidos del tenant | Solo en registros compartidos del tenant | No edita notas profesionales | No por defecto |

## Reglas para cambios

- No aceptar `barbershop_id` de un owner/barber para determinar su ámbito; derivarlo del usuario autenticado.
- En rutas superadmin que acepten tenant, verificar primero el rol y luego exigir el identificador explícito.
- Comprobar pertenencia por objeto (cita, cliente, barbero, pago, imagen) además del rol.
- Responder sin filtrar existencia ajena donde el contrato y la privacidad lo requieran.
- Una cita guest se gestiona con su secreto aleatorio; el ID de cita nunca sirve como credencial.
- Una cuenta cliente solo reclama citas con el token privado de esa reserva; el teléfono no enlaza identidades ni comparte historiales CRM.
- La cuenta cliente sigue siendo parcial: favoritos, perfil e historial están integrados; pagos y beneficios no están implementados.
- Mantener pruebas negativas de acceso cruzado entre tenants para cada endpoint nuevo.
- Las fotos del Style Passport nunca se sirven desde `/uploads` público; preservar autenticación, consentimiento, `no-store` y aislamiento de tenant en lecturas.
