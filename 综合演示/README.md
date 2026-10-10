# 综合演示

## 概述

智能情绪反馈手套的综合演示程序，提供 BLE 手套连接、情绪区域下发、OLED 文字显示的交互界面。

**当前状态：⚠️ 功能基本完整，BLE 连接不稳定**

## 文件说明

| 文件 | 说明 |
|------|------|
| `demo_main.py` | 综合演示主程序 |
| `ble_glove_controller.py` | BLE 手套控制器（从声音识别目录导入） |

## 使用方法

```powershell
# 正常启动
python demo_main.py

# 扫描 BLE 设备
python demo_main.py --scan

# 指定右手 BLE 地址
python demo_main.py --right 00:00:00:00:00:00
```

## 交互命令

| 输入 | 功能 |
|------|------|
| `1` | 发送 PH（积极高唤醒） |
| `2` | 发送 PL（积极低唤醒） |
| `3` | 发送 NH（消极高唤醒） |
| `4` | 发送 NL（消极低唤醒） |
| `5` | 发送 CF（冲突表达） |
| `6` | 发送 UK（不确定） |
| `7` | 发送 NT（中性） |
| `t:文字` | 发送文字到 OLED 显示 |
| `r` | 重新连接 BLE |
| `q` | 退出 |

## ⚠️ 已知问题：BLE 连接不稳定

### 问题描述
综合演示的 BLE 连接非常不稳定，经常在几秒到几十秒内断开，情绪指令和 OLED 文字经常发送失败。

### 原因分析
- `ble_glove_controller.py` 使用纯 `write_gatt_char` 模式，没有 `start_notify` 订阅
- BLE 连接空闲时容易被 Windows 驱动断开
- 没有心跳保活机制
- 连续发送两条指令（zone + text）间隔仅 80ms，可能来不及

### 🔄 待办任务3：修复 BLE 连接不稳定

**参考手语识别模块的成功做法：**

手语识别的 `ble_gesture_predict.py` 使用 `start_notify` 订阅模式，Arduino 持续推送传感器数据，连接保持活跃，非常稳定。具体做法：

```python
# 手语识别的做法（稳定）
await client.start_notify(BLE_UUID, notification_handler)
# 连接持续活跃，不断连
```

```python
# 当前声音识别/综合演示的做法（不稳定）
await client.write_gatt_char(uuid, data, response=False)
# 写完就闲着，容易被断开
```

**修复方案：**
1. 在 `ble_glove_controller.py` 的 `connect()` 方法中，连接成功后立即 `start_notify`
2. 即使不需要接收数据，也注册一个空的 notification handler 保持连接活跃
3. 增加心跳：定时发送保活包（如每 2 秒发 `NT`）
4. 加大写入间隔：zone 和 text 之间至少 200ms
5. 改进重连逻辑：断连后自动重连 + 重新订阅 notify

### 🔄 待办任务2：综合演示需要更加贴合脚本

当前综合演示只是手动输入情绪编号，不够贴合实际拍摄/演示脚本。

**改进方向：**
1. 根据拍摄脚本设计演示流程，按场景自动切换情绪
2. 增加语音识别自动触发模式（与 `声音识别/vocie_llm_combination_prd_ble.py` 整合）
3. 增加手语识别实时显示（与 `手语识别/ble_gesture_predict.py` 整合）
4. 增加时间轴/场景切换提示，方便演示时按流程操作
5. 显示当前系统状态：BLE 连接状态、情绪识别结果、手语识别结果

**理想演示流程：**
```
[场景1: 患者表达疼痛] → 语音识别 "好疼啊" → NH + OLED: "pain"
[场景2: 护工安慰] → 手语识别 "谢谢" → PL + OLED: "thanks"  
[场景3: 情绪冲突] → 语音愤怒+文字积极 → CF + OLED: "conflict"
...
```

## BLE 连接参数

- 右手 BLE 地址：`00:00:00:00:00:00`
- BLE UUID：`0000ffe1-0000-1000-8000-00805f9b34fb`

## 依赖

```
pip install bleak
```
