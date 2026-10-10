/*
  right_master_prd_feedback_fixed.ino
  第二版汇总 - PRD 决策法庭硬件反馈修复版

  基于 right_master_lite_jelly，扩展 PRD finalEmotionZone。
  不使用脉冲计数状态机，避免 interval 期间的阻塞。

  状态：
  PH = positive_high  积极高唤醒
  PL = positive_low   积极低唤醒
  NH = negative_high  消极高唤醒
  NL = negative_low   消极低唤醒
  CF = conflict       冲突表达
  UK = unknown        不确定
  NT = neutral        中性

  兼容旧命令：A/S/C/F/U。
*/

#include <SoftwareSerial.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_ADDR 0x3C
#define MPU_ADDR 0x68

#define BT_RX_PIN 2
#define BT_TX_PIN 3
#define MOTOR_PIN 5

const int potPins[5] = {A0, A1, A2, A3, A6};

SoftwareSerial BTSerial(BT_RX_PIN, BT_TX_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

enum FeedbackZone {
  Z_POS_HIGH,   // PH
  Z_POS_LOW,    // PL
  Z_NEG_HIGH,   // NH / A
  Z_NEG_LOW,    // NL / S
  Z_CONFLICT,   // CF / F
  Z_UNKNOWN,    // UK / U
  Z_NEUTRAL    // NT / C
};

FeedbackZone currentZone = Z_NEUTRAL;
bool isVibrating = false;
unsigned long vibrationStartMs = 0;
unsigned long lastReportMs = 0;
unsigned long lastOledMs = 0;
unsigned long prevMotorMs = 0;

const unsigned long VIB_DURATION_MS = 3000;
const unsigned long SENSOR_REPORT_INTERVAL_MS = 100;
const unsigned long OLED_REFRESH_INTERVAL_MS = 300;

int thumbVal = 0;
int indexVal = 0;
int middleVal = 0;
int ringVal = 0;
int pinkyVal = 0;
int16_t ax = 0;
int16_t ay = 0;
int16_t az = 0;
int16_t gx = 0;
int16_t gy = 0;
int16_t gz = 0;

int sadPWM = 0;
int sadState = 0;

static const unsigned char PROGMEM jelly_happy[] = {
  0x00, 0x3F, 0x80, 0x00, 0x03, 0xC0, 0x70, 0x00, 0x0C, 0x00, 0x03, 0x00, 0x30, 0x00, 0x00, 0xC0,
  0x40, 0x00, 0x00, 0x80, 0x40, 0x00, 0x00, 0x80, 0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40,
  0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40, 0x80, 0x00, 0x00, 0x40,
  0x86, 0x33, 0x18, 0x40, 0x80, 0x0C, 0x00, 0x40, 0x80, 0x00, 0x00, 0x40, 0x87, 0x0C, 0x38, 0x40,
  0x48, 0x92, 0x44, 0x80, 0x30, 0x61, 0x83, 0x00, 0x30, 0x61, 0x83, 0x00, 0x18, 0xC0, 0xC6, 0x00,
  0x0C, 0xC0, 0xCC, 0x00, 0x19, 0x80, 0x66, 0x00, 0x30, 0x00, 0x03, 0x00
};

static const unsigned char PROGMEM jelly_angry[] = {
  0x00, 0x3F, 0x80, 0x00, 0x03, 0xC0, 0x70, 0x00, 0x0C, 0x00, 0x03, 0x00, 0x30, 0x00, 0x00, 0xC0,
  0x46, 0x00, 0x18, 0x80, 0x41, 0x80, 0x60, 0x80, 0x80, 0x00, 0x00, 0x40, 0x81, 0x80, 0x60, 0x40,
  0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40, 0x80, 0x00, 0x00, 0x40,
  0x80, 0x0C, 0x00, 0x40, 0x80, 0x33, 0x00, 0x40, 0x80, 0x00, 0x00, 0x40, 0x87, 0x0C, 0x38, 0x40,
  0x48, 0x92, 0x44, 0x80, 0x30, 0x61, 0x83, 0x00, 0x30, 0x61, 0x83, 0x00, 0x18, 0xC0, 0xC6, 0x00,
  0x0C, 0xC0, 0xCC, 0x00, 0x19, 0x80, 0x66, 0x00, 0x30, 0x00, 0x03, 0x00
};

static const unsigned char PROGMEM jelly_sad[] = {
  0x00, 0x3F, 0x80, 0x00, 0x03, 0xC0, 0x70, 0x00, 0x0C, 0x00, 0x03, 0x00, 0x30, 0x00, 0x00, 0xC0,
  0x41, 0x80, 0x60, 0x80, 0x46, 0x00, 0x18, 0x80, 0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40,
  0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40, 0x81, 0x80, 0x60, 0x40, 0x80, 0x00, 0x00, 0x40,
  0x86, 0x0C, 0x18, 0x40, 0x80, 0x33, 0x00, 0x40, 0x80, 0x00, 0x00, 0x40, 0x87, 0x0C, 0x38, 0x40,
  0x48, 0x92, 0x44, 0x80, 0x30, 0x61, 0x83, 0x00, 0x30, 0x61, 0x83, 0x00, 0x18, 0xC0, 0xC6, 0x00,
  0x0C, 0xC0, 0xCC, 0x00, 0x19, 0x80, 0x66, 0x00, 0x30, 0x00, 0x03, 0x00
};

const char* zoneCode(FeedbackZone z) {
  switch (z) {
    case Z_POS_HIGH: return "PH";
    case Z_POS_LOW: return "PL";
    case Z_NEG_HIGH: return "NH";
    case Z_NEG_LOW: return "NL";
    case Z_CONFLICT: return "CF";
    case Z_UNKNOWN: return "UK";
    default: return "NT";
  }
}

const char* zoneText(FeedbackZone z) {
  switch (z) {
    case Z_POS_HIGH: return "POS HIGH";
    case Z_POS_LOW: return "POS LOW";
    case Z_NEG_HIGH: return "NEG HIGH";
    case Z_NEG_LOW: return "NEG LOW";
    case Z_CONFLICT: return "CONFLICT";
    case Z_UNKNOWN: return "UNKNOWN";
    default: return "NEUTRAL";
  }
}

void drawScaledBitmap(int16_t x, int16_t y, const uint8_t *bitmap, int16_t w, int16_t h, uint8_t scale) {
  int16_t byteWidth = (w + 7) / 8;
  uint8_t byte = 0;
  for (int16_t j = 0; j < h; j++) {
    for (int16_t i = 0; i < w; i++) {
      if (i & 7) byte <<= 1;
      else byte = pgm_read_byte(&bitmap[j * byteWidth + i / 8]);
      if (byte & 0x80) {
        display.fillRect(x + i * scale, y + j * scale, scale, scale, SSD1306_WHITE);
      }
    }
  }
}

void readSensors() {
  thumbVal = analogRead(potPins[0]);
  indexVal = analogRead(potPins[1]);
  middleVal = analogRead(potPins[2]);
  ringVal = analogRead(potPins[3]);
  pinkyVal = analogRead(potPins[4]);

  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) == 0) {
    Wire.requestFrom(MPU_ADDR, 14, true);
    if (Wire.available() >= 14) {
      ax = Wire.read() << 8 | Wire.read();
      ay = Wire.read() << 8 | Wire.read();
      az = Wire.read() << 8 | Wire.read();
      Wire.read(); Wire.read();
      gx = Wire.read() << 8 | Wire.read();
      gy = Wire.read() << 8 | Wire.read();
      gz = Wire.read() << 8 | Wire.read();
    }
  }
}

