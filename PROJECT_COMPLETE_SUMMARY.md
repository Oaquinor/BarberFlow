# Resumen integral del proyecto

Este documento reemplaza el resumen histórico de 2024. Aquel snapshot afirmaba que el sistema estaba listo para producción y describía rutas, migraciones y proveedores que no coincidían con el repositorio actual.

Consulta el estado verificado y las limitaciones vigentes en [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md). La referencia de rutas vigente es [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

La CI valida las imágenes de producción y ejecuta Docker Compose con MySQL, pero no se ha hecho un despliegue real a producción. Tampoco se ha verificado la entrega externa de correo o WhatsApp con credenciales de proveedores.
