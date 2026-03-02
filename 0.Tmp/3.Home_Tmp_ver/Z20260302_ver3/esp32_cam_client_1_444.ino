// ESP32-CAM 클라이언트 444 — UDP 이미지 전송을 별도 스레드(FreeRTOS 태스크)로 처리
// 333과 동일 포트( TCP 8082, UDP 7071 ) → 기존 333 서버로 테스트 가능

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiClient.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#if 1 // Debug Home Mode
const char* ssid     = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";
const char* serverIP = "192.168.25.35";
const uint16_t serverPort = 8082;   // 333 서버 TCP
const char* udpAddress = "192.168.25.35";
const int   udpPort    = 7071;      // 333 서버 UDP
#else
const char* ssid     = "addinedu_201class_2-2.4G";
const char* password = "201class2!";
const char* serverIP = "192.168.0.149";
const uint16_t serverPort = 8082;
const char* udpAddress = "192.168.0.149";
const int   udpPort    = 7071;
#endif

#define TYPE_PING          0xFE
#define TYPE_PONG          0xFD
#define TYPE_DEVICE_LIST   4
#define TYPE_CMD_CAM_START 6
#define TYPE_CMD_CAM_STOP  7
#define TYPE_CMD_FLASH_ON  8
#define TYPE_CMD_FLASH_OFF 9
#define TYPE_CMD_FLASH_BLINK 10

#pragma pack(push, 1)
struct UnifiedPacket {
    uint8_t type;
    uint8_t payload[32];
};
#pragma pack(pop)

#define DEVICE_COUNT 1
static const struct { const char guid[17]; const char name[15]; } DEVICE_LIST[DEVICE_COUNT] = {
    { "ESP32-CAM-01    ", "CamStream" },
};

WiFiClient client;
WiFiUDP udp;
UnifiedPacket txPkt;
UnifiedPacket rxPkt;

bool deviceListSent = false;
volatile bool camStreaming = false;   // loop()에서 설정, UDP 태스크에서 읽음
unsigned long lastKeepAliveTime = 0;
const unsigned long PING_INTERVAL_MS = 5000;
const unsigned long PONG_TIMEOUT_MS = 5000;
const unsigned long FRAME_INTERVAL_MS = 100;

// UDP 태스크 전용 (태스크에서만 갱신)
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

void sendDeviceList() {
    if (!client.connected()) return;
    for (uint8_t i = 0; i < DEVICE_COUNT; i++) {
        memset(&txPkt, 0, sizeof(txPkt));
        txPkt.type = TYPE_DEVICE_LIST;
        txPkt.payload[0] = i;
        txPkt.payload[1] = DEVICE_COUNT;
        strncpy((char*)&txPkt.payload[2], DEVICE_LIST[i].guid, 16);
        strncpy((char*)&txPkt.payload[18], DEVICE_LIST[i].name, 14);
        client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket));
        delay(20);
    }
    Serial.println("Device list sent to server (444).");
}

// 444: TCP는 loop()에서만 처리. UDP 태스크에서는 호출하지 않음 (공유 소켓 충돌 방지)
void yieldToTcp() {
    (void)0;
}

void sendImageUDP(uint8_t* imageData, size_t imageSize, uint8_t fno) {
    size_t remainingSize = imageSize;
    uint8_t packetNo = 0;
    uint8_t checksum = 0;
    for (size_t i = 0; i < imageSize; i++) checksum += imageData[i];

    while (remainingSize > 0) {
        size_t chunkSize = (remainingSize <= 1024) ? remainingSize : (size_t)1024;
        bool isLastPacket = (remainingSize <= 1024);

        udp.beginPacket(udpAddress, udpPort);
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
    Serial.printf("[SEND444] f_no=%u pkts=%u size=%u\n", (unsigned)fno, (unsigned)packetNo, (unsigned)imageSize);
}

// FreeRTOS 태스크: 캡처 + UDP 전송만 담당. TCP(명령 수신)는 loop()에서만 처리.
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
            // 스트리밍 대기 중: loop()가 CAM_START 수신할 수 있도록 충분히 양보
            vTaskDelay(pdMS_TO_TICKS(20));
        }
    }
}

