/**
 * esp_cam_entrance.ino
 * ESP32-CAM 현관 보안 카메라 — UDP JPEG 스트리밍
 * Voice IoT Controller v0.8
 *
 * 보드: AI Thinker ESP32-CAM (OV2640)
 * 기능: Wi-Fi 연결 → 캡처 → UDP로 Python 서버 전송
 *
 * 전송 방식: 단순 모드 (JPEG 한 패킷, QVGA 권장)
 *           패킷 크기 초과 시 멀티파트 모드로 전환
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>

// ──────────────────────────────────────────88888888888888888888888888888888888888888888
// Wi-Fi 설정
// ──────────────────────────────────────────
#define WIFI_SSID      "addinedu_201class_2-2.4G"
#define WIFI_PASSWORD  "201class2!"


// ──────────────────────────────────────────
// 서버 설정
// ──────────────────────────────────────────
const char*    SERVER_IP   = "192.168.0.154";  // Python 서버 IP
const uint16_t SERVER_PORT = 5005;             // camera_stream.py UDP 포트
const uint16_t LOCAL_PORT  = 5006;             // ESP-CAM 로컬 UDP 포트

// ──────────────────────────────────────────
// 카메라 핀 (AI Thinker ESP32-CAM)
// ──────────────────────────────────────────
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

// ──────────────────────────────────────────
// 파라미터
// ──────────────────────────────────────────
#define FRAME_INTERVAL_MS  100    // 캡처 간격 (100ms = 10fps)
#define UDP_MTU            1400   // 안전한 UDP MTU (이더넷 1500 - 헤더)
#define FLASH_LED_PIN        4    // 플래시 LED (침입 감지 시 점등 명령 수신용)

// 멀티파트 헤더 구조체
struct __attribute__((packed)) FrameHeader {
  uint8_t  magic[4];        // 0xAB 0xCD 0xEF 0x01
  uint32_t frame_id;
  uint32_t total_len;
  uint16_t part_idx;
  uint16_t total_parts;
};

// ──────────────────────────────────────────
// 전역
// ──────────────────────────────────────────
WiFiUDP    udp;
uint32_t   frameId    = 0;
bool       flashState = false;

// ──────────────────────────────────────────
// 카메라 초기화
// ──────────────────────────────────────────
bool initCamera() {
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
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // PSRAM 유무에 따라 해상도 결정
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_VGA;    // 640x480
    config.jpeg_quality = 12;               // 0-63 낮을수록 고품질
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_QVGA;   // 320x240 (단일 패킷 가능)
    config.jpeg_quality = 15;
    config.fb_count     = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] 카메라 초기화 실패: 0x%x\n", err);
    return false;
  }

  // 카메라 화질 튜닝
  sensor_t* s = esp_camera_sensor_get();
  s->set_brightness(s, 0);     // -2 ~ 2
  s->set_contrast(s, 0);       // -2 ~ 2
  s->set_saturation(s, 0);     // -2 ~ 2
  s->set_gainceiling(s, (gainceiling_t)2);
  s->set_whitebal(s, 1);       // 자동 화이트 밸런스
  s->set_awb_gain(s, 1);
  s->set_exposure_ctrl(s, 1);  // 자동 노출
  s->set_aec2(s, 1);
  s->set_ae_level(s, 0);
  s->set_aec_value(s, 300);
  s->set_gain_ctrl(s, 1);      // 자동 게인
  s->set_agc_gain(s, 0);
  s->set_bpc(s, 0);
  s->set_wpc(s, 1);
  s->set_raw_gma(s, 1);
  s->set_lenc(s, 1);
  s->set_hmirror(s, 0);        // 수평 미러 (현관 설치 방향에 따라 조정)
  s->set_vflip(s, 0);          // 수직 플립

  Serial.println("[CAM] 카메라 초기화 완료");
  return true;
}

// ──────────────────────────────────────────
// Wi-Fi 연결
// ──────────────────────────────────────────
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WiFi] 연결 중");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] 연결 완료 — IP: %s\n",
                WiFi.localIP().toString().c_str());
}

// ──────────────────────────────────────────
// UDP 전송 (단순 모드 — QVGA용)
// ──────────────────────────────────────────
void sendFrameSimple(camera_fb_t* fb) {
  if (fb->len > 65000) {
    // 너무 크면 멀티파트로 전환
    sendFrameMultipart(fb);
    return;
  }
  udp.beginPacket(SERVER_IP, SERVER_PORT);
  udp.write(fb->buf, fb->len);
  udp.endPacket();
}

// ──────────────────────────────────────────
// UDP 전송 (멀티파트 모드 — VGA용)
// ──────────────────────────────────────────
void sendFrameMultipart(camera_fb_t* fb) {
  const uint8_t magic[4] = {0xAB, 0xCD, 0xEF, 0x01};
  uint32_t totalLen   = fb->len;
  uint16_t totalParts = (totalLen + UDP_MTU - 1) / UDP_MTU;

  for (uint16_t i = 0; i < totalParts; i++) {
    uint32_t offset   = (uint32_t)i * UDP_MTU;
    uint32_t chunkLen = min((uint32_t)UDP_MTU, totalLen - offset);

    // 헤더 구성 (빅엔디안)
    uint8_t header[16];
    memcpy(header, magic, 4);
    uint32_t fid_be = htonl(frameId);
    memcpy(header + 4, &fid_be, 4);
    uint32_t tl_be = htonl(totalLen);
    memcpy(header + 8, &tl_be, 4);
    uint16_t pi_be = htons(i);
    memcpy(header + 12, &pi_be, 2);
    uint16_t tp_be = htons(totalParts);
    memcpy(header + 14, &tp_be, 2);

    udp.beginPacket(SERVER_IP, SERVER_PORT);
    udp.write(header, 16);
    udp.write(fb->buf + offset, chunkLen);
    udp.endPacket();

    delay(2);  // 패킷 드롭 방지 딜레이
  }
}

// ──────────────────────────────────────────
// 서버 명령 수신 (UDP 역방향)
// Python 서버 → ESP-CAM: {"cmd":"flash_on"} 등
// ──────────────────────────────────────────
void checkServerCommand() {
  int packetSize = udp.parsePacket();
  if (!packetSize) return;

  char buf[64] = {0};
  udp.read(buf, sizeof(buf) - 1);
  String cmd = String(buf);
  cmd.trim();

  Serial.printf("[CMD] 수신: %s\n", cmd.c_str());

  if (cmd.indexOf("flash_on") >= 0) {
    digitalWrite(FLASH_LED_PIN, HIGH);
    flashState = true;
  } else if (cmd.indexOf("flash_off") >= 0) {
    digitalWrite(FLASH_LED_PIN, LOW);
    flashState = false;
  } else if (cmd.indexOf("flash_blink") >= 0) {
    // 침입 감지 알람 시 3회 점멸
    for (int i = 0; i < 3; i++) {
      digitalWrite(FLASH_LED_PIN, HIGH); delay(200);
      digitalWrite(FLASH_LED_PIN, LOW);  delay(200);
    }
  }
}

// ──────────────────────────────────────────
// Setup
// ──────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.println("\n[ESP32-CAM] 현관 보안 카메라 시작");

  // 플래시 LED 핀 설정
  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);

  // Wi-Fi 연결
  connectWiFi();

  // 카메라 초기화
  if (!initCamera()) {
    Serial.println("[ERROR] 카메라 초기화 실패 — 재시작");
    delay(3000);
    ESP.restart();
  }

  // UDP 시작
  udp.begin(LOCAL_PORT);
  Serial.printf("[UDP] 서버: %s:%d, 로컬포트: %d\n",
                SERVER_IP, SERVER_PORT, LOCAL_PORT);

  Serial.println("[ESP32-CAM] 준비 완료 — 스트리밍 시작");
}

// ──────────────────────────────────────────
// Loop
// ──────────────────────────────────────────
void loop() {
  // Wi-Fi 재연결
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] 연결 끊김 — 재연결 시도");
    connectWiFi();
    return;
  }

  // 서버 명령 확인
  checkServerCommand();

  // 프레임 캡처
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] 프레임 캡처 실패");
    delay(100);
    return;
  }

  // JPEG 확인
  if (fb->format == PIXFORMAT_JPEG && fb->len > 0) {
    sendFrameSimple(fb);
    frameId++;

    if (frameId % 100 == 0) {
      Serial.printf("[CAM] 프레임 %u 전송 완료 (크기: %u bytes)\n",
                    frameId, fb->len);
    }
  }

  esp_camera_fb_return(fb);
  delay(FRAME_INTERVAL_MS);
}