void reportSensorsToBluetooth() {
  BTSerial.print(F("Thumb:")); BTSerial.print(thumbVal);
  BTSerial.print(F(", Index:")); BTSerial.print(indexVal);
  BTSerial.print(F(", Middle:")); BTSerial.print(middleVal);
  BTSerial.print(F(", Ring:")); BTSerial.print(ringVal);
  BTSerial.print(F(", Pinky:")); BTSerial.print(pinkyVal);
  BTSerial.print(F(", aX:")); BTSerial.print(ax / 100);
  BTSerial.print(F(", aY:")); BTSerial.print(ay / 100);
  BTSerial.print(F(", gZ:")); BTSerial.println(gz / 100);
}

void reportSensorsToUSB() {
  Serial.print(F("Thumb:")); Serial.print(thumbVal);
  Serial.print(F(",Index:")); Serial.print(indexVal);
  Serial.print(F(",Middle:")); Serial.print(middleVal);
  Serial.print(F(",Ring:")); Serial.print(ringVal);
  Serial.print(F(",Pinky:")); Serial.print(pinkyVal);
  Serial.print(F(",aY:")); Serial.print(ay / 100);
  Serial.print(F(",gZ:")); Serial.println(gz / 100);
}

void updateOLED() {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  uint8_t scale = 2;
  int x = (128 - 26 * scale) / 2;
  int y = 0;

  if (currentZone == Z_CONFLICT) {
    drawScaledBitmap(x, y, jelly_happy, 26, 23, scale);
    display.drawRect(36, 4, 56, 48, SSD1306_WHITE);
    display.drawLine(36, 4, 92, 52, SSD1306_WHITE);
    display.drawLine(92, 4, 36, 52, SSD1306_WHITE);
  } else if (currentZone == Z_UNKNOWN) {
    display.setTextSize(4);
    display.setCursor(50, 8);
    display.print(F("?"));
  } else if (currentZone == Z_NEG_HIGH) {
    drawScaledBitmap(x, y, jelly_angry, 26, 23, scale);
    display.setTextSize(2);
    display.setCursor(100, 4);
    display.print(F("!"));
  } else if (currentZone == Z_NEG_LOW) {
    drawScaledBitmap(x, y, jelly_sad, 26, 23, scale);
  } else {
    drawScaledBitmap(x, y, jelly_happy, 26, 23, scale);
  }

  display.setTextSize(1);
  display.setCursor(0, 55);
  display.print(zoneCode(currentZone));
  display.print(F(" "));
  display.print(zoneText(currentZone));

  display.display();
}

