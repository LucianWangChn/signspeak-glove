# -*- coding: utf-8 -*-
"""
智能手套双脑情感识别 - Web 控制面板
通过浏览器控制单片机 OLED 显示对应情绪表情

双击运行，自动打开浏览器 http://localhost:7861

依赖：pip install flask torch transformers librosa soundfile requests numpy sounddevice pyserial
（双脑模型由 voice_train.py 训练生成，首次运行约需 10-30 秒加载）
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import io
import time
import base64
import json
import tempfile

# Windows 控制台 UTF-8 修复
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import numpy as np
import sounddevice as sd
import soundfile as sf
import requests
import serial
from flask import Flask, request, jsonify, render_template_string

# ==============================================================
# 凭证配置区（请填入你自己的密钥！）
# ==============================================================
BAIDU_AK = __import__('os').environ.get('SIGNSPEAK_BAIDU_AK', '')
BAIDU_SK = __import__('os').environ.get('SIGNSPEAK_BAIDU_SK', '')
SPARK_PWD = "gWeMluADmkjpUNSojhhL:WlAvVRhFVRXhQlPKRXNm"

# 串口配置（请根据实际情况修改 COM 口）
SERIAL_PORT = 'COM6'
SERIAL_BAUD = 9600

# ==============================================================
# 右脑：Wav2Vec2 + MLP 声学情绪识别（复用 voice_demo）
# ==============================================================
import voice_demo

# ==============================================================
# 串口通信控制器
# ==============================================================
class GloveController:
    def __init__(self, port=SERIAL_PORT, baudrate=SERIAL_BAUD):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._connect()

    def _connect(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.5)
            print(f"✅ 串口 [{self.port}] 连接成功！")
            time.sleep(1.5)
        except Exception as e:
            print(f"⚠️  串口连接失败: {e}")
            self.ser = None

    def is_connected(self):
        return self.ser is not None and self.ser.is_open

    def send_emotion(self, emotion_char):
        """发送 A/C/S 指令到单片机，触发 OLED 显示对应表情"""
        try:
            if not self.is_connected():
                return False, "串口未连接"
            self.ser.write(emotion_char.encode('utf-8'))
            self.ser.flush()
            return True, f"已发送 {emotion_char}"
        except Exception as e:
            return False, str(e)

# 初始化串口
print("正在初始化外设...")
glove = GloveController(port=SERIAL_PORT)

# ==============================================================
# 左脑：百度 ASR + 讯飞 Spark LLM 语义分析
# ==============================================================
def get_baidu_token():
    url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={BAIDU_AK}&client_secret={BAIDU_SK}"
    try:
        return requests.post(url, timeout=10).json().get("access_token")
    except:
        return None

def asr_process(audio_file, token):
    if not token:
        return "Error"
    with open(audio_file, 'rb') as f:
        audio_data = f.read()
    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
    url = "https://vop.baidu.com/server_api"
    payload = {
        "format": "wav", "rate": 16000, "channel": 1,
        "cuid": "glove_web_brain", "token": token,
        "speech": audio_base64, "len": len(audio_data), "dev_pid": 1537
    }
    try:
        res = requests.post(url, json=payload, timeout=10).json()
        if res.get("err_no") == 0 and res.get("result"):
            return res["result"][0]
    except:
        pass
    return "Error"

def llm_process(text):
    url = "https://spark-api-open.xf-yun.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {SPARK_PWD}", "Content-Type": "application/json"}
    prompt = f"""你是一个专业的医疗情感分析AI。请分析患者家属的话语，判断其真实情绪，并严格按要求输出控制指令（绝对只输出单个字母，不要解释）：

【指令映射表】
C - 平静/正面：打招呼、询问、喜悦、感谢。
A - 急躁/高压：愤怒、焦急、害怕、不耐烦、质问。
S - 悲伤/低落：伤心、绝望、无助。

