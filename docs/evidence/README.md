# Evidencia visual de configuración

- `owner-settings-before.png` conserva la captura que compartió el usuario para documentar controles desalineados y formularios sin estructura.
- `owner-settings-after.png` se generó en Playwright desde el formulario real, con datos de prueba sintéticos (nombre de barbería y servicio de ejemplo); no representa información real de producción. Muestra el resultado del layout, las paletas, la vista previa conectada y la política de cancelación.

La prueba visual cubre anchos de 320, 375, 390, 430, 768, 1024, 1366 y 1920 píxeles. Esto valida desbordamiento y geometría del formulario en Chromium; no reemplaza la revisión manual de todas las pantallas ni la validación Firefox/WebKit.
