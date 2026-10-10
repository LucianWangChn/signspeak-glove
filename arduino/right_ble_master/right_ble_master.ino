/*
  right_ble_master.ino
  第二版汇总 - 右手 BLE 主控

  硬件：
  - Arduino Nano + BLE 透传模块（JDY-23/HM-10/AT-09 等）
  - BLE 模块 TX -> Nano D2 (SoftwareSerial RX)
  - BLE 模块 RX -> Nano D3 (SoftwareSerial TX)
  - 五指电位器: A0/A1/A2/A3/A6
  - MPU6050: SDA=A4, SCL=A5
  - OLED SSD1306: I2C 0x3C
  - 振动马达: D5
  - 315M 接收: D4 (可选，接收左手数据)

  BLE 模块配置（通过 AT 指令预设，不在代码里配置）：
  - 角色：从机 (Peripheral)
  - 透传模式：连接后串口数据双向透传
  - 设备名：RIGHT_GLOVE
  - UUID：0000ffe1-0000-1000-8000-00805f9b34fb

  电脑端通过 bleak/BleakClient 连接后：
  1. 向 ffe1 写入命令字节 (A/S/C/F/U 或 PH/PL/NH/NL/CF/UK/NT)
  2. 从 ffe1 读取传感器数据 (Thumb:xxx, Index:xxx, ...)
  3. 从 ffe1 读取左手转发数据 (L:Thumb:xxx, ...)

  数据格式：
  右手传感器：R:Thumb:xxx,Index:xxx,Middle:xxx,Ring:xxx,Pinky:xxx,aX:xxx,aY:xxx,gZ:xxx
  左手传感器：L:Thumb:xxx,Index:xxx,Middle:xxx,Ring:xxx,Pinky:xxx,aX:xxx,aY:xxx,gZ:xxx
  情绪确认：  CMD_OK:PH

  前缀 R: / L: 用于 Python 端区分左右手数据。
*/

#include <SoftwareSerial.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_ADDR 0x3C
#define MPU_ADDR 0x68

#define BLE_RX_PIN 2
#define BLE_TX_PIN 3
#define MOTOR_PIN 5
#define RADIO_RX_PIN 4

const int potPins[5] = {A0, A1, A2, A3, A6};

SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// --- PRD Zones ---
enum FeedbackZone {
  Z_POS_HIGH, Z_POS_LOW, Z_NEG_HIGH, Z_NEG_LOW, Z_CONFLICT, Z_UNKNOWN, Z_NEUTRAL
};

FeedbackZone currentZone = Z_NEUTRAL;
bool isVibrating = false;
unsigned long vibrationStartMs = 0;
unsigned long lastSensorMs = 0;
unsigned long lastOledMs = 0;
unsigned long prevMotorMs = 0;

const unsigned long VIB_DURATION_MS = 3000;
const unsigned long SENSOR_INTERVAL_MS = 200;   // 5Hz, 减少 BLE 带宽压力
const unsigned long OLED_INTERVAL_MS = 300;

int thumbVal = 0, indexVal = 0, middleVal = 0, ringVal = 0, pinkyVal = 0;
int16_t ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;

// 左手缓存（315M 接收）
int lThumb = 0, lIndex = 0, lMiddle = 0, lRing = 0, lPinky = 0;
int16_t lAx = 0, lAy = 0, lGz = 0;
bool leftDataValid = false;
unsigned long leftDataTime = 0;

int sadPWM = 0, sadState = 0;

// 315M 接收缓冲
#define RADIO_BUF_LEN 40
char radioBuf[RADIO_BUF_LEN];
byte radioIdx = 0;

// --- 水母 bitmap PROGMEM ---
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
  switch(z) {
    case Z_POS_HIGH: return "PH"; case Z_POS_LOW: return "PL";
    case Z_NEG_HIGH: return "NH"; case Z_NEG_LOW: return "NL";
    case Z_CONFLICT: return "CF"; case Z_UNKNOWN: return "UK";
    default: return "NT";
  }
}

void drawScaledBitmap(int16_t x, int16_t y, const uint8_t *bmp, int16_t w, int16_t h, uint8_t s) {
  int16_t bw = (w + 7) / 8; uint8_t b = 0;
  for (int16_t j = 0; j < h; j++)
    for (int16_t i = 0; i < w; i++) {
      if (i & 7) b <<= 1; else b = pgm_read_byte(&bmp[j * bw + i / 8]);
      if (b & 0x80) display.fillRect(x + i * s, y + j * s, s, s, SSD1306_WHITE);
    }
}

