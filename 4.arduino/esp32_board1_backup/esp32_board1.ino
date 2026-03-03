#include <WiFi.h>

// ===== 1. 네트워크 설정 (디바이스 PC의 3.device_client/.env 와 일치) =====
const char *ssid     = "addinedu_201class_2-2.4G";
const char *password = "201class2!";

const char *serverHost = "192.168.0.149";   // DEVICE PC IP (ESP32_1_HOST)
const uint16_t serverPort = 9001;           // ESP32_1_PORT

WiFiClient client;

// ===== 2. 입출차 관리용 센서/장비 핀 정의 (예시) =====
// 실제 센서 연결에 맞게 수정
const int PIN_RFID      = 4;   // RFID 모듈용(예: UART, SPI 등 별도 라이브러리 사용)
const int PIN_PROX      = 13;  // 근접/초음파 센서 트리거
const int PIN_GATE_SERVO = 12; // 차단기 서보 PWM 출력 등

// ===== 3. 헬퍼: 서버로 한 줄(JSON) 전송 =====
void sendJson(const String &jsonLine) {
  if (!client.connected()) return;
  client.print(jsonLine);
  client.print("\n");
}

// 슬롯 상태 보고 예:
// {"board":"esp32_1","type":"slot","slot":"S1","occupied":1}
void reportSlot(const char *slotName, bool occupied) {
  String payload = String("{\"board\":\"esp32_1\",\"type\":\"slot\",\"slot\":\"") +
                   slotName + "\",\"occupied\":" + (occupied ? "1" : "0") + "}";
  sendJson(payload);
}

// ===== 4. 서버 명령 처리 =====
// PC → ESP32_1 명령(JSON) 예:
// {"cmd":"gate","action":"open"}
void handleCommand(const String &jsonLine) {
  // 여기서는 아주 단순하게 문자열 포함 여부만 체크 (필요시 아두이노용 JSON 파서 라이브러리 사용)
  if (jsonLine.indexOf("\"cmd\"") == -1) return;

  if (jsonLine.indexOf("\"gate\"") != -1 && jsonLine.indexOf("\"open\"") != -1) {
    // TODO: 차단기 서보모터 열기 동작
    Serial.println("[CMD] Gate OPEN");
  }
  if (jsonLine.indexOf("\"gate\"") != -1 && jsonLine.indexOf("\"close\"") != -1) {
    // TODO: 차단기 서보모터 닫기 동작
    Serial.println("[CMD] Gate CLOSE");
  }
}

// ===== 5. WiFi + TCP 연결 =====
void connectWiFi() {
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.print("\nWiFi Connected. IP: ");
  Serial.println(WiFi.localIP());
}

void connectServer() {
  while (!client.connected()) {
    Serial.printf("Connecting to %s:%d ...\n", serverHost, serverPort);
    if (client.connect(serverHost, serverPort)) {
      Serial.println("Connected to device PC (esp32_1).");
      // 첫 접속 시 간단한 hello 메시지
      sendJson("{\"board\":\"esp32_1\",\"type\":\"hello\"}");
    } else {
      Serial.println("Connect failed. Retry in 3s...");
      delay(3000);
    }
  }
}

// ===== 6. setup / loop =====
void setup() {
  Serial.begin(115200);
  Serial.println("\n--- ESP32 Board1 (입출차/노상 관리) ---");

  connectWiFi();
  connectServer();

  // TODO: 센서/서보 핀 모드 설정
}

void loop() {
  // 1) 서버와의 연결 유지
  if (!client.connected()) {
    connectServer();
  }

  // 2) 서버에서 들어오는 명령 수신
  while (client.available()) {
    String line = client.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      Serial.print("[RX] ");
      Serial.println(line);
      handleCommand(line);
    }
  }

  // 3) 센서 상태를 일정 주기로 서버에 보고 (예: S1, S2)
  static unsigned long lastReport = 0;
  unsigned long now = millis();
  if (now - lastReport > 1000) {  // 1초마다 예시 보고
    lastReport = now;

    // TODO: 실제 센서값으로 교체
    bool s1_occupied = false;
    bool s2_occupied = true;

    reportSlot("S1", s1_occupied);
    reportSlot("S2", s2_occupied);
  }

  delay(10);
}

