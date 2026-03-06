#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <freertos/queue.h>

// --- [설정] 사용자 환경에 맞춰 수정 ---
#if 0 // Debug Home Mode
const char* ssid     = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";
char serverHostBuf[64] = "192.168.25.35"; // 파이썬 서버 IP
#else
const char* ssid     = "addinedu_201class_2-2.4G";
const char* password = "201class2!";
char serverHostBuf[64] = "192.168.0.149"; // 파이썬 서버 IP
#endif

uint16_t restPortNum = 7080;
uint16_t udpPortNum  = 7070;

#define DEVICE_GUID "ESP32-CAM-01"
#define DEVICE_NAME "CamStream"
#define FLASH_LED_PIN 4

// --- [핀 정의] AI-Thinker ESP32-CAM 기준 ---
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

// --- [FreeRTOS 객체] ---
QueueHandle_t cmdQueue;      // 명령어 큐
struct CommandMsg {
    char cmdText[64];        // 명령어 문자열 저장 공간
};

WiFiUDP udp;
WebServer server(80);
volatile bool camStreaming = false;
unsigned long lastAliveHit = 0;
const unsigned long ALIVE_TIMEOUT_MS = 60000;
uint8_t frameNo = 0;

// --- [함수] 서버 등록 로직 ---
void restRegister() {
    HTTPClient http;
    http.setTimeout(3000);
    String url = "http://" + String(serverHostBuf) + ":" + String(restPortNum) + "/api/device/register";
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    String body = "{\"guid\":\"" + String(DEVICE_GUID) + "\",\"name\":\"" + String(DEVICE_NAME) + "\",\"ip\":\"" + WiFi.localIP().toString() + "\"}";
    int code = http.POST(body);
    http.end();
    Serial.printf("[REST] Register Result: %d\n", code);
}