void readSensors() {
  thumbVal = analogRead(potPins[0]); indexVal = analogRead(potPins[1]);
  middleVal = analogRead(potPins[2]); ringVal = analogRead(potPins[3]); pinkyVal = analogRead(potPins[4]);
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B);
  if (Wire.endTransmission(false) == 0) {
    Wire.requestFrom(MPU_ADDR, 14, true);
    if (Wire.available() >= 14) {
      ax=Wire.read()<<8|Wire.read(); ay=Wire.read()<<8|Wire.read(); az=Wire.read()<<8|Wire.read();
      Wire.read(); Wire.read();
      gx=Wire.read()<<8|Wire.read(); gy=Wire.read()<<8|Wire.read(); gz=Wire.read()<<8|Wire.read();
    }
  }
}

void sendSensorBLE() {
  BLESerial.print(F("R:Thumb:")); BLESerial.print(thumbVal);
  BLESerial.print(F(",Index:")); BLESerial.print(indexVal);
  BLESerial.print(F(",Middle:")); BLESerial.print(middleVal);
  BLESerial.print(F(",Ring:")); BLESerial.print(ringVal);
  BLESerial.print(F(",Pinky:")); BLESerial.print(pinkyVal);
  BLESerial.print(F(",aX:")); BLESerial.print(ax/100);
  BLESerial.print(F(",aY:")); BLESerial.print(ay/100);
  BLESerial.print(F(",gZ:")); BLESerial.println(gz/100);
}

void sendLeftSensorBLE() {
  if (!leftDataValid || millis() - leftDataTime > 1000) { leftDataValid = false; return; }
  BLESerial.print(F("L:Thumb:")); BLESerial.print(lThumb);
  BLESerial.print(F(",Index:")); BLESerial.print(lIndex);
  BLESerial.print(F(",Middle:")); BLESerial.print(lMiddle);
  BLESerial.print(F(",Ring:")); BLESerial.print(lRing);
  BLESerial.print(F(",Pinky:")); BLESerial.print(lPinky);
  BLESerial.print(F(",aX:")); BLESerial.print(lAx);
  BLESerial.print(F(",aY:")); BLESerial.print(lAy);
  BLESerial.print(F(",gZ:")); BLESerial.println(lGz);
}

void updateOLED() {
  display.clearDisplay(); display.setTextColor(SSD1306_WHITE);
  uint8_t sc = 2; int x = (128 - 26*sc)/2; int y = 0;
  if (currentZone == Z_CONFLICT) {
    drawScaledBitmap(x,y,jelly_happy,26,23,sc);
    display.drawRect(36,4,56,48,SSD1306_WHITE);
    display.drawLine(36,4,92,52,SSD1306_WHITE); display.drawLine(92,4,36,52,SSD1306_WHITE);
  } else if (currentZone == Z_UNKNOWN) {
    display.setTextSize(4); display.setCursor(50,8); display.print(F("?"));
  } else if (currentZone == Z_NEG_HIGH) {
    drawScaledBitmap(x,y,jelly_angry,26,23,sc);
    display.setTextSize(2); display.setCursor(100,4); display.print(F("!"));
  } else if (currentZone == Z_NEG_LOW) {
    drawScaledBitmap(x,y,jelly_sad,26,23,sc);
  } else {
    drawScaledBitmap(x,y,jelly_happy,26,23,sc);
  }
  display.setTextSize(1); display.setCursor(0,55);
  display.print(zoneCode(currentZone)); display.print(F(" "));
  display.print(thumbVal); display.print(F(" ")); display.print(indexVal);
  display.display();
}

void triggerZone(FeedbackZone z) {
  currentZone = z; isVibrating = true; vibrationStartMs = millis();
  sadState = 0; sadPWM = 0;
  Serial.print(F("Zone:")); Serial.println(zoneCode(z));
  BLESerial.print(F("CMD_OK:")); BLESerial.println(zoneCode(z));
  updateOLED();
}

