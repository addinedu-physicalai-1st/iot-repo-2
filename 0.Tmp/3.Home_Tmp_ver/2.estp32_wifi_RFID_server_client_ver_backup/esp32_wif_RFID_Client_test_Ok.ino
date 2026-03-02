#include <WiFi.h>
#include <SPI.h>
#include <MFRC522.h>

#if 1 //Debug Home Mode
const char* ssid = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";

const char* serverIP = "192.168.25.35"; // PyQt6 서버(PC)의 IP 주소 //192.168.25.34 ~ 35

#else
const char *ssid     = "addinedu_201class_2-2.4G";   // 2.4G WiFi SSID
const char *password = "201class2!";                 // WiFi 비밀번호

const char* serverIP = "192.168.25.5";               // 디바이스 PC IP

#endif

const uint16_t serverPort = 8080;
const unsigned long RECONNECT_INTERVAL_MS = 5000;  // 연결 실패 시 5초마다 재시도
const unsigned long PING_INTERVAL_MS = 5000;       // Keep-alive: 5초마다 PING 전송
const unsigned long PONG_TIMEOUT_MS = 5000;       // PONG 대기 시간, 없으면 연결 종료

#define PING_MODE 0xFE  // 클라이언트 → 서버 Keep-alive 요청
#define PONG_MODE 0xFD  // 서버 → 클라이언트 Keep-alive 응답

WiFiClient client;
unsigned long lastKeepAliveTime = 0;

#define SS_PIN 5
#define RST_PIN 22
MFRC522 rfid(SS_PIN, RST_PIN);
MFRC522::MIFARE_Key key;

#pragma pack(push, 1)
struct ParkData {
    uint8_t mode;       // 0: Read, 2: Write SiteID
    char uid[16];       // 카드 고유번호
    char siteID[16];    // 주차장 유일값 (Block 4 저장)
};
#pragma pack(pop)

ParkData currentData;

void setup() {
    Serial.begin(115200);
    SPI.begin();
    rfid.PCD_Init();
    for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) delay(500);
}

void loop() {
    // 연결 끊김 시 정리 후 5초 간격으로 재접속 시도
    if (!client.connected()) {
        client.stop();
        if (!client.connect(serverIP, serverPort)) {
            Serial.println("[Client] 서버 연결 실패. 5초 후 재시도...");
            delay(RECONNECT_INTERVAL_MS);
            return;
        }
        lastKeepAliveTime = millis();
        Serial.println("[Client] to [serverIP:" + String(serverIP) + "] 접속되었습니다.");
        delay(300);  // 서버 handle() 스레드가 recv()에 들어갈 시간 확보
    }

    // Keep-alive: 5초마다 PING 전송, PONG 없으면 연결 종료 후 다음 루프에서 재시도
    if (client.connected() && (millis() - lastKeepAliveTime >= PING_INTERVAL_MS)) {
        // PING 전에 버퍼에 남은 데이터(서버 명령 등) 먼저 처리 — PONG과 혼동 방지
        while (client.available() >= sizeof(ParkData)) {
            client.read((uint8_t*)&currentData, sizeof(ParkData));
        }
        ParkData pingPacket;
        memset(&pingPacket, 0, sizeof(pingPacket));
        pingPacket.mode = PING_MODE;
        if (client.write((uint8_t*)&pingPacket, sizeof(ParkData)) != sizeof(ParkData)) {
            client.stop();
            return;
        }
        // PONG 수신: 타임아웃 내에 33바이트가 조각나서 올 수 있으므로 바이트 단위로 모아서 읽기
        client.setTimeout(PONG_TIMEOUT_MS);
        size_t total = 0;
        unsigned long deadline = millis() + PONG_TIMEOUT_MS;
        while (total < sizeof(ParkData) && millis() < deadline) {
            if (client.available() > 0) {
                size_t n = client.read((uint8_t*)&currentData + total, sizeof(ParkData) - total);
                total += n;
            } else {
                delay(10);
            }
        }
        client.setTimeout(0);
        if (total != sizeof(ParkData) || currentData.mode != PONG_MODE) {
            Serial.println("[Client] Keep-alive 응답 없음. 연결을 끊고 재시도합니다.");
            client.stop();
            return;
        }
        lastKeepAliveTime = millis();
    }

    // 서버로부터 '주차장 ID 쓰기' 명령 수신
    if (client.available() >= sizeof(ParkData)) {
        size_t n = client.read((uint8_t*)&currentData, sizeof(ParkData));
        if (n != sizeof(ParkData)) {
            Serial.println("[Client] 수신 오류. 연결을 끊고 재시도합니다.");
            client.stop();
            return;
        }
    }

    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
        // 1. UID 읽기
        String uidStr = "";
        for (byte i = 0; i < rfid.uid.size; i++) {
            uidStr += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
            uidStr += String(rfid.uid.uidByte[i], HEX);
        }
        strncpy(currentData.uid, uidStr.c_str(), 16);

        // 2. 주차장 ID 처리
        int targetBlock = 4; // Block 4에 주차장 ID만 저장
        MFRC522::StatusCode status = rfid.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, targetBlock, &key, &(rfid.uid));

        if (status == MFRC522::STATUS_OK) {
            if (currentData.mode == 2) { // WRITE 모드: 서버가 준 SiteID를 카드에 저장
                byte buffer[16];
                memset(buffer, 0, 16);
                memcpy(buffer, currentData.siteID, 16);
                rfid.MIFARE_Write(targetBlock, buffer, 16);
                Serial.println("RFID 카드에 값을 저장하였습니다.");
                currentData.mode = 0;
            } else { // READ 모드: 카드에서 SiteID를 읽어옴
                byte buffer[18];
                byte size = sizeof(buffer);
                if (rfid.MIFARE_Read(targetBlock, buffer, &size) == MFRC522::STATUS_OK) {
                    memcpy(currentData.siteID, buffer, 16);
                }
            }
        }

        // 3. 서버로 전송 (UID + SiteID) — 전송 실패 시 연결 끊김 처리
        if (!client.connected()) {
            client.stop();
            return;
        }
        size_t sent = client.write((uint8_t*)&currentData, sizeof(ParkData));
        if (sent != sizeof(ParkData)) {
            Serial.println("[Client] 전송 실패. 연결 끊김. 5초 후 재시도합니다.");
            client.stop();
            delay(RECONNECT_INTERVAL_MS);
            return;
        }

        rfid.PICC_HaltA();
        rfid.PCD_StopCrypto1();
        delay(1000);
    }
}