-- 1. DB 선택
CREATE DATABASE IF NOT EXISTS smart_parking
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE smart_parking;

-- 2. 기존 테이블 삭제 (FK 순서 고려: 자식 → 부모)
DROP TABLE IF EXISTS event_logs;
DROP TABLE IF EXISTS rfid_cards;
DROP TABLE IF EXISTS residents;
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

-- 입주민 테이블
CREATE TABLE residents (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  unit_number  VARCHAR(20)  NOT NULL,  -- 몇 호
  name         VARCHAR(50)  NOT NULL,
  phone        VARCHAR(20)  NOT NULL,
  car_plate    VARCHAR(20)  NOT NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_residents_id (id),
  KEY idx_residents_unit (unit_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- RFID 카드 테이블
CREATE TABLE rfid_cards (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  card_uid     VARCHAR(64)  NOT NULL UNIQUE,
  resident_id  INT          NULL,
  is_active    TINYINT(1)   NOT NULL DEFAULT 1,
  description  VARCHAR(100) NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_rfid_cards_id (id),
  KEY idx_rfid_cards_uid (card_uid),
  CONSTRAINT fk_rfid_resident
    FOREIGN KEY (resident_id) REFERENCES residents(id)
    ON DELETE SET NULL
    ON UPDATE CASCADE
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

-- 입주민 샘플 데이터
INSERT INTO residents (unit_number, name, phone, car_plate, created_at, updated_at)
VALUES
  ('101-101', '홍길동',    '010-1111-1111', '12가1234', NOW(), NOW()),
  ('101-102', '김철수',    '010-2222-2222', '23나2345', NOW(), NOW()),
  ('102-201', '이영희',    '010-3333-3333', '34다3456', NOW(), NOW()),
  ('102-202', '박민수',    '010-4444-4444', '45라4567', NOW(), NOW()),
  ('103-301', '최서연',    '010-5555-5555', '56마5678', NOW(), NOW()),
  ('103-302', '오지훈',    '010-6666-6666', '67바6789', NOW(), NOW()),
  ('104-401', '정하늘',    '010-7777-7777', '78사7890', NOW(), NOW()),
  ('104-402', '한지민',    '010-8888-8888', '89아8901', NOW(), NOW()),
  ('105-501', '조은우',    '010-9999-9999', '90자9012', NOW(), NOW()),
  ('105-502', '신다인',    '010-0000-0000', '01차0123', NOW(), NOW())
ON DUPLICATE KEY UPDATE updated_at = NOW();

-- RFID 카드 샘플 데이터 (입주민과 일부 매핑)
INSERT INTO rfid_cards (card_uid, resident_id, is_active, description, created_at, updated_at)
VALUES
  ('RFID0001', 1, 1, '101-101 차량', NOW(), NOW()),
  ('RFID0002', 2, 1, '101-102 차량', NOW(), NOW()),
  ('RFID0003', 3, 1, '102-201 차량', NOW(), NOW()),
  ('RFID0004', 4, 1, '102-202 차량', NOW(), NOW()),
  ('RFID0005', 5, 1, '103-301 차량', NOW(), NOW()),
  ('RFID0006', 6, 1, '103-302 차량', NOW(), NOW()),
  ('RFID0007', 7, 1, '104-401 차량', NOW(), NOW()),
  ('RFID0008', 8, 1, '104-402 차량', NOW(), NOW()),
  ('RFID0009', 9, 1, '105-501 차량', NOW(), NOW()),
  ('RFID0010', 10, 1, '105-502 차량', NOW(), NOW())
ON DUPLICATE KEY UPDATE updated_at = NOW();