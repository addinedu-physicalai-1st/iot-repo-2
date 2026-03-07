// ESP32-CAM LPR TCP + UDP 테스트 클라이언트
// - 영상: UDP로 JPEG 프레임 전송 (포트 7070)
// - 제어: TCP 텍스트 명령(cam_start 등) 수신 → 상태 변경

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

// ───── WiFi 설정 ─────
#if 1  // Debug Home Mode
const char* ssid     = "addinedu_201class_2-2.4G";
const char* password = "201class2!";
#else
const char* ssid     = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";
#endif

// ───── 서버(PC) IP/포트 설정 ─────
char serverHostBuf[64] = "192.168.0.149";  // PC IP
uint16_t udpPortNum    = 7070;             // 영상 UDP 포트
uint16_t tcpPortNum    = 8091;             // 제어용 TCP 포트

#define DEVICE_GUID "DEV-LPR-1"
#define DEVICE_NAME "입구 LPR 카메라"

// ───── 카메라 핀맵 ─────
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
#define FLASH_LED_PIN      4

// ───── 전역 상태 ─────
WiFiUDP udp;
WiFiClient ctrlClient;

volatile bool camStreaming = false;
const unsigned long FRAME_INTERVAL_MS = 100;  // UDP 프레임 간격
unsigned long lastFrameTime = 0;
uint8_t frameNo = 0;

unsigned long lastConnectAttempt = 0;
const unsigned long RECONNECT_INTERVAL_MS = 3000;

// ───── UDP 영상 전송 ─────
void sendImageUDP(uint8_t* imageData, size_t imageSize, uint8_t fno) {
  size_t remainingSize = imageSize;
  uint8_t packetNo = 0;
  uint8_t checksum = 0;

  for (size_t i = 0; i < imageSize; i++) {
    checksum += imageData[i];
  }

  while (remainingSize > 0) {
    size_t chunkSize = (remainingSize <= 1024) ? remainingSize : (size_t)1024;
    bool isLastPacket = (remainingSize <= 1024);

    udp.beginPacket(serverHostBuf, udpPortNum);
    udp.write(fno);
    udp.write(packetNo);
    udp.write(isLastPacket ? (uint8_t)1 : (uint8_t)0);
    udp.write(isLastPacket ? checksum : (uint8_t)0);
    udp.write(imageData, chunkSize);
    udp.endPacket();

    imageData += chunkSize;
    remainingSize -= chunkSize;
    packetNo++;
    delayMicroseconds(2500);
  }

  Serial.printf("[SEND555] f_no=%u pkts=%u size=%u\n",
                (unsigned)fno, (unsigned)packetNo, (unsigned)imageSize);
}

// ───── UDP 영상 전송 태스크 ─────
void udpStreamTask(void* pvParameters) {
  for (;;) {
    if (camStreaming && (millis() - lastFrameTime >= FRAME_INTERVAL_MS)) {
      lastFrameTime = millis();
      camera_fb_t* fb = esp_camera_fb_get();
      if (fb) {
        sendImageUDP(fb->buf, fb->len, frameNo);
        esp_camera_fb_return(fb);
        frameNo++;
      }
      vTaskDelay(1);
    } else {
      vTaskDelay(pdMS_TO_TICKS(20));
    }
  }
}

// ───── TCP 명령 처리 ─────
// 명령은 개행('\n') 단위의 ASCII 문자열로 가정: cam_start\n, cam_stop\n 등
String ctrlLine = "";

void handleCommandLine(const String& lineRaw) {
  String line = lineRaw;
  line.trim();
  if (line.length() == 0) return;

  Serial.print("[TCP-CMD] recv: ");
  Serial.println(line);

  if (line == "cam_start") {
    camStreaming = true;
    Serial.println("REST(TCP): cam_start → UDP stream ON.");
  } else if (line == "cam_stop") {
    camStreaming = false;
    Serial.println("REST(TCP): cam_stop → UDP stream OFF.");
  } else if (line == "flash_on") {
    digitalWrite(FLASH_LED_PIN, HIGH);
    Serial.println("REST(TCP): flash_on.");
  } else if (line == "flash_off") {
    digitalWrite(FLASH_LED_PIN, LOW);
    Serial.println("REST(TCP): flash_off.");
  } else if (line == "flash_blink") {
    for (int i = 0; i < 3; i++) {
      digitalWrite(FLASH_LED_PIN, HIGH);
      delay(200);
      digitalWrite(FLASH_LED_PIN, LOW);
      delay(200);
    }
    Serial.println("REST(TCP): flash_blink (3).");
  } else {
    Serial.println("[TCP-CMD] unknown command");
  }
}

void pollTcpControl() {
  if (!ctrlClient.connected()) {
    // 주기적으로 재접속 시도
    if (millis() - lastConnectAttempt >= RECONNECT_INTERVAL_MS) {
      lastConnectAttempt = millis();
      Serial.printf("[TCP] connecting to %s:%u ...\n", serverHostBuf, tcpPortNum);
      if (ctrlClient.connect(serverHostBuf, tcpPortNum)) {
        ctrlClient.setNoDelay(true);
        Serial.println("[TCP] connected.");
        // 접속 직후 장비 식별 정보 한 줄 전송(옵션)
        ctrlClient.print(String("hello ") + DEVICE_GUID + " " + DEVICE_NAME + "\n");
      } else {
        Serial.println("[TCP] connect failed.");
      }
    }
    return;
  }

  // 수신된 데이터를 줄 단위로 읽기
  while (ctrlClient.available() > 0) {
    char c = (char)ctrlClient.read();
    if (c == '\n') {
      handleCommandLine(ctrlLine);
      ctrlLine = "";
    } else if (c != '\r') {
      ctrlLine += c;
      if (ctrlLine.length() > 80) {
        ctrlLine = "";
      }
    }
  }

  // 필요하면 서버로 keepalive 전송 등 추가 가능
}

// ───── 초기화 ─────
void setup() {
  Serial.begin(115200);
  Serial.println("\n--- ESP32-CAM LPR (TCP control + UDP video) ---");

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
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 10;
  config.fb_count = 2;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera init failed.");
    delay(1000);
    ESP.restart();
  }

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected.");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  // UDP 전송 태스크 시작
  xTaskCreate(udpStreamTask, "udp555", 8192, NULL, 1, NULL);
  Serial.println("UDP stream task started.");

  lastConnectAttempt = millis() - RECONNECT_INTERVAL_MS;
}

// ───── 메인 루프 ─────
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    return;
  }

  // TCP 제어 폴링
  pollTcpControl();

  // 필요 시 다른 작업 추가
  delay(10);
}