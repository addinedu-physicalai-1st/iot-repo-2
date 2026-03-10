import express from 'express';
import mysql from 'mysql2/promise';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '.env') });

const app = express();
const port = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

// DB 설정 (RDS 연결용)
const dbConfig = {
    host: process.env.DB_HOST,
    user: process.env.DB_USER || 'admin',
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME || 'smart_parking',
    port: parseInt(process.env.DB_PORT || '3306'),
    ssl: {
        rejectUnauthorized: false // AWS RDS 연결 시 SSL 처리
    }
};

// DB 연결 및 스키마 테스트 (Startup 시)
(async () => {
    let connection;
    try {
        console.log('🔄 DB 연결 및 스키마 체크 중... (Host:', dbConfig.host, ')');
        connection = await mysql.createConnection(dbConfig);
        console.log('✅ DB 연결 성공!');

        // residents 테이블에 password 컬럼이 있는지 확인하고 없으면 추가
        try {
            await connection.execute('SELECT password FROM residents LIMIT 1');
            console.log('✅ password 컬럼 확인 완료.');
        } catch (colErr) {
            if (colErr.code === 'ER_BAD_FIELD_ERROR') {
                console.log('🚧 password 컬럼이 없습니다. 자동 생성을 시도합니다...');
                await connection.execute('ALTER TABLE residents ADD COLUMN password VARCHAR(255) NOT NULL DEFAULT "1234" AFTER phone');
                console.log('✅ password 컬럼이 성공적으로 생성되었습니다!');
            } else {
                throw colErr;
            }
        }

        // 결제 카드 테이블 없으면 생성
        await connection.execute(`
            CREATE TABLE IF NOT EXISTS payment_cards (
                id INT AUTO_INCREMENT PRIMARY KEY,
                resident_id INT NOT NULL,
                card_type VARCHAR(50) NOT NULL,
                card_number VARCHAR(20) NOT NULL,
                expiry VARCHAR(10) NOT NULL,
                is_default TINYINT(1) NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_card_resident_idx FOREIGN KEY (resident_id) REFERENCES residents(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        `);

        // residents 테이블에 balance 컬럼이 있는지 확인하고 없으면 추가
        try {
            await connection.execute('SELECT balance FROM residents LIMIT 1');
            console.log('✅ balance 컬럼 확인 완료.');
        } catch (colErr) {
            if (colErr.code === 'ER_BAD_FIELD_ERROR') {
                console.log('🚧 balance 컬럼이 없습니다. 자동 생성을 시도합니다...');
                await connection.execute('ALTER TABLE residents ADD COLUMN balance INT NOT NULL DEFAULT 0 AFTER car_plate');
                console.log('✅ balance 컬럼이 성공적으로 생성되었습니다!');
            } else {
                throw colErr;
            }
        }

        // residents 테이블에 is_active 컬럼이 있는지 확인하고 없으면 추가
        try {
            await connection.execute('SELECT is_active FROM residents LIMIT 1');
            console.log('✅ is_active 컬럼 확인 완료.');
        } catch (colErr) {
            if (colErr.code === 'ER_BAD_FIELD_ERROR') {
                console.log('🚧 is_active 컬럼이 없습니다. 자동 생성을 시도합니다...');
                await connection.execute('ALTER TABLE residents ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1 AFTER balance');
                console.log('✅ is_active 컬럼이 성공적으로 생성되었습니다!');
            } else {
                throw colErr;
            }
        }

        // guest_visits 테이블 없으면 생성
        await connection.execute(`
            CREATE TABLE IF NOT EXISTS guest_visits (
                id INT AUTO_INCREMENT PRIMARY KEY,
                car_plate VARCHAR(20) NOT NULL,
                unit_number VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT '승인대기',
                arrival_time DATETIME NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                KEY idx_guest_visits_unit (unit_number)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        `);

        // payments 테이블 없으면 생성
        await connection.execute(`
            CREATE TABLE IF NOT EXISTS payments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                car_plate VARCHAR(20) NOT NULL,
                unit_number VARCHAR(20) NOT NULL,
                amount INT NOT NULL,
                payment_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                method VARCHAR(50) NULL,
                status VARCHAR(20) NOT NULL DEFAULT '결제완료',
                KEY idx_payments_unit (unit_number)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        `);

    } catch (err) {
        console.error('❌ DB 진단 실패!');
        console.error('Error Code:', err.code);
        console.error('Error Message:', err.message);
        if (err.code === 'ETIMEDOUT') {
            console.error('💡 팁: RDS 보안 그룹에서 3306 포트가 내 IP에 대해 열려있는지 확인하세요.');
        } else if (err.code === 'ER_ACCESS_DENIED_ERROR') {
            console.error('💡 팁: DB_USER 또는 DB_PASSWORD가 정확한지 확인하세요.');
        } else if (err.code === 'ENOTFOUND') {
            console.error('💡 팁: DB_HOST 주소가 정확한지 확인하세요.');
        }
    } finally {
        if (connection) await connection.end();
    }
})();

