/*
  oled_story_jelly_sentence_demo.ino
  视频剧本 OLED：先显示水母，再显示完整句子页

  特点：
  1. display.setRotation(2)，适配屏幕装反。
  2. USB 串口和 BLE 都可控制。
  3. 支持两种蓝牙输入：
     - 透传串口模块 D2/D3：TW / TA / TP ...
     - BLE 连接不稳定时，也可用 USB 串口先拍。
  4. 命令触发后先显示水母 + 状态，再自动切换到完整句子页。

  命令：
  TW = 妈妈担忧 -> 妈妈有些担忧
  TS = 焦虑犹豫 -> 妈妈焦虑犹豫
  TA = 妈妈安心 -> 妈妈安心接受
  TP = 住院交费 -> 医生建议住院现在 / 去交费可以吗
  TB = 陪你一起 -> 钱不用担心我已 / 请好假陪您一起
  TG = 去办手续 -> 走办手续去
  TC = 平静沟通 -> 保持平静沟通
*/

#include <SoftwareSerial.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "oled_story_words.h"
#include "oled_story_sentences.h"

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDR 0x3C

#define BLE_RX_PIN 2
#define BLE_TX_PIN 3

SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

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
bool sentenceMode = false;
unsigned long lastCommandMs = 0;
const unsigned long JELLY_MS = 1500;

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

void drawJellyState(const String &cmd) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  drawScaledBitmap(6, 8, jellyBitmap(cmd), 26, 23, 2);
  display.drawBitmap(60, 12, phraseBitmap(cmd), 64, 16, SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(62, 34);
  display.print(englishHint(cmd));
  display.setCursor(62, 50);
  display.print(cmd);
  display.display();
}

void drawSentencePage1(const String &cmd) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print(cmd);
  display.print(F(" STORY"));

  if (cmd == "TP") {
    display.drawBitmap(0, 16, SENT_PAY_1, 128, 32, SSD1306_WHITE);
  } else if (cmd == "TB") {
    display.drawBitmap(0, 16, SENT_WITH_1, 128, 32, SSD1306_WHITE);
  } else if (cmd == "TG") {
    display.drawBitmap(0, 16, SENT_GO_1, 128, 32, SSD1306_WHITE);
  } else if (cmd == "TW") {
    display.drawBitmap(0, 16, SENT_WORRY_1, 128, 32, SSD1306_WHITE);
  } else if (cmd == "TS") {
    display.drawBitmap(0, 16, SENT_ANXIETY_1, 128, 32, SSD1306_WHITE);
  } else if (cmd == "TA" || cmd == "TO" || cmd == "TR") {
    display.drawBitmap(0, 16, SENT_RELIEF_1, 128, 32, SSD1306_WHITE);
  } else {
    display.drawBitmap(0, 16, SENT_CALM_1, 128, 32, SSD1306_WHITE);
  }

  display.setCursor(0, 56);
  display.print(F("NEXT: same cmd again"));
  display.display();
}

void drawSentencePage2(const String &cmd) {
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.print(cmd);
  display.print(F(" STORY 2"));

  if (cmd == "TP") {
    display.drawBitmap(0, 16, SENT_PAY_2, 128, 32, SSD1306_WHITE);
  } else if (cmd == "TB") {
    display.drawBitmap(0, 16, SENT_WITH_2, 128, 32, SSD1306_WHITE);
  } else {
    drawSentencePage1(cmd);
    return;
  }

  display.setCursor(0, 56);
  display.print(F("DONE"));
  display.display();
}

bool isKnownCmd(const String &cmd) {
  return cmd == "TW" || cmd == "TS" || cmd == "TA" || cmd == "TR" ||
         cmd == "TP" || cmd == "TB" || cmd == "TG" || cmd == "TC" || cmd == "TO" ||
         cmd == "P1" || cmd == "P2" || cmd == "B1" || cmd == "B2";
}

void handleCommand(String cmd, const char* source) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd.startsWith("T:")) cmd = cmd.substring(2);
  if (cmd == "NL") cmd = "TW";
  else if (cmd == "NH") cmd = "TS";
  else if (cmd == "PL") cmd = "TA";
  else if (cmd == "NT") cmd = "TC";

  if (cmd == "P1") { currentCmd = "TP"; sentenceMode = true; drawSentencePage1(currentCmd); return; }
  if (cmd == "P2") { currentCmd = "TP"; sentenceMode = true; drawSentencePage2(currentCmd); return; }
  if (cmd == "B1") { currentCmd = "TB"; sentenceMode = true; drawSentencePage1(currentCmd); return; }
  if (cmd == "B2") { currentCmd = "TB"; sentenceMode = true; drawSentencePage2(currentCmd); return; }

  if (!isKnownCmd(cmd)) {
    Serial.print(F("UNKNOWN "));
    Serial.print(source);
    Serial.print(F(":"));
    Serial.println(cmd);
    return;
  }

  currentCmd = cmd;
  sentenceMode = false;
  lastCommandMs = millis();
  drawJellyState(currentCmd);
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
    if (c == '\r' || c == '\n' || c == ' ' || c == '\t') {
      if (buf.length() > 0) { handleCommand(buf, source); buf = ""; }
      continue;
    }
    c = toupper(c);
    if (c == ':') { if (buf == "T") buf += c; continue; }
    if (buf.length() < 20) buf += c;
    if (buf.length() == 2 && buf != "T:") { handleCommand(buf, source); buf = ""; continue; }
    if (buf.length() >= 4 && buf.startsWith("T:")) { handleCommand(buf, source); buf = ""; continue; }
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

  display.setRotation(2);
  Serial.println(F("OLED story sentence demo ready"));
  Serial.println(F("Commands: TW TS TA TR TP TB TG TC P1 P2 B1 B2"));
  BLESerial.println(F("OLED_SENTENCE_READY"));
  drawJellyState(currentCmd);
  lastCommandMs = millis();
}

void loop() {
  readStream(Serial, inputUsb, "USB");
  readStream(BLESerial, inputBle, "BLE");

  // 先显示水母 1.5 秒，再自动切换到句子第一页。
  if (!sentenceMode && millis() - lastCommandMs > JELLY_MS) {
    sentenceMode = true;
    drawSentencePage1(currentCmd);
  }
}
