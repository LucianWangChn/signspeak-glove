/*
  right_master_lite.ino
  第二版汇总 - 右手主控轻量稳定版

  目标：先保证右手主链路稳定运行。

  功能：
  1. HC-05 蓝牙接收电脑/v3 发来的 A/C/S 情绪指令。
  2. OLED 显示当前情绪和传感器状态。
  3. 振动马达按 A/S/C 执行不同反馈。
  4. 读取右手五指电位器和 MPU6050。
  5. 通过蓝牙回传手语识别需要的数据。

  暂时不包含：
  - RadioHead / 315M 左手接收
  - 水母 bitmap 表情

  原因：Arduino Nano SRAM 只有 2KB，SSD1306 128x64 显示缓存约占 1024B。
  同时加入 RadioHead、SoftwareSerial、bitmap 后容易导致 OLED 初始化失败。

  接线：
  - HC-05 TXD -> Nano D2  (SoftwareSerial RX)
  - HC-05 RXD -> Nano D3  (SoftwareSerial TX)
  - 振动马达信号 -> D5
  - Thumb  -> A0
  - Index  -> A1
  - Middle -> A2
  - Ring   -> A3
  - Pinky  -> A6
  - OLED + MPU6050: SDA=A4, SCL=A5
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
const unsigned long OLED_REFRESH_INTERVAL_MS = 250;

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

bool isEmotionCmd(char c) {
  return c == 'A' || c == 'C' || c == 'S';
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
  // 这个格式兼容手语识别采集脚本 serial_gesture_collector.py
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

  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println(F("Right Master Lite"));

  display.setTextSize(2);
  display.setCursor(0, 14);
  display.print(F("Mode:"));
  display.println(currentEmotion);

  display.setTextSize(1);
  display.setCursor(0, 36);
  display.print(F("T:")); display.print(thumbVal);
  display.print(F(" I:")); display.println(indexVal);
  display.print(F("M:")); display.print(middleVal);
  display.print(F(" R:")); display.println(ringVal);
  display.print(F("aY:")); display.print(ay / 100);
  display.print(F(" gZ:")); display.println(gz / 100);

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
    if (isEmotionCmd(c)) {
      triggerEmotion(c);
    }
  }
}

void handleUSBSerial() {
  // 也允许从 USB 串口监视器直接发 A/S/C 测试
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (isEmotionCmd(c)) {
      triggerEmotion(c);
    }
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
    // 急躁/愤怒：强烈脉冲
    int phase = now % 180;
    if (phase < 120) analogWrite(MOTOR_PIN, 255);
    else analogWrite(MOTOR_PIN, 0);
  } else if (currentEmotion == 'S') {
    // 悲伤：衰减叹息
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
    // 平静：轻柔呼吸
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

  Serial.println(F("Right master lite booting..."));

  // 马达自检，方便确认供电和引脚
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
  display.println(F("Right Master Lite"));
  display.println(F("OLED OK"));
  display.display();
  delay(800);

  initMPU();
  readSensors();
  updateOLED();

  BTSerial.println(F("RIGHT_MASTER_LITE_READY"));
  Serial.println(F("Right master lite ready. Send A/S/C by USB or Bluetooth."));
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