// 逐字节解析命令，避免 String 分配
void parseBLE() {
  while (BLESerial.available() > 0) {
    char c = toupper((char)BLESerial.read());
    if (c == 'A') triggerZone(Z_NEG_HIGH);
    else if (c == 'S') triggerZone(Z_NEG_LOW);
    else if (c == 'C') triggerZone(Z_NEUTRAL);
    else if (c == 'F') triggerZone(Z_CONFLICT);
    else if (c == 'U') triggerZone(Z_UNKNOWN);
    // 双字母命令：P 开头
    else if (c == 'P') {
      delay(5); // 等第二个字节
      if (BLESerial.available()) {
        char c2 = toupper((char)BLESerial.read());
        if (c2 == 'H') triggerZone(Z_POS_HIGH);
        else if (c2 == 'L') triggerZone(Z_POS_LOW);
      }
    }
    else if (c == 'N') {
      delay(5);
      if (BLESerial.available()) {
        char c2 = toupper((char)BLESerial.read());
        if (c2 == 'H') triggerZone(Z_NEG_HIGH);
        else if (c2 == 'L') triggerZone(Z_NEG_LOW);
      }
    }
    else if (c == 'C') {
      delay(5);
      if (BLESerial.available()) {
        char c2 = toupper((char)BLESerial.read());
        if (c2 == 'F') triggerZone(Z_CONFLICT);
        else triggerZone(Z_NEUTRAL);
      }
    }
  }
}

void parseUSB() {
  while (Serial.available() > 0) {
    char c = toupper((char)Serial.read());
    if (c == 'A') triggerZone(Z_NEG_HIGH);
    else if (c == 'S') triggerZone(Z_NEG_LOW);
    else if (c == 'C') triggerZone(Z_NEUTRAL);
    else if (c == 'F') triggerZone(Z_CONFLICT);
  }
}

void handleMotor() {
  unsigned long now = millis();
  if (!isVibrating || now - vibrationStartMs >= VIB_DURATION_MS) {
    isVibrating = false; analogWrite(MOTOR_PIN, 0); return;
  }
  switch (currentZone) {
    case Z_NEG_HIGH: { int p = now%180; analogWrite(MOTOR_PIN, p<120?255:0); break; }
    case Z_NEG_LOW: {
      if (now-prevMotorMs>=30) { prevMotorMs=now;
        if (sadState==0){sadPWM=180;sadState=1;} else if(sadState==1){sadPWM-=3;if(sadPWM<=80){sadPWM=0;sadState=2;}}
        else{static int wc=0;wc++;if(wc>40){wc=0;sadState=0;}} analogWrite(MOTOR_PIN,sadPWM); } break; }
    case Z_POS_HIGH: { int p=now%240; analogWrite(MOTOR_PIN,p<100?115:0); break; }
    case Z_POS_LOW: { int p=now%400; analogWrite(MOTOR_PIN,p<80?64:0); break; }
    case Z_CONFLICT: { int p=now%500; analogWrite(MOTOR_PIN,p<100?140:0); break; }
    case Z_UNKNOWN: { analogWrite(MOTOR_PIN,51); break; }
    default: { float ph=(now%4000)/4000.0*2.0*PI; analogWrite(MOTOR_PIN,110+(int)(sin(ph)*30)); break; }
  }
}

// 315M 左手数据接收（简单串行协议）
void pollRadio() {
  while (digitalRead(RADIO_RX_PIN) == HIGH && radioIdx < RADIO_BUF_LEN - 1) {
    // 简单方式：直接读 D4 上的 315M 信号
    // 实际应使用 RadioHead 库，这里预留接口
    // 如果不使用 315M，此函数不执行任何操作
    break;
  }
}

void initMPU() {
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x6B); Wire.write(0);
  if (Wire.endTransmission(true) == 0) Serial.println(F("MPU6050 OK"));
  else Serial.println(F("MPU6050 FAILED"));
}

void setup() {
  Serial.begin(9600); BLESerial.begin(9600);
  pinMode(MOTOR_PIN, OUTPUT); analogWrite(MOTOR_PIN, 0);
  pinMode(RADIO_RX_PIN, INPUT);

  Serial.println(F("Right BLE master booting..."));

  digitalWrite(MOTOR_PIN, HIGH); delay(200); digitalWrite(MOTOR_PIN, LOW);

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) { Serial.println(F("OLED FAILED")); for(;;); }
  display.clearDisplay(); display.setTextSize(1); display.setTextColor(SSD1306_WHITE);
  display.setCursor(0,0); display.println(F("Right BLE Master")); display.println(F("OLED OK"));
  display.display(); delay(600);

  initMPU(); readSensors(); updateOLED();
  BLESerial.println(F("RIGHT_BLE_READY"));
  Serial.println(F("Right BLE ready."));
}

void loop() {
  unsigned long now = millis();
  parseBLE(); parseUSB(); handleMotor();

  if (now - lastSensorMs >= SENSOR_INTERVAL_MS) {
    lastSensorMs = now; readSensors(); sendSensorBLE(); sendLeftSensorBLE();
  }
  if (now - lastOledMs >= OLED_INTERVAL_MS) { lastOledMs = now; updateOLED(); }
}