void triggerZone(FeedbackZone z) {
  currentZone = z;
  isVibrating = true;
  vibrationStartMs = millis();
  sadState = 0;
  sadPWM = 0;

  Serial.print(F("Zone: "));
  Serial.println(zoneCode(z));
  BTSerial.print(F("CMD_OK:"));
  BTSerial.println(zoneCode(z));

  updateOLED();
}

void handleBluetooth() {
  while (BTSerial.available() > 0) {
    char c = BTSerial.read();
    parseCommandChar(c);
  }
}

void handleUSBSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    parseCommandChar(c);
  }
}

void parseCommandChar(char c) {
  c = toupper(c);
  if (c == 'P') {
    char next = 0;
    if (BTSerial.available()) next = toupper(BTSerial.read());
    else if (Serial.available()) next = toupper(Serial.read());
    if (next == 'H') triggerZone(Z_POS_HIGH);
    else if (next == 'L') triggerZone(Z_POS_LOW);
    else triggerZone(Z_NEUTRAL);
  } else if (c == 'N') {
    char next = 0;
    if (BTSerial.available()) next = toupper(BTSerial.read());
    else if (Serial.available()) next = toupper(Serial.read());
    if (next == 'H') triggerZone(Z_NEG_HIGH);
    else if (next == 'L') triggerZone(Z_NEG_LOW);
    else triggerZone(Z_NEUTRAL);
  } else if (c == 'C') {
    char next = 0;
    if (BTSerial.available()) next = toupper(BTSerial.read());
    else if (Serial.available()) next = toupper(Serial.read());
    if (next == 'F') triggerZone(Z_CONFLICT);
    else triggerZone(Z_NEUTRAL);
  } else if (c == 'U') {
    char next = 0;
    if (BTSerial.available()) next = toupper(BTSerial.read());
    else if (Serial.available()) next = toupper(Serial.read());
    if (next == 'K') triggerZone(Z_UNKNOWN);
    else triggerZone(Z_UNKNOWN);
  } else if (c == 'A') {
    triggerZone(Z_NEG_HIGH);
  } else if (c == 'S') {
    triggerZone(Z_NEG_LOW);
  } else if (c == 'F') {
    triggerZone(Z_CONFLICT);
  }
}