请分析以下话语：
话语："{text}" -> 输出："""
    payload = {"model": "lite", "messages": [{"role": "user", "content": prompt}], "temperature": 0.01}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=15).json()
        return resp['choices'][0]['message']['content'].strip()
    except:
        return "Error"

# ==============================================================
# 决策融合规则
# ==============================================================
def fuse_decision(acoustic_result, semantic_result):
    if acoustic_result == 'sad':
        return 'S', "右脑截获明显哭泣/哽咽声，行使悲伤否决权"
    elif semantic_result == 'A' or acoustic_result in ['angry', 'fearful']:
        return 'A', "高敏急躁报警（左脑或右脑察觉急躁/愤怒）"
    elif semantic_result == 'S':
        return 'S', "左脑文本逻辑推理出低落情绪"
    else:
        return 'C', "双脑一致认为情绪平稳"

# ==============================================================
# Flask Web UI（内嵌 HTML/CSS/JS）
# ==============================================================
HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>智能手套 - 双脑情感控制系统</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#06060a;--surface:#0e0e18;--border:#1e1e30;
  --primary:#6366f1;--primary2:#0ea5e9;--accent:#8b5cf6;
  --text:#e2e8f0;--muted:#475569;--dim:#64748b;
  --green:#22c55e;--red:#ef4444;--yellow:#f59e0b;--blue:#3b82f6;
  --c-bg:#0c1a14;--c-border:#14532d;--c-text:#4ade80;
  --a-bg:#1a0c0c;--a-border:#7f1d1d;--a-text:#f87171;
  --s-bg:#0c1220;--s-border:#1e3a5f;--s-text:#60a5fa;
}
body{font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
.bg{position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(ellipse 600px 400px at 15% 20%,rgba(99,102,241,0.07) 0%,transparent 60%),
             radial-gradient(ellipse 500px 350px at 85% 75%,rgba(14,165,233,0.06) 0%,transparent 60%),
             radial-gradient(ellipse 400px 300px at 50% 50%,rgba(139,92,246,0.04) 0%,transparent 60%);}
.wrap{position:relative;z-index:1;max-width:720px;margin:0 auto;padding:20px 16px 48px}
.status-bar{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;background:var(--surface);border:1px solid var(--border);border-radius:14px;margin-bottom:20px;font-size:0.78em}
.status-item{display:flex;align-items:center;gap:6px;color:var(--dim)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);flex-shrink:0}
.dot.ok{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot.err{background:var(--red);box-shadow:0 0 6px var(--red)}
.header{text-align:center;margin-bottom:24px}
.header-icon{width:60px;height:60px;margin:0 auto 12px;background:linear-gradient(135deg,#6366f1,#0ea5e9);border-radius:18px;display:flex;align-items:center;justify-content:center;font-size:30px;box-shadow:0 8px 32px rgba(99,102,241,0.3)}
.header h1{font-size:1.5em;font-weight:800;background:linear-gradient(135deg,#c7d2fe,#7dd3fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.header p{color:var(--dim);font-size:0.78em;margin-top:4px}
.card{background:rgba(14,14,24,0.85);border:1px solid var(--border);border-radius:20px;padding:22px;backdrop-filter:blur(20px);margin-bottom:16px;box-shadow:0 4px 24px rgba(0,0,0,0.4)}
.section-title{font-size:0.7em;color:var(--dim);text-transform:uppercase;letter-spacing:0.1em;font-weight:600;margin-bottom:12px}
.tabs{display:flex;gap:4px;margin-bottom:18px;background:rgba(20,20,36,0.7);border-radius:12px;padding:4px}
.tab{flex:1;padding:8px 12px;border:none;border-radius:10px;background:transparent;color:var(--dim);font-size:0.82em;cursor:pointer;transition:all 0.2s;font-family:inherit;font-weight:500}
.tab:hover{color:var(--text)}
.tab.on{background:linear-gradient(135deg,rgba(99,102,241,0.2),rgba(14,165,233,0.15));color:#7dd3fc;box-shadow:0 2px 10px rgba(99,102,241,0.12)}
.panel{display:none}
.panel.on{display:block}

/* 麦克风 */
.mic-row{display:flex;flex-direction:column;align-items:center;gap:10px;padding:10px 0}
.mic-btn{width:88px;height:88px;border-radius:50%;border:3px solid rgba(99,102,241,0.4);background:rgba(99,102,241,0.05);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:34px;transition:all 0.2s}
.mic-btn:hover{background:rgba(99,102,241,0.12);border-color:rgba(99,102,241,0.7);transform:scale(1.05)}
.mic-btn.rec{border-color:var(--red);background:rgba(239,68,68,0.1);animation:ripple 1.4s infinite}
@keyframes ripple{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.3)}50%{box-shadow:0 0 0 18px rgba(239,68,68,0)}}
.mic-timer{font-size:1em;font-weight:700;color:var(--red);min-height:24px;text-align:center}
.mic-status{font-size:0.8em;color:var(--dim);min-height:18px;text-align:center}
.wave-box{width:100%;height:48px;background:rgba(20,20,40,0.5);border-radius:10px;overflow:hidden;display:none}
.wave-box.on{display:block}
#waveCanvas{width:100%;height:100%}
.or{color:var(--muted);font-size:0.78em;flex-shrink:0;text-align:center;margin:4px 0}

/* 上传区 */
.upload-zone{border:2px dashed rgba(99,102,241,0.2);border-radius:14px;padding:18px;text-align:center;cursor:pointer;transition:all 0.2s;font-size:0.82em;color:var(--dim);margin:4px 0}
.upload-zone:hover{border-color:rgba(99,102,241,0.5);background:rgba(99,102,241,0.03)}
.upload-zone input{display:none}
.dz-icon{font-size:22px;margin-bottom:4px;display:block}
.dz-hint{font-size:0.7em;color:var(--muted);margin-top:3px}
#fileName{font-size:0.75em;color:var(--primary2);margin-top:6px;min-height:16px;text-align:center}

.action-btn{width:100%;padding:12px;border:none;border-radius:12px;font-size:0.88em;font-weight:600;cursor:pointer;font-family:inherit;transition:all 0.2s;
  background:linear-gradient(135deg,#6366f1,#0ea5e9);color:#fff;box-shadow:0 4px 16px rgba(99,102,241,0.3);margin-top:10px}
.action-btn:hover{box-shadow:0 6px 24px rgba(99,102,241,0.45);transform:translateY(-1px)}
.action-btn:active{transform:translateY(0)}
.action-btn:disabled{background:rgba(25,25,45,0.9);color:var(--muted);box-shadow:none;cursor:not-allowed;transform:none}

.loader{display:none;text-align:center;padding:18px}
.loader.on{display:block}
.spinner{width:34px;height:34px;margin:0 auto 8px;border:3px solid rgba(99,102,241,0.15);border-top-color:#6366f1;border-radius:50%;animation:spin 0.7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loader p{color:var(--primary2);font-size:0.8em}

.err-box{display:none;padding:12px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:12px;font-size:0.8em;color:#f87171;margin-top:10px}

/* 结果 */
.result-box{display:none;margin-top:14px}
.result-box.on{display:block;animation:fadeIn 0.4s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.result-card{padding:16px;border-radius:16px;border:1px solid;margin-bottom:10px}
.result-card.calm{background:var(--c-bg);border-color:var(--c-border)}
.result-card.angry{background:var(--a-bg);border-color:var(--a-border)}
.result-card.sad{background:var(--s-bg);border-color:var(--s-border)}
.result-card.neutral{background:rgba(20,20,40,0.6);border-color:var(--border)}
.result-emoji{font-size:32px;margin-bottom:6px}
.result-label{font-size:1.2em;font-weight:700}
.result-label.calm{color:var(--c-text)}
.result-label.angry{color:var(--a-text)}
.result-label.sad{color:var(--s-text)}
.result-label.neutral{color:var(--dim)}
.result-score{font-size:0.78em;color:var(--dim);margin-top:3px}
.result-detail{font-size:0.75em;color:var(--dim);margin-top:6px;line-height:1.7;padding-top:6px;border-top:1px solid rgba(255,255,255,0.04)}
.command-badge{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:10px;font-weight:700;font-size:0.95em;margin-top:8px}
.command-badge.A{background:var(--a-bg);border:1px solid var(--a-border);color:var(--a-text)}
.command-badge.C{background:var(--c-bg);border:1px solid var(--c-border);color:var(--c-text)}
.command-badge.S{background:var(--s-bg);border:1px solid var(--s-border);color:var(--s-text)}
.sent-badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:6px;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);color:#4ade80;font-size:0.75em;margin-top:8px;margin-left:6px}
.sent-badge.fail{background:rgba(239,68,68,0.1);border-color:rgba(239,68,68,0.3);color:#f87171}

/* 手动控制 */
.ctrl-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin:8px 0}
.ctrl-btn{height:76px;border-radius:16px;border:2px solid;font-size:1.1em;font-weight:700;cursor:pointer;transition:all 0.2s;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;font-family:inherit}
.ctrl-btn .cb-icon{font-size:1.3em}
.ctrl-btn .cb-label{font-size:0.6em;font-weight:500;opacity:0.65}
.ctrl-btn.C{border-color:var(--c-border);background:var(--c-bg);color:var(--c-text)}
.ctrl-btn.A{border-color:var(--a-border);background:var(--a-bg);color:var(--a-text)}
.ctrl-btn.S{border-color:var(--s-border);background:var(--s-bg);color:var(--s-text)}
.ctrl-btn:hover{transform:scale(1.03);box-shadow:0 6px 20px rgba(0,0,0,0.3)}
.ctrl-btn:active{transform:scale(0.97)}
.ctrl-btn.on{transform:scale(1.06)}
.ctrl-btn.C.on{box-shadow:0 0 18px rgba(34,197,94,0.35)}
.ctrl-btn.A.on{box-shadow:0 0 18px rgba(239,68,68,0.35)}
.ctrl-btn.S.on{box-shadow:0 0 18px rgba(59,130,246,0.35)}
.ctrl-hint{font-size:0.72em;color:var(--muted);text-align:center;margin-top:8px}
.tips{font-size:0.73em;color:var(--muted);text-align:center;margin-top:18px;line-height:1.9}
</style>
</head>
<body>
<div class="bg"></div>
<div class="wrap">

  <!-- 状态栏 -->
  <div class="status-bar">
    <div class="status-item">
      <span class="dot" id="serialDot"></span>
      <span id="serialStatus">串口: 检测中...</span>
    </div>
    <div class="status-item">
      🧠 右脑: <span id="brainStatus" style="color:#f59e0b">加载中...</span>
    </div>
  </div>

  <div class="header">
    <div class="header-icon">🧤</div>
    <h1>智能手套 · 双脑情感控制系统</h1>
    <p>Wav2Vec2 + MLP 声学分析 &nbsp;|&nbsp; 讯飞 Spark LLM 语义分析</p>
  </div>

  <div class="card">
    <div class="tabs">
      <button class="tab on" id="tab-recog" onclick="switchTab('recog')">🧠 语音情感识别</button>
      <button class="tab" id="tab-ctrl" onclick="switchTab('ctrl')">🎮 手动控制</button>
    </div>

    <!-- 语音识别面板 -->
    <div class="panel on" id="panel-recog">
      <div class="section-title">🎙️ 麦克风录音</div>
      <div class="mic-row">
        <button class="mic-btn" id="micBtn" onclick="toggleMic()">
          <span id="micIcon">🎙️</span>
        </button>
        <div class="mic-timer" id="recTimer"></div>
        <div class="mic-status" id="micStatus">点击开始录音（建议 3-5 秒）</div>
        <div class="wave-box" id="waveBox"><canvas id="waveCanvas"></canvas></div>
      </div>

      <div class="or">— 或者上传音频文件 —</div>

      <div class="upload-zone" onclick="document.getElementById('fileInput').click()">
        <span class="dz-icon">📁</span>
        <div>点击上传音频文件</div>
        <div class="dz-hint">支持 MP3 / WAV / M4A / OGG</div>
        <input type="file" id="fileInput" accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*" onchange="onFileChosen(this)">
      </div>
      <div id="fileName"></div>

      <button class="action-btn" id="analyzeBtn" onclick="analyzeAudio()" disabled>
        🔍 开始双脑情感分析
      </button>

      <div class="loader" id="loader">
        <div class="spinner"></div>
        <p id="loaderText">唤醒双脑分析中，请稍候...</p>
      </div>
      <div class="err-box" id="errBox"></div>

      <div class="result-box" id="resultBox">
        <div class="section-title" style="margin-top:4px">📊 双脑分析结果</div>
        <div class="result-card" id="resultCard">
          <div class="result-emoji" id="resultEmoji">😌</div>
          <div class="result-label" id="resultLabel">平静</div>
          <div class="result-score" id="resultScore"></div>
          <div class="result-detail" id="resultDetail"></div>
          <div id="commandArea"></div>
        </div>
      </div>
    </div>

    <!-- 手动控制面板 -->
    <div class="panel" id="panel-ctrl">
      <div class="section-title">🎮 直接控制 OLED 表情</div>
      <div class="ctrl-grid">
        <button class="ctrl-btn C" id="btnC" onclick="sendCmd('C')">
          <span class="cb-icon">😌</span>
          <span class="cb-label">平静 Calm</span>
        </button>
        <button class="ctrl-btn A" id="btnA" onclick="sendCmd('A')">
          <span class="cb-icon">😡</span>
          <span class="cb-label">急躁 Angry</span>
        </button>
        <button class="ctrl-btn S" id="btnS" onclick="sendCmd('S')">
          <span class="cb-icon">😢</span>
          <span class="cb-label">悲伤 Sad</span>
        </button>
      </div>
      <div class="ctrl-hint">点击按钮直接发送 A/C/S 指令到单片机，控制 OLED 显示对应表情</div>
    </div>
  </div>

  <div class="tips">
    💡 录音 3-5 秒效果最佳<br>
    🤖 右脑: Wav2Vec2-Base + MLP &nbsp;|&nbsp; 🧠 左脑: Baidu ASR + 讯飞 Spark LLM
  </div>
</div>

<script>
// ==============================================================
// WAV 编码器（Web Audio API PCM → WAV Blob）
// ==============================================================
function encodeWAV(samples, sr) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  function ws(o, s) { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); }
  ws(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true);
  ws(8, 'WAVE'); ws(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, sr, true);
  v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  ws(36, 'data'); v.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    off += 2;
  }
  return new Blob([buf], { type: 'audio/wav' });
}

// ==============================================================
// 麦克风录音
// ==============================================================
let rec = false, bufs = [], ac = null, an = null, sp = null, blob = null;
let recT = 0, tI = null;

const mB = document.getElementById('micBtn');
const mS = document.getElementById('micStatus');
const mT = document.getElementById('recTimer');
const wb = document.getElementById('waveBox');
const wc = document.getElementById('waveCanvas');
const wcCtx = wc.getContext('2d');

function drawWave() {
  if (!an) return;
  const bl = an.frequencyBinCount, data = new Uint8Array(bl);
  an.getByteTimeDomainData(data);
  const dpr = window.devicePixelRatio || 1;
  wc.width = wc.offsetWidth * dpr; wc.height = wc.offsetHeight * dpr;
  wcCtx.scale(dpr, dpr);
  const w = wc.offsetWidth, h = wc.offsetHeight;
  wcCtx.clearRect(0, 0, w, h);
  wcCtx.lineWidth = 2; wcCtx.strokeStyle = '#6366f1'; wcCtx.beginPath();
  const sw = w / bl; let x = 0;
  for (let i = 0; i < bl; i++) {
    const v = data[i] / 128.0, y = v * h / 2;
    if (i === 0) wcCtx.moveTo(x, y); else wcCtx.lineTo(x, y);
    x += sw;
  }
  wcCtx.lineTo(w, h / 2); wcCtx.stroke();
  if (rec) requestAnimationFrame(drawWave);
}

async function toggleMic() {
  if (!rec) {
    try {
      const ms = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      ac = new (window.AudioContext || window.webkitAudioContext)();
      const src = ac.createMediaStreamSource(ms);
      an = ac.createAnalyser(); an.fftSize = 2048;
      src.connect(an);
      sp = ac.createScriptProcessor(4096, 1, 1);
      bufs = [];
      sp.onaudioprocess = function(e) { if (rec) bufs.push(new Float32Array(e.inputBuffer.getChannelData(0))); };
      src.connect(sp); sp.connect(ac.destination);
      rec = true;
      mB.classList.add('rec');
      document.getElementById('micIcon').textContent = '⏹️';
      mS.textContent = '🔴 录音中... 再点一下结束';
      document.getElementById('analyzeBtn').disabled = true;
      wb.classList.add('on');
      recT = Date.now();
      tI = setInterval(() => { mT.textContent = '⏱ ' + ((Date.now() - recT) / 1000).toFixed(1) + 's'; }, 100);
      drawWave();
    } catch (e) { mS.textContent = '❌ 无法访问麦克风: ' + e.message; }
  } else {
    rec = false;
    if (sp) sp.disconnect();
    if (ac && ac.getTracks) ac.getTracks().forEach(t => t.stop());
    if (tI) { clearInterval(tI); tI = null; }
    mT.textContent = '✅ ' + ((Date.now() - recT) / 1000).toFixed(1) + 's';
    mB.classList.remove('rec');
    document.getElementById('micIcon').textContent = '🎙️';
    if (bufs.length === 0) { mS.textContent = '未采集到音频，请重试'; return; }
    const total = bufs.reduce((a, b) => a + b.length, 0);
    const merged = new Float32Array(total); let off = 0;
    for (const b of bufs) { merged.set(b, off); off += b.length; }
    const sr = ac.sampleRate || 16000;
    blob = encodeWAV(merged, sr);
    mS.textContent = '✅ 录音完成 (' + (total / sr).toFixed(1) + 's)，点击"开始双脑情感分析"';
    document.getElementById('analyzeBtn').disabled = false;
  }
}

// ==============================================================
// 文件上传
// ==============================================================
let selFile = null;
function onFileChosen(input) {
  if (input.files && input.files[0]) {
    selFile = input.files[0];
    document.getElementById('fileName').textContent = '📎 ' + selFile.name + ' (' + (selFile.size / 1024).toFixed(1) + ' KB)';
    document.getElementById('analyzeBtn').disabled = false;
    blob = null;
    mS.textContent = '已选择文件，请点击"开始双脑情感分析"';
  }
}

// ==============================================================
// 提交音频分析
// ==============================================================
async function analyzeAudio() {
  const fd = new FormData();
  if (blob) {
    fd.append('audio', blob, 'recording.wav');
  } else if (selFile) {
    fd.append('audio', selFile);
  } else {
    showErr('请先录音或上传音频文件');
    return;
  }
  const loader = document.getElementById('loader');
  const errBox = document.getElementById('errBox');
  const resultBox = document.getElementById('resultBox');
  const btn = document.getElementById('analyzeBtn');
  errBox.style.display = 'none';
  resultBox.classList.remove('on');
  loader.classList.add('on');
  btn.disabled = true;
  try {
    const resp = await fetch('/recognize', { method: 'POST', body: fd });
    const data = await resp.json();
    loader.classList.remove('on'); btn.disabled = false;
    if (data.error) {
      showErr(data.error);
    } else {
      showResult(data);
    }
  } catch (e) {
    loader.classList.remove('on'); btn.disabled = false;
    showErr('网络错误: ' + e.message);
  }
}

function showResult(data) {
  const resultBox = document.getElementById('resultBox');
  resultBox.classList.add('on');
  const card = document.getElementById('resultCard');
  const emojiMap = { calm: '😌', happy: '😄', sad: '😢', angry: '😡', fearful: '😨', neutral: '😐' };
  const labelMap = { calm: '平静', happy: '快乐', sad: '悲伤', angry: '愤怒', fearful: '恐惧', neutral: '中性' };
  const emotion = labelMap[data.acoustic_label] || data.acoustic_label || '中性';
  const emoji = emojiMap[data.acoustic_label] || '😐';
  const score = (data.acoustic_score * 100).toFixed(1);
  card.className = 'result-card ' + (data.acoustic_label || 'neutral');

  document.getElementById('resultEmoji').textContent = emoji;
  document.getElementById('resultLabel').textContent = emotion;
  document.getElementById('resultLabel').className = 'result-label ' + (data.acoustic_label || 'neutral');
  document.getElementById('resultScore').textContent = '声学置信度: ' + score + '%';

  let detail = '';
  if (data.acoustic_label) detail += '🎵 声学: ' + emotion + ' (' + score + '%)';
  if (data.asr_text && data.asr_text !== 'Error') {
    detail += (detail ? ' | ' : '') + '🗣️ ASR: ' + data.asr_text;
  }
  if (data.semantic_command && data.semantic_command !== 'Error') {
    detail += (detail ? ' | ' : '') + '🧠 左脑: ' + data.semantic_command;
  }
  detail += (detail ? ' | ' : '') + '⏱️ ' + data.total_time + 's';
  document.getElementById('resultDetail').innerHTML = detail.replace(/ \| /g, '<br>');

  const cmd = data.final_command;
  const cmdText = { A: '😡 急躁 / 愤怒', S: '😢 悲伤 / 低落', C: '😌 平静 / 正面' };
  document.getElementById('commandArea').innerHTML =
    '<div style="margin-top:8px">⚖️ 最终判决: <span class="command-badge ' + cmd + '">' + (cmdText[cmd] || cmd) + '</span> <span class="sent-badge" id="sentBadge">发送中...</span></div>';
  updateCtrlButtons(cmd);
  resultBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function showErr(msg) {
  const b = document.getElementById('errBox');
  b.textContent = '❌ ' + msg;
  b.style.display = 'block';
}

// ==============================================================
// 手动发送 A/C/S
// ==============================================================
function sendCmd(cmd) {
  updateCtrlButtons(cmd);
  fetch('/manual_cmd', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cmd: cmd })
  }).then(r => r.json()).then(d => {
    const badge = document.getElementById('sentBadge');
    if (d.success) {
      if (badge) { badge.textContent = '✅ 已发送'; badge.className = 'sent-badge'; }
    } else {
      if (badge) { badge.textContent = '❌ ' + (d.message || '发送失败'); badge.className = 'sent-badge fail'; }
    }
  }).catch(() => {
    const badge = document.getElementById('sentBadge');
    if (badge) { badge.textContent = '❌ 网络错误'; badge.className = 'sent-badge fail'; }
  });
}

function updateCtrlButtons(cmd) {
  ['C', 'A', 'S'].forEach(c => {
    const b = document.getElementById('btn' + c);
    if (b) b.classList.toggle('on', c === cmd);
  });
}

// ==============================================================
// Tab 切换
// ==============================================================
function switchTab(panel) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('on'));
  document.getElementById('tab-' + panel).classList.add('on');
  document.getElementById('panel-' + panel).classList.add('on');
}

// ==============================================================
// 初始化：检查后端状态
// ==============================================================
(function init() {
  fetch('/status').then(r => r.json()).then(d => {
    if (d.serial_connected) {
      document.getElementById('serialDot').className = 'dot ok';
      document.getElementById('serialStatus').textContent = '串口: ' + d.serial_port + ' ✅';
    } else {
      document.getElementById('serialDot').className = 'dot err';
      document.getElementById('serialStatus').textContent = '串口: 未连接 ❌';
    }
    document.getElementById('brainStatus').textContent = '已就绪 ✅';
    document.getElementById('brainStatus').style.color = '#4ade80';
  }).catch(() => {
    document.getElementById('brainStatus').textContent = '连接失败 ❌';
    document.getElementById('brainStatus').style.color = '#f87171';
  });
})();
</script>
</body>
</html>"""

