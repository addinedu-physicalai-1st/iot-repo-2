#include <Wire.h>
#include <SparkFun_APDS9960.h>

// 센서 객체 생성
SparkFun_APDS9960 apds = SparkFun_APDS9960();

// 핀 설정 (문서 및 이전 논의 기반)
#define I2C_SDA 32 // [cite: 341, 410]
#define I2C_SCL 14 // 서보모터(13)와 충돌을 피하기 위해 14 사용 // [cite: 342]

void setup() {
  Serial.begin(115200); // [cite: 347]
  Serial.println(F("--- APDS-9960 Light Sensor Test ---"));

  // I2C 초기화
  Wire.begin(I2C_SDA, I2C_SCL); // [cite: 351]

  // APDS-9960 초기화
  if (apds.init()) { // [cite: 353]
    Serial.println(F("APDS-9960 initialization complete"));
  } else {
    Serial.println(F("Something went wrong during APDS-9960 init!"));
  }

  // 조도 센서 활성화 (인터럽트 미사용)
  if (apds.enableLightSensor(false)) { // [cite: 377]
    Serial.println(F("Light sensor is now running"));
  } else {
    Serial.println(F("Something went wrong during light sensor init!"));
  }
  
  delay(500);
}

void loop() {
  uint16_t ambient_light = 0;
  
  // 조도 값 읽기
  if (apds.readAmbientLight(ambient_light)) { // [cite: 388]
    Serial.print(F("Ambient Light: "));
    Serial.println(ambient_light); // [cite: 390]
  } else {
    Serial.println(F("Error reading light level")); // [cite: 403]
  }

  delay(200); // 0.2초 간격으로 확인
}