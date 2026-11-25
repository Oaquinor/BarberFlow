# Sistema visual actual

## Fuente de verdad

La experiencia está construida en HTML/CSS/JS estático. Los estilos del panel viven principalmente en `frontend/css/owner-dashboard.css`; el sitio público en `frontend/css/client.css`. No hay framework de componentes común ni una librería de iconos central establecida. Mantener los iconos como SVG/recursos explícitos, consistentes y accesibles; evitar emojis como sustitutos de iconos de interfaz.

## Tokens observados

| Token | Valor/base | Uso |
|---|---|---|
| `--brand-primary` | `#b98752` | Acento configurable de barbería |
| `--brand-secondary` | `#5a4635` | Acento secundario configurable |
| `--brand-text-color` | `#69492b` | Texto/acento de marca |
| `--brand-on-primary` | `#181713` | Texto sobre acento |
| `--kf-ink` | `#25231f` | Texto principal del panel |
| `--kf-muted` | `#77746d` | Texto secundario |
| `--kf-line` | `#e8e3da` | Bordes y divisores |
| `--kf-paper` | `#fffefa` | Superficie clara |
| `--kf-canvas` | `#f3f0ea` | Fondo claro |
| `--kf-dark` | `#29251f` | Superficie oscura |

El portal público define tokens homónimos en su propia hoja y aplica variantes de color y tema. El panel de owner contiene tokens globales; antes de añadir modos/temas a otra página, inspeccionar su CSS: no todos los portales consumen un contrato único. La vista previa actual refleja los datos del perfil/catálogo disponibles en el panel y calcula el contraste del botón; las preferencias guardadas por el negocio son personalización básica, no un editor visual completo.

## Criterios de interfaz

- Diseñar primero el orden de lectura y acciones primarias; alinear etiquetas, campos y botones en una cuadrícula consistente.
- Mantener contraste legible en tema claro y oscuro, estados de foco visibles, etiquetas persistentes y mensajes asociados a campos.
- No comunicar estado únicamente por color; conservar texto/etiqueta y nombre accesible en controles con icono.
- Para móvil, verificar 320, 375, 768 y escritorio; prevenir desbordamiento horizontal y objetivos táctiles pequeños.
- Usar fotografía de negocio y servicios solo si el recurso está cargado; contemplar estados vacíos útiles y fallos de carga.
- Respetar `prefers-reduced-motion`; evitar animaciones decorativas que distraigan en tareas de agenda/cobro.

## Límites conocidos

No existe auditoría WCAG completa ni un catálogo de componentes compartidos entre panel, público y superadmin. El tema/branding no sustituye una herramienta de composición de páginas. La captura original de configuración muestra precisamente un formulario comprimido; priorizar ese flujo con revisión manual al rediseñarlo.
