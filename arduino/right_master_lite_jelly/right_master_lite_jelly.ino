/*
  right_master_lite_jelly.ino
  第二版汇总 - 右手主控轻量水母版

  基于 right_master_lite 增加 OLED 水母图像。
  仍然不加入 RadioHead/315M，先保证右手主链路稳定。

  功能：
  - HC-05 蓝牙 D2/D3 接收 A/S/C。
  - USB 串口也可发送 A/S/C 测试。
  - OLED 显示水母表情。
  - 马达按 A/S/C 反馈。
  - 右手传感器通过蓝牙回传，供手语识别采集。
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

char currentEmotion = 'C';
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

// 26x23 jellyfish bitmaps, stored in Flash/PROGMEM, not SRAM.
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

bool isEmotionCmd(char c) {
  return c == 'A' || c == 'C' || c == 'S';
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

  // Large jellyfish view. Scale 2 keeps full 26x23 bitmap visible on 128x64.
  uint8_t scale = 2;
  int x = (128 - 26 * scale) / 2;
  int y = 0;

  if (currentEmotion == 'A') {
    drawScaledBitmap(x, y, jelly_angry, 26, 23, scale);
  } else if (currentEmotion == 'S') {
    drawScaledBitmap(x, y, jelly_sad, 26, 23, scale);
  } else {
    drawScaledBitmap(x, y, jelly_happy, 26, 23, scale);
  }

  // Small status bar at bottom.
  display.setTextSize(1);
  display.setCursor(0, 55);
  display.print(F("Mode:"));
  display.print(currentEmotion);
  display.print(F(" T:"));
  display.print(thumbVal);
  display.print(F(" I:"));
  display.print(indexVal);

  display.display();
}

void triggerEmotion(char cmd) {
  currentEmotion = cmd;
  isVibrating = true;
  vibrationStartMs = millis();
  sadState = 0;
  sadPWM = 0;

  Serial.print(F("Emotion command: "));
  Serial.println(cmd);
  BTSerial.print(F("CMD_OK:"));
  BTSerial.println(cmd);

  updateOLED();
}

void handleBluetooth() {
  while (BTSerial.available() > 0) {
    char c = BTSerial.read();
    if (isEmotionCmd(c)) triggerEmotion(c);
  }
}

void handleUSBSerial() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (isEmotionCmd(c)) triggerEmotion(c);
  }
}

void handleMotor() {
  unsigned long now = millis();

  if (!isVibrating || now - vibrationStartMs >= VIB_DURATION_MS) {
    isVibrating = false;
    analogWrite(MOTOR_PIN, 0);
    return;
  }

  if (currentEmotion == 'A') {
    int phase = now % 180;
    analogWrite(MOTOR_PIN, phase < 120 ? 255 : 0);
  } else if (currentEmotion == 'S') {
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
  } else {
    float phase = (now % 4000) / 4000.0 * 2.0 * PI;
    int calmPWM = 110 + (int)(sin(phase) * 30.0);
    analogWrite(MOTOR_PIN, calmPWM);
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

  Serial.println(F("Right master lite jelly booting..."));

  digitalWrite(MOTOR_PIN, HIGH);
  delay(300);
  digitalWrite(MOTOR_PIN, LOW);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println(F("OLED FAILED"));
    for (;;);
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(F("Right Lite Jelly"));
  display.println(F("OLED OK"));
  display.display();
  delay(800);

  initMPU();
  readSensors();
  updateOLED();

  BTSerial.println(F("RIGHT_LITE_JELLY_READY"));
  Serial.println(F("Right lite jelly ready. Send A/S/C by USB or Bluetooth."));
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
