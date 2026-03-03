#include <LiquidCrystal.h>
#include <WiFi.h>

// --- Network Configuration ---
const char* ssid = "iptime";
const char* password = "0000000625";

const char* serverIP = "192.168.0.4"; // The Python server IP
const uint16_t serverPort = 8080;     // The Control Server Port

// --- Packet Definitions ---
#define TYPE_IR_EVENT    0
#define TYPE_DEVICE_LIST 4
#define TYPE_PING        0xFE
#define TYPE_PONG        0xFD

#pragma pack(push, 1)
struct UnifiedPacket {
    uint8_t type;
    uint8_t payload[32];
};
#pragma pack(pop)

WiFiClient client;
UnifiedPacket txPkt;
UnifiedPacket rxPkt;

const int MAX_RETRY = 5;
bool deviceListSent = false;
unsigned long lastKeepAliveTime = 0;
unsigned long lastReconnectAttempt = 0;
const unsigned long PING_INTERVAL_MS = 5000;
const unsigned long PONG_TIMEOUT_MS = 5000;
const unsigned long RECONNECT_INTERVAL_MS = 3000;

// --- LCD 1602 Pins ---
// RS = 18, EN = 19, D4 = 21, D5 = 22, D6 = 23, D7 = 27
LiquidCrystal lcd(18, 19, 21, 22, 23, 27);

// --- IR Sensor Pins ---
const int irPin1 = 25;
const int irPin2 = 33;
const int irPin3 = 34; // Input-only pin
const int irPin4 = 35; // Input-only pin

// --- LED Pins ---
const int ledPin1 = 4;
const int ledPin2 = 26;
const int ledPin3 = 13;
const int ledPin4 = 14;

// --- Logic Configuration ---
const int DETECTED_STATE = LOW; 

// State Tracking
int lastState1 = -1;
int lastState2 = -1;
int lastState3 = -1;
int lastState4 = -1;

void sendDeviceList() {
    if (!client.connected()) return;
    memset(&txPkt, 0, sizeof(txPkt));
    txPkt.type = TYPE_DEVICE_LIST;
    txPkt.payload[0] = 0; // Index 0
    txPkt.payload[1] = 1; // Total 1
    strncpy((char*)&txPkt.payload[2], "ESP32-PARKING-01", 16); 
    strncpy((char*)&txPkt.payload[18], "ParkingDetect", 14);     
    client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket));
    delay(20);
    Serial.println("Device list sent to server.");
}

void sendParkingEvent(uint8_t spotNum, const char* srcName, bool isOccupied) {
    if (!client.connected()) return;
    uint8_t eventId = 10 + spotNum; 
    memset(&txPkt, 0, sizeof(txPkt));
    txPkt.type = TYPE_IR_EVENT;
    txPkt.payload[0] = eventId;
    strncpy((char*)&txPkt.payload[1], srcName, 15);
    
    if (isOccupied) {
        strncpy((char*)&txPkt.payload[17], "OCCUPIED", 14);
    } else {
        strncpy((char*)&txPkt.payload[17], "EMPTY", 14);
    }
    client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket));
    Serial.printf("Sent event: %s %s\n", srcName, isOccupied ? "OCCUPIED" : "EMPTY");
}

void setup() {
  Serial.begin(115200);

  lcd.begin(16, 2);
  lcd.print("System Starting.");
  delay(1500);
  lcd.clear();

  pinMode(irPin1, INPUT);
  pinMode(irPin2, INPUT);
  pinMode(irPin3, INPUT);
  pinMode(irPin4, INPUT);

  pinMode(ledPin1, OUTPUT);
  pinMode(ledPin2, OUTPUT);
  pinMode(ledPin3, OUTPUT);
  pinMode(ledPin4, OUTPUT);
  
  lcd.print("Connecting WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
      delay(500);
      Serial.print(".");
  }
  Serial.println("\nWiFi Connected.");
  lcd.clear();
  lcd.print("WiFi Connected!!");
  delay(1000);
  lcd.clear();
}

