-- Recrear el usuario con el plugin correcto para PyMySQL
DROP USER IF EXISTS 'kingflow'@'localhost';
CREATE USER 'kingflow'@'localhost' IDENTIFIED WITH mysql_native_password BY 'kingflow123';
GRANT ALL PRIVILEGES ON kingflow_barber.* TO 'kingflow'@'localhost';
FLUSH PRIVILEGES;
SELECT user, host, plugin FROM mysql.user WHERE user='kingflow';
