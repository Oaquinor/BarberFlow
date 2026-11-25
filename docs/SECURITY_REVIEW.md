# Revisión defensiva de seguridad

**Alcance:** lectura del código y cobertura automatizada local, 25-11-2026. No es un pentest, certificación, revisión de infraestructura productiva ni auditoría legal.

## Controles observados

- JWT de acceso/refresh con refresh persistido y revocación; cambios de contraseña invalidan sesiones por versión de autenticación.
- Dependencias de autenticación/rol y helpers tenant; límites de intentos guardados en MySQL con operación atómica.
- Token aleatorio de gestión de reserva; documentar y probar límites de caducidad/uso según contrato actual.
- Migraciones explícitas; pagos y cambio de estado usan transacción del flujo.
- Carga de imagen con decodificación/re-encode y tipos/tamaños limitados (volver a comprobar cada endpoint de carga).
- Los registros CRM generados por reservas, turnos presenciales o alta manual no verifican correo/teléfono; `users.is_verified` permanece falso. No vincular una cuenta de cliente al CRM solo por teléfono.
- Cabeceras HTTP, CORS/secretos y validación de configuración productiva se establecen al arrancar.

## Riesgos / verificaciones pendientes

1. No hay evidencia de pentest externo ni de checklist ASVS completa. La referencia actual de ASVS es 5.0; elegir perfil/requisitos según aplicación y riesgo.
2. MySQL de pruebas no estaba disponible bajo `TEST_DATABASE_URL`; 99 casos se omitieron, así que transacciones y aislamiento tenant no quedaron íntegramente verificados localmente.
3. La revisión no confirma configuración real de proxy, TLS, backups/restauración, logs/alertas, secretos del proveedor ni permisos mínimos en producción.
4. SMTP y WhatsApp requieren proveedor/credenciales y worker; entrega real no fue validada.
5. MFA no está implementado. Considerar MFA especialmente para superadmin y owner antes de exposición amplia.
6. Revisar CSRF según transporte de credenciales en cada flujo, límites de sesión, caducidad y seguridad de links secretos.
7. Falta prueba sistemática de autorización por objeto/tenant para cada endpoint nuevo y análisis dinámico de API.
8. `pip-audit` está configurado en CI, pero no instalado en el entorno local de esta revisión.

## Acciones mínimas antes de producción

- Ejecutar integración sobre MySQL limpio y migración desde una copia representativa; probar restauración de backup.
- Revisión de autorización negativa multi-tenant, abuso de reservas, recuperación y carga de archivos.
- MFA para cuentas privilegiadas, rotación y monitoreo de secretos, política de headers/CORS/proxy revisada.
- Ejecutar análisis de dependencias Python y JS, SAST/DAST y revisión humana conforme al perfil ASVS seleccionado.
- Confirmar alertas y operación del worker; documentar retención de PII y respuesta a incidentes.

Referencias: [OWASP ASVS](https://asvs.owasp.org/), [OWASP API Security Top 10](https://owasp.org/www-project-api-security/).