void loop() {
  // ---------------------------------------------------------
  // 1. ALWAYS Read Sensors and Update LCD (Regardless of Network)
  // ---------------------------------------------------------
  int state1 = digitalRead(irPin1);
  int state2 = digitalRead(irPin2);
  int state3 = digitalRead(irPin3);
  int state4 = digitalRead(irPin4);

  digitalWrite(ledPin1, (state1 == DETECTED_STATE) ? LOW : HIGH);
  digitalWrite(ledPin2, (state2 == DETECTED_STATE) ? LOW : HIGH);
  digitalWrite(ledPin3, (state3 == DETECTED_STATE) ? LOW : HIGH);
  digitalWrite(ledPin4, (state4 == DETECTED_STATE) ? LOW : HIGH);

  lcd.setCursor(0, 0);
  lcd.print("S1:"); lcd.print((state1 == DETECTED_STATE) ? "OCC " : "EMP ");
  lcd.print(" S2:"); lcd.print((state2 == DETECTED_STATE) ? "OCC " : "EMP ");
  lcd.setCursor(0, 1);
  lcd.print("S3:"); lcd.print((state3 == DETECTED_STATE) ? "OCC " : "EMP ");
  lcd.print(" S4:"); lcd.print((state4 == DETECTED_STATE) ? "OCC " : "EMP ");

  // ---------------------------------------------------------
  // 2. Handle Server Connection Asynchronously
  // ---------------------------------------------------------
  if (!client.connected()) {
      if (millis() - lastReconnectAttempt > RECONNECT_INTERVAL_MS) {
          lastReconnectAttempt = millis();
          deviceListSent = false;
          client.stop();
          Serial.println("Attempting to connect to Server...");
          
          if (client.connect(serverIP, serverPort)) {
              Serial.println("Connected to Server!");
              // Force full status update upon connection
              lastState1 = -1; lastState2 = -1; lastState3 = -1; lastState4 = -1;
          }
      }
  } else {
      // We are connected.
      if (!deviceListSent) {
          sendDeviceList();
          deviceListSent = true;
          lastKeepAliveTime = millis();
      }

      // Keep-Alive (PING) Protocol
      if (millis() - lastKeepAliveTime >= PING_INTERVAL_MS) {
          while (client.available() >= sizeof(UnifiedPacket)) {
              client.read((uint8_t*)&rxPkt, sizeof(UnifiedPacket));
          }
          memset(&txPkt, 0, sizeof(txPkt));
          txPkt.type = TYPE_PING;
          if (client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket)) == sizeof(UnifiedPacket)) {
              // Wait for PONG
              client.setTimeout(PONG_TIMEOUT_MS);
              size_t total = 0;
              unsigned long deadline = millis() + PONG_TIMEOUT_MS;
              while (total < sizeof(UnifiedPacket) && millis() < deadline) {
                  if (client.available() > 0) {
                      total += client.read((uint8_t*)&rxPkt + total, sizeof(UnifiedPacket) - total);
                  } else delay(10);
              }
              client.setTimeout(0);
              if (total != sizeof(UnifiedPacket) || rxPkt.type != TYPE_PONG) {
                  Serial.println("Server timeout! Disconnecting...");
                  client.stop();
              }
          } else {
              client.stop();
          }
          lastKeepAliveTime = millis();
      }

      // Transmit Event Changes
      if (client.connected()) {
          if (state1 != lastState1) { sendParkingEvent(1, "SPOT_1", (state1 == DETECTED_STATE)); lastState1 = state1; }
          if (state2 != lastState2) { sendParkingEvent(2, "SPOT_2", (state2 == DETECTED_STATE)); lastState2 = state2; }
          if (state3 != lastState3) { sendParkingEvent(3, "SPOT_3", (state3 == DETECTED_STATE)); lastState3 = state3; }
          if (state4 != lastState4) { sendParkingEvent(4, "SPOT_4", (state4 == DETECTED_STATE)); lastState4 = state4; }
      }
  }

  delay(150); 
}