# Evidencia visual de configuración

- `owner-settings-before.png` conserva la captura que compartió el usuario para documentar controles desalineados y formularios sin estructura.
- `owner-settings-after.png` se generó en Playwright desde el formulario real, con datos de prueba sintéticos (nombre de barbería y servicio de ejemplo); no representa información real de producción. Muestra el resultado del layout, las paletas, la vista previa conectada y la política de cancelación.

La prueba visual cubre anchos de 320, 375, 390, 430, 768, 1024, 1366 y 1920 píxeles. Esto valida desbordamiento y geometría del formulario en Chromium; no reemplaza la revisión manual de todas las pantallas ni la validación Firefox/WebKit.

- client-account-desktop.png y client-account-mobile.png muestran el portal cliente en estado de acceso, capturado desde la página real con datos vacíos a 1366 px y 390 px. La zona de estado vacía no deja espacio reservado entre introducción y formulario.
- `client-account-upcoming-appointment.png` muestra el panel autenticado con una cita sintética, para revisar la tarjeta de próxima visita, perfil, exportación y controles de cita. La captura confirma que guardar perfil destaca como acción principal y descargar datos permanece como acción secundaria.
- `client-barbershop-favorite-before.png` y `client-barbershop-favorite-after.png` muestran la acción de guardar una barbería desde su perfil público antes y después del cambio, usando un negocio sintético. La portada no presenta una foto genérica: muestra la identidad del negocio si no hay imágenes propias. El layout responsive se verifica de 320 a 1920 px.
- `public-booking-answers-before.png` y `public-booking-answers-after.png` muestran el cuestionario configurado y la confirmación de una reserva sintética; el flujo de navegador verifica que estilo, respuestas personalizadas y notas se envían por separado.
