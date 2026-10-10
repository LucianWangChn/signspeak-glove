# -*- coding: utf-8 -*-
"""
语音情感识别 - Web Demo（基于 Wav2Vec2 + MLP 模型）
双击运行即可打开网页，支持上传音频 + 麦克风录音

依赖：pip install flask transformers torch librosa soundfile
（模型由 voice_train.py 训练生成，首次运行约需 10-30 秒加载）
"""

import warnings
warnings.filterwarnings("ignore")

import os, sys, io, webbrowser, threading, time, tempfile, json
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# ⚠️ 不要在这里重定向 stdout/stderr！
# vocie_llm_combination.py 已设置了 wrapper
# 这里再 wrap 会导致第二次导入时 wrapper 失效，报 "I/O operation on closed file"

from flask import Flask, request, jsonify, render_template_string
import numpy as np
import librosa
import torch  # 必须在 @torch.no_grad() 装饰器之前 import

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_model")

EMOTION_CN = {
    'calm':'平静 (Calm)','happy':'快乐 (Happy)','sad':'悲伤 (Sad)',
    'angry':'愤怒 (Angry)','fearful':'恐惧 (Fearful)','neutral':'中性 (Neutral)',
}
EMOTION_COLORS = {
    'calm':'#14b8a6','happy':'#22c55e','sad':'#3b82f6',
    'angry':'#ef4444','fearful':'#f97316','neutral':'#94a3b8',
}
EMOTION_ICONS = {
    'calm':'😌','happy':'😄','sad':'😢','angry':'😡','fearful':'😨','neutral':'😐',
}

_classifier = None

def load_my_model():
    global _classifier
    if _classifier is not None:
        return _classifier
    print("[INFO] 首次调用，正在加载 Wav2Vec2 + MLP 模型...")
    model_path = os.path.join(MODEL_DIR, "emotion_mlp.pkl")
    if not os.path.exists(model_path):
        print("[WARN] 未找到本地模型，使用预训练 Wav2Vec2 作为备用...")
        return None
    import pickle, torch
    from transformers import AutoFeatureExtractor, AutoModel
    with open(model_path, "rb") as f:
        model_data = pickle.load(f)
    # 强制离线加载，避免演示现场因 HuggingFace 网络失败导致程序崩溃。
    # 本机缓存路径通常在 <LOCAL_PROJECT_PATH>\.cache\huggingface\hub\models--facebook--wav2vec2-base
    fe = AutoFeatureExtractor.from_pretrained("facebook/wav2vec2-base", local_files_only=True)
    wav2vec = AutoModel.from_pretrained("facebook/wav2vec2-base", local_files_only=True, use_safetensors=False)
    wav2vec.eval()
    _classifier = {
        "mlp": model_data["mlp"], "scaler": model_data["scaler"],
        "le": model_data["label_encoder"], "feature_extractor": fe,
        "wav2vec": wav2vec, "device": "cuda" if torch.cuda.is_available() else "cpu",
    }
    print("[INFO] Wav2Vec2 + MLP 模型加载完成！")
    return _classifier

