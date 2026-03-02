#include <Wire.h>
#include <SparkFun_APDS9960.h>

// 센서 2 객체 생성
SparkFun_APDS9960 apds2 = SparkFun_APDS9960();

// 센서 2 전용 핀 (이전 가이드 기준)
#define SDA2 25
#define SCL2 26

void setup() {
  Serial.begin(115200);
  Serial.println(F("--- APDS-9960 Sensor 2 (Exit) Test ---"));

  // 센서 2가 연결된 핀으로 I2C 통신 시작
  // 라이브러리가 기본 Wire를 사용하므로, Wire를 센서 2 핀으로 시작합니다.
  Wire.begin(SDA2, SCL2);

  // 센서 2 초기화
  if (apds2.init()) {
    Serial.println(F("Sensor 2: Initialization complete"));
  } else {
    Serial.println(F("Sensor 2: Init failed! Check wiring on GPIO 25, 26"));
  }

  // 조도 및 근접 센서 활성화
  apds2.enableLightSensor(false);
  apds2.enableProximitySensor(false);
  
  delay(500);
}

void loop() {
  uint16_t light = 0;
  uint8_t proximity = 0;
  
  // 조도 읽기
  bool light_ok = apds2.readAmbientLight(light);
  // 근접도 읽기
  bool prox_ok = apds2.readProximity(proximity);

  if (light_ok && prox_ok) {
    Serial.print(F("Sensor 2 -> Light: "));
    Serial.print(light);
    Serial.print(F(" | Proximity: "));
    Serial.println(proximity);
  } else {
    Serial.println(F("Error: Cannot read from Sensor 2"));
  }

  delay(300); // 0.3초 간격 출력
}