#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>

#if 1 //Debug Home Mode
const char *ssid     = "iptime_WiFiCE6D";   // 2.4G WiFi SSID
const char *password = "!Tony6251@";                 // WiFi 비밀번호

//192.168.25.34 ~ 35
const char *udpAddress = "192.168.25.35";            // 디바이스 PC IP
const int   udpPort    = 7070;                       // 디바이스 PC 수신 포트
#else
const char *ssid     = "addinedu_201class_2-2.4G";   // 2.4G WiFi SSID
const char *password = "201class2!";                 // WiFi 비밀번호

const char *udpAddress = "192.168.0.149";            // 디바이스 PC IP
const int   udpPort    = 7070;                       // 디바이스 PC 수신 포트
#endif

WiFiUDP udp;

// 2. AI-Thinker 카메라 핀 맵핑
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

void setup() {
  Serial.begin(115200);
  Serial.println("\n--- Esp32 Cam 10FPS 듀얼버퍼 모드 부팅 ---");

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;
  
  // LPR 시스템 최적화 설정
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 10;              // 품질 10~12 권장
  config.fb_count = 3;                   // 듀얼 프레임 버퍼 사용 (안정성 핵심)
  config.grab_mode = CAMERA_GRAB_LATEST; // 항상 가장 최신 프레임 캡처

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK)
  {
    Serial.printf("카메라 초기화 실패: 0x%x", err);
    delay(1000);
    ESP.restart();
  }

  WiFi.begin(ssid, password);
  WiFi.setSleep(false); // 스트리밍 끊김 방지
  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected. Esp32 Cam Streaming Start!");
}

// Checksum 기능을 포함한 전송 함수
void sendImageUDP(uint8_t *imageData, size_t imageSize, uint8_t frameNo)
{
  size_t remainingSize = imageSize;
  uint8_t packetNo = 0;
  
  // 1. 체크섬 계산 (전체 바이트 합산)
  uint8_t checksum = 0;
  for (size_t i = 0; i < imageSize; i++)
  {
    checksum += imageData[i];
  }

  while (remainingSize > 0)
  {
    size_t chunkSize = std::min(remainingSize, (size_t)1024);
    bool isLastPacket = (remainingSize <= 1024); // 마지막 패킷 여부 확인

    udp.beginPacket(udpAddress, udpPort);
    udp.write(frameNo);
    udp.write(packetNo);
    udp.write(isLastPacket ? (uint8_t)1 : (uint8_t)0);  // 3번째: 마지막 패킷 여부 (수신측 체크섬 오판 방지)
    udp.write(isLastPacket ? checksum : (uint8_t)0);   // 4번째: 체크섬 (마지막 패킷에서만 유효)

    udp.write(imageData, chunkSize);
    udp.endPacket();

    imageData += chunkSize;
    remainingSize -= chunkSize;
    packetNo++;
    
    delayMicroseconds(2500); 
  }
  // 한 프레임 전송 후 패킷 수·크기 확인용 (수신측 로그와 대조)
  Serial.printf("[SEND] f_no=%u pkts=%u size=%u bytes\n", (unsigned)frameNo, (unsigned)packetNo, (unsigned)imageSize);
}

void loop() {
  static unsigned long lastFrameTime = 0;
  static uint8_t frameNo = 0;
  const unsigned long frameInterval = 100; // 정확히 10 FPS 유지
  
  unsigned long now = millis();
  
  if (now - lastFrameTime >= frameInterval)
  {
    lastFrameTime = now;
    
    camera_fb_t *fb = esp_camera_fb_get();
    if (fb) {
      sendImageUDP(fb->buf, fb->len, frameNo);
      esp_camera_fb_return(fb);
      frameNo++;
    }
  }

  delay(1); // 시스템 유휴 시간 확보
}
