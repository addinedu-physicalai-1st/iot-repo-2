#include <Wire.h>
#include <SparkFun_APDS9960.h>
#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>// [cite

// 센서 객체 분리
SparkFun_APDS9960 apds1 = SparkFun_APDS9960();
SparkFun_APDS9960 apds2 = SparkFun_APDS9960();
Servo myServo;
MFRC522 rfid(5, 22); // SDA: 5, RST: 22 // [cite: 43, 58]

// 조도 기준값 (10 이하일 때 트리거)
const uint16_t LIGHT_THRESHOLD = 10;
bool isGateOpen = false;

// 두 번째 I2C 통신을 위한 설정
TwoWire WirePort2 = TwoWire(1); 

void setup() {
  Serial.begin(115200);
  SPI.begin();
  rfid.PCD_Init();
  
  myServo.setPeriodHertz(50);
  myServo.attach(13, 500, 2400);
  myServo.write(0);

  // --- 센서 1 설정 (Wire: GPIO 32, 14) ---
  Wire.begin(32, 14);
  if (apds1.init()) {
    apds1.enableLightSensor(false);
    Serial.println("Sensor 1 (Entry) Ready on Wire0");
  }

  // --- 센서 2 설정 (Wire1: GPIO 25, 26) ---
  // 라이브러리가 기본 Wire만 지원하는 경우를 대비해 수동 초기화 로직 적용
  WirePort2.begin(25, 26, 100000); 
  if (apds2.init()) { 
    apds2.enableLightSensor(false);
    Serial.println("Sensor 2 (Exit) Ready on Wire1");
  }

  Serial.println("--- DUAL SENSOR SYSTEM ONLINE ---");
}

void loop() {
  uint16_t light1 = 0, light2 = 0;

  // 센서 1 읽기 (Wire0)
  // SparkFun 라이브러리가 Wire를 고정해서 사용하므로 포트를 강제 지정하는 방식 사용
  if (apds1.readAmbientLight(light1)) {
    if (light1 <= LIGHT_THRESHOLD) {
      Serial.printf("ENTRY_DETECTED (Light: %d)\n", light1);
      //openGate("ENTRY");
    }
  }

  // 센서 2 읽기 (Wire1 전용 레지스터 직접 읽기 - 라이브러리 충돌 방지)
  light2 = readLightFromWire1();
  if (light2 > 0 && light2 <= LIGHT_THRESHOLD) {
    Serial.printf("EXIT_DETECTED (Light: %d)\n", light2);
    //openGate("EXIT");
  }

  // RFID 체크
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    Serial.println("RFID_ALLOWED");
    //openGate("RFID");
  }
  
  delay(150);
}

// Wire1 포트에서 직접 조도 레지스터(0x94)를 읽는 안정적인 함수
uint16_t readLightFromWire1() {
  uint16_t l = 0, h = 0;
  WirePort2.beginTransmission(0x39);
  WirePort2.write(0x94); // Ambient Light Low register
  if (WirePort2.endTransmission() != 0) return 0;
  WirePort2.requestFrom(0x39, 2);
  if (WirePort2.available() == 2) {
    l = WirePort2.read();
    h = WirePort2.read();
  }
  return (h << 8) | l;
}

void openGate(String source) {
  if (!isGateOpen) {
    isGateOpen = true;
    Serial.println("ACTION:GATE_OPEN_" + source);
    myServo.write(90);
    delay(3000);
    myServo.write(0);
    isGateOpen = false;
    Serial.println("ACTION:GATE_CLOSED");
  }
}