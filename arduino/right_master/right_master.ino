/*
  right_master.ino
  第二版汇总 - 右手主控程序

  Hardware role:
  - Right hand is the master hand.
  - HC-05 Bluetooth is connected to the right hand.
  - PC/v3 sends emotion command A/C/S through Bluetooth.
  - Right hand controls OLED and vibration motor locally.
  - Right hand reports its own sensor data to PC through Bluetooth for sign-language collection.
  - Right hand optionally receives left-hand auxiliary data from 315M RX on D4.

  Wiring:
  - HC-05 TXD -> Nano D2  (SoftwareSerial RX)
  - HC-05 RXD -> Nano D3  (SoftwareSerial TX)
  - 315M RX DATA -> Nano D4
  - Vibration motor signal -> D5
  - Fingers: Thumb=A0, Index=A1, Middle=A2, Ring=A3, Pinky=A6
  - OLED + MPU6050 I2C: SDA=A4, SCL=A5

  Required libraries:
  - SoftwareSerial
  - Wire
  - SPI
  - RadioHead: RH_ASK
  - Adafruit_GFX
  - Adafruit_SSD1306
*/

#include <SoftwareSerial.h>
#include <Wire.h>
#include <SPI.h>
#include <RH_ASK.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ========================= Pin and peripheral config =========================
#define BT_RX_PIN 2   // Nano RX, connected to HC-05 TXD
#define BT_TX_PIN 3   // Nano TX, connected to HC-05 RXD
#define RF_RX_PIN 4   // 315M receiver DATA
#define MOTOR_PIN 5

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_ADDR 0x3C
#define MPU_ADDR 0x68

const uint8_t fingerPins[5] = {A0, A1, A2, A3, A6};

SoftwareSerial BTSerial(BT_RX_PIN, BT_TX_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// RH_ASK(speed, rxPin, txPin, pttPin). txPin/pttPin are unused placeholders here.
RH_ASK rfDriver(2000, RF_RX_PIN, 12, 10);

// ========================= Timing config =========================
const unsigned long SENSOR_REPORT_INTERVAL_MS = 100;  // 10Hz, compatible with sign_language_dl docs
const unsigned long LEFT_TIMEOUT_MS = 1500;
const unsigned long VIB_DURATION_MS = 3000;

unsigned long lastSensorReportMs = 0;
unsigned long lastLeftPacketMs = 0;

// ========================= Runtime state =========================
char currentEmotion = 'C';
bool isVibrating = false;
unsigned long vibrationStartMs = 0;
unsigned long prevMotorMs = 0;
int sadPWM = 0;
int sadState = 0;

struct SensorFrame {
  uint16_t thumb;
  uint16_t index;
  uint16_t middle;
  uint16_t ring;
  uint16_t pinky;
  int16_t ax;
  int16_t ay;
  int16_t az;
  int16_t gx;
  int16_t gy;
  int16_t gz;
};

struct __attribute__((packed)) LeftPacket {
  uint8_t magic;      // 'L'
  uint8_t seq;
  uint16_t thumb;
  uint16_t index;
  uint16_t middle;
  uint16_t ring;
  uint16_t pinky;
  int16_t ax;
  int16_t ay;
  int16_t gz;
  uint8_t checksum;
};

LeftPacket lastLeftPacket;
bool hasLeftPacket = false;

// ========================= 26x23 jellyfish bitmaps =========================
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

// ========================= Utility =========================
uint8_t calcChecksum(const uint8_t *data, uint8_t len) {
  uint8_t sum = 0;
  for (uint8_t i = 0; i < len; i++) sum ^= data[i];
  return sum;
}

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

void updateOLED() {
  display.clearDisplay();

  uint8_t scale = 2;
  int x = (128 - 26 * scale) / 2;
  int y = 0;

  switch (currentEmotion) {
    case 'A': drawScaledBitmap(x, y, jelly_angry, 26, 23, scale); break;
    case 'S': drawScaledBitmap(x, y, jelly_sad, 26, 23, scale); break;
    case 'C':
    default: drawScaledBitmap(x, y, jelly_happy, 26, 23, scale); break;
  }

  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 55);
  display.print(F("Mode:"));
  display.print(currentEmotion);
  display.print(F(" L:"));
  display.print((millis() - lastLeftPacketMs < LEFT_TIMEOUT_MS) ? F("OK") : F("--"));
  display.display();
}

void triggerEmotion(char cmd) {
  currentEmotion = cmd;
  isVibrating = true;
  vibrationStartMs = millis();
  sadState = 0;
  sadPWM = 0;
  updateOLED();

  Serial.print(F("Emotion command: "));
  Serial.println(cmd);
  BTSerial.print(F("CMD_OK:"));
  BTSerial.println(cmd);
}

