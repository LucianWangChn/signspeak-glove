/*
  oled_mother_lines_demo.ino
  妈妈台词 OLED 最简拍摄版 - 大水母/大字版

  只保留两个映射：
  1 / M1：伤心水母全屏 -> 大字“行吧”
  2 / M2：开心水母全屏 -> 大字“行吧听你的”
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

#define BLE_RX_PIN 2
#define BLE_TX_PIN 3
#define VIBRATION_PIN 5

const int potPins[5] = {A0, A1, A2, A3, A6};
const unsigned long SENSOR_INTERVAL_MS = 300;
unsigned long lastSensorMs = 0;
int thumbVal = 0;
int indexVal = 0;
int middleVal = 0;
int ringVal = 0;
int pinkyVal = 0;

SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

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

String inputUsb = "";
String inputBle = "";
int currentState = 1;
bool textMode = false;
unsigned long lastCommandMs = 0;
const unsigned long JELLY_MS = 1400;

struct VibrationPattern {
  uint8_t repeat;
  uint16_t durationMs;
  uint16_t intervalMs;
  uint8_t intensity;
};

const VibrationPattern VIB_POSITIVE_LOW = {1, 80, 0, 25};
const VibrationPattern VIB_CONFLICT = {2, 100, 250, 55};

void readSensors() {
  thumbVal = analogRead(potPins[0]);
  indexVal = analogRead(potPins[1]);
  middleVal = analogRead(potPins[2]);
  ringVal = analogRead(potPins[3]);
  pinkyVal = analogRead(potPins[4]);
}

void sendSensorBLE() {
  // 拍摄稳定版：BLE 只发触发音频需要的三根手指，缩短软串口占用时间。
  // SoftwareSerial 在发送长数据时容易漏收电脑写入的 1/2 命令，所以这里不要发 Ring/Pinky/MPU。
  BLESerial.print(F("R:Thumb:")); BLESerial.print(thumbVal);
  BLESerial.print(F(",Index:")); BLESerial.print(indexVal);
  BLESerial.print(F(",Middle:")); BLESerial.println(middleVal);
}

void printSensorUSB() {
  Serial.print(F("R:Thumb:")); Serial.print(thumbVal);
  Serial.print(F(",Index:")); Serial.print(indexVal);
  Serial.print(F(",Middle:")); Serial.print(middleVal);
  Serial.print(F(",Ring:")); Serial.print(ringVal);
  Serial.print(F(",Pinky:")); Serial.print(pinkyVal);
  Serial.println(F(",aX:0,aY:0,gZ:0"));
}

void playVibration(const VibrationPattern &p) {
  if (p.repeat == 0 || p.intensity == 0 || p.durationMs == 0) {
    analogWrite(VIBRATION_PIN, 0);
    return;
  }
  uint8_t pwm = map(p.intensity, 0, 100, 0, 255);
  for (uint8_t i = 0; i < p.repeat; i++) {
    analogWrite(VIBRATION_PIN, pwm);
    delay(p.durationMs);
    analogWrite(VIBRATION_PIN, 0);
    if (i + 1 < p.repeat && p.intervalMs > 0) delay(p.intervalMs);
  }
}

void drawScaledBitmap(int16_t x, int16_t y, const uint8_t *bmp, int16_t w, int16_t h, uint8_t s) {
  int16_t bw = (w + 7) / 8;
  uint8_t b = 0;
  for (int16_t j = 0; j < h; j++) {
    for (int16_t i = 0; i < w; i++) {
      if (i & 7) b <<= 1;
      else b = pgm_read_byte(&bmp[j * bw + i / 8]);
      if (b & 0x80) display.fillRect(x + i * s, y + j * s, s, s, SSD1306_WHITE);
    }
  }
}

void drawJelly() {
  display.clearDisplay();
  // 原图 26x23，放大 3 倍为 78x69；略微裁切上下边缘，让水母尽量占满屏幕。
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
    // PRD: conflict，2 次间隔提示，duration=100ms，interval=250ms，intensity=55。
    playVibration(VIB_CONFLICT);
  } else {
    // PRD: positive_low，1 次轻短振，duration=80ms，intensity=25。
    playVibration(VIB_POSITIVE_LOW);
  }
  Serial.print(F("SHOW:"));
  Serial.println(currentState);
  BLESerial.print(F("SHOW:"));
  BLESerial.println(currentState);
}

void handleCommand(String raw) {
  raw.trim();
  raw.toUpperCase();
  if (raw.startsWith("T:")) raw = raw.substring(2);

  if (raw == "1" || raw == "M1" || raw == "NL") {
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
        (buf.length() >= 4 && buf.startsWith("T:"))) {
      handleCommand(buf);
      buf = "";
    }
  }
}

void setup() {
  Serial.begin(9600);
  BLESerial.begin(9600);
  pinMode(VIBRATION_PIN, OUTPUT);
  analogWrite(VIBRATION_PIN, 0);
  Wire.begin();
  readSensors();

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
    sendSensorBLE();
    printSensorUSB();
  }

  if (!textMode && millis() - lastCommandMs > JELLY_MS) {
    textMode = true;
    drawText();
  }
}
