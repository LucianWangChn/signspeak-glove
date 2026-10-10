# 手语识别模块

## 概述

通过右手 BLE 手套采集五指电位器 + MPU6050 传感器数据，训练轻量级随机森林模型，实现实时手语动作识别。

**当前状态：✅ 已打通全流程（采集→训练→预测）**

## 文件说明

| 文件 | 说明 |
|------|------|
| `gesture_labels.json` | 动作编号与标签映射 |
| `ble_gesture_collector.py` | BLE 手语数据采集（推荐） |
| `serial_gesture_collector.py` | 串口版采集（旧版，备用） |
| `train_gesture_model.py` | 训练随机森林模型 |
| `realtime_gesture_predict.py` | 串口版实时预测（旧版，备用） |
| `ble_gesture_predict.py` | BLE 版实时预测（推荐） |
| `dataset/` | 采集的 CSV 数据 |
| `gesture_model.pkl` | 训练好的模型 |

## 使用流程

### 1. 采集数据
```powershell
python ble_gesture_collector.py
```
- 默认连接右手 BLE 地址 `00:00:00:00:00:00`
- 输入动作编号（1-5），倒计时后采集
- 每个动作建议采集 15-30 次
- 数据保存到脚本所在目录的 `dataset/`

### 2. 训练模型
```powershell
python train_gesture_model.py
```
- 自动读取 `dataset/` 下所有 CSV
- 输出 `gesture_model.pkl`

### 3. 实时预测
```powershell
python ble_gesture_predict.py
```
- 加载模型，通过 BLE 实时读取传感器数据并预测

## 当前动作标签

| 编号 | 标签 |
|------|------|
| 1 | 你好 |
| 2 | 谢谢 |
| 3 | 帮助 |
| 4 | 疼痛 |
| 5 | 停止 |

## 待办任务

### 🔄 任务1：更换动作标签为拍摄脚本中的单词

当前标签（你好/谢谢/帮助/疼痛/停止）是临时设定的，需要替换为**拍摄脚本中实际使用的手语单词**。

**操作步骤：**
1. 确认拍摄脚本中的手语单词列表
2. 修改 `gesture_labels.json`，更新编号与标签的映射
3. 删除 `dataset/` 下旧数据，重新采集
4. 重新训练模型

**注意事项：**
- 每次修改标签后，旧数据作废，必须重新采集
- 建议动作数量控制在 5-8 个，太多准确率会下降
- 采集时每个动作至少 15 次，越多越好

## 数据格式

传感器数据 CSV 格式：
```
Thumb,Index,Middle,Ring,Pinky,aX,aY,gZ,label
512,480,500,510,490,0.12,-0.05,0.03,1
...
```

- `Thumb/Index/Middle/Ring/Pinky`：五指电位器读数（0-1023）
- `aX/aY`：加速度计 X/Y（g）
- `gZ`：陀螺仪 Z（°/s）
- `label`：动作编号

## BLE 连接参数

- 右手 BLE 地址：`00:00:00:00:00:00`
- BLE UUID：`0000ffe1-0000-1000-8000-00805f9b34fb`
- 采集和预测使用 `start_notify` 订阅模式，连接稳定

## 依赖

```
pip install bleak pyserial pandas numpy scikit-learn
```
