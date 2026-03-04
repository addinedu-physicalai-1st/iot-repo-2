#include <WiFi.h>

// ===== 1. 네트워크 설정 (디바이스 PC의 3.device_client/.env 와 일치) =====
const char *ssid     = "addinedu_201class_2-2.4G";
const char *password = "201class2!";

const char *serverHost = "192.168.0.149";   // DEVICE PC IP (ESP32_2_HOST)
const uint16_t serverPort = 9002;           // ESP32_2_PORT

WiFiClient client;

// ===== 2. 평면 주차면 센서 + 1602 LCD 핀 정의 (예시) =====
// 실제 센서 연결에 맞게 수정 (HAM4311 / IR 센서 3~4개, I2C LCD 등)
const int PIN_SLOT1_SENSOR = 32;   // HAM4311 / IR - 슬롯 A1
const int PIN_SLOT2_SENSOR = 33;   // HAM4311 / IR - 슬롯 A2
const int PIN_SLOT3_SENSOR = 25;   // HAM4311 / IR - 슬롯 A3

// I2C 1602 LCD (예: PCF8574 I2C 인터페이스 모듈 사용)
// Arduino용 LiquidCrystal_I2C 라이브러리 사용 가정
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
LiquidCrystal_I2C lcd(0x27, 16, 2);  // 주소/사이즈는 실제 모듈에 맞게 수정

// ===== 3. 헬퍼: 서버로 한 줄(JSON) 전송 =====
void sendJson(const String &jsonLine) {
  if (!client.connected()) return;
  client.print(jsonLine);
  client.print("\n");
}

// 슬롯 상태 보고 예:
// {"board":"esp32_2","type":"slot","slot":"S3","occupied":1}
void reportSlot(const char *slotName, bool occupied) {
  String payload = String("{\"board\":\"esp32_2\",\"type\":\"slot\",\"slot\":\"") +
                   slotName + "\",\"occupied\":" + (occupied ? "1" : "0") + "}";
  sendJson(payload);
}

// ===== 4. (선택) 서버 명령 처리 =====
// 현재는 주차타워 제어를 하지 않고, 보드2는 평면 주차면 + LCD 전용이므로
// PC에서 오는 명령은 필요 시 LCD 메시지 변경 등에만 사용.
void handleCommand(const String &jsonLine) {
  if (jsonLine.indexOf("\"cmd\"") == -1) return;

  // 예시: {"cmd":"lcd","line1":"안녕하세요","line2":"현재 3대 주차중"}
  if (jsonLine.indexOf("\"lcd\"") != -1) {
    int l1 = jsonLine.indexOf("\"line1\"");
    int l2 = jsonLine.indexOf("\"line2\"");
    String line1 = "";
    String line2 = "";
    if (l1 != -1) {
      int c = jsonLine.indexOf(":", l1);
      int q1 = jsonLine.indexOf("\"", c + 1);
      int q2 = jsonLine.indexOf("\"", q1 + 1);
      if (q1 != -1 && q2 != -1) line1 = jsonLine.substring(q1 + 1, q2);
    }
    if (l2 != -1) {
      int c = jsonLine.indexOf(":", l2);
      int q1 = jsonLine.indexOf("\"", c + 1);
      int q2 = jsonLine.indexOf("\"", q1 + 1);
      if (q1 != -1 && q2 != -1) line2 = jsonLine.substring(q1 + 1, q2);
    }
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(line1);
    lcd.setCursor(0, 1);
    lcd.print(line2);
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
      Serial.println("Connected to device PC (esp32_2).");
      sendJson("{\"board\":\"esp32_2\",\"type\":\"hello\"}");
    } else {
      Serial.println("Connect failed. Retry in 3s...");
      delay(3000);
    }
  }
}

// ===== 6. setup / loop =====
void setup() {
  Serial.begin(115200);
  Serial.println("\n--- ESP32 Board2 (평면 주차면 + LCD 안내) ---");

  connectWiFi();
  connectServer();

  pinMode(PIN_SLOT1_SENSOR, INPUT);
  pinMode(PIN_SLOT2_SENSOR, INPUT);
  pinMode(PIN_SLOT3_SENSOR, INPUT);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Smart Parking");
  lcd.setCursor(0, 1);
  lcd.print("Initializing...");
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

  // 3) 평면 주차면 센서 상태를 주기적으로 보고 (예: S2~S4 등)
  static unsigned long lastReport = 0;
  unsigned long now = millis();
  if (now - lastReport > 1500) {
    lastReport = now;

    // TODO: 실제 HAM4311/IR 센서 판독으로 교체
    bool s2_occupied = digitalRead(PIN_SLOT1_SENSOR) == HIGH;
    bool s3_occupied = digitalRead(PIN_SLOT2_SENSOR) == HIGH;
    bool s4_occupied = digitalRead(PIN_SLOT3_SENSOR) == HIGH;

    reportSlot("S2", s2_occupied);
    reportSlot("S3", s3_occupied);
    reportSlot("S4", s4_occupied);

    int count = (int)s2_occupied + (int)s3_occupied + (int)s4_occupied;
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("안녕하세요");
    lcd.setCursor(0, 1);
    lcd.print("현재 ");
    lcd.print(count);
    lcd.print("대 주차중");
  }

  delay(10);
}

