# 声音识别模块

## 概述

语音情绪识别系统，基于 Wav2Vec2 + MLP 声学模型 + 百度 ASR + 讯飞星火 LLM 语义分析，实现"左右脑双通道"情绪识别，通过决策法庭输出最终情绪区域，经 BLE 下发到右手手套。

**当前状态：⚠️ 语音识别功能正常，BLE 连接不稳定**

## 文件说明

| 文件 | 说明 |
|------|------|
| `vocie_llm_combination_prd_ble.py` | 主程序：语音+PRD+BLE |
| `ble_glove_controller.py` | BLE 手套控制器 |
| `voice_demo.py` | Wav2Vec2 + MLP 声学情绪识别（原版） |
| `voice_train.py` | 模型训练脚本（原版） |
| `web_control.py` | Web 控制界面（原版，未改造） |
| `saved_model/` | 已训练的声学模型 |

## 系统架构

```
麦克风 → sounddevice 采集 WAV
        ↓
    百度 ASR → 文字 → 讯飞星火 LLM → 语义情绪（左脑）
        ↓
    Wav2Vec2 + MLP → 声学情绪（右脑）
        ↓
    决策法庭 → courtState + finalEmotionZone
        ↓
    BLE → 右手手套（PH/PL/NH/NL/CF/UK/NT + OLED 文字）
```

## 使用方法

```powershell
python vocie_llm_combination_prd_ble.py
```

运行后：
1. 自动连接右手 BLE
2. 按回车录音，再按回车停止
3. 自动执行 ASR → LLM → 声学分析 → 决策法庭 → BLE 下发

## PRD 决策法庭

| courtState | 含义 |
|------------|------|
| consistent | 语义与声学一致 |
| intensified | 高唤醒度，情绪增强 |
| conflict | 语义与声学冲突 |
| uncertain | 置信度低，无法判断 |

| finalEmotionZone | 含义 | BLE 指令 |
|------------------|------|----------|
| positive_high | 积极高唤醒 | PH |
| positive_low | 积极低唤醒 | PL |
| negative_high | 消极高唤醒 | NH |
| negative_low | 消极低唤醒 | NL |
| conflict | 冲突表达 | CF |
| unknown | 不确定 | UK |
| neutral | 中性 | NT |

## ⚠️ 已知问题：BLE 连接不稳定

### 问题描述
`ble_glove_controller.py` 使用的 `write_gatt_char` 模式经常断连、写入失败。声音识别主程序运行时，BLE 连接容易在几秒到几十秒内断开，导致情绪指令无法送达手套。

### 可能原因
1. **单向 write 模式不稳定**：当前控制器只做 `write_gatt_char`，没有订阅通知，BLE 连接空闲时容易被系统休眠
2. **写入间隔太短**：连续发送 zone + text 两条指令时，间隔仅 80ms，BLE 透传模块可能来不及处理
3. **Windows BLE 驱动**：Windows 的 BLE 栈不如 macOS/Linux 稳定，长时间 idle 连接容易被断开
4. **未做心跳保活**：没有定期发送心跳包维持连接

### 对比：手语识别的 BLE 连接是稳定的
手语识别（`ble_gesture_collector.py` / `ble_gesture_predict.py`）使用 `start_notify` 订阅模式，Arduino 主动推送数据，连接持续活跃，不容易断。这说明 **notify 订阅模式比 write-only 模式更稳定**。

### 🔄 待办任务3：修复 BLE 连接不稳定

**修复方向（参考手语识别的成功经验）：**
1. 在 `ble_glove_controller.py` 中启用 `start_notify` 订阅，即使不需要接收数据，也让连接保持活跃
2. 增加心跳机制：每隔 1-2 秒发送一个保活包（如 `NT` 指令）
3. 加大写入间隔：zone 和 text 之间至少间隔 200ms
4. 优化重连逻辑：断连后自动重连，重连时重新订阅 notify
5. 在 `vocie_llm_combination_prd_ble.py` 主循环中，每次录音前检查连接状态

**参考文件：**
- 稳定版：`手语识别/ble_gesture_predict.py`（使用 `start_notify`，连接稳定）
- 不稳定版：`声音识别/ble_glove_controller.py`（只做 `write_gatt_char`，容易断连）

## API 配置

- 百度 ASR：`BAIDU_AK` / `BAIDU_SK`（已内置）
- 讯飞星火 LLM：`SPARK_PWD`（已内置）

⚠️ 分享代码前需移除明文凭据

## 依赖

```
pip install bleak requests sounddevice soundfile numpy
```
