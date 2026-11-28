# Migración a Tailwind CSS

## Estado y alcance

Todas las páginas HTML cargan únicamente `css/tailwind.css`, generado con Tailwind CSS 4. Se eliminaron las nueve hojas de estilos anteriores y los bloques `<style>` de las páginas. Las clases semánticas que siguen en el marcado se conservan como identificadores para JavaScript y accesibilidad; la presentación se expresa mediante utilidades Tailwind.

Páginas: panel de barbería, administración, página pública de reservas, cuenta del cliente, alta de barbería, recuperación, configuración inicial y página sin conexión.

## Construcción

Desde `frontend`:

```sh
npm ci
npm run build:css
```

Para desarrollar: `npm run watch:css`. La hoja compilada se versiona en el repositorio para que FastAPI y la PWA puedan servirla sin Node en producción. No se utiliza un CDN de Tailwind.

## Invariantes del diseño

- Preflight aplica `box-sizing: border-box` globalmente.
- La estructura utiliza Grid/Flexbox, columnas `minmax(0,1fr)` y elementos con `min-w-0`.
- Los tamaños de texto y componentes se expresan con utilidades relativas; no se usan flotantes, márgenes negativos ni posicionamiento absoluto para estructurar componentes.
- Los controles táctiles tienen una altura mínima relativa y los formularios cambian a una columna en móvil.
- Las tablas de gestión muestran etiquetas `data-label` en la presentación móvil.
- Se conserva CSS dinámico únicamente para estado visible/oculto, porcentajes de progreso, dimensiones del canvas y colores elegidos por el negocio. No se conserva una hoja propia de reglas o sobrescrituras.
- Los diálogos nativos, Canvas para rendimiento y JavaScript de reservas, cobros, galería y gestión siguen conectados a sus recorridos existentes.

## Evidencia del 28 de noviembre de 2026

- `npm test`: 131 pruebas aprobadas, incluida la comprobación de arquitectura Tailwind.
- `npm run test:browser`: 80 pruebas aprobadas.
- Comprobación adicional de capturas a 320 y 1366 píxeles: 14 pruebas aprobadas.
- La suite cubre adaptación entre 320 y 1920 píxeles, temas públicos, reservas y preferencias, cuenta del cliente, inventario, caja, configuración, tablero, descargas de galería y diálogos compartidos.
- Capturas de revisión: `evidence/tailwind-mobile-review.jpg`, `evidence/tailwind-desktop-review.jpg`.

Las pruebas de navegador utilizan datos controlados para que las operaciones de prueba no creen cobros ni modifiquen cuentas reales. La migración visual no cambia el esquema MySQL ni las reglas de autorización del backend.
