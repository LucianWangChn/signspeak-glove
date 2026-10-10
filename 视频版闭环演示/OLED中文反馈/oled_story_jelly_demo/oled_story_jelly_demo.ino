/*
  oled_story_jelly_demo.ino
  视频剧本 OLED 中文 + 水母图案演示

  特点：
  1. OLED 上下翻转：display.setRotation(2)，适配屏幕装反。
  2. 支持串口切换：在 Arduino 串口监视器输入 TW/TS/TA/TR/TP/TB/TG/TC。
  3. 支持 BLE 透传切换：BLE 模块接 D2/D3，电脑发同样指令即可。
  4. 配合水母图案：负面显示 sad/angry，正面显示 happy。
  5. 中文不是完整字库，而是固定点阵，需同目录 oled_story_words.h。

  指令：
  TW = 妈妈担忧 + sad jelly
  TS = 焦虑犹豫 + angry jelly
  TA = 妈妈安心 + happy jelly
  TR = 放松接受 + happy jelly
  TP = 住院交费 + happy jelly
  TB = 陪你一起 + happy jelly
  TG = 去办手续 + happy jelly
  TC = 平静沟通 + happy jelly
*/

#include <SoftwareSerial.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "oled_story_words.h"

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDR 0x3C

#define BLE_RX_PIN 2
#define BLE_TX_PIN 3

SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// 26x23 jelly bitmaps from previous stable demo
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

String currentCmd = "TC";
String inputUsb = "";
String inputBle = "";

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

const unsigned char* phraseBitmap(const String &cmd) {
  if (cmd == "TW") return TXT_MOM_WORRY;
  if (cmd == "TS") return TXT_ANXIETY;
  if (cmd == "TA") return TXT_RELIEF;
  if (cmd == "TR") return TXT_RELAX;
  if (cmd == "TP") return TXT_PAY;
  if (cmd == "TB") return TXT_ACCOMPANY;
  if (cmd == "TG") return TXT_PAPERWORK;
  return TXT_CALM;
}

const uint8_t* jellyBitmap(const String &cmd) {
  if (cmd == "TW") return jelly_sad;
  if (cmd == "TS") return jelly_angry;
  return jelly_happy;
}

const char* englishHint(const String &cmd) {
  if (cmd == "TW") return "WORRY";
  if (cmd == "TS") return "ANXIETY";
  if (cmd == "TA") return "RELIEF";
  if (cmd == "TR") return "RELAX";
  if (cmd == "TP") return "PAYMENT";
  if (cmd == "TB") return "WITH YOU";
  if (cmd == "TG") return "PAPERWORK";
  if (cmd == "TO") return "ACCEPT";
  return "CALM";
}

void renderScreen(const String &cmd) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);

  // 左侧水母，右侧中文短语。
  drawScaledBitmap(6, 8, jellyBitmap(cmd), 26, 23, 2);
  display.drawBitmap(60, 12, phraseBitmap(cmd), 64, 16, SSD1306_WHITE);

  display.setTextSize(1);
  display.setCursor(62, 34);
  display.print(englishHint(cmd));
  display.setCursor(62, 50);
  display.print(cmd);

  display.display();
}

bool isKnownCmd(const String &cmd) {
  return cmd == "TW" || cmd == "TS" || cmd == "TA" || cmd == "TR" ||
         cmd == "TP" || cmd == "TB" || cmd == "TG" || cmd == "TC" || cmd == "TO";
}

void handleCommand(String cmd, const char* source) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd.startsWith("T:")) cmd = cmd.substring(2);
  if (cmd == "NL") cmd = "TW";
  else if (cmd == "NH") cmd = "TS";
  else if (cmd == "PL") cmd = "TA";
  else if (cmd == "NT") cmd = "TC";

  if (!isKnownCmd(cmd)) {
    Serial.print(F("UNKNOWN "));
    Serial.print(source);
    Serial.print(F(":"));
    Serial.println(cmd);
    return;
  }
  currentCmd = cmd;
  renderScreen(currentCmd);
  Serial.print(F("SHOW "));
  Serial.print(source);
  Serial.print(F(":"));
  Serial.println(currentCmd);
  BLESerial.print(F("SHOW:"));
  BLESerial.println(currentCmd);
}

void readStream(Stream &s, String &buf, const char* source) {
  while (s.available()) {
    char c = (char)s.read();

    // 换行/空格：如果缓冲区里已有内容，就处理一次。
    if (c == '\r' || c == '\n' || c == ' ' || c == '\t') {
      if (buf.length() > 0) {
        handleCommand(buf, source);
        buf = "";
      }
      continue;
    }

    c = toupper(c);

    // 支持旧格式 T:TW / T:TA；遇到冒号先保留，等完整 4 字符或换行。
    if (c == ':') {
      if (buf == "T") buf += c;
      continue;
    }

    if (buf.length() < 20) buf += c;

    // 关键修复：普通两字符命令立即执行，不再依赖串口监视器的换行设置。
    // 例如串口/BLE 只发送 TW、TA、TP，也能马上切换 OLED。
    if (buf.length() == 2 && buf != "T:") {
      handleCommand(buf, source);
      buf = "";
      continue;
    }

    // 兼容 T:TW 这种 4 字符格式，也立即执行。
    if (buf.length() >= 4 && buf.startsWith("T:")) {
      handleCommand(buf, source);
      buf = "";
      continue;
    }
  }
}

void setup() {
  Serial.begin(9600);
  BLESerial.begin(9600);
  Wire.begin();

  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println(F("OLED failed"));
    while (1) delay(100);
  }

  // 屏幕装反：整体旋转 180 度。
  display.setRotation(2);

  Serial.println(F("OLED story jelly demo ready"));
  Serial.println(F("Commands: TW TS TA TR TP TB TG TC"));
  BLESerial.println(F("OLED_STORY_READY"));
  renderScreen(currentCmd);
}

void loop() {
  readStream(Serial, inputUsb, "USB");
  readStream(BLESerial, inputBle, "BLE");
}