# ==============================================================
# Flask 应用
# ==============================================================
app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/status")
def status():
    return jsonify({
        "serial_connected": glove.is_connected(),
        "serial_port": SERIAL_PORT,
        "brain_ready": True
    })

@app.route("/manual_cmd", methods=["POST"])
def manual_cmd():
    data = request.get_json()
    cmd = data.get("cmd", "").upper()
    if cmd not in ['A', 'C', 'S']:
        return jsonify({"success": False, "error": "无效指令"})
    success, msg = glove.send_emotion(cmd)
    return jsonify({"success": success, "message": msg, "command": cmd})

@app.route("/recognize", methods=["POST"])
def recognize():
    start_time = time.time()
    temp_file = None
    try:
        af = request.files.get("audio")
        if not af:
            return jsonify({"error": "未收到音频文件"}), 400

        suf = os.path.splitext(af.filename)[1] if af.filename else ".wav"
        if not suf: suf = ".wav"
        with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
            af.save(tmp.name)
            temp_file = tmp.name

        # --- 右脑：声学分析 ---
        acoustic_res = voice_demo.recognize_emotion(temp_file)
        acoustic_label = acoustic_res.get("top_label", "neutral")
        acoustic_score = acoustic_res.get("top_score", 0.0)
        acoustic_cn = acoustic_res.get("top_emotion", "中性")

        # --- 左脑：语义分析 ---
        baidu_token = get_baidu_token()
        asr_text = asr_process(temp_file, baidu_token) if baidu_token else "Error"
        semantic_cmd = llm_process(asr_text) if asr_text != "Error" else "Error"

        # --- 决策融合 ---
        final_cmd, reason = fuse_decision(acoustic_label, semantic_cmd)

        # --- 发送到单片机 ---
        glove.send_emotion(final_cmd)

        total_time = time.time() - start_time

        return jsonify({
            "success": True,
            "acoustic_label": acoustic_label,
            "acoustic_score": float(acoustic_score),
            "acoustic_cn": acoustic_cn,
            "asr_text": asr_text,
            "semantic_command": semantic_cmd,
            "final_command": final_cmd,
            "reason": reason,
            "total_time": round(total_time, 2)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if temp_file:
            try: os.remove(temp_file)
            except: pass

def open_browser():
    import webbrowser
    time.sleep(2)
    webbrowser.open("http://localhost:7861")

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  🧤 智能手套 · 双脑情感识别 Web 控制面板")
    print("  自动打开浏览器 http://localhost:7861")
    print("  按 Ctrl+C 停止服务")
    print("=" * 55 + "\n")
    print("正在加载双脑模型（首次运行约需 10-30 秒）...")
    voice_demo.load_my_model()
    print("双脑模型加载完成！\n")
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=7861, debug=False, use_reloader=False)
