// ESP32-CAM LPR 666 — 기동 후 자동 UDP 스트리밍 (REST 명령 없음)
// - WiFi 연결 후 즉시 UDP 영상 전송 (cam_start 폴링 불필요)
// - REST 명령 폴링(restPollCommand 등)은 기동 후 스타트하는 부분을 주석 처리

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#if 1 // Debug Home Mode
const char* ssid     = "addinedu_201class_2-2.4G";
const char* password = "201class2!";
#else
const char* ssid     = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";
#endif
char serverHostBuf[64] = "192.168.0.137";

uint16_t restPortNum = 7080;
uint16_t udpPortNum  = 7070;

#define DEVICE_GUID "DEV-LPR-1"
#define DEVICE_NAME "입구 LPR 카메라"

WiFiUDP udp;
// 666: 기동 후 자동 스트리밍 — true 고정 (REST cam_start 불필요)
volatile bool camStreaming = true;

const unsigned long REST_POLL_INTERVAL_MS = 1500;
const unsigned long REST_CONFIG_POLL_INTERVAL_MS = 10000;
const unsigned long REST_DEVICES_POLL_INTERVAL_MS = 10000;
unsigned long lastConfigPoll = 0;
unsigned long lastDevicesPoll = 0;
const unsigned long FRAME_INTERVAL_MS = 100;
unsigned long lastRestPoll = 0;
unsigned long lastFrameTime = 0;
uint8_t frameNo = 0;

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
#define FLASH_LED_PIN     4

void restRegister() {
    HTTPClient http;
    String url = "http://";
    url += serverHostBuf;
    url += ":";
    url += String(restPortNum);
    url += "/api/device/register";
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    String ipStr = WiFi.localIP().toString();
    String body = "{\"guid\":\"";
    body += DEVICE_GUID;
    body += "\",\"name\":\"";
    body += DEVICE_NAME;
    body += "\",\"ip\":\"";
    body += ipStr;
    body += "\"}";
    int code = http.POST(body);
    http.end();
    if (code == 200)
        Serial.println("[666] REST register OK (ip=" + ipStr + ").");
    else
        Serial.printf("[666] REST register %d\n", code);
}

void restPollConfig() {
    HTTPClient http;
    String url = "http://";
    url += serverHostBuf;
    url += ":";
    url += String(restPortNum);
    url += "/api/device/config";
    http.begin(url);
    int code = http.GET();
    String payload;
    if (code == 200)
        payload = http.getString();
    http.end();
    if (code != 200 || payload.length() == 0) return;
    int hostStart = payload.indexOf("\"server_host\":\"");
    if (hostStart >= 0) {
        hostStart += 15;
        int hostEnd = payload.indexOf("\"", hostStart);
        if (hostEnd > hostStart && hostEnd - hostStart < (int)sizeof(serverHostBuf) - 1) {
            payload.substring(hostStart, hostEnd).toCharArray(serverHostBuf, sizeof(serverHostBuf));
        }
    }
    int rpStart = payload.indexOf("\"rest_port\":");
    if (rpStart >= 0) {
        restPortNum = (uint16_t)payload.substring(rpStart + 12).toInt();
        if (restPortNum == 0) restPortNum = 7080;
    }
    int upStart = payload.indexOf("\"udp_port\":");
    if (upStart >= 0) {
        udpPortNum = (uint16_t)payload.substring(upStart + 11).toInt();
        if (udpPortNum == 0) udpPortNum = 7070;
    }
    Serial.printf("[666] config → host=%s rest=%u udp=%u\n", serverHostBuf, restPortNum, udpPortNum);
}

// REST: 명령 폴링 — 666에서는 사용하지 않음 (기동 후 자동 스트리밍이므로 주석으로 비활성화)
// void restPollCommand() { ... }

// REST: /api/devices — 666에서는 사용하지 않음 (주석 처리)
// void restPollDevices() { ... }

void sendImageUDP(uint8_t* imageData, size_t imageSize, uint8_t fno) {
    size_t remainingSize = imageSize;
    uint8_t packetNo = 0;
    uint8_t checksum = 0;
    for (size_t i = 0; i < imageSize; i++) checksum += imageData[i];
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
    Serial.printf("[SEND666] f_no=%u pkts=%u size=%u\n", (unsigned)fno, (unsigned)packetNo, (unsigned)imageSize);
}

void udpStreamTask(void* pvParameters) {
    Serial.println("[666] UDP stream task started (auto streaming on boot).");
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

void setup() {
    Serial.begin(115200);
    Serial.println("\n--- ESP32-CAM LPR 666 (auto UDP stream, no REST command) ---");

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
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.println("\nWiFi Connected.");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());

    restRegister();
    restPollConfig();
    xTaskCreate(udpStreamTask, "udp666", 8192, NULL, 1, NULL);
    Serial.println("[666] Init done. UDP streaming auto started.");
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        delay(5000);
        return;
    }
    // --- 666: REST API 명령 폴링은 기동 후 스타트하지 않음 (주석 처리) ---
    // if (millis() - lastRestPoll >= REST_POLL_INTERVAL_MS) {
    //     lastRestPoll = millis();
    //     restPollCommand();
    // }
    if (millis() - lastConfigPoll >= REST_CONFIG_POLL_INTERVAL_MS) {
        lastConfigPoll = millis();
        restPollConfig();
    }
    // --- 666: /api/devices 폴링도 주석 처리 ---
    // if (millis() - lastDevicesPoll >= REST_DEVICES_POLL_INTERVAL_MS) {
    //     lastDevicesPoll = millis();
    //     restPollDevices();
    // }
    delay(10);
}
