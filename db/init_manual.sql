-- 1. DB 선택
CREATE DATABASE IF NOT EXISTS smart_parking
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE smart_parking;

-- 2. 기존 테이블 삭제 (FK 순서 고려: 자식 → 부모)
DROP TABLE IF EXISTS event_logs;
DROP TABLE IF EXISTS parking_slots;
DROP TABLE IF EXISTS devices;

-- 3. 새 테이블 생성

-- 장비 테이블
CREATE TABLE devices (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  name            VARCHAR(100) NOT NULL,
  type            VARCHAR(50)  NOT NULL,         -- esp32, gate_controller, tower 등
  ip_address      VARCHAR(45)  NULL,
  config          VARCHAR(255) NULL,             -- JSON 문자열 등
  is_active       TINYINT(1)   NOT NULL DEFAULT 1,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_devices_id (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 주차면 테이블 (sensor_connected 포함)
CREATE TABLE parking_slots (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  name               VARCHAR(50)  NOT NULL,      -- S1~S4, T1~T6 등
  level              VARCHAR(20)  NULL,          -- street, tower 등
  is_occupied        TINYINT(1)   NOT NULL DEFAULT 0,
  sensor_connected   TINYINT(1)   NOT NULL DEFAULT 0,
  last_vehicle_plate VARCHAR(20)  NULL,
  created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_parking_slots_id (id),
  KEY idx_parking_slots_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 이벤트 로그 테이블
CREATE TABLE event_logs (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  device_id  INT NULL,
  event_type VARCHAR(50)  NOT NULL,             -- ENTER, EXIT, ERROR, STATUS 등
  message    VARCHAR(255) NULL,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_event_logs_id (id),
  KEY idx_event_logs_device_id (device_id),
  CONSTRAINT fk_event_logs_device
    FOREIGN KEY (device_id) REFERENCES devices(id)
    ON DELETE SET NULL
    ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 초기 데이터(장비 + 슬롯) 삽입

INSERT INTO devices (name, type, ip_address, config, is_active, created_at, updated_at)
VALUES
  ('입차 차단기 컨트롤러', 'gate_controller', '192.168.0.101', '{"relay_channel":1}', 1, NOW(), NOW()),
  ('주차타워 컨트롤러',   'tower_controller', '192.168.0.102', '{"slots":8}',       1, NOW(), NOW())
ON DUPLICATE KEY UPDATE updated_at = NOW();

INSERT INTO parking_slots (name, level, is_occupied, sensor_connected, last_vehicle_plate, created_at, updated_at)
VALUES
  ('S1', 'street', 0, 0, NULL, NOW(), NOW()),
  ('S2', 'street', 0, 0, NULL, NOW(), NOW()),
  ('S3', 'street', 0, 0, NULL, NOW(), NOW()),
  ('S4', 'street', 0, 0, NULL, NOW(), NOW()),
  ('T1', 'tower',  0, 0, NULL, NOW(), NOW()),
  ('T2', 'tower',  0, 0, NULL, NOW(), NOW()),
  ('T3', 'tower',  0, 0, NULL, NOW(), NOW()),
  ('T4', 'tower',  0, 0, NULL, NOW(), NOW()),
  ('T5', 'tower',  0, 0, NULL, NOW(), NOW()),
  ('T6', 'tower',  0, 0, NULL, NOW(), NOW())
ON DUPLICATE KEY UPDATE updated_at = NOW();