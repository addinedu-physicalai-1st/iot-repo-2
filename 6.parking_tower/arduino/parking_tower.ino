#include <AccelStepper.h>

const int STEP_PIN = 2;
const int DIR_PIN = 3;
const int ENABLE_PIN = 4;
const int SENSOR_PIN = 5;
const int GREEN_LED_PIN = 6;
const int RED_LED_PIN = 7;
const int EMERGENCY_PIN = 8;

AccelStepper stepper(AccelStepper::DRIVER, STEP_PIN, DIR_PIN);

long stepsPerPlate = 400;
long homeOffsetSteps = 0;
long currentPlateIndex = 0;
const int TOTAL_PLATES = 6;

bool homed = false;
bool moving = false;
bool emergencyStop = false;
bool fullState = false;
bool allowInState = true;

String inputBuffer = "";

void setLamps() {
  bool greenOn = (!moving && !emergencyStop && !fullState && allowInState);
  bool redOn = !greenOn;
  digitalWrite(GREEN_LED_PIN, greenOn ? HIGH : LOW);
  digitalWrite(RED_LED_PIN, redOn ? HIGH : LOW);
}

bool isHomeSensorDetected() {
  return digitalRead(SENSOR_PIN) == LOW;
}

void sendStatus(const String& extra = "") {
  Serial.print("STATUS|");
  Serial.print("homed="); Serial.print(homed ? 1 : 0);
  Serial.print("|moving="); Serial.print(moving ? 1 : 0);
  Serial.print("|emergency="); Serial.print(emergencyStop ? 1 : 0);
  Serial.print("|full="); Serial.print(fullState ? 1 : 0);
  Serial.print("|allowIn="); Serial.print(allowInState ? 1 : 0);
  Serial.print("|plate="); Serial.print(currentPlateIndex);
  Serial.print("|sensor="); Serial.print(isHomeSensorDetected() ? 1 : 0);
  Serial.print("|stepPos="); Serial.print(stepper.currentPosition());
  if (extra.length() > 0) { Serial.print("|"); Serial.print(extra); }
  Serial.println();
}

void stopMotorNow() {
  stepper.stop();
  moving = false;
  setLamps();
}

void homeTower() {
  if (emergencyStop) { Serial.println("ERR|EMERGENCY_ACTIVE"); return; }
  moving = true;
  setLamps();

  for (int i = 0; i < 300; i++) {
    stepper.moveTo(stepper.currentPosition() + 1);
    while (stepper.distanceToGo() != 0) {
      stepper.run();
      if (emergencyStop) {
        stopMotorNow();
        Serial.println("ERR|EMERGENCY_STOP_DURING_HOME");
        return;
      }
    }
  }

  long maxSeek = stepsPerPlate * TOTAL_PLATES * 2;
  long moved = 0;
  while (!isHomeSensorDetected() && moved < maxSeek) {
    stepper.moveTo(stepper.currentPosition() + 1);
    while (stepper.distanceToGo() != 0) {
      stepper.run();
      if (emergencyStop) {
        stopMotorNow();
        Serial.println("ERR|EMERGENCY_STOP_DURING_HOME");
        return;
      }
    }
    moved++;
  }

  if (!isHomeSensorDetected()) {
    moving = false;
    setLamps();
    Serial.println("ERR|HOME_NOT_FOUND");
    return;
  }

  stepper.setCurrentPosition(homeOffsetSteps);
  currentPlateIndex = 0;
  homed = true;
  moving = false;
  setLamps();
  Serial.println("OK|HOME_DONE");
  sendStatus();
}

void moveToPlate(int targetPlateIndex) {
  if (!homed) { Serial.println("ERR|NOT_HOMED"); return; }
  if (emergencyStop) { Serial.println("ERR|EMERGENCY_ACTIVE"); return; }
  if (targetPlateIndex < 0 || targetPlateIndex >= TOTAL_PLATES) { Serial.println("ERR|INVALID_PLATE"); return; }

  int deltaIndex = targetPlateIndex - currentPlateIndex;
  long targetSteps = stepper.currentPosition() + (long)deltaIndex * stepsPerPlate;

  moving = true;
  setLamps();
  stepper.moveTo(targetSteps);

  while (stepper.distanceToGo() != 0) {
    stepper.run();
    if (emergencyStop) {
      stopMotorNow();
      Serial.println("ERR|EMERGENCY_STOP_DURING_MOVE");
      return;
    }
  }

  currentPlateIndex = targetPlateIndex;
  moving = false;
  setLamps();
  Serial.print("OK|MOVE_DONE|plate=");
  Serial.println(currentPlateIndex);
  sendStatus();
}

void processCommand(String cmd) {
  cmd.trim();
  if (cmd == "PING") { Serial.println("OK|PONG"); return; }
  if (cmd == "HOME") { homeTower(); return; }
  if (cmd == "STATUS") { sendStatus(); return; }

  if (cmd == "EMG_ON") {
    emergencyStop = true;
    stopMotorNow();
    Serial.println("OK|EMG_ON");
    sendStatus();
    return;
  }

  if (cmd == "EMG_OFF") {
    emergencyStop = false;
    setLamps();
    Serial.println("OK|EMG_OFF");
    sendStatus();
    return;
  }

  if (cmd.startsWith("FULL=")) {
    String value = cmd.substring(5);
    fullState = (value == "1");
    setLamps();
    Serial.println("OK|FULL_SET");
    sendStatus();
    return;
  }

  if (cmd.startsWith("ALLOW_IN=")) {
    String value = cmd.substring(9);
    allowInState = (value == "1");
    setLamps();
    Serial.println("OK|ALLOW_IN_SET");
    sendStatus();
    return;
  }

  if (cmd.startsWith("SET_STEPS=")) {
    String value = cmd.substring(10);
    long newSteps = value.toInt();
    if (newSteps <= 0) { Serial.println("ERR|INVALID_STEPS"); return; }
    stepsPerPlate = newSteps;
    Serial.println("OK|STEPS_UPDATED");
    sendStatus();
    return;
  }

  if (cmd.startsWith("SET_OFFSET=")) {
    String value = cmd.substring(11);
    homeOffsetSteps = value.toInt();
    Serial.println("OK|OFFSET_UPDATED");
    sendStatus();
    return;
  }

  if (cmd.startsWith("MOVE=")) {
    int target = cmd.substring(5).toInt();
    moveToPlate(target);
    return;
  }

  Serial.println("ERR|UNKNOWN_COMMAND");
}

void setup() {
  pinMode(SENSOR_PIN, INPUT_PULLUP);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(ENABLE_PIN, OUTPUT);
  pinMode(EMERGENCY_PIN, INPUT_PULLUP);

  digitalWrite(ENABLE_PIN, LOW);
  stepper.setMaxSpeed(1200);
  stepper.setAcceleration(800);

  Serial.begin(115200);
  setLamps();
  Serial.println("OK|BOOT");
}

void loop() {
  if (digitalRead(EMERGENCY_PIN) == LOW) {
    emergencyStop = true;
    stopMotorNow();
  }

  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else if (c != '\r') {
      inputBuffer += c;
    }
  }

  setLamps();
}