void handleMotor() {
  unsigned long now = millis();

  if (!isVibrating || now - vibrationStartMs >= VIB_DURATION_MS) {
    isVibrating = false;
    analogWrite(MOTOR_PIN, 0);
    return;
  }

  switch (currentZone) {
    case Z_NEG_HIGH: {
      int phase = now % 180;
      analogWrite(MOTOR_PIN, phase < 120 ? 255 : 0);
      break;
    }
    case Z_NEG_LOW: {
      if (now - prevMotorMs >= 30) {
        prevMotorMs = now;
        if (sadState == 0) {
          sadPWM = 180;
          sadState = 1;
        } else if (sadState == 1) {
          sadPWM -= 3;
          if (sadPWM <= 80) {
            sadPWM = 0;
            sadState = 2;
          }
        } else {
          static int waitCounter = 0;
          waitCounter++;
          if (waitCounter > 40) {
            waitCounter = 0;
            sadState = 0;
          }
        }
        analogWrite(MOTOR_PIN, sadPWM);
      }
      break;
    }
    case Z_POS_HIGH: {
      int phase = now % 240;
      analogWrite(MOTOR_PIN, phase < 100 ? 115 : 0);
      break;
    }
    case Z_POS_LOW: {
      int phase = now % 400;
      analogWrite(MOTOR_PIN, phase < 80 ? 64 : 0);
      break;
    }
    case Z_CONFLICT: {
      int phase = now % 500;
      analogWrite(MOTOR_PIN, phase < 100 ? 140 : 0);
      break;
    }
    case Z_UNKNOWN: {
      analogWrite(MOTOR_PIN, 51);
      break;
    }
    default: {
      float phase = (now % 4000) / 4000.0 * 2.0 * PI;
      int calmPWM = 110 + (int)(sin(phase) * 30.0);
      analogWrite(MOTOR_PIN, calmPWM);
      break;
    }
  }
}

void initMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0);
  if (Wire.endTransmission(true) == 0) {
    Serial.println(F("MPU6050 OK"));
  } else {
    Serial.println(F("MPU6050 FAILED"));
  }
}

void setup() {
  Serial.begin(9600);
  BTSerial.begin(9600);
  pinMode(MOTOR_PIN, OUTPUT);
  analogWrite(MOTOR_PIN, 0);

  Serial.println(F("Right PRD feedback fixed booting..."));

  digitalWrite(MOTOR_PIN, HIGH);
  delay(250);
  digitalWrite(MOTOR_PIN, LOW);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println(F("OLED FAILED"));
    for (;;);
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(F("Right PRD Fixed"));
  display.println(F("OLED OK"));
  display.display();
  delay(700);

  initMPU();
  readSensors();
  updateOLED();

  BTSerial.println(F("RIGHT_PRD_FIXED_READY"));
  Serial.println(F("Right PRD fixed ready. Send PH/PL/NH/NL/CF/UK/NT or A/S/C."));
}

void loop() {
  unsigned long now = millis();

  handleBluetooth();
  handleUSBSerial();
  handleMotor();

  if (now - lastReportMs >= SENSOR_REPORT_INTERVAL_MS) {
    lastReportMs = now;
    readSensors();
    reportSensorsToBluetooth();
    reportSensorsToUSB();
  }

  if (now - lastOledMs >= OLED_REFRESH_INTERVAL_MS) {
    lastOledMs = now;
    updateOLED();
  }
}