// --- [태스크 1] 웹 서버 (명령 수신 -> 큐에 삽입) (Core 1) ---
void taskWebServer(void* pvParameters) {
    server.on("/api/devices/info", []() {
        server.send(200, "application/json", "{\"guid\":\"" + String(DEVICE_GUID) + "\"}");
    });
    
    server.on("/api/devices/alive", []() {
        lastAliveHit = millis();
        server.send(200, "text/plain", "OK");
    });

    server.on("/api/device/command", HTTP_ANY, []() {
        String payload = server.hasArg("plain") ? server.arg("plain") : server.arg("command");
        if (payload.length() == 0) {
            server.send(400, "application/json", "{\"error\":\"no command\"}");
            return;
        }

        CommandMsg msg;
        strncpy(msg.cmdText, payload.c_str(), sizeof(msg.cmdText) - 1);
        msg.cmdText[sizeof(msg.cmdText) - 1] = '\0';

        if (xQueueSend(cmdQueue, &msg, 0) == pdPASS) {
            server.send(200, "application/json", "{\"status\":\"queued\"}");
        } else {
            server.send(500, "application/json", "{\"status\":\"queue_full\"}");
        }
    });

    server.begin();
    Serial.println("[Task] WebServer started on Core 1");
    for (;;) {
        server.handleClient();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

// --- [태스크 2] 명령 처리기 (큐에서 꺼내서 실행) (Core 1) ---
void taskCommandProcessor(void* pvParameters) {
    CommandMsg receivedMsg;
    Serial.println("[Task] Command Processor started on Core 1");
    for (;;) {
        if (xQueueReceive(cmdQueue, &receivedMsg, portMAX_DELAY)) {
            String cmd = String(receivedMsg.cmdText);
            Serial.printf("[Queue Exec] %s\n", cmd.c_str());

            if (cmd.indexOf("cam_start") >= 0) camStreaming = true;
            else if (cmd.indexOf("cam_stop") >= 0) camStreaming = false;
            else if (cmd.indexOf("flash_on") >= 0) digitalWrite(FLASH_LED_PIN, HIGH);
            else if (cmd.indexOf("flash_off") >= 0) digitalWrite(FLASH_LED_PIN, LOW);
            else if (cmd.indexOf("flash_blink") >= 0) {
                for (int i = 0; i < 3; i++) {
                    digitalWrite(FLASH_LED_PIN, HIGH); vTaskDelay(pdMS_TO_TICKS(200));
                    digitalWrite(FLASH_LED_PIN, LOW);  vTaskDelay(pdMS_TO_TICKS(200));
                }
            }
        }
    }
}

// --- [태스크 3] UDP 영상 전송 (Core 0) ---
void taskUdpStream(void* pvParameters) {
    Serial.println("[Task] UDP Stream started on Core 0");
    for (;;) {
        if (camStreaming) {
            camera_fb_t* fb = esp_camera_fb_get();
            if (fb) {
                size_t imgSize = fb->len;
                uint8_t* data = fb->buf;
                uint8_t packetNo = 0;

                // 전체 프레임에 대한 1바이트 체크섬 (sum % 256)
                uint8_t checksum = 0;
                for (size_t i = 0; i < imgSize; i++) {
                    checksum += fb->buf[i];
                }

                size_t remaining = imgSize;
                uint8_t* p = data;
                while (remaining > 0) {
                    size_t chunk = (remaining <= 1024) ? remaining : 1024;
                    bool isLast = (remaining <= 1024);
                    udp.beginPacket(serverHostBuf, udpPortNum);
                    udp.write(frameNo);
                    udp.write(packetNo++);
                    udp.write(isLast ? 1 : 0);                 // isLast
                    udp.write(isLast ? checksum : (uint8_t)0); // 마지막 패킷에만 체크섬 전송
                    udp.write(p, chunk);
                    udp.endPacket();
                    
                    p += chunk;
                    remaining -= chunk;
                    vTaskDelay(pdMS_TO_TICKS(2)); // 네트워크 드라이버 숨통 틔워주기
                }
                esp_camera_fb_return(fb);
                frameNo++;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(50)); // 약 20fps 시도
    }
}

// --- [태스크 4] 시스템 관리/폴링 (Core 1) ---
void taskSystemMonitor(void* pvParameters) {
    for (;;) {
        if (WiFi.status() == WL_CONNECTED) {
            if (millis() - lastAliveHit >= ALIVE_TIMEOUT_MS) {
                restRegister();
                lastAliveHit = millis();
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}

void setup() {
    Serial.begin(115200);
    pinMode(FLASH_LED_PIN, OUTPUT);
    digitalWrite(FLASH_LED_PIN, LOW);

    // 1. 카메라 초기화
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM; config.pin_d1 = Y3_GPIO_NUM; config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM; config.pin_d4 = Y6_GPIO_NUM; config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM; config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM; config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM; config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM; config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM; config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;

    if (esp_camera_init(&config) != ESP_OK) {
        Serial.println("Camera Init Failed");
        delay(1000); ESP.restart();
    }

    // 2. WiFi 연결
    WiFi.begin(ssid, password);
    WiFi.setSleep(false);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.println("\nWiFi Connected. IP: " + WiFi.localIP().toString());

    // 3. 명령어 큐 생성 (10개 저장 가능)
    cmdQueue = xQueueCreate(10, sizeof(CommandMsg));

    // 4. 초기 등록
    restRegister();
    lastAliveHit = millis();

    // 5. 멀티코어 태스크 시작
    // Core 0: 영상 전송 전담
    xTaskCreatePinnedToCore(taskUdpStream, "UDP", 8192, NULL, 2, NULL, 0);

    // Core 1: 통신 및 명령 처리
    xTaskCreatePinnedToCore(taskWebServer, "Web", 4096, NULL, 3, NULL, 1);
    xTaskCreatePinnedToCore(taskCommandProcessor, "Cmd", 4096, NULL, 2, NULL, 1);
    xTaskCreatePinnedToCore(taskSystemMonitor, "Sys", 4096, NULL, 1, NULL, 1);
}

void loop() {
    // 멀티태스킹 환경이므로 loop는 비워둡니다.
    vTaskDelay(pdMS_TO_TICKS(1000));
}