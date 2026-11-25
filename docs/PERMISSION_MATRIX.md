# Matriz de permisos

Esta matriz resume el código y las rutas montadas; `docs/API_REFERENCE.md` es la referencia canónica de endpoints. Toda operación autenticada deriva el tenant de la identidad y restringe cada lectura/escritura al ámbito autorizado.

| Función | Público/visitante | Owner | Barber | Cuenta cliente | Super admin |
|---|---|---|---|---|---|
| Registro/login/reset | Sí | Sí | Sí | Sí | Sí |
| Ver perfil, catálogo y disponibilidad pública | Sí | Sí | Sí | Sí | Sí |
| Crear reserva como invitado | Sí | Sí | Sí | Sí; además se guarda en su historial | Sí |
| Solicitar contacto por horario (lista de espera) | Sí; solo propia solicitud | Consulta y seguimiento de su tenant | No | Sí; se comporta como petición guest | No por defecto |
| Filtrar, contactar y cambiar estado de solicitudes de espera | No | Solo su tenant | No | No | No por defecto |
| Consultar/cancelar/reprogramar reserva guest con token privado | Token de esa reserva | Token de esa reserva | Token de esa reserva | Token de esa reserva | Token de esa reserva |
| Agenda/estado/cobro/caja | No | Su negocio | Solo operaciones propias permitidas | No | Según endpoint administrativo explícito |
| Crear/editar barberos, clientes y comisiones | No | Su tenant | No; consulta permitida de sus comisiones | No | Según endpoints administrativos explícitos |
| Configurar negocio, horarios y branding | No | Su tenant | Lectura o acceso limitado según ruta | No | No por defecto |
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

## Reglas para cambios

- No aceptar `barbershop_id` de un owner/barber para determinar su ámbito; derivarlo del usuario autenticado.
- En rutas superadmin que acepten tenant, verificar primero el rol y luego exigir el identificador explícito.
- Comprobar pertenencia por objeto (cita, cliente, barbero, pago, imagen) además del rol.
- Responder sin filtrar existencia ajena donde el contrato y la privacidad lo requieran.
- Una cita guest se gestiona con su secreto aleatorio; el ID de cita nunca sirve como credencial.
- Una cuenta cliente solo reclama citas con el token privado de esa reserva; el teléfono no enlaza identidades ni comparte historiales CRM.
- La cuenta cliente sigue siendo parcial: favoritos, perfil e historial están integrados; pagos y beneficios no están implementados.
- Mantener pruebas negativas de acceso cruzado entre tenants para cada endpoint nuevo.
