// ESP32-CAM 클라이언트 555 — REST API 양방향 제어 + UDP 영상 전송(별도 스레드)
// REST: POST /api/device/register, GET /api/device/command (폴링) → 서버 명령 수신
// UDP: 영상 전송은 FreeRTOS 태스크에서 전담 (loop와 분리)

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <HTTPClient.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#if 0 // Debug Home Mode
const char* ssid     = "addinedu_201class_2-2.4G";
const char* password = "201class2!";
#else
const char* ssid     = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";
#endif
// 서버 주소: 초기값 사용, GET /api/device/config 폴링으로 파이썬에서 수정 가능
//char serverHostBuf[64] = "192.168.0.35"; //Tony Home
char serverHostBuf[64] = "192.168.0.149"; //Tony Home


uint16_t restPortNum = 5555;
uint16_t udpPortNum  = 7072;

#define DEVICE_GUID "ESP32-CAM-01    "
#define DEVICE_NAME "CamStream"

WiFiUDP udp;
volatile bool camStreaming = false;
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

// REST: 장비 등록 (POST JSON) — 초기 셋업 끝난 후 서버에 IP 등 보고
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
        Serial.println("[555] REST register OK (ip=" + ipStr + ").");
    else
        Serial.printf("[555] REST register %d\n", code);
}

// REST: 서버에서 장비에 내려보낼 설정 수신 (GET) — 파이썬 에디터에서 수정한 값 반영
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
        if (restPortNum == 0) restPortNum = 5555;
    }
    int upStart = payload.indexOf("\"udp_port\":");
    if (upStart >= 0) {
        udpPortNum = (uint16_t)payload.substring(upStart + 11).toInt();
        if (udpPortNum == 0) udpPortNum = 7072;
    }
    Serial.printf("[555] config → host=%s rest=%u udp=%u\n", serverHostBuf, restPortNum, udpPortNum);
}

// REST: 명령 폴링 (GET) → 응답 JSON에서 command 파싱
void restPollCommand() {
    HTTPClient http;
    String url = "http://";
    url += serverHostBuf;
    url += ":";
    url += String(restPortNum);
    url += "/api/device/command?guid=";
    url += String(DEVICE_GUID);
    http.begin(url);
    int code = http.GET();
    String payload;
    if (code == 200)
        payload = http.getString();
    http.end();
    if (code != 200 || payload.length() == 0)
        return;
    if (payload.indexOf("\"command\":\"cam_start\"") >= 0) {
        camStreaming = true;
        Serial.println("REST: cam_start → UDP stream ON.");
    } else if (payload.indexOf("\"command\":\"cam_stop\"") >= 0) {
        camStreaming = false;
        Serial.println("REST: cam_stop → UDP stream OFF.");
    } else if (payload.indexOf("\"command\":\"flash_on\"") >= 0) {
        digitalWrite(FLASH_LED_PIN, HIGH);
        Serial.println("REST: flash_on.");
    } else if (payload.indexOf("\"command\":\"flash_off\"") >= 0) {
        digitalWrite(FLASH_LED_PIN, LOW);
        Serial.println("REST: flash_off.");
    } else if (payload.indexOf("\"command\":\"flash_blink\"") >= 0) {
        for (int i = 0; i < 3; i++) {
            digitalWrite(FLASH_LED_PIN, HIGH);
            delay(200);
            digitalWrite(FLASH_LED_PIN, LOW);
            delay(200);
        }
        Serial.println("REST: flash_blink (3).");
    }
}

// REST: /api/devices 호출 → 서버가 알고 있는 장비 목록(guid, name 등)을 확인용으로 출력
void restPollDevices() {
    HTTPClient http;
    String url = "http://";
    url += serverHostBuf;
    url += ":";
    url += String(restPortNum);
    url += "/api/devices";
    http.begin(url);
    int code = http.GET();
    String payload;
    if (code == 200) {
        payload = http.getString();
    }
    http.end();

    if (code != 200 || payload.length() == 0) {
        return;
    }

    // 아주 단순하게 JSON 문자열에서 "guid" / "name" 쌍을 찾아서 시리얼에 출력
    int pos = 0;
    while (true) {
        int gIdx = payload.indexOf("\"guid\"", pos);
        if (gIdx < 0) break;
        int gValStart = payload.indexOf("\"", gIdx + 6);
        if (gValStart < 0) break;
        gValStart += 1;
        int gValEnd = payload.indexOf("\"", gValStart);
        if (gValEnd < 0) break;
        String guid = payload.substring(gValStart, gValEnd);

        int nIdx = payload.indexOf("\"name\"", gValEnd);
        if (nIdx < 0) {
            pos = gValEnd;
            continue;
        }
        int nValStart = payload.indexOf("\"", nIdx + 6);
        if (nValStart < 0) break;
        nValStart += 1;
        int nValEnd = payload.indexOf("\"", nValStart);
        if (nValEnd < 0) break;
        String name = payload.substring(nValStart, nValEnd);

        Serial.print("[555] /api/devices → guid=");
        Serial.print(guid);
        Serial.print(" name=");
        Serial.println(name);

        pos = nValEnd;
    }
}

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
    Serial.printf("[SEND555] f_no=%u pkts=%u size=%u\n", (unsigned)fno, (unsigned)packetNo, (unsigned)imageSize);
}

// UDP 영상 전송 전용 태스크 (별도 스레드)
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

void setup() {
    Serial.begin(115200);
    Serial.println("\n--- ESP32-CAM client 555 (REST API + UDP task) ---");

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

    restRegister();
    restPollConfig();
    xTaskCreate(udpStreamTask, "udp555", 8192, NULL, 1, NULL);
    Serial.println("UDP stream task started.");
    Serial.println("Init setup : End");
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        delay(5000);
        return;
    }
    if (millis() - lastRestPoll >= REST_POLL_INTERVAL_MS) {
        lastRestPoll = millis();
        restPollCommand();
    }
    if (millis() - lastConfigPoll >= REST_CONFIG_POLL_INTERVAL_MS) {
        lastConfigPoll = millis();
        restPollConfig();
    }
    if (millis() - lastDevicesPoll >= REST_DEVICES_POLL_INTERVAL_MS) {
      lastDevicesPoll = millis();
      restPollDevices();
    }
    delay(10);
}