@torch.no_grad()
def recognize_emotion(audio_path):
    try:
        import torch
        clf = load_my_model()
        if clf is None:
            return {"success": False, "error": "模型未训练，请先运行 voice_train.py"}
        audio, sr = librosa.load(audio_path, sr=16000, mono=True)
        if len(audio) < 8000:
            return {"success": False, "error": "音频太短（<0.5秒），请录制更长时间的语音"}
        fe, model = clf["feature_extractor"], clf["wav2vec"]
        device = clf["device"]
        inputs = fe(audio, sampling_rate=16000, return_tensors="pt", padding=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        outputs = model(**inputs)
        embedding = outputs.last_hidden_state.mean(dim=1).squeeze().cpu().numpy()
        X = clf["scaler"].transform([embedding])
        pred_idx = clf["mlp"].predict(X)[0]
        pred_proba = clf["mlp"].predict_proba(X)[0]
        pred_label = clf["le"].classes_[pred_idx]
        all_results = []
        for i, label in enumerate(clf["le"].classes_):
            all_results.append({"label": label, "emotion": EMOTION_CN.get(label, label), "score": round(float(pred_proba[i]), 4)})
        all_results.sort(key=lambda x: x["score"], reverse=True)
        return {"success": True, "top_label": pred_label, "top_emotion": EMOTION_CN.get(pred_label, pred_label),
                "top_score": round(float(pred_proba[pred_idx]), 4), "all_results": all_results}
    except FileNotFoundError:
        return {"success": False, "error": "模型文件不存在，请先运行 voice_train.py 训练模型"}
    except Exception as e:
        return {"success": False, "error": str(e)}

HTML = r"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>语音情感识别 | Wav2Vec2+MLP</title><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter','PingFang SC','Microsoft YaHei',sans-serif;background:#0a0a0f;color:#e2e8f0;min-height:100vh;overflow-x:hidden}
.bg-glow{position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:0;background:radial-gradient(ellipse 600px 400px at 20% 30%,rgba(99,102,241,0.08) 0%,transparent 70%),radial-gradient(ellipse 500px 350px at 80% 70%,rgba(14,165,233,0.06) 0%,transparent 70%),radial-gradient(ellipse 400px 300px at 50% 50%,rgba(168,85,247,0.04) 0%,transparent 70%)}
.container{position:relative;z-index:1;max-width:680px;margin:0 auto;padding:48px 20px 60px}
.header{text-align:center;margin-bottom:48px}
.header-icon{width:64px;height:64px;margin:0 auto 16px;background:linear-gradient(135deg,#6366f1,#0ea5e9);border-radius:20px;display:flex;align-items:center;justify-content:center;font-size:32px;box-shadow:0 8px 32px rgba(99,102,241,0.3)}
.header h1{font-size:1.75em;font-weight:700;background:linear-gradient(135deg,#c7d2fe,#7dd3fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.header p{color:#64748b;font-size:0.9em;margin-top:6px}
.card{background:rgba(15,15,25,0.8);border:1px solid rgba(99,102,241,0.15);border-radius:20px;padding:32px;backdrop-filter:blur(20px);box-shadow:0 4px 24px rgba(0,0,0,0.3);margin-bottom:24px}
.mode-tabs{display:flex;gap:6px;margin-bottom:28px;background:rgba(30,30,50,0.6);border-radius:12px;padding:4px}
.tab-btn{flex:1;padding:10px 16px;border:none;border-radius:10px;background:transparent;color:#64748b;font-size:0.88em;cursor:pointer;transition:all 0.25s;font-family:inherit;font-weight:500}
.tab-btn:hover{color:#94a3b8}
.tab-btn.active{background:linear-gradient(135deg,rgba(99,102,241,0.2),rgba(14,165,233,0.15));color:#7dd3fc;box-shadow:0 2px 12px rgba(99,102,241,0.15)}
.tab-panel{display:none}
.tab-panel.active{display:block;animation:fadeIn 0.3s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.upload-zone{border:2px dashed rgba(99,102,241,0.25);border-radius:16px;padding:40px 20px;text-align:center;cursor:pointer;transition:all 0.25s;position:relative;background:rgba(99,102,241,0.02)}
.upload-zone:hover,.upload-zone.dragover{border-color:rgba(99,102,241,0.6);background:rgba(99,102,241,0.06)}
.upload-zone .icon{font-size:40px;margin-bottom:12px;opacity:0.6}
.upload-zone .text{color:#94a3b8;font-size:0.9em}
.upload-zone .hint{color:#475569;font-size:0.78em;margin-top:6px}
.upload-zone input[type="file"]{display:none}
#fileName{color:#7dd3fc;font-size:0.85em;margin-top:12px;min-height:20px;text-align:center}
.mic-area{text-align:center;padding:20px 0}
.mic-btn{width:110px;height:110px;border-radius:50%;border:3px solid rgba(99,102,241,0.4);background:rgba(99,102,241,0.05);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;transition:all 0.25s}
.mic-btn:hover{background:rgba(99,102,241,0.12);border-color:rgba(99,102,241,0.6);transform:scale(1.04)}
.mic-btn .icon{font-size:40px}
.mic-btn.recording{border-color:#ef4444;background:rgba(239,68,68,0.1);animation:micPulse 1.2s infinite}
@keyframes micPulse{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.3)}50%{box-shadow:0 0 0 18px rgba(239,68,68,0)}}
.mic-status{color:#94a3b8;font-size:0.88em;margin:14px 0 20px;min-height:24px}
.waveform-container{width:100%;height:60px;margin:12px 0 16px;background:rgba(30,30,50,0.4);border-radius:10px;overflow:hidden;display:none}
.waveform-container.active{display:block}
#waveCanvas{width:100%;height:100%}
.rec-timer{font-size:1.1em;font-weight:600;color:#ef4444;margin:8px 0 4px;min-height:28px}
.action-btn{width:100%;padding:14px;border:none;border-radius:12px;font-size:0.95em;font-weight:600;cursor:pointer;font-family:inherit;transition:all 0.2s;margin-top:8px;background:linear-gradient(135deg,#6366f1,#0ea5e9);color:#fff;box-shadow:0 4px 16px rgba(99,102,241,0.3)}
.action-btn:hover{box-shadow:0 6px 24px rgba(99,102,241,0.45);transform:translateY(-1px)}
.action-btn:active{transform:translateY(0)}
.action-btn:disabled{background:rgba(30,30,50,0.8);color:#475569;box-shadow:none;cursor:not-allowed;transform:none}
.loader{display:none;text-align:center;padding:24px}
.loader.active{display:block}
.loader-spinner{width:40px;height:40px;margin:0 auto 12px;border:3px solid rgba(99,102,241,0.15);border-top-color:#6366f1;border-radius:50%;animation:spin 0.8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loader p{color:#7dd3fc;font-size:0.88em}
.error-msg{display:none;color:#f87171;text-align:center;padding:14px;background:rgba(239,68,68,0.08);border-radius:12px;border:1px solid rgba(239,68,68,0.15);font-size:0.85em;margin-top:12px}
.result{display:none}
.result.show{display:block;animation:fadeIn 0.5s ease}
.top-result{text-align:center;padding:28px 20px;margin-bottom:24px;background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);border-radius:16px}
.top-emoji{font-size:52px;margin-bottom:10px}
.top-label{font-size:1.4em;font-weight:700;color:#e2e8f0}
.top-score{font-size:0.95em;color:#7dd3fc;margin-top:6px;font-weight:500}
.top-bar-track{width:80%;max-width:300px;height:8px;margin:16px auto 0;background:rgba(30,30,50,0.6);border-radius:4px;overflow:hidden}
.top-bar-fill{height:100%;border-radius:4px;background:linear-gradient(90deg,#6366f1,#0ea5e9);transition:width 0.8s ease}
.chart-title{font-size:0.85em;color:#64748b;font-weight:500;margin-bottom:14px;text-transform:uppercase;letter-spacing:0.05em}
.bar-row{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.bar-emoji{width:28px;text-align:center;font-size:1.1em;flex-shrink:0}
.bar-label{width:70px;font-size:0.82em;color:#94a3b8;text-align:right;flex-shrink:0}
.bar-track{flex:1;height:24px;background:rgba(30,30,50,0.5);border-radius:6px;overflow:hidden}
.bar-fill{height:100%;border-radius:6px;display:flex;align-items:center;padding-left:8px;font-size:0.72em;color:#fff;font-weight:600;transition:width 0.8s cubic-bezier(0.25,0.8,0.25,1);min-width:0}
.bar-pct{width:52px;text-align:right;font-size:0.82em;color:#94a3b8;flex-shrink:0;font-weight:500}
.tips{font-size:0.78em;color:#475569;text-align:center;margin-top:32px;line-height:1.8}
.tips span{color:#64748b}
</style></head>
<body><div class="bg-glow"></div>
<div class="container">
<div class="header"><div class="header-icon">🎙️</div><h1>语音情感识别系统</h1><p>基于 Wav2Vec2 + MLP 深度学习模型</p></div>
<div class="card">
<div class="mode-tabs">
<button class="tab-btn active" onclick="switchTab('upload')">📁 上传音频</button>
<button class="tab-btn" onclick="switchTab('mic')">🎙️ 麦克风录音</button>
</div>
<div class="tab-panel active" id="panel-upload">
<div class="upload-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
<div class="icon">🎵</div><div class="text">点击选择或拖拽音频文件到这里</div>
<div class="hint">支持 MP3 / WAV / M4A / OGG / FLAC，建议 3-10 秒</div>
<input type="file" id="fileInput" accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*" onchange="onFileSelected(this)">
</div>
<div id="fileName"></div>
<button class="action-btn" id="uploadBtn" onclick="uploadFile()" disabled>🔍 开始情感分析</button>
<div class="loader" id="uploadLoader"><div class="loader-spinner"></div><p>正在分析音频情感，请稍候...</p></div>
<div class="error-msg" id="uploadError"></div>
</div>
<div class="tab-panel" id="panel-mic">
<div class="mic-area">
<button class="mic-btn" id="micBtn" onclick="toggleMic()"><span class="icon" id="micIcon">🎙️</span></button>
<div class="rec-timer" id="recTimer"></div>
<div class="mic-status" id="micStatus">点击按钮开始录音</div>
<div class="waveform-container" id="waveformBox"><canvas id="waveCanvas"></canvas></div>
<button class="action-btn" id="micSubmitBtn" onclick="sendMicAudio()" disabled>🔍 识别录音情感</button>
</div>
<div class="loader" id="micLoader"><div class="loader-spinner"></div><p>正在分析录音情感，请稍候...</p></div>
<div class="error-msg" id="micError"></div>
</div>
<div class="result" id="result">
<div class="top-result">
<div class="top-emoji" id="topEmoji"></div>
<div class="top-label" id="topLabel"></div>
<div class="top-score" id="topScore"></div>
<div class="top-bar-track"><div class="top-bar-fill" id="topBarFill"></div></div>
</div>
<div class="chart-title">所有情绪分布</div>
<div id="barChart"></div>
</div>
</div>
<div class="tips"><span>💡</span> 录音时长 3-10 秒效果最佳<br><span>🔬</span> 模型：Wav2Vec2-Base (768维) + MLP (256-128-64) 分类器</div>
</div>
<script>
const EI={'calm':'😌','happy':'😄','sad':'😢','angry':'😡','fearful':'😨','neutral':'😐'};
const EC={'calm':'#14b8a6','happy':'#22c55e','sad':'#3b82f6','angry':'#ef4444','fearful':'#f97316','neutral':'#94a3b8'};
function switchTab(tab){document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab-btn')[tab==='upload'?0:1].classList.add('active');document.getElementById('panel-'+tab).classList.add('active');}
const dz=document.getElementById('dropZone');
['dragenter','dragover'].forEach(e=>dz.addEventListener(e,ev=>{ev.preventDefault();dz.classList.add('dragover');}));
['dragleave','drop'].forEach(e=>dz.addEventListener(e,ev=>{ev.preventDefault();dz.classList.remove('dragover');}));
dz.addEventListener('drop',e=>{const f=e.dataTransfer.files[0];if(f){const dt=new DataTransfer();dt.items.add(f);document.getElementById('fileInput').files=dt.files;onFileSelected(document.getElementById('fileInput'));}});
let sel=null;
function onFileSelected(input){sel=input.files[0];const el=document.getElementById('fileName');if(sel){el.textContent='📎 '+sel.name+' ('+(sel.size/1024/1024).toFixed(2)+' MB)';document.getElementById('uploadBtn').disabled=false;}else{el.textContent='';document.getElementById('uploadBtn').disabled=true;}}
async function uploadFile(){if(!sel)return;const btn=document.getElementById('uploadBtn'),ld=document.getElementById('uploadLoader'),err=document.getElementById('uploadError');btn.disabled=true;err.style.display='none';document.getElementById('result').classList.remove('show');ld.classList.add('active');const fd=new FormData();fd.append('audio',sel);try{const resp=await fetch('/recognize',{method:'POST',body:fd});const data=await resp.json();ld.classList.remove('active');btn.disabled=false;if(data.success)showResult(data);else{err.textContent='❌ '+(data.error||'识别失败');err.style.display='block';}}catch(e){ld.classList.remove('active');btn.disabled=false;err.textContent='❌ 网络错误: '+e.message;err.style.display='block';}}
let ms,ac,sp,an,rec=false,bufs=[],blob=null,recT=0,tI=null;
const mB=document.getElementById('micBtn'),mS=document.getElementById('micStatus'),mSB=document.getElementById('micSubmitBtn');
const wb=document.getElementById('waveformBox'),wc=document.getElementById('waveCanvas'),wcCtx=wc.getContext('2d'),rt=document.getElementById('recTimer');
function encodeWAV(samples,sr){const buf=new ArrayBuffer(44+samples.length*2),view=new DataView(buf);
function ws(o,s){for(let i=0;i<s.length;i++)view.setUint8(o+i,s.charCodeAt(i));}
ws(0,'RIFF');view.setUint32(4,36+samples.length*2,true);ws(8,'WAVE');ws(12,'fmt ');
view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,sr,true);view.setUint32(28,sr*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);ws(36,'data');view.setUint32(40,samples.length*2,true);
let off=44;for(let i=0;i<samples.length;i++){const s=Math.max(-1,Math.min(1,samples[i]));view.setInt16(off,s<0?s*0x8000:s*0x7FFF,true);off+=2;}
return new Blob([buf],{type:'audio/wav'});}
function drawWave(){if(!an)return;const bl=an.frequencyBinCount,data=new Uint8Array(bl);an.getByteTimeDomainData(data);
const dpr=window.devicePixelRatio||1;wc.width=wc.offsetWidth*dpr;wc.height=wc.offsetHeight*dpr;wcCtx.scale(dpr,dpr);
const w=wc.offsetWidth,h=wc.offsetHeight;wcCtx.clearRect(0,0,w,h);wcCtx.lineWidth=2;wcCtx.strokeStyle='#6366f1';wcCtx.beginPath();
const sw=w/bl;let x=0;for(let i=0;i<bl;i++){const v=data[i]/128.0,y=v*h/2;if(i===0)wcCtx.moveTo(x,y);else wcCtx.lineTo(x,y);x+=sw;}wcCtx.lineTo(w,h/2);wcCtx.stroke();if(rec)requestAnimationFrame(drawWave);}
async function toggleMic(){if(!rec){try{ms=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true}});ac=new(window.AudioContext||window.webkitAudioContext)();const src=ac.createMediaStreamSource(ms);an=ac.createAnalyser();an.fftSize=2048;src.connect(an);sp=ac.createScriptProcessor(4096,1,1);bufs=[];sp.onaudioprocess=function(e){if(rec)bufs.push(new Float32Array(e.inputBuffer.getChannelData(0)));};src.connect(sp);sp.connect(ac.destination);rec=true;mB.classList.add('recording');document.getElementById('micIcon').textContent='⏹️';mS.textContent='🔴 录音中... 再点一下结束';mSB.disabled=true;wb.classList.add('active');recT=Date.now();tI=setInterval(()=>{rt.textContent='⏱ '+((Date.now()-recT)/1000).toFixed(1)+' s';},100);drawWave();}catch(e){mS.textContent='❌ 无法访问麦克风: '+e.message;}}else{rec=false;sp.disconnect();ms.getTracks().forEach(t=>t.stop());if(tI){clearInterval(tI);tI=null;}rt.textContent='✅ '+((Date.now()-recT)/1000).toFixed(1)+' s';mB.classList.remove('recording');document.getElementById('micIcon').textContent='🎙️';wb.classList.remove('active');
const total=bufs.reduce((acc,b)=>acc+b.length,0);const merged=new Float32Array(total);let off=0;for(const b of bufs){merged.set(b,off);off+=b.length;}blob=encodeWAV(merged,ac.sampleRate);const dur=(total/ac.sampleRate).toFixed(1);mS.textContent='✅ 录音完成（'+dur+' 秒），点击下方按钮识别';mSB.disabled=false;}}
async function sendMicAudio(){if(!blob)return;const ld=document.getElementById('micLoader'),err=document.getElementById('micError');ld.classList.add('active');err.style.display='none';document.getElementById('result').classList.remove('show');const fd=new FormData();fd.append('audio',blob,'recording.wav');try{const resp=await fetch('/recognize',{method:'POST',body:fd});const data=await resp.json();ld.classList.remove('active');if(data.success)showResult(data);else{err.textContent='❌ '+(data.error||'识别失败');err.style.display='block';}}catch(e){ld.classList.remove('active');err.textContent='❌ 网络错误: '+e.message;err.style.display='block';}}
function showResult(data){const r=document.getElementById('result');r.classList.add('show');const icon=EI[data.top_label]||'❓',color=EC[data.top_label]||'#7dd3fc',pct=(data.top_score*100).toFixed(1);document.getElementById('topEmoji').textContent=icon;document.getElementById('topLabel').textContent=data.top_emotion;document.getElementById('topLabel').style.color=color;document.getElementById('topScore').textContent='置信度 '+pct+'%';document.getElementById('topBarFill').style.width=pct+'%';document.getElementById('topBarFill').style.background='linear-gradient(90deg,'+color+','+color+'aa)';const c=document.getElementById('barChart');c.innerHTML='';for(const item of data.all_results){const col=EC[item.label]||'#7dd3fc',ic=EI[item.label]||'❓',p=(item.score*100).toFixed(1),show=p>10?p+'%':'';c.innerHTML+='<div class="bar-row"><span class="bar-emoji">'+ic+'</span><span class="bar-label">'+item.emotion.split(' ')[0]+'</span><div class="bar-track"><div class="bar-fill" style="background:'+col+';width:'+p+'%">'+show+'</div></div><span class="bar-pct">'+p+'%</span></div>';}r.scrollIntoView({behavior:'smooth',block:'nearest'});}
</script></body></html>"""

app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/recognize", methods=["POST"])
def recognize():
    try:
        af = request.files["audio"]
        suf = os.path.splitext(af.filename)[1] if af.filename else ".wav"
        if not suf: suf = ".wav"
        with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
            af.save(tmp.name)
            tp = tmp.name
        result = recognize_emotion(tp)
        try: os.remove(tp)
        except: pass
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def open_browser():
    time.sleep(2)
    webbrowser.open("http://localhost:7860")

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  🎙️  语音情感识别系统  (Wav2Vec2 + MLP)")
    print("=" * 55)
    print("\n  正在加载模型（首次运行约需 10-30 秒）...")
    print("  浏览器将自动打开 http://localhost:7860")
    print("\n  如未自动打开，请手动访问上述地址")
    print("  按 Ctrl+C 停止服务\n" + "=" * 55 + "\n")
    load_my_model()
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=7860, debug=False, use_reloader=False)
