# Revisión defensiva de seguridad

**Alcance:** revisión defensiva del código y CI hasta `f8aaf04` y los cambios locales en favoritos de barberías, 25-11-2026. No es un pentest, certificación, revisión de infraestructura productiva ni auditoría legal.

## Controles observados

- JWT de acceso/refresh con refresh persistido y revocación; cambios de contraseña invalidan sesiones por versión de autenticación.
- Dependencias de autenticación/rol y helpers tenant; límites de intentos guardados en MySQL con operación atómica.
- Token aleatorio de gestión de reserva; documentar y probar límites de caducidad/uso según contrato actual.
- Migraciones explícitas; pagos y cambio de estado usan transacción del flujo.
- Carga de imagen con decodificación/re-encode y tipos/tamaños limitados (volver a comprobar cada endpoint de carga).
- Los registros CRM generados por reservas, turnos presenciales o alta manual no verifican correo/teléfono; `users.is_verified` permanece falso. No vincular una cuenta de cliente al CRM solo por teléfono.
- El perfil, historial y exportación de datos del portal cliente responden con `Cache-Control: no-store`; la PWA omite las respuestas `/api/` de su caché. Los cambios de perfil y las exportaciones se auditan sin guardar valores personales en el detalle del evento.
- Los favoritos de cuentas verificadas limitan cada alta/baja al titular y cada barbería, barbero o servicio al tenant activo; las lecturas no se cachean. Las rutas y pruebas MySQL de `f8aaf04` cubren rechazo de borrado entre cuentas; la ampliación al tipo barbería se está validando en el próximo CI.
- Cabeceras HTTP, CORS/secretos y validación de configuración productiva se establecen al arrancar.

## Riesgos / verificaciones pendientes

1. No hay evidencia de pentest externo ni de checklist ASVS completa. La referencia actual de ASVS es 5.0; elegir perfil/requisitos según aplicación y riesgo.
2. La máquina local no tenía `TEST_DATABASE_URL`, por lo que las pruebas de integración se omitieron localmente. GitHub Actions sí ejecutó las pruebas en MySQL 8.4: 171 pasaron con migración limpia, downgrade y recuperación. Esto cubre los flujos presentes, pero no sustituye pruebas de producción bajo carga ni una auditoría completa de aislamiento.
3. La revisión no confirma configuración real de proxy, TLS, backups/restauración, logs/alertas, secretos del proveedor ni permisos mínimos en producción.
4. SMTP y WhatsApp requieren proveedor/credenciales y worker; entrega real no fue validada.
5. MFA no está implementado. Considerar MFA especialmente para superadmin y owner antes de exposición amplia.
6. Revisar CSRF según transporte de credenciales en cada flujo, límites de sesión, caducidad y seguridad de links secretos.
7. Hay pruebas negativas para varias acciones sensibles nuevas (incluidos reclamo, cancelación, reprogramación y exportación de cuenta), pero falta cobertura sistemática de autorización por objeto/tenant para todo el API y análisis dinámico de API.
8. `pip-audit` y `npm audit` forman parte del workflow y pasaron en las ejecuciones CI citadas en `docs/PRODUCT_AUDIT.md`; el entorno local no los ejecutó.

## Acciones mínimas antes de producción

- Ejecutar integración sobre MySQL limpio y migración desde una copia representativa; probar restauración de backup.
- Revisión de autorización negativa multi-tenant, abuso de reservas, recuperación y carga de archivos.
- MFA para cuentas privilegiadas, rotación y monitoreo de secretos, política de headers/CORS/proxy revisada.
- Ejecutar análisis de dependencias Python y JS, SAST/DAST y revisión humana conforme al perfil ASVS seleccionado.
- Confirmar alertas y operación del worker; documentar retención de PII y respuesta a incidentes.

La CI de `b74a8d4` pasó en MySQL 8.4 y en los tres motores de navegador. Las pruebas de integración afirman explícitamente `Cache-Control: no-store` para respuestas de perfil, citas e historial exportado. Run: [GitHub Actions 45621663593](https://github.com/Oaquinor/BarberFlow/actions/runs/45621663593).

Referencias: [OWASP ASVS](https://asvs.org/), [OWASP API Security Top 10](https://owasp.org/www-project-api-security/).
