#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>

// ===== 1. 네트워크 및 전송 설정 =====
// PC(device_client)의 3.device_client/.env 에 설정한 WIFI / UDP 정보와 맞춰서 수정
const char *ssid     = "addinedu_201class_2-2.4G";   // 2.4G WiFi SSID
const char *password = "201class2!";                 // WiFi 비밀번호

const char *udpAddress = "192.168.0.149";            // 디바이스 PC IP
const int   udpPort    = 7070;                       // 디바이스 PC 수신 포트

WiFiUDP udp;

// ===== 2. AI-Thinker 카메라 핀 맵핑 =====
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ===== 3. 초기 설정 =====
void setup() {
  Serial.begin(115200);
  Serial.println("\n--- ESP32 Cam UDP LPR 모드 부팅 ---");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  config.xclk_freq_hz = 10000000;          // 10MHz
  config.pixel_format = PIXFORMAT_JPEG;

  // LPR 최적화 설정 (QVGA, 품질 10, 트리플 버퍼)
  config.frame_size   = FRAMESIZE_QVGA;    // 320x240
  config.jpeg_quality = 10;
  config.fb_count     = 3;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("카메라 초기화 실패: 0x%x\n", err);
    delay(1000);
    ESP.restart();
  }

  // WiFi 연결
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.print("\nWiFi Connected. IP: ");
  Serial.println(WiFi.localIP());
  Serial.println("ESP32 Cam UDP Streaming Ready!");
}

// ===== 4. UDP 전송 (체크섬 포함, 3.device_client/esp32_receiver.py 와 매칭) =====
void sendImageUDP(uint8_t *imageData, size_t imageSize, uint8_t frameNo) {
  size_t remainingSize = imageSize;
  uint8_t packetNo = 0;

  // 전체 바이트 합산으로 8비트 체크섬 생성
  uint8_t checksum = 0;
  for (size_t i = 0; i < imageSize; i++) {
    checksum += imageData[i];
  }

  while (remainingSize > 0) {
    size_t chunkSize   = std::min(remainingSize, (size_t)1024);
    bool   isLastPacket = (remainingSize <= 1024);

    udp.beginPacket(udpAddress, udpPort);

    // 헤더: frameNo, packetNo, checksum(마지막 패킷에서만 실제 값)
    udp.write(frameNo);
    udp.write(packetNo);
    if (isLastPacket) {
      udp.write(checksum);
    } else {
      udp.write((uint8_t)0);
    }

    // JPEG 데이터 조각
    udp.write(imageData, chunkSize);
    udp.endPacket();

    imageData      += chunkSize;
    remainingSize  -= chunkSize;
    packetNo++;

    // 네트워크 버퍼 보호용 딜레이
    delayMicroseconds(2500);
  }
}

// ===== 5. 메인 루프 (10 FPS) =====
void loop() {
  static unsigned long lastFrameTime = 0;
  static uint8_t frameNo = 0;
  const unsigned long frameInterval = 100;  // 10 FPS

  unsigned long now = millis();
  if (now - lastFrameTime >= frameInterval) {
    lastFrameTime = now;

    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      sendImageUDP(fb->buf, fb->len, frameNo);
      esp_camera_fb_return(fb);
      frameNo++;
    }
  }

  delay(1);
}

