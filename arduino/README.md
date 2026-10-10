# Arduino 代码

## 概述

智能情绪反馈手套的 Arduino 端代码，经过多轮迭代。当前推荐使用 BLE 方案。

## 版本说明

### ✅ 当前推荐版本

| 目录 | 版本 | 状态 | 说明 |
|------|------|------|------|
| `right_ble_master_v2/` | 右手 BLE 主控 v2 | ✅ 推荐 | OLED 倒装、BLE 文字显示、只有右手 |
| `left_ble_slave/` | 左手 BLE 从机 | ✅ 推荐 | 只采集+BLE 透传，不做反馈 |

### 历史版本（保留参考）

| 目录 | 版本 | 状态 | 说明 |
|------|------|------|------|
| `right_master/` | 右手完整版 | ❌ OLED failed | SRAM 不足，Adafruit_SSD1306 1024B 缓冲区申请失败 |
| `right_master_lite/` | 右手轻量版 | ⚠️ 可用 | 无水母图，OLED OK |
| `right_master_lite_jelly/` | 右手轻量+水母 | ⚠️ 可用 | 有水母 bitmap，OLED OK |
| `right_ble_master/` | 右手 BLE v1 | ⚠️ 旧版 | 包含左手 315M 接收逻辑 |
| `right_master_prd_feedback/` | PRD 版 | ❌ 通信失效 | 蓝牙无法通信，String 引用+静态变量问题 |
| `right_master_prd_feedback_fixed/` | PRD 修复版 | ⚠️ 未验证 | 修复了通信问题，但未实际测试 |
| `left_aux_tx/` | 左手 315M 发射 | ⚠️ 旧方案 | 315M 不稳定，已改用 BLE |
| `i2c_scanner/` | I2C 扫描工具 | 🔧 工具 | 用于排查 OLED 地址和接线 |

## 硬件连接（右手）

### 右手 BLE 主控 v2

```
Arduino Nano 引脚分配：
  D2  ← BLE 模块 TX（SoftwareSerial RX）
  D3  → BLE 模块 RX（SoftwareSerial TX）
  D5  → 振动马达（PWM）
  A0  ← 拇指电位器
  A1  ← 食指电位器
  A2  ← 中指电位器
  A3  ← 无名指电位器
  A6  ← 小指电位器
  A4  ← MPU6050 SDA（I2C）
  A5  ← MPU6050 SCL（I2C）
  I2C ← OLED SSD1306 (0x3C)
```

### 左手 BLE 从机

```
Arduino Nano 引脚分配：
  D2  ← BLE 模块 TX（SoftwareSerial RX）
  D3  → BLE 模块 RX（SoftwareSerial TX）
  A0  ← 拇指电位器
  A1  ← 食指电位器
  A2  ← 中指电位器
  A3  ← 无名指电位器
  A6  ← 小指电位器
  A4  ← MPU6050 SDA（I2C）
  A5  ← MPU6050 SCL（I2C）
```

## BLE 通信协议

### 电脑 → 右手（下发指令）

| 指令 | 含义 | Arduino 行为 |
|------|------|-------------|
| `A` | 愤怒（旧版） | 马达强震 + OLED 愤怒表情 |
| `C` | 平静（旧版） | 马达关 + OLED 平静 |
| `S` | 悲伤（旧版） | 马达轻震 + OLED 悲伤 |
| `PH` | 积极高唤醒 | 对应硬件反馈 |
| `PL` | 积极低唤醒 | 对应硬件反馈 |
| `NH` | 消极高唤醒 | 对应硬件反馈 |
| `NL` | 消极低唤醒 | 对应硬件反馈 |
| `CF` | 冲突表达 | 对应硬件反馈 |
| `UK` | 不确定 | 对应硬件反馈 |
| `NT` | 中性 | 默认状态 |
| `T:文字\n` | OLED 显示文字 | T: 开头，\n 结尾，显示在 OLED 底部 |

### 右手 → 电脑（传感器数据，5Hz）

```
R:Thumb:512,Index:480,Middle:500,Ring:510,Pinky:490,aX:0.12,aY:-0.05,gZ:0.03
```

### 左手 → 电脑（传感器数据，5Hz）

```
L:Thumb:512,Index:480,Middle:500,Ring:510,Pinky:490,aX:0.12,aY:-0.05,gZ:0.03
```

## ⚠️ 已知问题

1. **OLED 中文乱码**：Adafruit_GFX 不支持中文字库，`T:文字` 发送中文可能无法正确显示，建议使用英文/拼音
2. **Arduino Nano SRAM 有限**：SSD1306 128x64 缓冲区占 1024B，加 SoftwareSerial + MPU6050 容易 OOM，导致 OLED 初始化失败
3. **PRD 版通信失效**：`right_master_prd_feedback` 的蓝牙无法通信，原因可能是 String 引用 + static 变量 + 传感器输出频率过高阻塞接收

## 🔄 待办任务4：写出最终的 Arduino 代码

当前 `right_ble_master_v2` 基本可用，但需要整合为**最终版**，满足以下要求：

1. **稳定 BLE 通信**：
   - 解决 BLE 写入不稳定的问题（配合 Python 端 notify 订阅）
   - Arduino 端需要正确处理 BLE notify 订阅请求
   - 降低传感器输出频率（5Hz → 3Hz），减少 BLE 带宽占用

2. **PRD 硬件反馈映射**：
   - PH → 高频强震 + OLED 积极高唤醒表情/水母
   - PL → 轻震 + OLED 积极低唤醒
   - NH → 强震 + OLED 消极高唤醒
   - NL → 低频弱震 + OLED 消极低唤醒
   - CF → 交替震动 + OLED 冲突符号
   - UK → 微震 + OLED 问号
   - NT → 无震动 + OLED 默认

3. **OLED 显示优化**：
   - 顶部显示情绪区域英文缩写（PH/PL/NH/NL/CF/UK/NT）
   - 底部显示 LLM 文字（英文/拼音，避免中文乱码）
   - 保留倒装适配 `setRotation(2)`

4. **左手整合（可选）**：
   - 如果需要左手数据，通过 BLE notify 转发到电脑
   - 不依赖 315M

5. **代码精简**：
   - 去掉所有旧版兼容代码（A/S/C 指令可保留但非核心）
   - 去掉 315M 相关代码
   - 减少 SRAM 占用，避免 OLED 初始化失败
