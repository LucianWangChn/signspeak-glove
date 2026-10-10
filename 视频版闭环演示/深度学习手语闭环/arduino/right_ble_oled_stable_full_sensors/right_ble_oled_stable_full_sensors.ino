/*
  right_ble_oled_stable_full_sensors.ino
  右手 Nano 稳定拍摄版：BLE + OLED 中文/水母 + 振动 + 右手五指/MPU 输出

  注意：本版本故意不加入 RadioHead/315M RX。
  原因：Nano SRAM 只有 2KB，SSD1306 需要 1024B 屏幕缓冲；再加 RadioHead 很容易 OLED failed。

  接线：
  - BLE TX -> D2, BLE RX -> D3
  - 振动马达 -> D5
  - 五指：A0/A1/A2/A3/A6
  - OLED + MPU6050：I2C A4/A5
*/

#include <SoftwareSerial.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "oled_mother_lines.h"

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDR 0x3C
#define MPU_ADDR 0x68

#define BLE_RX_PIN 2
#define BLE_TX_PIN 3
#define VIBRATION_PIN 5

const uint8_t fingerPins[5] = {A0, A1, A2, A3, A6};
const unsigned long SENSOR_INTERVAL_MS = 250;
const unsigned long JELLY_MS = 1400;

SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

struct VibrationPattern {
  uint8_t repeat;
  uint16_t durationMs;
  uint16_t intervalMs;
  uint8_t intensity;
};

const VibrationPattern VIB_POSITIVE_LOW = {1, 80, 0, 25};
const VibrationPattern VIB_CONFLICT = {2, 100, 250, 55};

int thumbVal = 0;
int indexVal = 0;
int middleVal = 0;
int ringVal = 0;
int pinkyVal = 0;
int16_t axVal = 0;
int16_t ayVal = 0;
int16_t gzVal = 0;

String inputUsb = "";
String inputBle = "";
int currentState = 1;
bool textMode = false;
unsigned long lastCommandMs = 0;
unsigned long lastSensorMs = 0;

static const unsigned char PROGMEM jelly_happy[] = {
  0x00,0x3F,0x00,0x00,0x03,0xC0,0xF0,0x00,0x0C,0x00,0x0C,0x00,0x30,0x00,0x03,0x00,
  0x40,0x00,0x00,0x80,0x40,0x00,0x00,0x80,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,
  0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x80,0x00,0x00,0x40,
  0x86,0x33,0x18,0x40,0x80,0x0C,0x00,0x40,0x80,0x00,0x00,0x40,0x87,0x0C,0x38,0x40,
  0x48,0x92,0x44,0x80,0x30,0x61,0x83,0x00,0x30,0x61,0x83,0x00,0x18,0xC0,0xC6,0x00,
  0x0C,0xC0,0xCC,0x00,0x19,0x80,0x66,0x00,0x30,0x00,0x03,0x00
};

static const unsigned char PROGMEM jelly_sad[] = {
  0x00,0x3F,0x00,0x00,0x03,0xC0,0xF0,0x00,0x0C,0x00,0x0C,0x00,0x30,0x00,0x03,0x00,
  0x41,0x80,0x60,0x80,0x46,0x00,0x18,0x80,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,
  0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x80,0x00,0x00,0x40,
  0x86,0x0C,0x18,0x40,0x80,0x33,0x00,0x40,0x80,0x00,0x00,0x40,0x87,0x0C,0x38,0x40,
  0x48,0x92,0x44,0x80,0x30,0x61,0x83,0x00,0x30,0x61,0x83,0x00,0x18,0xC0,0xC6,0x00,
  0x0C,0xC0,0xCC,0x00,0x19,0x80,0x66,0x00,0x30,0x00,0x03,0x00
};

void initMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0);
  Wire.endTransmission(true);
}

bool readMPU(int16_t &ax, int16_t &ay, int16_t &gz) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t n = Wire.requestFrom(MPU_ADDR, 14, true);
  if (n < 14) return false;

  int16_t axRaw = (Wire.read() << 8) | Wire.read();
  int16_t ayRaw = (Wire.read() << 8) | Wire.read();
  Wire.read(); Wire.read(); // az ignored
  Wire.read(); Wire.read(); // temp ignored
  Wire.read(); Wire.read(); // gx ignored
  Wire.read(); Wire.read(); // gy ignored
  int16_t gzRaw = (Wire.read() << 8) | Wire.read();

  ax = axRaw / 100;
  ay = ayRaw / 100;
  gz = gzRaw / 100;
  return true;
}

void readSensors() {
  thumbVal = analogRead(fingerPins[0]);
  indexVal = analogRead(fingerPins[1]);
  middleVal = analogRead(fingerPins[2]);
  ringVal = analogRead(fingerPins[3]);
  pinkyVal = analogRead(fingerPins[4]);

  if (!readMPU(axVal, ayVal, gzVal)) {
    axVal = 0;
    ayVal = 0;
    gzVal = 0;
  }
}