void setup() {
    Serial.begin(115200);
    Serial.println("\n--- ESP32-CAM client 444 (UDP in task, TCP 8082, UDP 7071) ---");

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

    if (client.connect(serverIP, serverPort)) {
        Serial.println("Server (444/333 port) Connected.");
        lastKeepAliveTime = millis();
    }

    // UDP 영상 전송 전용 태스크 생성 (스레드)
    xTaskCreate(udpStreamTask, "udpStream", 8192, NULL, 1, NULL);
    Serial.println("UDP stream task started.");

    Serial.println("Init setup : End");
}

void loop() {
    // TCP 재접속
    if (!client.connected()) {
        client.stop();
        deviceListSent = false;
        camStreaming = false;
        if (client.connect(serverIP, serverPort)) {
            lastKeepAliveTime = millis();
            Serial.println("Reconnected to Server (444).");
        } else {
            delay(5000);
            return;
        }
    }

    if (client.connected() && !deviceListSent) {
        sendDeviceList();
        deviceListSent = true;
    }

    // UDP 전송 중이 아닐 때만 KEEPALIVE
    if (!camStreaming && client.connected() && (millis() - lastKeepAliveTime >= PING_INTERVAL_MS)) {
        while (client.available() >= sizeof(UnifiedPacket))
            client.read((uint8_t*)&rxPkt, sizeof(UnifiedPacket));
        memset(&txPkt, 0, sizeof(txPkt));
        txPkt.type = TYPE_PING;
        if (client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket)) != sizeof(UnifiedPacket)) {
            client.stop();
            return;
        }
        client.setTimeout(PONG_TIMEOUT_MS);
        size_t total = 0;
        unsigned long deadline = millis() + PONG_TIMEOUT_MS;
        while (total < sizeof(UnifiedPacket) && millis() < deadline) {
            if (client.available() > 0) {
                size_t n = client.read((uint8_t*)&rxPkt + total, sizeof(UnifiedPacket) - total);
                total += n;
            } else delay(10);
        }
        client.setTimeout(0);
        if (total != sizeof(UnifiedPacket) || rxPkt.type != TYPE_PONG) {
            Serial.println("Keep-alive timeout.");
            client.stop();
            return;
        }
        lastKeepAliveTime = millis();
    }

    // 서버 명령: CAM_START/STOP, 플래시
    if (client.available() >= sizeof(UnifiedPacket)) {
        client.read((uint8_t*)&rxPkt, sizeof(UnifiedPacket));
        if (rxPkt.type == TYPE_CMD_CAM_START) {
            camStreaming = true;
            Serial.println("CAM_START (444): UDP stream started.");
        } else if (rxPkt.type == TYPE_CMD_CAM_STOP) {
            camStreaming = false;
            Serial.println("CAM_STOP (444): UDP stream stopped.");
        } else if (rxPkt.type == TYPE_CMD_FLASH_ON) {
            digitalWrite(FLASH_LED_PIN, HIGH);
            Serial.println("FLASH_ON.");
        } else if (rxPkt.type == TYPE_CMD_FLASH_OFF) {
            digitalWrite(FLASH_LED_PIN, LOW);
            Serial.println("FLASH_OFF.");
        } else if (rxPkt.type == TYPE_CMD_FLASH_BLINK) {
            for (int i = 0; i < 3; i++) {
                digitalWrite(FLASH_LED_PIN, HIGH);
                delay(200);
                digitalWrite(FLASH_LED_PIN, LOW);
                delay(200);
            }
            Serial.println("FLASH_BLINK (3회).");
        }
    }

    delay(1);
}
