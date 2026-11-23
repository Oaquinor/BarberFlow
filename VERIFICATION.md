# Validación actual de KingFlow Barber

Este archivo reemplaza una checklist histórica que contenía endpoints, IDs y comandos obsoletos. No uses copias anteriores de la checklist para operar o modificar datos.

Consulta los procedimientos vigentes:

- [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md): entornos y suites de pruebas.
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md): módulos validados, límites y evidencia CI.
- [README.md](README.md): instalación y ejecución local sobre MySQL.
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md): contratos y permisos API.
- [docs/DATABASE.md](docs/DATABASE.md): estructura y migraciones MySQL.

La CI actual usa una base MySQL 8.4 desechable y valida migraciones, recuperación, pruebas backend, frontend, Chromium, WhatsApp y contenedores. La producción no se ha desplegado desde esta rama.
