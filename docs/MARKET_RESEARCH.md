# Investigación de mercado: plataformas de barbería y citas

**Revisión:** 25 de noviembre de 2026. Se revisaron páginas oficiales públicas; no se crearon cuentas de prueba ni se verificaron las afirmaciones comerciales de los proveedores. Las funciones pueden depender de país, plan, terminal, cuenta o integraciones disponibles.

## Referentes consultados

| Plataforma | Patrones funcionales que declara su fuente oficial | Oportunidad para KingFlow |
|---|---|---|
| [SQUIRE](https://www.getsquire.com/) | Descubrimiento con páginas preparadas para búsqueda, lista de espera que envía texto al liberarse un puesto, marketing/reseñas, fidelidad, comisiones y renta de silla. | Conectar agenda, retención y operación sin esconder las reglas del negocio tras automatizaciones opacas. Su waitlist es una referencia para madurar la coincidencia manual actual; pagos y automatización requieren consentimiento, país y políticas explícitas. |
| [Booksy](https://biz.booksy.com/en-ie/features) | Calendario personalizable y coloreado, buffers/tiempo de proceso, servicios combinados, QR y widget de reserva, lista de espera con notificación ante una apertura y campañas. | Ofrecer desde la página pública menús, agenda y enlaces listos para compartir; extender la cola gradualmente con ofertas limitadas y aceptadas por el cliente. |
| [Fresha](https://www.fresha.com/for-business/barber) | Agenda, walk-ins, citas recurrentes, gestión del equipo y varias sedes, historial/perfil, rebooking, pagos, depósitos, retail, marketing, informes y marketplace. | Mantener el calendario y la ficha de cliente conectados a la venta; distinguir integraciones propias del negocio de los marketplaces que captan demanda. |
| [Vagaro](https://mysite.vagaro.com/vagarouniversity/barber) | Sitio sincronizado con servicios/equipo/precios, personalización y SEO, portafolio, campañas de correo/texto e integración de reservas con redes y directorios. | Tratar la página pública como canal de adquisición editable por tenant, con contenido real, metadatos y una reserva visible desde cada sección. |
| [Square Appointments](https://squareup.com/us/en/appointments) | Agenda en tiempo real por empleado/ubicación, reserva web, recursos como sillas, pagos conectados, mensajes, perfiles y una waitlist que llena cancelaciones. | Asegurar una fuente común de disponibilidad y estados financieros. La compatibilidad de los pagos de Square es regional; no se infiere disponibilidad para República Dominicana. |
| [theCut](https://thecut.co/barber-features) | Perfil profesional, calendario continuo, intervalos, auto confirmación, mensajes, notas de estilo, citas recurrentes, fidelidad, pagos y propinas en la app. | Conservar un flujo rápido para el barbero y el contexto de estilo; separar estos beneficios del panel administrativo complejo. |
| [GlossGenius](https://glossgenius.com/overview) | Sitio de reservas configurable, complementos de servicio, waitlist, recordatorios, fotos/notas del cliente, rebooking, pagos, personal, informes y varias sedes. | Conectar marca, formulario previo, preferencias y material visual con la reserva y el seguimiento, siempre con consentimiento y acceso limitado. |
| [Trendly (República Dominicana)](https://www.apptrendly.com/) | El sitio ofrece agenda, recordatorios, historial/preferencias y reportes; muestra galería de capturas de inicio, dashboard, semana y servicios, y declara personalización de perfil/servicios, bloqueo de horarios y citas recurrentes en planes publicados. | Es la referencia más cercana al mercado/localidad citados por el usuario. La galería demostrativa ayuda a comunicar el producto, pero KingFlow debe hacer que la propia barbería exhiba servicios, equipo y trabajos reales, con una ruta clara hacia reservar. |

**FlowJ:** no se encontró una fuente oficial identificable de una plataforma de citas para barberías con ese nombre. Los resultados públicos revisados no permitieron asociar de forma fiable “FlowJ” con un producto de barbería; por eso no se usa para inferir funciones. Un enlace o nombre exacto permitiría incorporarlo a la siguiente revisión.

## Lectura comparativa del producto

La revisión de repositorio y estas páginas converge en que los sistemas competitivos conectan la adquisición de clientes, la reserva, el trabajo diario, el cobro y la repetición de visitas. Tener pantallas aisladas no equivale a tener ese ciclo integrado. El estado de KingFlow aquí se basa en su código y documentación de producto, no en lo que declara la competencia:

| Ciclo | KingFlow hoy | Brecha que se observa en el contraste |
|---|---|---|
| Descubrir y confiar | Página pública por barbería con tema, portada, galería, servicios con fotos, equipo y tarifas. | Faltan directorio/descubrimiento y metadatos/SEO estructurados; la galería del cliente depende del material real que cargue cada tenant. |
| Reservar | Reserva web de invitado o cuenta, selección de servicio/barbero/turno, preguntas configurables y políticas de cancelación. | Faltan multi-servicio, buffers configurables, reservas recurrentes/grupales y recursos/sillas como capacidad. |
| Recuperar una apertura | Waitlist con filtros reales de duración, fechas, barbero, bloqueos y solapamientos; owner ofrece enlace preseleccionado. | No existe oferta automática con vencimiento, reserva temporal y aceptación atómica. La coincidencia actual no aparta ni confirma el turno. |
| Atender y dar continuidad | Agenda/checkout/caja; Style Passport con consentimiento y fotos privadas; check-in y estimación aproximada de cola. | No hay tablero Live Chair ni aviso en tiempo real; faltan mejor historial visual cliente/barbero y repetir un corte desde Passport. |
| Cobrar y retener | Cobro manual, ventas POS de productos, gastos y conciliación; perfiles/favoritos y citas guardadas. | No hay pasarela/depósitos, reembolsos, pagos parciales, membresías, puntos, gift cards o motor de referidos cliente. |
| Crecer el equipo | Barberos, agenda, comisiones y reportes base. | No hay sedes/sillas contratadas, turnos laborales, liquidaciones bancarias ni permisos granulares personalizables por negocio. |

## Prioridades derivadas

1. Terminar la página pública con imágenes propias y una jerarquía que presente negocio, equipo, trabajos y servicios, y verificar SEO/compartición desde el perfil real.
2. Evolucionar la waitlist desde coincidencia a oferta con token de un uso, expiración, consentimiento de contacto y reserva MySQL atómica; invalidar ofertas competidoras al aceptar. No mandar ofertas automáticas hasta resolver el canal y las preferencias de contacto.
3. Completar continuidad de visita: repetir una configuración autorizada del Style Passport, rebooking rápido y estados de atención del barbero que alimenten una cola aproximada, sin divulgar clientes ajenos.
4. Diseñar fidelidad y pagos junto con los registros de reverso/expiración y conciliación. No introducir puntos, depósitos o montos que puedan quedar sin compensación.
5. Definir unidad de sucursal, recursos, permisos y modelo contractual antes de extender reportes y comisión a múltiples sedes o renta de silla.

No se recomienda copiar las interfaces, los nombres ni el modelo comercial de estas plataformas. Los sitios son materiales oficiales de mercadeo y no prueban calidad, cobertura local ni disponibilidad de funciones en todos los planes o países.
