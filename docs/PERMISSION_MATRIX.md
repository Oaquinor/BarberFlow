# Matriz de permisos

Esta matriz resume el código y las rutas montadas; `docs/API_REFERENCE.md` es la referencia canónica de endpoints. Toda operación de negocio autenticada debe derivar el tenant desde la identidad y filtrar cada lectura/escritura por ese tenant.

| Función | Público/visitante | Owner | Barber | Super admin |
|---|---:|---:|---:|---:|
| Registro/login/reset | Sí | Sí | Sí | Sí |
| Ver perfil, catálogo, disponibilidad pública | Sí | Sí | Sí | Sí |
| Crear reserva pública y consultar/cancelar con token privado | Sí | Sí | Sí | Sí |
| Agenda/estado/cobro/caja | No | Su negocio | Solo propias operaciones permitidas | Según endpoint explícito |
| Crear/editar barberos, clientes y comisiones | No | Su tenant | No; consulta de sus comisiones | Según endpoints administrativos explícitos |
| Configurar negocio, horarios y branding | No | Su tenant | Lectura o acceso limitado según ruta | No por defecto |
| Métricas de negocio | No | Su tenant | Sus métricas | Métricas globales/operación explícita |
| Tenants, suscripciones, soporte/auditoría plataforma | No | No | No | Sí |
| Cobro de suscripción | No | Solicitud manual; no carga fondos | No | Registro de pago externo ya recibido |
| Crear cuenta global y verificar correo | Sí | Sí | Sí | Sí |
| Consultar historial de cliente | No | Solo con una sesión propia de cliente verificada | Solo con una sesión propia de cliente verificada | No por defecto |
| Reclamar cita guest | Solo cuenta cliente verificada y token privado vigente | Igual | Igual | No por defecto |

## Reglas para cambios

- No aceptar `barbershop_id` de un owner/barber para determinar su ámbito; derivarlo del usuario autenticado.
- En rutas superadmin que acepten tenant, verificar primero el rol y luego exigir el identificador explícito.
- Comprobar pertenencia por objeto (cita, cliente, barbero, pago, imagen) además del rol.
- Responder sin filtrar existencia ajena donde el contrato y la privacidad lo requieran.
- Reservas guest solo pueden gestionarse con su secreto aleatorio; no tratar el ID de cita como credencial.
- Una cuenta cliente solo reclama citas con el token privado de esa reserva; el número telefónico no enlaza identidades ni comparte historial CRM.
- Las capacidades del cliente con sesión son parciales; no prometer una matriz de cuenta cliente completa.
- Agregar pruebas negativas de acceso cruzado entre tenants para cada nuevo endpoint.
