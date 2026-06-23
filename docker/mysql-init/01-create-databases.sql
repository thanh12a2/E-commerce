CREATE DATABASE IF NOT EXISTS user_db;
CREATE DATABASE IF NOT EXISTS order_db;

CREATE USER IF NOT EXISTS 'user_user'@'%' IDENTIFIED BY 'user_password';
CREATE USER IF NOT EXISTS 'order_user'@'%' IDENTIFIED BY 'order_password';

GRANT ALL PRIVILEGES ON user_db.* TO 'user_user'@'%';
GRANT ALL PRIVILEGES ON order_db.* TO 'order_user'@'%';
GRANT ALL PRIVILEGES ON `test\_%`.* TO 'user_user'@'%';
GRANT ALL PRIVILEGES ON `test\_%`.* TO 'order_user'@'%';
GRANT CREATE, DROP ON *.* TO 'user_user'@'%';
GRANT CREATE, DROP ON *.* TO 'order_user'@'%';
FLUSH PRIVILEGES;
