"""
web_app.py
==========
Özgün geliştirme: Canlı 2B görsel ortam (web panosu).

Tarayıcıda çalışan, gerçek Python ajanını kullanan bir kontrol panosu. Doğal
dilde komut yazarsınız; drone, engeller, uçuşa yasak bölgeler ve uçuş izi
tepeden görünüşte CANLI güncellenir; telemetri ve karar/gerekçe gösterilir.

Yalnızca standart kütüphane (http.server) kullanır — ek bağımlılık yoktur.

Çalıştırma:
    python web_app.py                 # http://127.0.0.1:8000
    python web_app.py --port 8080 --llm
Tarayıcıda açın: http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from uav_assistant import DronePilotAgent, DroneSimulator
from uav_assistant.safety import MAX_HORIZONTAL_RANGE

_lock = threading.Lock()


def build_agent(use_llm: bool = False) -> DronePilotAgent:
    sim = DroneSimulator()
    sim.load_demo_environment()
    return DronePilotAgent(simulator=sim, use_llm=use_llm, log_dir="logs")


def snapshot(agent: DronePilotAgent) -> dict:
    st = agent.sim.get_state()
    return {
        "telemetry": st.to_dict(),
        "trail": [list(p) for p in agent.sim.trail],
        "keepouts": [k.to_dict() for k in agent.sim.keepouts],
        "drops": [list(d) for d in agent.sim.drops],
        "observe_zone": (list(agent.sim.observe_zone)
                         if agent.sim.observe_zone else None),
        "home": [st.home_x, st.home_y],
        "max_range": MAX_HORIZONTAL_RANGE,
        "max_altitude": agent.sim.max_altitude,
        "mode_label": agent.active_mode,
    }


def process(agent: DronePilotAgent, command: str) -> dict:
    with _lock:
        res = agent.handle(command)
        snap = snapshot(agent)
    snap.update({"reply": res["reply"], "decision": res["decision"],
                 "action": res["action"]})
    return snap


PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>İHA GCS // Taktik Pano</title>
<style>
  :root{
    --bg:#04120b; --panel:#07190f; --panel2:#0a2114; --edge:#12563a;
    --grn:#38ffa3; --grn-dim:#1f8f60; --amb:#ffb000; --red:#ff5a52;
    --blu:#58e6ff; --txt:#bff5d8; --mut:#4f8a6d;
    --mono:'Courier New',ui-monospace,SFMono-Regular,Menlo,monospace;
    color-scheme:dark;
  }
  *{box-sizing:border-box;}
  body{margin:0;background:
      radial-gradient(1200px 700px at 70% -10%,#0a2a1a 0,transparent 60%),
      var(--bg);
    color:var(--txt);font-family:var(--mono);letter-spacing:.3px;
    text-shadow:0 0 6px rgba(56,255,163,.18);}
  /* CRT tarama çizgileri */
  body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:9;
    background:repeating-linear-gradient(0deg,rgba(0,0,0,.16) 0,rgba(0,0,0,.16) 1px,transparent 2px,transparent 3px);
    mix-blend-mode:multiply;opacity:.5;}
  header{display:flex;align-items:center;gap:14px;padding:10px 18px;
    background:linear-gradient(180deg,#0a2416,#061710);
    border-bottom:1px solid var(--edge);box-shadow:0 0 24px rgba(56,255,163,.08);}
  header .brand{font-weight:700;font-size:16px;color:var(--grn);text-transform:uppercase;}
  header .brand small{color:var(--mut);font-weight:400;font-size:11px;display:block;letter-spacing:2px;}
  .leds{display:flex;gap:16px;margin-left:auto;font-size:11px;text-transform:uppercase;}
  .led{display:flex;align-items:center;gap:6px;color:var(--mut);}
  .led i{width:9px;height:9px;border-radius:50%;background:var(--grn-dim);
    box-shadow:0 0 8px currentColor;display:inline-block;}
  .led.on i{background:var(--grn);color:var(--grn);animation:pulse 1.6s infinite;}
  .led.warn i{background:var(--amb);color:var(--amb);}
  .led.off i{background:#20402e;box-shadow:none;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  #modeTag{color:var(--amb);font-size:12px;}
  .wrap{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:14px;padding:14px;}
  @media(max-width:900px){.wrap{grid-template-columns:1fr;}}
  .panel{background:linear-gradient(180deg,var(--panel2),var(--panel));
    border:1px solid var(--edge);border-radius:10px;position:relative;
    box-shadow:inset 0 0 40px rgba(0,0,0,.5),0 0 0 1px rgba(56,255,163,.05);}
  .panel>.hd{padding:7px 12px;font-size:11px;letter-spacing:2px;text-transform:uppercase;
    color:var(--grn-dim);border-bottom:1px solid #10402a;display:flex;justify-content:space-between;}
  .panel>.bd{padding:12px;}
  /* radar */
  .radarwrap{position:relative;}
  #cv{display:block;width:100%;height:auto;border-radius:0 0 10px 10px;cursor:crosshair;}
  .radar-ov{position:absolute;bottom:10px;left:12px;font-size:11px;color:var(--grn-dim);
    pointer-events:none;text-transform:uppercase;letter-spacing:1px;}
  #readout{position:absolute;top:10px;right:12px;font-size:11px;color:var(--amb);
    pointer-events:none;text-align:right;line-height:1.5;}
  .hint{position:absolute;bottom:10px;right:12px;font-size:10px;color:var(--mut);pointer-events:none;}
  /* telemetri */
  .tele{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
  .cell{background:#061510;border:1px solid #10402a;border-radius:7px;padding:8px 10px;}
  .cell .k{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:1px;}
  .cell .v{font-size:18px;color:var(--grn);font-weight:700;}
  .cell .v small{font-size:11px;color:var(--grn-dim);}
  .bat{grid-column:1/-1;}
  .batbar{height:9px;border-radius:5px;background:#0b2417;overflow:hidden;margin-top:5px;
    border:1px solid #10402a;}
  .batbar i{display:block;height:100%;background:linear-gradient(90deg,var(--grn),var(--blu));
    box-shadow:0 0 10px var(--grn);transition:width .4s;}
  /* sohbet */
  #chat{height:300px;overflow:auto;display:flex;flex-direction:column;gap:8px;
    padding:10px 4px 0 0;margin-top:10px;border-top:1px solid #10402a;
    scrollbar-width:thin;scrollbar-color:#1f8f60 transparent;}
  #chat::-webkit-scrollbar{width:6px;}#chat::-webkit-scrollbar-thumb{background:#1f8f60;border-radius:3px;}
  .msg{max-width:88%;padding:7px 10px;border-radius:9px;font-size:13px;line-height:1.4;
    white-space:pre-wrap;word-break:break-word;animation:in .2s ease;}
  @keyframes in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  .msg .t{font-size:9px;color:var(--mut);letter-spacing:1px;display:block;margin-bottom:2px;}
  .u{align-self:flex-end;background:linear-gradient(180deg,#123f28,#0c2c1c);
    border:1px solid #1f8f60;color:#d9ffe9;}
  .a{align-self:flex-start;background:#061510;border:1px solid #10402a;}
  .a.approved{border-left:3px solid var(--grn);}
  .a.rejected,.a.error{border-left:3px solid var(--red);color:#ffd9d6;}
  .a.clarify{border-left:3px solid var(--amb);}
  .a.mission_plan{border-left:3px solid var(--blu);}
  .badge{font-size:9px;padding:1px 5px;border-radius:4px;margin-left:6px;letter-spacing:1px;
    text-transform:uppercase;vertical-align:middle;}
  .b-approved{background:#123f28;color:var(--grn);}
  .b-rejected,.b-error{background:#3f1512;color:var(--red);}
  .b-clarify{background:#3f2f0a;color:var(--amb);}
  .b-mission_plan{background:#0a2f3f;color:var(--blu);}
  /* komut girişi */
  form{display:flex;gap:8px;margin-top:0;}
  #cmd{flex:1;padding:10px;border-radius:7px;border:1px solid var(--edge);
    background:#04120b;color:var(--grn);font-family:var(--mono);font-size:13px;outline:none;}
  #cmd:focus{border-color:var(--grn);box-shadow:0 0 12px rgba(56,255,163,.25);}
  form button{padding:10px 16px;border:1px solid var(--grn);border-radius:7px;
    background:#0c2c1c;color:var(--grn);font-family:var(--mono);font-weight:700;
    text-transform:uppercase;letter-spacing:1px;cursor:pointer;}
  form button:hover{background:#123f28;box-shadow:0 0 14px rgba(56,255,163,.3);}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;}
  .chips button{background:#061510;color:var(--grn-dim);border:1px solid #10402a;
    border-radius:6px;font-family:var(--mono);font-size:11px;padding:5px 9px;cursor:pointer;}
  .chips button:hover{color:var(--grn);border-color:var(--grn);}
  .tools{display:flex;gap:6px;}
  .tools button{background:transparent;border:1px solid #10402a;color:var(--mut);
    border-radius:5px;font-family:var(--mono);font-size:10px;padding:2px 7px;cursor:pointer;}
  .tools button:hover{color:var(--amb);border-color:var(--amb);}
  .tools button.on{color:var(--grn);border-color:var(--grn);}
  #mic{padding:10px 12px;border:1px solid var(--edge);border-radius:7px;
    background:#04120b;color:var(--grn-dim);font-size:15px;cursor:pointer;}
  #mic:hover{color:var(--grn);border-color:var(--grn);}
  #mic.listening{color:#ff5a52;border-color:#ff5a52;
    animation:micpulse 1s infinite;}
  @keyframes micpulse{0%,100%{box-shadow:0 0 0 0 rgba(255,90,82,.5);}
    50%{box-shadow:0 0 0 6px rgba(255,90,82,0);}}
  .vstat{font-size:11px;color:var(--mut);min-height:14px;margin-top:6px;
    letter-spacing:.5px;}
  .vstat.rec{color:#ff5a52;} .vstat.err{color:var(--amb);}
</style></head>
<body>
<header>
  <div class="brand">İHA · GCS<small>YER KONTROL İSTASYONU</small></div>
  <span id="modeTag"></span>
  <div class="leds">
    <div class="led on" id="ledLink"><i></i>BAĞLANTI</div>
    <div class="led" id="ledAir"><i></i>HAVADA</div>
    <div class="led" id="ledBat"><i></i>BATARYA</div>
  </div>
</header>
<div class="wrap">
  <div class="panel radarwrap">
    <div class="hd"><span>TAKTİK RADAR // TEPEDEN GÖRÜNÜM</span><span id="zoomLbl">ZOOM 1.0x</span></div>
    <canvas id="cv" width="760" height="600"></canvas>
    <div id="readout"></div>
    <div class="radar-ov" id="scaleLbl"></div>
    <div class="hint">tekerlek: zoom · sürükle: kaydır · çift tık: sıfırla</div>
  </div>
  <div class="side">
    <div class="panel"><div class="hd"><span>TELEMETRİ</span><span id="clk"></span></div>
      <div class="bd"><div class="tele" id="tele"></div></div></div>
    <div class="panel"><div class="hd"><span>KOMUT KONSOLU / SOHBET</span>
        <span class="tools"><button id="ttsToggle" title="Asistan sesli yanıt">🔊 SES</button>
          <button id="clrChat">TEMİZLE</button></span></div>
      <div class="bd">
        <form id="f"><input id="cmd" autocomplete="off"
          placeholder="Komut yazın ya da 🎙 ile söyleyin: 20 metreye kalk, 12,23'ü gözlemle..."/>
          <button type="button" id="mic" title="Sesli komut (bas-konuş)">🎙</button>
          <button>Gönder</button></form>
        <div class="vstat" id="voiceStat"></div>
        <div class="chips">
          <button data-c="20 metreye kalk">▲ kalk</button>
          <button data-c="35 20 noktasına git">◎ git 35,20</button>
          <button data-c="10 sağa git">▶ sağa 10</button>
          <button data-c="40,25 noktasını 12 metre çapında dolaşıp gözlemle 2 tur at">🔭 gözlem</button>
          <button data-c="40 20 noktasına destek bırak">📦 destek bırak</button>
          <button data-c="önceki konuma dön">↩ önceki konum</button>
          <button data-c="eve dön">⌂ eve dön</button>
          <button data-c="bataryayı şarj et">🔋 şarj et</button>
        </div>
        <div id="chat"></div>
      </div>
    </div>
  </div>
</div>
<script>
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const W=cv.width, H=cv.height, PAD=54;
let view={zoom:1, ox:0, oy:0};      // kullanıcı zoom/pan
let drag=null, lastData=null, sweep=0, mouseW=null;
// --- oynatma (animasyon) durumu: rota adım adım çizilir ---
let scene=null, shownTrail=[], animQueue=[], dronePos=[0,0,0], teleFinal=null;
function currentView(){
  if(!scene) return null;
  const t=scene.telemetry, p=dronePos;
  return Object.assign({}, scene, {
    trail: shownTrail,
    telemetry: Object.assign({}, t, {x:p[0], y:p[1],
      altitude:(p[2]!=null?p[2]:t.altitude)}),
    // gözlem ışıldağı sadece o daireye ulaşınca yansın
    observe_zone: animQueue.length? null : scene.observe_zone,
  });
}
function renderFrame(){const v=currentView(); if(!v)return; lastData=v; draw(v); tele(v);}
function applyResponse(d){
  const start=shownTrail.length;
  const fresh=(d.trail||[]).slice(start);
  if(fresh.length) animQueue.push(...fresh);
  else if(d.telemetry) dronePos=[d.telemetry.x,d.telemetry.y,d.telemetry.altitude];
  scene=d; teleFinal=d.telemetry;
}
function stepAnim(){
  if(!animQueue.length) return;
  const q=animQueue.length;
  const n=q>240?4:(q>140?3:(q>80?2:1));   // uzun görevde biraz hızlan
  for(let i=0;i<n && animQueue.length;i++){
    const p=animQueue.shift(); shownTrail.push(p); dronePos=p;
  }
  if(!animQueue.length && teleFinal)
    dronePos=[teleFinal.x,teleFinal.y,teleFinal.altitude];
}

function baseFit(d){
  let xs=[0], ys=[0];
  d.trail.forEach(p=>{xs.push(p[0]);ys.push(p[1]);});
  d.keepouts.forEach(k=>{xs.push(k.x-k.radius,k.x+k.radius);ys.push(k.y-k.radius,k.y+k.radius);});
  xs.push(d.home[0]-d.max_range*0.15,d.home[0]+d.max_range*0.15);
  ys.push(d.home[1]-d.max_range*0.15,d.home[1]+d.max_range*0.15);
  let minx=Math.min(...xs),maxx=Math.max(...xs),miny=Math.min(...ys),maxy=Math.max(...ys);
  if(maxx-minx<100){let c=(minx+maxx)/2;minx=c-50;maxx=c+50;}
  if(maxy-miny<100){let c=(miny+maxy)/2;miny=c-50;maxy=c+50;}
  const s=Math.min((W-2*PAD)/(maxx-minx),(H-2*PAD)/(maxy-miny));
  return {s,minx,miny,maxx,maxy};
}
function proj(d){
  const b=baseFit(d), s=b.s*view.zoom;
  const cx=(b.minx+b.maxx)/2, cy=(b.miny+b.maxy)/2;
  const tx=x=>W/2+(x-cx)*s+view.ox;
  const ty=y=>H/2-(y-cy)*s+view.oy;
  const inv=(px,py)=>[cx+(px-view.ox-W/2)/s, cy-(py-view.oy-H/2)/s];
  return {s,tx,ty,inv};
}
function ring(f,cx,cy,rWorld,col,dash){
  ctx.beginPath();ctx.arc(f.tx(cx),f.ty(cy),rWorld*f.s,0,7);
  ctx.strokeStyle=col;ctx.lineWidth=1;ctx.setLineDash(dash||[]);ctx.stroke();ctx.setLineDash([]);
}
function draw(d){
  if(!d)return; lastData=d;
  const f=proj(d);
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle='#04120b';ctx.fillRect(0,0,W,H);
  // ince ızgara
  ctx.strokeStyle='rgba(31,143,96,.12)';ctx.lineWidth=1;
  for(let gx=0;gx<=W;gx+=38){ctx.beginPath();ctx.moveTo(gx,0);ctx.lineTo(gx,H);ctx.stroke();}
  for(let gy=0;gy<=H;gy+=38){ctx.beginPath();ctx.moveTo(0,gy);ctx.lineTo(W,gy);ctx.stroke();}
  const hx=f.tx(d.home[0]), hy=f.ty(d.home[1]);
  // menzil halkaları (ev merkezli)
  const steps=4;
  for(let i=1;i<=steps;i++){
    const rr=d.max_range*i/steps;
    ring(f,d.home[0],d.home[1],rr,'rgba(56,255,163,.16)',[3,5]);
    ctx.fillStyle='rgba(56,255,163,.35)';ctx.font='10px "Courier New",monospace';ctx.textAlign='left';
    ctx.fillText(Math.round(rr)+'m', hx+2, hy-rr*f.s+12);
  }
  // dış menzil sınırı
  ring(f,d.home[0],d.home[1],d.max_range,'rgba(255,90,82,.5)',[8,6]);
  // pusula çizgileri
  ctx.strokeStyle='rgba(31,143,96,.18)';ctx.beginPath();
  ctx.moveTo(hx,hy-d.max_range*f.s);ctx.lineTo(hx,hy+d.max_range*f.s);
  ctx.moveTo(hx-d.max_range*f.s,hy);ctx.lineTo(hx+d.max_range*f.s,hy);ctx.stroke();
  ctx.fillStyle='#38ffa3';ctx.textAlign='center';ctx.font='11px "Courier New",monospace';
  ctx.fillText('K', hx, hy-d.max_range*f.s-4);
  ctx.fillText('G', hx, hy+d.max_range*f.s+14);
  ctx.fillText('D', hx+d.max_range*f.s+10, hy+4);
  ctx.fillText('B', hx-d.max_range*f.s-10, hy+4);
  // radar tarama süpürmesi. Aktif GÖZLEM alanı varsa ışıldak ORADA döner.
  const oz=d.observe_zone;
  if(oz){
    const ox=f.tx(oz[0]), oy=f.ty(oz[1]);
    const orad=Math.max(oz[2]*f.s, 10);
    const sR=Math.max(orad*1.8, 52);
    // dönen tarama ışıldağı (kama)
    ctx.save();
    ctx.beginPath();ctx.moveTo(ox,oy);ctx.arc(ox,oy,sR,sweep,sweep+0.6);ctx.closePath();
    ctx.fillStyle='rgba(255,176,0,.18)';ctx.fill();
    ctx.beginPath();ctx.moveTo(ox,oy);
    ctx.lineTo(ox+Math.cos(sweep)*sR, oy+Math.sin(sweep)*sR);
    ctx.strokeStyle='rgba(255,176,0,.7)';ctx.lineWidth=1.5;ctx.stroke();
    ctx.restore();
    // nabız atan gözlem halkası (yörünge yarıçapı)
    const pr=orad+3*Math.sin(sweep*3);
    ctx.beginPath();ctx.arc(ox,oy,pr,0,7);
    ctx.strokeStyle='rgba(255,176,0,.85)';ctx.lineWidth=1.5;ctx.setLineDash([5,4]);
    ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle='#ffb000';ctx.font='10px "Courier New",monospace';ctx.textAlign='center';
    ctx.fillText('🔭 GÖZLEM', ox, oy-sR-4);
  } else {
    // ev merkezli hafif ambiyans süpürmesi
    const sweepR=d.max_range*f.s;
    ctx.save();ctx.beginPath();ctx.arc(hx,hy,sweepR,sweep,sweep+0.5);ctx.lineTo(hx,hy);ctx.closePath();
    ctx.fillStyle='rgba(56,255,163,.06)';ctx.fill();ctx.restore();
  }
  // keepout bölgeleri
  d.keepouts.forEach(k=>{
    ctx.beginPath();ctx.arc(f.tx(k.x),f.ty(k.y),k.radius*f.s,0,7);
    if(k.kind==='nofly'){ctx.fillStyle='rgba(255,90,82,.14)';ctx.strokeStyle='#ff5a52';ctx.setLineDash([6,4]);}
    else{ctx.fillStyle='rgba(255,176,0,.14)';ctx.strokeStyle='#ffb000';ctx.setLineDash([]);}
    ctx.lineWidth=1.5;ctx.fill();ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=k.kind==='nofly'?'#ff5a52':'#ffb000';ctx.font='10px "Courier New",monospace';ctx.textAlign='center';
    ctx.fillText((k.kind==='nofly'?'⛔ ':'▲ ')+k.name, f.tx(k.x), f.ty(k.y)-k.radius*f.s-5);
  });
  // bırakılan destek/kargo paketleri
  (d.drops||[]).forEach(dp=>{
    const X=f.tx(dp[0]),Y=f.ty(dp[1]);
    ctx.fillStyle='#ffb000';ctx.strokeStyle='#04120b';ctx.lineWidth=2;
    ctx.beginPath();ctx.rect(X-5,Y-5,10,10);ctx.fill();ctx.stroke();
    ctx.strokeStyle='#ffb000';ctx.lineWidth=1;ctx.beginPath();
    ctx.moveTo(X-5,Y);ctx.lineTo(X+5,Y);ctx.moveTo(X,Y-5);ctx.lineTo(X,Y+5);ctx.stroke();
    ctx.fillStyle='#ffb000';ctx.font='9px "Courier New",monospace';ctx.textAlign='center';
    ctx.fillText('📦 '+(dp[2]||''), X, Y+16);
  });
  // uçuş izi
  if(d.trail.length){
    ctx.beginPath();ctx.strokeStyle='rgba(88,230,255,.9)';ctx.lineWidth=2;
    ctx.shadowColor='#58e6ff';ctx.shadowBlur=8;
    d.trail.forEach((p,i)=>{const X=f.tx(p[0]),Y=f.ty(p[1]);i?ctx.lineTo(X,Y):ctx.moveTo(X,Y);});
    ctx.stroke();ctx.shadowBlur=0;
    ctx.fillStyle='rgba(88,230,255,.55)';
    d.trail.forEach(p=>{ctx.beginPath();ctx.arc(f.tx(p[0]),f.ty(p[1]),2,0,7);ctx.fill();});
  }
  // EV
  ctx.fillStyle='#38ffa3';ctx.strokeStyle='#04120b';ctx.lineWidth=2;
  ctx.beginPath();ctx.moveTo(hx,hy-8);ctx.lineTo(hx+7,hy);ctx.lineTo(hx,hy+8);ctx.lineTo(hx-7,hy);ctx.closePath();
  ctx.fill();ctx.stroke();
  ctx.fillStyle='#38ffa3';ctx.font='10px "Courier New",monospace';ctx.fillText('EV', hx, hy+20);
  // DRONE + yön
  const t=d.telemetry, dx=f.tx(t.x), dy=f.ty(t.y);
  let ang=-Math.PI/2;
  if(d.trail.length>1){const a=d.trail[d.trail.length-2],b=d.trail[d.trail.length-1];
    if(a[0]!==b[0]||a[1]!==b[1])ang=Math.atan2(-(b[1]-a[1]),(b[0]-a[0]));}
  ctx.save();ctx.translate(dx,dy);
  const pr=10+3*Math.sin(sweep*4);          // pulse
  ctx.beginPath();ctx.arc(0,0,pr+6,0,7);ctx.strokeStyle='rgba(56,255,163,.4)';ctx.lineWidth=1;ctx.stroke();
  ctx.rotate(ang);
  ctx.beginPath();ctx.moveTo(13,0);ctx.lineTo(-7,7);ctx.lineTo(-3,0);ctx.lineTo(-7,-7);ctx.closePath();
  ctx.fillStyle='#eafff4';ctx.shadowColor='#38ffa3';ctx.shadowBlur=12;ctx.fill();ctx.shadowBlur=0;
  ctx.restore();
  const bearing=((Math.round((90-ang*180/Math.PI))%360)+360)%360;
  ctx.fillStyle='#eafff4';ctx.textAlign='left';ctx.font='11px "Courier New",monospace';
  ctx.fillText('İHA '+t.x+','+t.y+' · '+t.altitude+'m · '+bearing+'°', dx+14, dy-10);
  // fare crosshair
  if(mouseW){
    ctx.strokeStyle='rgba(255,176,0,.4)';ctx.setLineDash([4,4]);ctx.beginPath();
    ctx.moveTo(mouseW.px,0);ctx.lineTo(mouseW.px,H);ctx.moveTo(0,mouseW.py);ctx.lineTo(W,mouseW.py);
    ctx.stroke();ctx.setLineDash([]);
  }
  // etiketler
  document.getElementById('scaleLbl').textContent=
    'ÖLÇEK ~'+Math.round(50/f.s)+'m/kare · MENZİL '+Math.round(d.max_range)+'m';
  document.getElementById('zoomLbl').textContent='ZOOM '+view.zoom.toFixed(1)+'x';
}
function tele(d){
  const t=d.telemetry;
  const dist=Math.round(Math.hypot(t.x-d.home[0],t.y-d.home[1]));
  const rangePct=Math.min(100,Math.round(dist/d.max_range*100));
  const cells=[
    ['KONUM X',t.x,'m'],['KONUM Y',t.y,'m'],
    ['İRTİFA',t.altitude,'m'],['MOD',t.mode,''],
    ['EVE UZAKLIK',dist,'m'],['MENZİL KUL.','%'+rangePct,''],
    ['KALAN YÜK',(t.payloads_remaining!=null?t.payloads_remaining:'-'),'paket'],
    ['BIRAKILAN',(d.drops||[]).length,'nokta'],
  ];
  let html=cells.map(c=>'<div class="cell"><div class="k">'+c[0]+
    '</div><div class="v">'+c[1]+'<small> '+c[2]+'</small></div></div>').join('');
  const bat=Math.round(t.battery);
  const bcol=bat<25?'#ff5a52':bat<50?'#ffb000':'#38ffa3';
  html+='<div class="cell bat"><div class="k">BATARYA · '+(t.in_air?'HAVADA':'YERDE')+
    '</div><div class="v">%'+bat+'</div><div class="batbar"><i style="width:'+bat+
    '%;background:'+bcol+';box-shadow:0 0 10px '+bcol+'"></i></div></div>';
  document.getElementById('tele').innerHTML=html;
  document.getElementById('modeTag').textContent=d.mode_label?('▷ '+d.mode_label):'';
  // LED'ler
  document.getElementById('ledAir').className='led '+(t.in_air?'on':'off');
  const lb=document.getElementById('ledBat');
  lb.className='led '+(bat<25?'warn':bat<50?'warn':'on');
}
/* ---------- SOHBET GEÇMİŞİ ---------- */
const CHATKEY='iha_chat_v1';
let history=[];
try{history=JSON.parse(localStorage.getItem(CHATKEY)||'[]');}catch(e){history=[];}
function saveHist(){try{localStorage.setItem(CHATKEY,JSON.stringify(history.slice(-200)));}catch(e){}}
function now(){const d=new Date();return d.toTimeString().slice(0,8);}
function bubble(m){
  const el=document.getElementById('chat');
  const div=document.createElement('div');
  if(m.role==='user'){div.className='msg u';
    div.innerHTML='<span class="t">SİZ · '+m.t+'</span>'+esc(m.text);}
  else{const dc=m.decision||'gray';
    div.className='msg a '+dc;
    const badge=m.decision?'<span class="badge b-'+m.decision+'">'+dc+'</span>':'';
    div.innerHTML='<span class="t">İHA · '+m.t+badge+'</span>'+esc(m.text);}
  el.appendChild(div);el.scrollTop=el.scrollHeight;
}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function renderHist(){document.getElementById('chat').innerHTML='';history.forEach(bubble);}
function pushMsg(m){m.t=m.t||now();history.push(m);bubble(m);saveHist();}

async function send(cmd){
  pushMsg({role:'user',text:cmd});
  try{
    const r=await fetch('/command',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({command:cmd})});
    const d=await r.json();
    applyResponse(d);
    pushMsg({role:'assistant',text:d.reply||'(yanıt yok)',decision:d.decision});
    speak(d.reply||'');
  }catch(e){
    pushMsg({role:'assistant',text:'BAĞLANTI HATASI: '+e.message,decision:'error'});
    document.getElementById('ledLink').className='led warn';
  }
}
document.getElementById('f').addEventListener('submit',e=>{
  e.preventDefault();const i=document.getElementById('cmd');
  if(i.value.trim()){send(i.value.trim());i.value='';}});
document.querySelectorAll('.chips button').forEach(b=>
  b.addEventListener('click',()=>send(b.dataset.c)));
document.getElementById('clrChat').addEventListener('click',()=>{
  history=[];saveHist();renderHist();});
/* ---------- SES: konuşma tanıma (STT) + sesli yanıt (TTS) ---------- */
let ttsOn=false; try{ttsOn=localStorage.getItem('iha_tts')==='1';}catch(e){}
const ttsBtn=document.getElementById('ttsToggle');
function refreshTts(){ttsBtn.classList.toggle('on',ttsOn);
  ttsBtn.textContent=ttsOn?'🔊 SES AÇIK':'🔇 SES';}
refreshTts();
ttsBtn.addEventListener('click',()=>{ttsOn=!ttsOn;
  try{localStorage.setItem('iha_tts',ttsOn?'1':'0');}catch(e){}
  if(!ttsOn && window.speechSynthesis)speechSynthesis.cancel();
  refreshTts();});
function speak(text){
  if(!ttsOn || !('speechSynthesis' in window) || !text)return;
  // İlk satırı, emoji/simgeleri temizleyerek seslendir (kısa ve net).
  let line=text.split('\n')[0].replace(/[^\p{L}\p{N}\s.,%:()\-]/gu,'').trim();
  if(!line)return;
  speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(line);
  u.lang='tr-TR'; u.rate=1.05; u.pitch=1;
  const v=speechSynthesis.getVoices().find(x=>x.lang&&x.lang.startsWith('tr'));
  if(v)u.voice=v;
  speechSynthesis.speak(u);
}
// --- kısa bip sesleri (Web Audio; dosya gerekmez) ---
let actx=null;
function beep(freq,dur,when){
  try{
    if(!actx)actx=new (window.AudioContext||window.webkitAudioContext)();
    if(actx.state==='suspended')actx.resume();
    const o=actx.createOscillator(), g=actx.createGain();
    o.type='sine'; o.frequency.value=freq; o.connect(g); g.connect(actx.destination);
    const t=actx.currentTime+(when||0);
    g.gain.setValueAtTime(0.0001,t);
    g.gain.exponentialRampToValueAtTime(0.3,t+0.012);
    g.gain.exponentialRampToValueAtTime(0.0001,t+dur);
    o.start(t); o.stop(t+dur+0.03);
  }catch(e){}
}
const beepStart=()=>{beep(760,0.12,0); beep(1040,0.13,0.11);};  // yükselen: başladı
const beepStop =()=>{beep(880,0.12,0); beep(560,0.15,0.11);};   // alçalan: bitti
const beepErr  =()=>{beep(300,0.28,0);};
// --- durum satırı ---
const vstat=document.getElementById('voiceStat');
let vstatTimer=null;
function setStat(msg,cls){
  vstat.textContent=msg; vstat.className='vstat '+(cls||'');
  if(vstatTimer)clearTimeout(vstatTimer);
  if(cls!=='rec'){vstatTimer=setTimeout(()=>{if(!listening){vstat.textContent='';
    vstat.className='vstat';}},4000);}
}
// Konuşma tanıma (Web Speech API — Chrome/Edge)
const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
const mic=document.getElementById('mic');
let rec=null, listening=false;
const ERRTR={'not-allowed':'Mikrofon izni reddedildi. Tarayıcı adres çubuğundaki 🔒/🎙 simgesinden izin verin.',
  'service-not-allowed':'Mikrofon izni engelli (tarayıcı ayarları).',
  'no-speech':'Ses algılanamadı, tekrar deneyin.',
  'audio-capture':'Mikrofon bulunamadı. Bir mikrofon bağlı mı?',
  'network':'Ağ hatası (konuşma tanıma çevrimiçi çalışır).',
  'aborted':'Dinleme iptal edildi.'};
if(!SR){
  mic.disabled=true; mic.style.opacity=.4;
  mic.title='Bu tarayıcı sesli komutu desteklemiyor (Chrome/Edge önerilir)';
  setStat('⚠️ Tarayıcı sesli komutu desteklemiyor — Chrome/Edge kullanın.','err');
}else{
  rec=new SR(); rec.lang='tr-TR'; rec.interimResults=true; rec.continuous=false;
  rec.onstart=()=>{listening=true;mic.classList.add('listening');
    setStat('🎙 Dinleniyor… konuşun','rec'); beepStart();};
  rec.onresult=e=>{
    let txt='';
    for(let i=e.resultIndex;i<e.results.length;i++)txt+=e.results[i][0].transcript;
    document.getElementById('cmd').value=txt;
    if(e.results[e.results.length-1].isFinal){
      const cmd=txt.trim();
      if(cmd){document.getElementById('cmd').value='';setStat('✓ "'+cmd+'"','');send(cmd);}
    }
  };
  rec.onerror=e=>{listening=false;mic.classList.remove('listening');
    beepErr(); setStat('⚠️ '+(ERRTR[e.error]||('Ses hatası: '+e.error)),'err');};
  rec.onend=()=>{const wasListening=listening; listening=false;
    mic.classList.remove('listening');
    if(wasListening){beepStop(); if(vstat.classList.contains('rec'))setStat('','');}};
  mic.addEventListener('click',()=>{
    if(actx&&actx.state==='suspended')actx.resume();   // ses için kullanıcı jesti
    if(listening){rec.stop();return;}
    try{rec.start(); document.getElementById('cmd').focus();}
    catch(err){setStat('⚠️ Başlatılamadı: '+err.message,'err');beepErr();}
  });
}
// Sesler asenkron yüklenir; hazır olunca tetikle.
if('speechSynthesis' in window)speechSynthesis.onvoiceschanged=()=>{};
/* ---------- RADAR ETKİLEŞİM: zoom / pan / crosshair ---------- */
function cvPos(e){const r=cv.getBoundingClientRect();
  return {px:(e.clientX-r.left)*W/r.width, py:(e.clientY-r.top)*H/r.height};}
cv.addEventListener('wheel',e=>{e.preventDefault();
  const f=e.deltaY<0?1.15:1/1.15;
  view.zoom=Math.max(0.4,Math.min(8,view.zoom*f));renderFrame();},{passive:false});
cv.addEventListener('mousedown',e=>{const p=cvPos(e);drag={x:p.px,y:p.py,ox:view.ox,oy:view.oy};});
window.addEventListener('mouseup',()=>drag=null);
cv.addEventListener('mousemove',e=>{
  const p=cvPos(e);
  if(drag){view.ox=drag.ox+(p.px-drag.x);view.oy=drag.oy+(p.py-drag.y);renderFrame();}
  if(lastData){const f=proj(lastData);const w=f.inv(p.px,p.py);
    mouseW={px:p.px,py:p.py};
    document.getElementById('readout').innerHTML=
      'X '+w[0].toFixed(0)+' m<br>Y '+w[1].toFixed(0)+' m';}
});
cv.addEventListener('mouseleave',()=>{mouseW=null;document.getElementById('readout').innerHTML='';});
cv.addEventListener('dblclick',()=>{view={zoom:1,ox:0,oy:0};renderFrame();});
/* ---------- döngüler: adım-adım oynatma + süpürme ---------- */
setInterval(()=>{stepAnim();sweep=(sweep+0.06)%(Math.PI*2);renderFrame();},45);
setInterval(()=>{document.getElementById('clk').textContent=now();},1000);
renderHist();
fetch('/state').then(r=>r.json()).then(d=>{
  scene=d; shownTrail=(d.trail||[]).slice(); animQueue=[];
  const t=d.telemetry; dronePos=[t.x,t.y,t.altitude]; teleFinal=t;
  renderFrame();
}).catch(()=>{document.getElementById('ledLink').className='led warn';});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    agent: DronePilotAgent = None  # type: ignore

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/state"):
            self._json(snapshot(self.agent))
        elif self.path == "/" or self.path.startswith("/index"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/command":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            self._json(process(self.agent, str(data.get("command", ""))))
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass  # sessiz


def main():
    ap = argparse.ArgumentParser(description="İHA Canlı Web Panosu")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()
    Handler.agent = build_agent(use_llm=args.llm)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"İHA canlı pano hazır: {url}  (durdurmak için Ctrl+C)")
    print(f"[Aktif NLU modu: {Handler.agent.active_mode}]")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatılıyor.")
        srv.shutdown()


if __name__ == "__main__":
    main()
