## 스마트 주차장 관리 시스템 (기본 골격)

### 1. 디렉터리 구조

- `1.server/` : FastAPI 기반 서버
  - `app/main.py` : 서버 엔트리, REST API + UDP 리스너 시작
  - `app/models.py` : SQLAlchemy ORM 모델 (`devices`, `parking_slots`, `event_logs`)
  - `app/schemas.py` : Pydantic 스키마 (JSON 직렬화)
  - `app/routers/` : `/devices`, `/parking` 등 도메인별 API
  - `.env` : MySQL 및 UDP 설정
- `2.client/` : PyQt6 클라이언트 (관리 PC 대시보드)
  - `main.py` : PyQt6 대시보드 실행
  - `ui/dashboard.py` : 대시보드 화면 구현
  - `api_client.py` : FastAPI 서버와 JSON 통신
  - `udp_video_receiver.py` : ESP32 영상 UDP 수신 뼈대
  - `.env` : 서버 접속 정보 및 UDP 수신 설정
- `db/init.sql` : MySQL 데이터베이스/초기 데이터 스크립트

### 2. DB 설정 (MySQL)

1. MySQL에서 DB 및 초기 데이터 생성:

```bash
mysql -u root -p < db/init.sql
```

2. 서버용 `.env` (이미 생성됨, 필요 시 수정):

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=trdbpw!1234
DB_NAME=smart_parking
UDP_HOST=0.0.0.0
UDP_PORT=9000
```

### 3. 서버 실행

```bash
cd 1.server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- `http://127.0.0.1:8000/docs` 에서 API 문서/테스트 가능
- 서버 시작 시:
  - `init_db()` 로 테이블 자동 생성
  - `run_udp_server()` 로 UDP(영상 데이터) 수신 대기 시작

### 4. 클라이언트(PyQt6) 실행

1. 클라이언트 `.env` (2.client/.env, 필요 시 서버 주소 수정):

```env
SERVER_BASE_URL=http://127.0.0.1:8000
CLIENT_NAME=관리PC
UDP_LISTEN_HOST=0.0.0.0
UDP_LISTEN_PORT=9100
```

2. 실행:

```bash
cd 2.client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py
```

- 대시보드는 서버의 `/parking/dashboard`, `/devices/` API를 주기적으로 호출하여
  - 총 주차면/점유/빈공간
  - 활성 장비 수
  - 최근 이벤트 로그
  를 표시합니다.

### 5. ESP32 / UDP 연동 개요

- **서버 측**: `1.server/app/udp_listener.py`
  - `UDP_HOST`, `UDP_PORT` 에서 UDP 패킷 수신
  - 현재는 패킷 크기 및 발신 IP만 로그
  - 이후 프레임 조립, LPR, 이벤트 생성 시 `EventLog` 테이블로 연동 가능

- **클라이언트 측**: `2.client/udp_video_receiver.py`
  - 필요 시 관리 PC에서 직접 영상/센서 패킷을 수신하도록 확장 가능

이 구조를 기반으로, 이후 각 SR(입차/출차 제어, 번호판 인식, 요금 정산, 주차타워 제어 등)에 맞춰
개별 기능을 점진적으로 추가하면 됩니다.

