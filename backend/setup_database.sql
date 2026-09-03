-- Crear la base de datos
CREATE DATABASE IF NOT EXISTS kingflow_barber CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Crear el usuario (si no existe)
CREATE USER IF NOT EXISTS 'kingflow'@'localhost' IDENTIFIED BY 'kingflow123';

-- Dar permisos al usuario
GRANT ALL PRIVILEGES ON kingflow_barber.* TO 'kingflow'@'localhost';

-- Aplicar los cambios
FLUSH PRIVILEGES;

-- Usar la base de datos
USE kingflow_barber;

-- Mostrar confirmación
SELECT 'Base de datos kingflow_barber creada exitosamente' AS Status;
