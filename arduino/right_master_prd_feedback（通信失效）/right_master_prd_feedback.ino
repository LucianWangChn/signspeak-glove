/*
  right_master_prd_feedback.ino
  第二版汇总 - PRD 决策法庭硬件反馈版

  基于 right_master_lite_jelly，支持 PRD 中的 finalEmotionZone：
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
  Z_POS_HIGH,
  Z_POS_LOW,
  Z_NEG_HIGH,
  Z_NEG_LOW,
  Z_CONFLICT,
  Z_UNKNOWN,
  Z_NEUTRAL
};

FeedbackZone currentZone = Z_NEUTRAL;
char currentLegacy = 'C';
bool isVibrating = false;
unsigned long vibrationStartMs = 0;
unsigned long lastReportMs = 0;
unsigned long lastOledMs = 0;
unsigned long patternStartMs = 0;
int patternPulseIndex = 0;
bool patternOn = false;

const unsigned long SENSOR_REPORT_INTERVAL_MS = 100;
const unsigned long OLED_REFRESH_INTERVAL_MS = 300;

int thumbVal = 0, indexVal = 0, middleVal = 0, ringVal = 0, pinkyVal = 0;
int16_t ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;

struct VibPattern {
  uint8_t repeat;
  uint16_t durationMs;
  uint16_t intervalMs;
  uint8_t intensity;
};

const VibPattern VIB_POS_HIGH = {2, 100, 120, 45};
const VibPattern VIB_POS_LOW  = {1, 80, 0, 25};
const VibPattern VIB_NEG_HIGH = {3, 150, 90, 85};
const VibPattern VIB_NEG_LOW  = {1, 350, 0, 35};
const VibPattern VIB_CONFLICT = {2, 100, 250, 55};
const VibPattern VIB_UNKNOWN  = {1, 90, 0, 20};
const VibPattern VIB_NEUTRAL  = {0, 0, 0, 0};

// 26x23 jellyfish-like icons in PROGMEM.
static const unsigned char PROGMEM jelly_happy[] = {
  0x00,0x3F,0x80,0x00,0x03,0xC0,0x70,0x00,0x0C,0x00,0x03,0x00,0x30,0x00,0x00,0xC0,
  0x40,0x00,0x00,0x80,0x40,0x00,0x00,0x80,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,
  0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x80,0x00,0x00,0x40,
  0x86,0x33,0x18,0x40,0x80,0x0C,0x00,0x40,0x80,0x00,0x00,0x40,0x87,0x0C,0x38,0x40,
  0x48,0x92,0x44,0x80,0x30,0x61,0x83,0x00,0x30,0x61,0x83,0x00,0x18,0xC0,0xC6,0x00,
  0x0C,0xC0,0xCC,0x00,0x19,0x80,0x66,0x00,0x30,0x00,0x03,0x00
};
static const unsigned char PROGMEM jelly_angry[] = {
  0x00,0x3F,0x80,0x00,0x03,0xC0,0x70,0x00,0x0C,0x00,0x03,0x00,0x30,0x00,0x00,0xC0,
  0x46,0x00,0x18,0x80,0x41,0x80,0x60,0x80,0x80,0x00,0x00,0x40,0x81,0x80,0x60,0x40,
  0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x80,0x00,0x00,0x40,
  0x80,0x0C,0x00,0x40,0x80,0x33,0x00,0x40,0x80,0x00,0x00,0x40,0x87,0x0C,0x38,0x40,
  0x48,0x92,0x44,0x80,0x30,0x61,0x83,0x00,0x30,0x61,0x83,0x00,0x18,0xC0,0xC6,0x00,
  0x0C,0xC0,0xCC,0x00,0x19,0x80,0x66,0x00,0x30,0x00,0x03,0x00
};
static const unsigned char PROGMEM jelly_sad[] = {
  0x00,0x3F,0x80,0x00,0x03,0xC0,0x70,0x00,0x0C,0x00,0x03,0x00,0x30,0x00,0x00,0xC0,
  0x41,0x80,0x60,0x80,0x46,0x00,0x18,0x80,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,
  0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x80,0x00,0x00,0x40,
  0x86,0x0C,0x18,0x40,0x80,0x33,0x00,0x40,0x80,0x00,0x00,0x40,0x87,0x0C,0x38,0x40,
  0x48,0x92,0x44,0x80,0x30,0x61,0x83,0x00,0x30,0x61,0x83,0x00,0x18,0xC0,0xC6,0x00,
  0x0C,0xC0,0xCC,0x00,0x19,0x80,0x66,0x00,0x30,0x00,0x03,0x00
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

const VibPattern getPattern(FeedbackZone z) {
  switch (z) {
    case Z_POS_HIGH: return VIB_POS_HIGH;
    case Z_POS_LOW: return VIB_POS_LOW;
    case Z_NEG_HIGH: return VIB_NEG_HIGH;
    case Z_NEG_LOW: return VIB_NEG_LOW;
    case Z_CONFLICT: return VIB_CONFLICT;
    case Z_UNKNOWN: return VIB_UNKNOWN;
    default: return VIB_NEUTRAL;
  }
}

void drawScaledBitmap(int16_t x, int16_t y, const uint8_t *bitmap, int16_t w, int16_t h, uint8_t scale) {
  int16_t byteWidth = (w + 7) / 8;
  uint8_t byte = 0;
  for (int16_t j = 0; j < h; j++) {
    for (int16_t i = 0; i < w; i++) {
      if (i & 7) byte <<= 1;
      else byte = pgm_read_byte(&bitmap[j * byteWidth + i / 8]);
      if (byte & 0x80) display.fillRect(x + i * scale, y + j * scale, scale, scale, SSD1306_WHITE);
    }
  }
}

void readSensors() {
  thumbVal = analogRead(potPins[0]); indexVal = analogRead(potPins[1]);
  middleVal = analogRead(potPins[2]); ringVal = analogRead(potPins[3]); pinkyVal = analogRead(potPins[4]);
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B);
  if (Wire.endTransmission(false) == 0) {
    Wire.requestFrom(MPU_ADDR, 14, true);
    if (Wire.available() >= 14) {
      ax = Wire.read() << 8 | Wire.read(); ay = Wire.read() << 8 | Wire.read(); az = Wire.read() << 8 | Wire.read();
      Wire.read(); Wire.read();
      gx = Wire.read() << 8 | Wire.read(); gy = Wire.read() << 8 | Wire.read(); gz = Wire.read() << 8 | Wire.read();
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

void updateOLED() {
  display.clearDisplay(); display.setTextColor(SSD1306_WHITE);
  uint8_t scale = 2; int x = (128 - 26 * scale) / 2; int y = 0;

  if (currentZone == Z_CONFLICT) {
    drawScaledBitmap(x, y, jelly_happy, 26, 23, scale);
    display.drawRect(36, 4, 56, 48, SSD1306_WHITE);
    display.drawLine(36, 4, 92, 52, SSD1306_WHITE);
    display.drawLine(92, 4, 36, 52, SSD1306_WHITE);
  } else if (currentZone == Z_UNKNOWN) {
    display.setTextSize(4); display.setCursor(50, 8); display.print(F("?"));
  } else if (currentZone == Z_NEG_HIGH) {
    drawScaledBitmap(x, y, jelly_angry, 26, 23, scale);
    display.setTextSize(2); display.setCursor(100, 4); display.print(F("!"));
  } else if (currentZone == Z_NEG_LOW) {
    drawScaledBitmap(x, y, jelly_sad, 26, 23, scale);
  } else {
    drawScaledBitmap(x, y, jelly_happy, 26, 23, scale);
  }

  display.setTextSize(1); display.setCursor(0, 55);
  display.print(zoneCode(currentZone)); display.print(F(" "));
  display.print(zoneText(currentZone));
  display.display();
}

void startFeedback(FeedbackZone z) {
  currentZone = z;
  currentLegacy = (z == Z_NEG_HIGH) ? 'A' : (z == Z_NEG_LOW ? 'S' : 'C');
  VibPattern p = getPattern(z);
  isVibrating = (p.repeat > 0 && p.intensity > 0);
  vibrationStartMs = millis(); patternStartMs = millis(); patternPulseIndex = 0; patternOn = true;
  Serial.print(F("Feedback zone: ")); Serial.println(zoneCode(z));
  BTSerial.print(F("CMD_OK:")); BTSerial.println(zoneCode(z));
  updateOLED();
}

void handleMotorPattern() {
  if (!isVibrating) { analogWrite(MOTOR_PIN, 0); return; }
  VibPattern p = getPattern(currentZone);
  if (p.repeat == 0) { isVibrating = false; analogWrite(MOTOR_PIN, 0); return; }

  unsigned long now = millis();
  unsigned long elapsed = now - patternStartMs;
  uint16_t pwm = map(p.intensity, 0, 100, 0, 255);

  if (patternOn) {
    analogWrite(MOTOR_PIN, pwm);
    if (elapsed >= p.durationMs) {
      patternOn = false; patternStartMs = now; analogWrite(MOTOR_PIN, 0); patternPulseIndex++;
      if (patternPulseIndex >= p.repeat) isVibrating = false;
    }
  } else {
    analogWrite(MOTOR_PIN, 0);
    if (elapsed >= p.intervalMs) { patternOn = true; patternStartMs = now; }
  }
}

void handleCommandToken(String token) {
  token.trim(); token.toUpperCase();
  if (token == "PH") startFeedback(Z_POS_HIGH);
  else if (token == "PL") startFeedback(Z_POS_LOW);
  else if (token == "NH" || token == "A") startFeedback(Z_NEG_HIGH);
  else if (token == "NL" || token == "S") startFeedback(Z_NEG_LOW);
  else if (token == "CF" || token == "F") startFeedback(Z_CONFLICT);
  else if (token == "UK" || token == "U") startFeedback(Z_UNKNOWN);
  else if (token == "NT" || token == "C") startFeedback(Z_NEUTRAL);
}

void readCommands(Stream &port) {
  static String usbBuf = "";
  static String btBuf = "";
  String &buf = (&port == &Serial) ? usbBuf : btBuf;
  while (port.available() > 0) {
    char c = port.read();
    if (c == '\n' || c == '\r') {
      if (buf.length() > 0) { handleCommandToken(buf); buf = ""; }
    } else {
      buf += c;
      if (buf.length() == 1 && (buf == "A" || buf == "S" || buf == "C" || buf == "F" || buf == "U")) {
        handleCommandToken(buf); buf = "";
      } else if (buf.length() >= 2) {
        handleCommandToken(buf); buf = "";
      }
    }
  }
}

void initMPU() {
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x6B); Wire.write(0);
  if (Wire.endTransmission(true) == 0) Serial.println(F("MPU6050 OK"));
  else Serial.println(F("MPU6050 FAILED"));
}

void setup() {
  Serial.begin(9600); BTSerial.begin(9600); pinMode(MOTOR_PIN, OUTPUT); analogWrite(MOTOR_PIN, 0);
  Serial.println(F("Right PRD feedback booting..."));
  digitalWrite(MOTOR_PIN, HIGH); delay(250); digitalWrite(MOTOR_PIN, LOW);
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) { Serial.println(F("OLED FAILED")); for (;;); }
  display.clearDisplay(); display.setTextSize(1); display.setTextColor(SSD1306_WHITE); display.setCursor(0,0);
  display.println(F("Right PRD Feedback")); display.println(F("OLED OK")); display.display(); delay(700);
  initMPU(); readSensors(); updateOLED();
  BTSerial.println(F("RIGHT_PRD_READY"));
  Serial.println(F("Right PRD ready. Send PH/PL/NH/NL/CF/UK/NT or A/S/C."));
}

void loop() {
  unsigned long now = millis();
  readCommands(Serial); readCommands(BTSerial); handleMotorPattern();
  if (now - lastReportMs >= SENSOR_REPORT_INTERVAL_MS) { lastReportMs = now; readSensors(); reportSensorsToBluetooth(); }
  if (now - lastOledMs >= OLED_REFRESH_INTERVAL_MS) { lastOledMs = now; updateOLED(); }
}