void handleMotor() {
  unsigned long now = millis();

  if (!isVibrating || now - vibrationStartMs >= VIB_DURATION_MS) {
    isVibrating = false;
    analogWrite(MOTOR_PIN, 0);
    return;
  }

  if (currentEmotion == 'A') {
    int phase = now % 150;
    analogWrite(MOTOR_PIN, phase < 100 ? 255 : 0);
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
  } else { // C
    float phase = (now % 4000) / 4000.0 * 2.0 * PI;
    int calmPWM = 110 + (int)(sin(phase) * 30.0);
    analogWrite(MOTOR_PIN, calmPWM);
  }
}

bool readMPU(SensorFrame &frame) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t n = Wire.requestFrom(MPU_ADDR, 14, true);
  if (n < 14) return false;

  frame.ax = Wire.read() << 8 | Wire.read();
  frame.ay = Wire.read() << 8 | Wire.read();
  frame.az = Wire.read() << 8 | Wire.read();
  Wire.read(); Wire.read(); // temperature ignored
  frame.gx = Wire.read() << 8 | Wire.read();
  frame.gy = Wire.read() << 8 | Wire.read();
  frame.gz = Wire.read() << 8 | Wire.read();
  return true;
}

SensorFrame readRightSensors() {
  SensorFrame f;
  f.thumb = analogRead(fingerPins[0]);
  f.index = analogRead(fingerPins[1]);
  f.middle = analogRead(fingerPins[2]);
  f.ring = analogRead(fingerPins[3]);
  f.pinky = analogRead(fingerPins[4]);
  f.ax = f.ay = f.az = f.gx = f.gy = f.gz = 0;
  readMPU(f);
  return f;
}

void reportRightSensorsToPC() {
  SensorFrame f = readRightSensors();

  // Keep this exact format compatible with sign_language_dl/data_collector.py and predict.py.
  BTSerial.print(F("Thumb:")); BTSerial.print(f.thumb);
  BTSerial.print(F(", Index:")); BTSerial.print(f.index);
  BTSerial.print(F(", Middle:")); BTSerial.print(f.middle);
  BTSerial.print(F(", Ring:")); BTSerial.print(f.ring);
  BTSerial.print(F(", Pinky:")); BTSerial.print(f.pinky);
  BTSerial.print(F(", aX:")); BTSerial.print(f.ax / 100);
  BTSerial.print(F(", aY:")); BTSerial.print(f.ay / 100);
  BTSerial.print(F(", gZ:")); BTSerial.println(f.gz / 100);
}

void handleBluetooth() {
  while (BTSerial.available() > 0) {
    char cmd = BTSerial.read();
    if (isEmotionCmd(cmd)) triggerEmotion(cmd);
  }
}

void handleLeftRadio() {
  uint8_t buf[RH_ASK_MAX_MESSAGE_LEN];
  uint8_t buflen = sizeof(buf);

  if (rfDriver.recv(buf, &buflen)) {
    if (buflen == sizeof(LeftPacket)) {
      LeftPacket pkt;
      memcpy(&pkt, buf, sizeof(LeftPacket));
      uint8_t expected = calcChecksum((uint8_t *)&pkt, sizeof(LeftPacket) - 1);
      if (pkt.magic == 'L' && pkt.checksum == expected) {
        lastLeftPacket = pkt;
        hasLeftPacket = true;
        lastLeftPacketMs = millis();

        Serial.print(F("Left packet seq=")); Serial.print(pkt.seq);
        Serial.print(F(" Thumb=")); Serial.print(pkt.thumb);
        Serial.print(F(" Index=")); Serial.println(pkt.index);
      }
    }
  }
}

void initMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0);
  byte err = Wire.endTransmission(true);
  if (err == 0) {
    Serial.println(F("MPU6050 OK"));
  } else {
    Serial.println(F("MPU6050 warning: check I2C wiring"));
  }
}

void setup() {
  Serial.begin(9600);
  Wire.begin();
  pinMode(MOTOR_PIN, OUTPUT);
  analogWrite(MOTOR_PIN, 0);

  Serial.println(F("Right master booting..."));

  // Important on Arduino Nano: initialize OLED early and keep string literals in flash via F().
  // Adafruit_SSD1306 needs a 1024-byte SRAM buffer for 128x64 screens.
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println(F("OLED failed"));
  } else {
    updateOLED();
    Serial.println(F("OLED OK"));
  }

  initMPU();

  if (!rfDriver.init()) {
    Serial.println(F("RadioHead RX init failed"));
  } else {
    Serial.println(F("RadioHead RX ready on D4"));
  }

  BTSerial.begin(9600);
  BTSerial.println(F("RIGHT_MASTER_READY"));
  Serial.println(F("Right master ready. Bluetooth commands: A/C/S"));
}

void loop() {
  unsigned long now = millis();

  handleBluetooth();
  handleLeftRadio();
  handleMotor();

  if (now - lastSensorReportMs >= SENSOR_REPORT_INTERVAL_MS) {
    lastSensorReportMs = now;
    reportRightSensorsToPC();
  }
}