void sendSensorLine(Stream &s) {
  s.print(F("R:Thumb:")); s.print(thumbVal);
  s.print(F(",Index:")); s.print(indexVal);
  s.print(F(",Middle:")); s.print(middleVal);
  s.print(F(",Ring:")); s.print(ringVal);
  s.print(F(",Pinky:")); s.print(pinkyVal);
  s.print(F(",aX:")); s.print(axVal);
  s.print(F(",aY:")); s.print(ayVal);
  s.print(F(",gZ:")); s.println(gzVal);
}

void sendSensors() {
  sendSensorLine(BLESerial);
  sendSensorLine(Serial);
}

void playVibration(const VibrationPattern &p) {
  uint8_t pwm = map(p.intensity, 0, 100, 0, 255);
  for (uint8_t i = 0; i < p.repeat; i++) {
    analogWrite(VIBRATION_PIN, pwm);
    delay(p.durationMs);
    analogWrite(VIBRATION_PIN, 0);
    if (i + 1 < p.repeat && p.intervalMs > 0) delay(p.intervalMs);
  }
}

void drawScaledBitmap(int16_t x, int16_t y, const uint8_t *bmp, int16_t w, int16_t h, uint8_t scale) {
  int16_t byteWidth = (w + 7) / 8;
  uint8_t b = 0;
  for (int16_t j = 0; j < h; j++) {
    for (int16_t i = 0; i < w; i++) {
      if (i & 7) b <<= 1;
      else b = pgm_read_byte(&bmp[j * byteWidth + i / 8]);
      if (b & 0x80) {
        display.fillRect(x + i * scale, y + j * scale, scale, scale, SSD1306_WHITE);
      }
    }
  }
}

void drawJelly() {
  display.clearDisplay();
  if (currentState == 1) {
    drawScaledBitmap(25, -2, jelly_sad, 26, 23, 3);
  } else {
    drawScaledBitmap(25, -2, jelly_happy, 26, 23, 3);
  }
  display.display();
}

void drawText() {
  display.clearDisplay();
  if (currentState == 1) {
    display.drawBitmap(0, 0, MOM_LINE_1, 128, 64, SSD1306_WHITE);
  } else {
    display.drawBitmap(0, 0, MOM_LINE_2, 128, 64, SSD1306_WHITE);
  }
  display.display();
}

void showState(int state) {
  currentState = state;
  textMode = false;
  lastCommandMs = millis();
  drawJelly();

  if (currentState == 1) {
    playVibration(VIB_CONFLICT);
  } else {
    playVibration(VIB_POSITIVE_LOW);
  }

  Serial.print(F("SHOW:")); Serial.println(currentState);
  BLESerial.print(F("SHOW:")); BLESerial.println(currentState);
}

void handleCommand(String raw) {
  raw.trim();
  raw.toUpperCase();
  if (raw.startsWith("T:")) raw = raw.substring(2);

  if (raw == "1" || raw == "M1" || raw == "CF" || raw == "NL") {
    showState(1);
  } else if (raw == "2" || raw == "M2" || raw == "PL") {
    showState(2);
  }
}

void readStream(Stream &s, String &buf) {
  while (s.available()) {
    char c = (char)s.read();

    if (c == '\r' || c == '\n' || c == ' ' || c == '\t') {
      if (buf.length() > 0) {
        handleCommand(buf);
        buf = "";
      }
      continue;
    }

    c = toupper(c);
    if (c == ':') {
      if (buf == "T") buf += c;
      continue;
    }

    if (buf.length() < 8) buf += c;

    if (buf == "1" || buf == "2" || buf == "M1" || buf == "M2" ||
        buf == "CF" || buf == "NL" || buf == "PL" ||
        (buf.length() >= 4 && buf.startsWith("T:"))) {
      handleCommand(buf);
      buf = "";
    }
  }
}

void setup() {
  Serial.begin(9600);
  BLESerial.begin(9600);
  Wire.begin();

  pinMode(VIBRATION_PIN, OUTPUT);
  analogWrite(VIBRATION_PIN, 0);
  initMPU();

  Serial.println(F("Right BLE OLED stable booting..."));

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println(F("OLED failed"));
    while (1) delay(100);
  }

  display.setRotation(2);
  showState(1);
}

void loop() {
  readStream(Serial, inputUsb);
  readStream(BLESerial, inputBle);

  unsigned long now = millis();
  if (now - lastSensorMs >= SENSOR_INTERVAL_MS) {
    lastSensorMs = now;
    readSensors();
    sendSensors();
  }

  if (!textMode && now - lastCommandMs >= JELLY_MS) {
    textMode = true;
    drawText();
  }
}