// 로그인 API
app.post('/api/login', async (req, res) => {
    const { phone, password } = req.body;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute(
            'SELECT name, unit_number as unitNumber, phone FROM residents WHERE phone = ? AND password = ?',
            [phone, password]
        );

        if (rows.length > 0) {
            res.json(rows[0]);
        } else {
            res.status(401).json({ error: '전화번호 또는 비밀번호가 올바르지 않습니다.' });
        }
    } catch (err) {
        console.error('로그인 오류:', err);
        res.status(500).json({ error: '서버 오류가 발생했습니다.' });
    } finally {
        if (connection) await connection.end();
    }
});

// 회원가입 API
app.post('/api/signup', async (req, res) => {
    const { name, phone, password, unitNumber, carPlate } = req.body;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        await connection.execute(
            'INSERT INTO residents (name, phone, password, unit_number, car_plate) VALUES (?, ?, ?, ?, ?)',
            [name, phone, password, unitNumber, carPlate]
        );
        res.json({ success: true });
    } catch (err) {
        console.error('회원가입 오류:', err);
        res.status(500).json({ error: '회원가입 중 오류가 발생했습니다.' });
    } finally {
        if (connection) await connection.end();
    }
});

// 프로필 업데이트 API
app.post('/api/profile/update', async (req, res) => {
    const { name, phone, currentPassword, newPassword } = req.body;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);

        // 1. 현재 비밀번호 확인
        const [rows] = await connection.execute(
            'SELECT password FROM residents WHERE phone = ?',
            [phone]
        );

        if (rows.length === 0 || rows[0].password !== currentPassword) {
            return res.status(401).json({ error: '현재 비밀번호가 일치하지 않습니다.' });
        }

        // 2. 정보 업데이트 (새 비밀번호가 있으면 비밀번호도 업데이트)
        if (newPassword && newPassword.trim() !== '') {
            await connection.execute(
                'UPDATE residents SET name = ?, password = ? WHERE phone = ?',
                [name, newPassword, phone]
            );
        } else {
            await connection.execute(
                'UPDATE residents SET name = ? WHERE phone = ?',
                [name, phone]
            );
        }

        res.json({ success: true });
    } catch (err) {
        console.error('프로필 업데이트 오류:', err);
        res.status(500).json({ error: '정보 수정 중 오류가 발생했습니다.' });
    } finally {
        if (connection) await connection.end();
    }
});

// 주차 현황 데이터 API
app.get('/api/parking/stats', async (req, res) => {
    const { unitNumber } = req.query;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);

        // 1. 지상 주차장 현황 (level = 'street')
        const [groundTotal] = await connection.execute("SELECT COUNT(*) as count FROM parking_slots WHERE level = 'street'");
        const [groundAvailable] = await connection.execute("SELECT COUNT(*) as count FROM parking_slots WHERE level = 'street' AND is_occupied = 0");

        // 2. 타워 주차장 현황 (level = 'tower')
        const [towerTotal] = await connection.execute("SELECT COUNT(*) as count FROM parking_slots WHERE level = 'tower'");
        const [towerAvailable] = await connection.execute("SELECT COUNT(*) as count FROM parking_slots WHERE level = 'tower' AND is_occupied = 0");

        // 3. 내 등록 차량 수 (활성 차량만)
        const [myCarRows] = await connection.execute('SELECT COUNT(*) as count FROM residents WHERE unit_number = ? AND is_active = 1', [unitNumber]);

        res.json({
            ground: { total: groundTotal[0].count, available: groundAvailable[0].count },
            tower: { total: towerTotal[0].count, available: towerAvailable[0].count },
            myCarsCount: myCarRows[0].count
        });
    } catch (err) {
        console.error('DB 쿼리 오류:', err);
        res.status(500).json({ error: '데이터를 가져오는 중 오류가 발생했습니다.' });
    } finally {
        if (connection) await connection.end();
    }
});

