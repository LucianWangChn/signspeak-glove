# -*- coding: utf-8 -*-
import argparse,pickle,queue,re,select,socket,sys,threading,time
from collections import deque,Counter
from pathlib import Path
try: import winsound
except Exception: winsound=None
import numpy as np
BASE=Path(__file__).resolve().parent; ROOT=BASE.parent; AUDIO=ROOT.parent/'拍摄控制台'/'audio_output'
FEATURE_ORDER=['R_Thumb','R_Index','R_Middle','R_Ring','R_Pinky','R_aX','R_aY','R_gZ','L_Thumb','L_Index','L_Middle','L_Ring','L_Pinky','L_aX','L_aY','L_gZ']
RE=re.compile(r'([RL]):Thumb:([-\d.]+),Index:([-\d.]+),Middle:([-\d.]+),Ring:([-\d.]+),Pinky:([-\d.]+),aX:([-\d.]+),aY:([-\d.]+),gZ:([-\d.]+)')
LABEL_TEXT={'1':'住院交费','2':'不用担心陪你','3':'去办手续','0':'静止'}; DELAY={'1':15.0,'2':15.0,'3':8.0}
AUDIO_MAP={'1':AUDIO/'01_hospital_payment.wav','2':AUDIO/'02_dont_worry.wav','3':AUDIO/'03_go_paperwork.wav'}
stop=False; q=queue.Queue(); latest={k:0.0 for k in FEATURE_ORDER}; win=deque(maxlen=80); last_play={'1':0,'2':0,'3':0}
def now(): return time.strftime('%H:%M:%S')
def dec(b):
    for e in ('utf-8','gbk','latin1'):
        try: return b.decode(e)
        except Exception: pass
    return b.decode('utf-8','replace')
def feat(rows):
    v=np.array([[r.get(k,0) for k in FEATURE_ORDER] for r in rows],dtype=np.float32); fs=[]
    fs+=list(v.mean(0))+list(v.std(0))+list(v.min(0))+list(v.max(0))+list(v[-1]-v[0])
    fs+=list(np.mean(np.abs(np.diff(v,axis=0)),axis=0)) if len(v)>1 else list(np.zeros(v.shape[1]))
    return np.array(fs,dtype=np.float32).reshape(1,-1)
def load_model(p):
    p=Path(p)
    if not p.exists(): print('⚠️ 模型不存在，用 --mock 可测试:',p); return None
    with p.open('rb') as f: pack=pickle.load(f)
    print('✅ 模型已加载:',p); return pack
def predict(pack):
    if pack is None or len(win)<20: return None,0
    model=pack['model'] if isinstance(pack,dict) and 'model' in pack else pack; X=feat(list(win))
    if hasattr(model,'predict_proba'):
        pr=model.predict_proba(X)[0]; i=int(np.argmax(pr)); return str(model.classes_[i]),float(pr[i])
    return str(model.predict(X)[0]),1.0
def stop_audio():
    if winsound:
        try: winsound.PlaySound(None,winsound.SND_PURGE)
        except Exception: pass
def play(label):
    p=AUDIO_MAP.get(str(label)); print(f'\n[{now()}] 🔊 播放 {label}={LABEL_TEXT.get(str(label),label)}')
    if winsound and p and p.exists(): stop_audio(); winsound.PlaySound(str(p),winsound.SND_FILENAME|winsound.SND_ASYNC)
    elif winsound: winsound.Beep(880,300)
def schedule(label,delay):
    label=str(label)
    if label=='0': return
    t=time.time()
    if t-last_play.get(label,0)<4: return
    last_play[label]=t; print(f'\n[{now()}] ✅ 识别到 {label}，{delay:.0f}秒后播放')
    threading.Timer(delay,play,args=(label,)).start()
def kb():
    global stop
    print('\n键盘：1/2 控 OLED；m1/m2/m3 模拟识别；s 停止音频；q 退出')
    while not stop:
        try: c=input('控制> ').strip().lower()
        except EOFError: break
        if c in ('q','quit','exit'): stop=True; q.put('__quit__'); break
        if c=='s': stop_audio(); continue
        if c in ('1','2'): q.put(c); continue
        if c in ('m1','m2','m3'): schedule(c[-1],DELAY[c[-1]]); continue
        print('只支持 1/2/m1/m2/m3/s/q')
def send(sock,c):
    ok=0
    for x in [c,c+'\n',c+'\r\n','T:'+c+'\n']:
        try: sock.sendall(x.encode('ascii')); ok+=1; time.sleep(.06)
        except Exception as e: print('发送失败:',e); break
    if ok: print(f'\n[{now()}] 📤 OLED命令 {c} 包数={ok}')
def update(line):
    m=RE.search(line)
    if not m: return False
    h=m.group(1); vals=list(map(float,m.groups()[1:])); names=['Thumb','Index','Middle','Ring','Pinky','aX','aY','gZ']
    for n,v in zip(names,vals): latest[f'{h}_{n}']=v
    win.append(dict(latest)); return True
def run(args):
    global stop
    pack=None if args.mock else load_model(args.model); threading.Thread(target=kb,daemon=True).start(); stable=deque(maxlen=args.stable); last=0; buf=''
    while not stop:
        try:
            print(f'[{now()}] 连接 {args.host}:{args.port} ...')
            with socket.create_connection((args.host,args.port),timeout=10) as sock:
                print('✅ 已连接，读取 R:/L:，预测并延时播放'); sock.setblocking(False)
                while not stop:
                    try:
                        while True:
                            c=q.get_nowait()
                            if c=='__quit__': stop=True; break
                            send(sock,c)
                    except queue.Empty: pass
                    r,_,_=select.select([sock],[],[],.1)
                    if r:
                        d=sock.recv(4096)
                        if not d: print('连接关闭'); break
                        buf+=dec(d); parts=re.split(r'[\r\n]+',buf); buf=parts[-1]
                        for line in parts[:-1]: update(line)
                    if not args.mock and time.time()-last>=args.predict_interval:
                        last=time.time(); lab,cf=predict(pack)
                        if lab is not None:
                            stable.append(lab if cf>=args.threshold else '0'); common,cnt=Counter(stable).most_common(1)[0]
                            sys.stdout.write(f'\r[{now()}] 预测 {lab} conf={cf:.0%} stable={common}/{cnt}   '); sys.stdout.flush()
                            if common!='0' and cnt>=max(2,int(args.stable*.7)): stable.clear(); schedule(common,DELAY.get(common,0))
        except Exception as e: print(f'[{now()}] 异常 {type(e).__name__}: {e}')
        if not stop: time.sleep(2)
    stop_audio(); print('已退出')
def main():
    ap=argparse.ArgumentParser(description='深度学习手语预测 + 延时音频 + OLED 控制')
    ap.add_argument('--host',default='127.0.0.1'); ap.add_argument('--port',type=int,default=9001)
    ap.add_argument('--model',default=str(ROOT/'collector'/'gesture_deep_model.pkl'))
    ap.add_argument('--threshold',type=float,default=.60); ap.add_argument('--stable',type=int,default=3); ap.add_argument('--predict-interval',type=float,default=.5); ap.add_argument('--mock',action='store_true')
    run(ap.parse_args())
if __name__=='__main__': main()
