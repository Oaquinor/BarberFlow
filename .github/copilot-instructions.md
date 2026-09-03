# Copilot Instructions

## Directrices del proyecto
- El objetivo del proyecto es que la página sea una PWA.
- La arquitectura de producción debe incluir tres experiencias: 
  - Cliente: acceso a través de un link compartible (sin registro, agendar y consultar cita por teléfono).
    - Cliente debe tener dos botones compactos: agendar y consultar.
  - Barbero: panel de gestión y personalización, con branding total por barbería en todas las vistas.
  - Admin: gestión de roles/permisos, afiliados, cobros de mensualidad y estado de pagos.
- Implementar notificaciones de WhatsApp con branding y link de seguimiento de cita.
- Soporte configurable por usuarios administradores marcados para recibir correos.
- Visibilidad de opciones por rol/plan.
- Quitar bloque de credenciales de prueba del login.
- Preferir una UI más elaborada, premium y visualmente atractiva en todas las plataformas web.
- En producción no deben existir datos hardcodeados para servicios, citas ni métricas; el frontend debe renderizar datos reales creados por el usuario/API.