CREATE DATABASE IF NOT EXISTS smart_parking
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE smart_parking;

-- SQLAlchemy에서 테이블을 생성하므로 여기서는 선택적으로 초기 데이터만 구성

INSERT INTO devices (name, type, ip_address, config, is_active, created_at, updated_at)
VALUES
  ('입차 차단기 컨트롤러', 'gate_controller', '192.168.0.101', '{"relay_channel":1}', 1, NOW(), NOW()),
  ('주차타워 컨트롤러', 'tower_controller', '192.168.0.102', '{"slots":8}', 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE updated_at = NOW();

