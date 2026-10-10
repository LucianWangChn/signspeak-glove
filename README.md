# SIGNSPEAK 多模态情感转译手语手套

可穿戴交互原型源码：Arduino Nano、五指与惯性传感器、BLE 采集、Random Forest 手势分类、Wav2Vec2/MLP 声学分析及 ASR/LLM 语义融合，输出 OLED 与振动反馈。

## 主要贡献与成果

除三维建模与 PPT 外，王晨旭主要独立完成硬件搭建、固件、传感采集、模型训练及系统集成。作品获第十四届未来设计师 NCDA 全国总决赛本科生组国家级三等奖，获奖署名为第二作者。

## 目录

- `arduino/`：不同迭代的右手与左手固件及显示资源。
- `手语识别/`：BLE/串口采集、统计特征、训练及实时预测。
- `声音识别/`：声学模型、语音转写、语义分析及反馈控制。
- `综合演示/`：综合交互程序。
- `视频版闭环演示/`：面向预定义演示脚本的采集、模型与反馈版本。

## 安装与配置

先建立 Python 虚拟环境，再安装所需依赖：

```bash
pip install -r requirements.txt
```

MAC 地址已替换为通用占位值，使用前在采集/控制脚本中设置自己的 BLE 设备。云服务凭据改从环境变量读取；变量名可搜索 `SIGNSPEAK_`。无需云服务的手势训练可独立运行。

```bash
python 手语识别/train_gesture_model.py --data YOUR_CSV_DIRECTORY --output gesture_model.pkl
python tools/offline_gesture_check.py
```

离线检查使用生成的合成数据，验证特征维度与分类训练接口，不代表真实手语识别准确率。真实录音、个人采集数据、模型权重和历史凭据不随快照发布。旧版本代码保留其原有状态说明，建议从各模块 README 选择适合自己硬件的入口。

项目技术说明：https://lucianwangchn.github.io/projects/signspeak.html