// 주차 슬롯 전체 조회 API (맵 용)
app.get('/api/parking/slots', async (req, res) => {
    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute("SELECT name, level, is_occupied, last_vehicle_plate FROM parking_slots");
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 내 차량 리스트 조회 API
app.get('/api/cars', async (req, res) => {
    const { unitNumber } = req.query;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute(`
            SELECT 
                r.id,
                r.car_plate as plate, 
                r.is_active,
                "등록 차량" as model,
                COALESCE(SUM(p.amount), 0) as total_payment
            FROM residents r
            LEFT JOIN payments p ON r.car_plate = p.car_plate
            WHERE r.unit_number = ?
            GROUP BY r.car_plate, r.id
        `, [unitNumber]);
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 차량 상태 변경 (활성화/비활성화) API
app.post('/api/cars/status', async (req, res) => {
    const { id, isActive } = req.body;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        await connection.execute('UPDATE residents SET is_active = ? WHERE id = ?', [isActive ? 1 : 0, id]);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 방문 예약 리스트 조회 API
app.get('/api/guests', async (req, res) => {
    const { unitNumber } = req.query;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute('SELECT * FROM guest_visits WHERE unit_number = ? ORDER BY created_at DESC', [unitNumber]);
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 방문 예약 등록 API
app.post('/api/guests', async (req, res) => {
    const { carPlate, arrivalTime, unitNumber } = req.body;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        await connection.execute(
            'INSERT INTO guest_visits (car_plate, arrival_time, unit_number, status) VALUES (?, ?, ?, "승인됨")',
            [carPlate, arrivalTime, unitNumber]
        );
        res.json({ success: true });
    } catch (err) {
        console.error('방문 예약 등록 오류:', err);
        res.status(500).json({ error: '방문 예약 등록 중 오류가 발생했습니다.' });
    } finally {
        if (connection) await connection.end();
    }
});

// 방문 예약 상태 업데이트 API
app.patch('/api/guests/:id', async (req, res) => {
    const { id } = req.params;
    const { status } = req.body;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        await connection.execute('UPDATE guest_visits SET status = ? WHERE id = ?', [status, id]);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 결제 내역 조회 API
app.get('/api/payments', async (req, res) => {
    const { unitNumber } = req.query;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute('SELECT * FROM payments WHERE unit_number = ? ORDER BY payment_date DESC', [unitNumber]);
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 카드 목록 조회 API
app.get('/api/cards', async (req, res) => {
    const { phone } = req.query;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute(
            'SELECT c.* FROM payment_cards c JOIN residents r ON c.resident_id = r.id WHERE r.phone = ?',
            [phone]
        );
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 카드 등록 API
app.post('/api/cards', async (req, res) => {
    const { phone, cardType, cardNumber, expiry } = req.body;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);

        // 1. 입주민 ID 찾기
        const [residents] = await connection.execute('SELECT id FROM residents WHERE phone = ?', [phone]);
        if (residents.length === 0) return res.status(404).json({ error: '사용자를 찾을 수 없습니다.' });
        const residentId = residents[0].id;

        // 2. 다른 카드들은 기본에서 해제 (만약 default 기능 추가 시 대비)
        // 여기서는 새로 등록된 카드를 기본으로 설정하도록 하겠음 (선택 사항)
        await connection.execute('UPDATE payment_cards SET is_default = 0 WHERE resident_id = ?', [residentId]);

        // 3. 카드 삽입
        await connection.execute(
            'INSERT INTO payment_cards (resident_id, card_type, card_number, expiry, is_default) VALUES (?, ?, ?, ?, 1)',
            [residentId, cardType, cardNumber, expiry]
        );

        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 카드 삭제 API
app.delete('/api/cards/:id', async (req, res) => {
    const { id } = req.params;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        await connection.execute('DELETE FROM payment_cards WHERE id = ?', [id]);
        res.json({ success: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 잔액 조회 API
app.get('/api/user/balance', async (req, res) => {
    const { phone } = req.query;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute('SELECT balance FROM residents WHERE phone = ?', [phone]);
        if (rows.length > 0) {
            res.json({ balance: rows[0].balance });
        } else {
            res.status(404).json({ error: '사용자를 찾을 수 없습니다.' });
        }
    } catch (err) {
        res.status(500).json({ error: err.message });
    } finally {
        if (connection) await connection.end();
    }
});

// 예치금 충전 API (10% 보너스 포함)
app.post('/api/payments/deposit', async (req, res) => {
    const { phone, amount, unitNumber, carPlate } = req.body;
    const bonus = Math.floor(amount * 0.1);
    const totalDeposit = amount + bonus;

    let connection;
    try {
        connection = await mysql.createConnection(dbConfig);
        // 트랜잭션 시작
        await connection.beginTransaction();

        // 1. 잔액 업데이트
        await connection.execute(
            'UPDATE residents SET balance = balance + ? WHERE phone = ?',
            [totalDeposit, phone]
        );

        // 2. 결제 내역 기록
        await connection.execute(
            'INSERT INTO payments (car_plate, unit_number, amount, method, status) VALUES (?, ?, ?, ?, "결제완료")',
            [carPlate, unitNumber, amount, '카드 충전 (10% 보너스)']
        );

        await connection.commit();
        res.json({ success: true, balance: totalDeposit });
    } catch (err) {
        if (connection) await connection.rollback();
        console.error('충전 오류:', err);
        res.status(500).json({ error: '충전 중 오류가 발생했습니다.' });
    } finally {
        if (connection) await connection.end();
    }
});

app.listen(port, () => {
    console.log(`백엔드 서버가 http://localhost:${port} 에서 실행 중입니다.`);
});
