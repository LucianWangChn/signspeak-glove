/* right_ble_315m_master_full.ino: right glove master with BLE + 315M + OLED/vibration */
#include <SoftwareSerial.h>
#include <Wire.h>
#include <SPI.h>
#include <RH_ASK.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "oled_mother_lines.h"
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_ADDR 0x3C
#define MPU_ADDR 0x68
#define BLE_RX_PIN 2
#define BLE_TX_PIN 3
#define RF_RX_PIN 4
#define VIBRATION_PIN 5
const unsigned long SENSOR_INTERVAL_MS=200,JELLY_MS=1400;
SoftwareSerial BLESerial(BLE_RX_PIN,BLE_TX_PIN);
RH_ASK rf(2000,RF_RX_PIN,13,10);
Adafruit_SSD1306 display(SCREEN_WIDTH,SCREEN_HEIGHT,&Wire,-1);
struct __attribute__((packed)) Packet{uint8_t magic,seq;uint16_t thumb,index,middle,ring,pinky;int16_t ax,ay,gz;uint8_t checksum;};
struct Vib{uint8_t repeat;uint16_t dur,interval;uint8_t intensity;};
const Vib VIB_POS={1,80,0,25},VIB_CONFLICT={2,100,250,55};
int rTh=0,rIn=0,rMi=0,rRi=0,rPi=0;int16_t rAx=0,rAy=0,rGz=0;Packet leftPkt;bool hasLeft=false;unsigned long lastLeftMs=0,lastSensorMs=0,lastCmdMs=0;String bufUsb="",bufBle="";int state=1;bool textMode=false;
static const unsigned char PROGMEM jelly_happy[]={0x00,0x3F,0x00,0x00,0x03,0xC0,0xF0,0x00,0x0C,0x00,0x0C,0x00,0x30,0x00,0x03,0x00,0x40,0x00,0x00,0x80,0x40,0x00,0x00,0x80,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x80,0x00,0x00,0x40,0x86,0x33,0x18,0x40,0x80,0x0C,0x00,0x40,0x80,0x00,0x00,0x40,0x87,0x0C,0x38,0x40,0x48,0x92,0x44,0x80,0x30,0x61,0x83,0x00,0x30,0x61,0x83,0x00,0x18,0xC0,0xC6,0x00,0x0C,0xC0,0xCC,0x00,0x19,0x80,0x66,0x00,0x30,0x00,0x03,0x00};
static const unsigned char PROGMEM jelly_sad[]={0x00,0x3F,0x00,0x00,0x03,0xC0,0xF0,0x00,0x0C,0x00,0x0C,0x00,0x30,0x00,0x03,0x00,0x41,0x80,0x60,0x80,0x46,0x00,0x18,0x80,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x81,0x80,0x60,0x40,0x80,0x00,0x00,0x40,0x86,0x0C,0x18,0x40,0x80,0x33,0x00,0x40,0x80,0x00,0x00,0x40,0x87,0x0C,0x38,0x40,0x48,0x92,0x44,0x80,0x30,0x61,0x83,0x00,0x30,0x61,0x83,0x00,0x18,0xC0,0xC6,0x00,0x0C,0xC0,0xCC,0x00,0x19,0x80,0x66,0x00,0x30,0x00,0x03,0x00};
uint8_t checksum(const uint8_t*d,uint8_t n){uint8_t s=0;for(uint8_t i=0;i<n;i++)s^=d[i];return s;}
void initMPU(){Wire.beginTransmission(MPU_ADDR);Wire.write(0x6B);Wire.write(0);Wire.endTransmission(true);} 
bool readMPU(int16_t &ax,int16_t &ay,int16_t &gz){Wire.beginTransmission(MPU_ADDR);Wire.write(0x3B);if(Wire.endTransmission(false)!=0)return false;uint8_t n=Wire.requestFrom(MPU_ADDR,14,true);if(n<14)return false;int16_t arx=(Wire.read()<<8)|Wire.read();int16_t ary=(Wire.read()<<8)|Wire.read();Wire.read();Wire.read();Wire.read();Wire.read();Wire.read();Wire.read();Wire.read();Wire.read();int16_t grz=(Wire.read()<<8)|Wire.read();ax=arx/100;ay=ary/100;gz=grz/100;return true;}
void readRight(){rTh=analogRead(A0);rIn=analogRead(A1);rMi=analogRead(A2);rRi=analogRead(A3);rPi=analogRead(A6);if(!readMPU(rAx,rAy,rGz)){rAx=0;rAy=0;rGz=0;}}
void sendLine(Stream&s,char h,uint16_t th,uint16_t ix,uint16_t mi,uint16_t ri,uint16_t pi,int16_t ax,int16_t ay,int16_t gz){s.print(h);s.print(F(":Thumb:"));s.print(th);s.print(F(",Index:"));s.print(ix);s.print(F(",Middle:"));s.print(mi);s.print(F(",Ring:"));s.print(ri);s.print(F(",Pinky:"));s.print(pi);s.print(F(",aX:"));s.print(ax);s.print(F(",aY:"));s.print(ay);s.print(F(",gZ:"));s.println(gz);} 
void sendSensors(){sendLine(BLESerial,'R',rTh,rIn,rMi,rRi,rPi,rAx,rAy,rGz);sendLine(Serial,'R',rTh,rIn,rMi,rRi,rPi,rAx,rAy,rGz);if(hasLeft&&millis()-lastLeftMs<1200){sendLine(BLESerial,'L',leftPkt.thumb,leftPkt.index,leftPkt.middle,leftPkt.ring,leftPkt.pinky,leftPkt.ax,leftPkt.ay,leftPkt.gz);sendLine(Serial,'L',leftPkt.thumb,leftPkt.index,leftPkt.middle,leftPkt.ring,leftPkt.pinky,leftPkt.ax,leftPkt.ay,leftPkt.gz);}}
void pollLeft(){uint8_t b[sizeof(Packet)],len=sizeof(b);if(rf.recv(b,&len)&&len==sizeof(Packet)){Packet p;memcpy(&p,b,sizeof(p));if(p.magic=='L'){uint8_t got=p.checksum;p.checksum=0;if(got==checksum((uint8_t*)&p,sizeof(Packet)-1)){p.checksum=got;leftPkt=p;hasLeft=true;lastLeftMs=millis();}}}}
void vib(const Vib&p){uint8_t pwm=map(p.intensity,0,100,0,255);for(uint8_t i=0;i<p.repeat;i++){analogWrite(VIBRATION_PIN,pwm);delay(p.dur);analogWrite(VIBRATION_PIN,0);if(i+1<p.repeat)delay(p.interval);}}
void drawScaled(int16_t x,int16_t y,const uint8_t*bmp,int16_t w,int16_t h,uint8_t sc){int16_t bw=(w+7)/8;uint8_t b=0;for(int16_t j=0;j<h;j++){for(int16_t i=0;i<w;i++){if(i&7)b<<=1;else b=pgm_read_byte(&bmp[j*bw+i/8]);if(b&0x80)display.fillRect(x+i*sc,y+j*sc,sc,sc,SSD1306_WHITE);}}}
void drawJelly(){display.clearDisplay();if(state==1)drawScaled(25,-2,jelly_sad,26,23,3);else drawScaled(25,-2,jelly_happy,26,23,3);display.display();}
void drawText(){display.clearDisplay();if(state==1)display.drawBitmap(0,0,MOM_LINE_1,128,64,SSD1306_WHITE);else display.drawBitmap(0,0,MOM_LINE_2,128,64,SSD1306_WHITE);display.display();}
void showState(int st){state=st;textMode=false;lastCmdMs=millis();drawJelly();if(st==1)vib(VIB_CONFLICT);else vib(VIB_POS);Serial.print(F("SHOW:"));Serial.println(st);BLESerial.print(F("SHOW:"));BLESerial.println(st);} 
void handle(String raw){raw.trim();raw.toUpperCase();if(raw.startsWith("T:"))raw=raw.substring(2);if(raw=="1"||raw=="M1"||raw=="CF"||raw=="NL")showState(1);else if(raw=="2"||raw=="M2"||raw=="PL")showState(2);} 
void readStream(Stream&s,String&buf){while(s.available()){char c=(char)s.read();if(c=='\r'||c=='\n'||c==' '||c=='\t'){if(buf.length()>0){handle(buf);buf="";}continue;}c=toupper(c);if(c==':'){if(buf=="T")buf+=c;continue;}if(buf.length()<8)buf+=c;if(buf=="1"||buf=="2"||buf=="M1"||buf=="M2"||buf=="CF"||buf=="NL"||buf=="PL"||(buf.length()>=4&&buf.startsWith("T:"))){handle(buf);buf="";}}}
void setup(){Serial.begin(9600);BLESerial.begin(9600);Wire.begin();pinMode(VIBRATION_PIN,OUTPUT);analogWrite(VIBRATION_PIN,0);initMPU();Serial.println(F("Right BLE+315M master full"));Serial.println(rf.init()?F("RF RX OK D4"):F("RF RX FAIL"));if(!display.begin(SSD1306_SWITCHCAPVCC,OLED_ADDR)){Serial.println(F("OLED failed"));while(1)delay(100);}display.setRotation(2);showState(1);} 
void loop(){readStream(Serial,bufUsb);readStream(BLESerial,bufBle);pollLeft();unsigned long now=millis();if(now-lastSensorMs>=SENSOR_INTERVAL_MS){lastSensorMs=now;readRight();sendSensors();}if(!textMode&&now-lastCmdMs>=JELLY_MS){textMode=true;drawText();}}
