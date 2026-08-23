# -*- coding: utf-8 -*-
"""服飾台帳の画面 — 一つの実体で Mac / Windows / Web / 電話を賄う。

`field_app` と同じ形にしてある: 127.0.0.1 の HTTP と標準ライブラリだけ。
ブラウザが客体なので、**枠を四つ作らない**。`--lan` のときだけ同じ LAN の
電話・タブレットから同じ画面が読める(既定は開かない)。

画面の規則は現場の道具のもの:

    確定・割れている・推論・未確定を**別の色と別の節**で出す。
    混ぜた瞬間、裁断してよいかが読めなくなる
    未確定には必ず「どうすれば閉じるか」を書く。
    「不明」とだけ出す画面は、二時に読む人に何も言っていない
    提案には**採用ボタン**を付ける。押すのは人で、押した人の名前が残る
"""
from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from . import i18n
from .garment import PARTS, Ledger

HOME = Path.home() / ".photoloset"
LEDGER = HOME / "ledger.json"
_PORT = 8910
LANG = "ja"          # serve() overrides this; see --lang

PAGE = """<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vera Atelier</title>
<style>
:root{
  --bg:#101016; --panel:#16161f; --panel2:#1b1b26; --line:#282836;
  --fg:#e9e9f2; --dim:#8a8a9d; --faint:#5b5b6e;
  --ok:#59c08a; --warn:#d9a24a; --bad:#e0645f; --sel:#5b8fd6;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);overflow:hidden;
 font:13px/1.55 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif}
#app{display:grid;height:100vh;
 grid-template-columns:minmax(150px,10%) 1fr minmax(240px,20%);
 grid-template-rows:42px 1fr 168px;
 grid-template-areas:"top top top" "rail work insp" "bot bot bot"}
#top{grid-area:top;border-bottom:1px solid var(--line);display:flex;
 align-items:center;gap:14px;padding:0 14px;background:var(--panel)}
#top b{font-weight:650;letter-spacing:.02em}
#top .proj{color:var(--dim)}
#top .sp{flex:1}
#rail{grid-area:rail;border-right:1px solid var(--line);background:var(--panel);
 padding:10px 0;overflow:auto}
#work{grid-area:work;position:relative;overflow:auto;background:var(--bg)}
#insp{grid-area:insp;border-left:1px solid var(--line);background:var(--panel);
 overflow:auto}
#bot{grid-area:bot;border-top:1px solid var(--line);background:var(--panel);
 display:grid;grid-template-columns:1fr 300px}
.step{padding:6px 14px;color:var(--dim);cursor:pointer;font-size:12px;
 border-left:2px solid transparent;display:flex;gap:8px;align-items:center}
.step:hover{background:var(--panel2);color:var(--fg)}
.step.on{color:var(--fg);border-left-color:var(--sel);background:var(--panel2)}
.step .num{color:var(--faint);font:11px ui-monospace,monospace}
.railh{padding:4px 14px 6px;color:var(--faint);font-size:10px;
 letter-spacing:.12em;text-transform:uppercase}
.tabs{display:flex;gap:6px;padding:10px 14px 0}
.tab{padding:4px 12px;border:1px solid var(--line);border-radius:999px;
 color:var(--dim);font-size:12px;cursor:pointer;background:var(--panel)}
.tab.on{color:var(--fg);border-color:var(--sel)}
#stage{display:flex;align-items:center;justify-content:center;
 min-height:calc(100% - 46px);padding:14px}
svg .hit{cursor:pointer}
svg .hit:hover .sh{stroke:var(--sel);stroke-width:2.2}
svg .sh{fill:#191924;stroke:#3a3a4c;stroke-width:1.4;
 transition:fill .12s,stroke .12s}
svg .lbl{fill:var(--dim);font:10px ui-monospace,monospace}
svg .hit.sel .sh{stroke:var(--sel);stroke-width:2.4;fill:#1f2436}
svg .st-OBSERVED .sh{fill:rgba(89,192,138,.20);stroke:var(--ok)}
svg .st-CONTESTED .sh{fill:rgba(224,100,95,.20);stroke:var(--bad)}
svg .st-INFERRED .sh{fill:rgba(217,162,74,.18);stroke:var(--warn)}
svg .st-PROPOSED .sh{stroke-dasharray:4 3;stroke:var(--dim)}
.viewsw{display:flex;gap:8px;justify-content:center;padding-bottom:10px}
.viewsw span{color:var(--faint);font-size:11px;cursor:pointer;padding:2px 10px;
 border-radius:4px}
.viewsw span.on{color:var(--fg);background:var(--panel2)}
.ih{padding:11px 13px 8px;border-bottom:1px solid var(--line)}
.ih .p{font-size:14px;font-weight:650;letter-spacing:.02em}
.ih .s{color:var(--dim);font-size:11px}
.asp{padding:10px 13px;border-bottom:1px solid var(--line)}
.asp .n{color:var(--dim);font-size:11px;font-family:ui-monospace,monospace}
.asp .v{font-weight:600;font-size:13px;margin-top:1px}
.badge{display:inline-block;font-size:10px;padding:1px 7px;border-radius:999px;
 border:1px solid var(--line);color:var(--dim);margin-left:6px;vertical-align:1px}
.b-OBSERVED{color:var(--ok);border-color:var(--ok)}
.b-CONTESTED{color:var(--bad);border-color:var(--bad)}
.b-INFERRED{color:var(--warn);border-color:var(--warn)}
.b-UNKNOWN_NOT_OBSERVED,.b-PROPOSED{color:var(--dim)}
.why{color:var(--dim);font-size:11px;margin-top:3px}
.ev{color:var(--faint);font-size:11px;font-family:ui-monospace,monospace;
 margin-top:3px}
.ev a{color:var(--sel);text-decoration:none;cursor:pointer}
.close{margin-top:5px;padding:6px 8px;border:1px dashed var(--line);
 border-radius:5px;background:#14141c}
.close .t{color:var(--warn);font-size:11px;margin-bottom:3px}
.close ul{margin:0;padding-left:16px;color:var(--dim);font-size:11px}
.prop{margin-top:6px;padding:6px 8px;border:1px dashed var(--line);
 border-radius:5px;background:#14141c}
button{background:#222230;color:var(--fg);border:1px solid var(--line);
 border-radius:5px;padding:3px 9px;font-size:11px;cursor:pointer}
button:hover{background:#2c2c3e}
button.pri{border-color:var(--sel);color:#cfe1fb}
#tl{overflow:auto;padding:8px 12px}
#tl .row{display:flex;gap:10px;align-items:baseline;padding:3px 0;
 border-bottom:1px solid #1e1e28;cursor:pointer;font-size:12px}
#tl .row:hover{background:var(--panel2)}
#tl .t{color:var(--sel);font-family:ui-monospace,monospace;width:64px;
 flex:none}
#tl .k{color:var(--dim);font-size:11px;width:150px;flex:none;
 font-family:ui-monospace,monospace}
#tl .s{color:var(--faint);font-size:11px;margin-left:auto}
#sum{border-left:1px solid var(--line);padding:10px 13px}
.bar{margin-bottom:7px}
.bar .l{display:flex;justify-content:space-between;font-size:11px;
 color:var(--dim)}
.bar .t{height:6px;border-radius:3px;background:#20202c;margin-top:3px;
 overflow:hidden}
.bar .f{height:100%}
.hint{color:var(--faint);font-size:10px;margin-top:8px;line-height:1.5}
.mats{display:flex;gap:8px;justify-content:center;align-items:center;
 padding-bottom:6px;flex-wrap:wrap}
.matchip{border:1px solid var(--line);border-radius:999px;padding:2px 11px;
 font-size:11px;cursor:pointer;color:var(--dim)}
.matchip:hover{background:var(--panel2)}
.matchip.on{border-color:var(--sel);color:var(--fg)}
.form{padding:10px 13px;border-top:1px solid var(--line)}
.form input,.form select{background:#111119;color:var(--fg);
 border:1px solid var(--line);border-radius:4px;padding:4px 6px;font-size:11px;
 margin:0 4px 4px 0}
#tp{position:fixed;inset:6% 10%;background:var(--panel);z-index:9;
 border:1px solid var(--line);border-radius:8px;overflow:auto;padding:20px 26px;
 display:none;box-shadow:0 20px 60px rgba(0,0,0,.6)}
#tp h2{font-size:15px;margin:0 0 2px}
#tp h3{font-size:12px;color:var(--dim);margin:18px 0 5px;
 border-bottom:1px solid var(--line);padding-bottom:3px}
#tp table{width:100%;border-collapse:collapse;font-size:12px}
#tp td{padding:3px 6px;border-bottom:1px solid #1e1e28;vertical-align:top}
#tp td.k{color:var(--dim);width:210px;font-family:ui-monospace,monospace}
</style>
<div id="app">
  <div id="top">
    <b>Vera Atelier</b>
    <span class="proj" id="proj">Project: —</span>
    <span class="sp"></span>
    <button id="anime">Anime Mode</button>
    <button class="pri" id="send">Send to Maker</button>
  </div>

  <div id="rail">
    <div class="railh">Project</div>
    <div id="steps"></div>
    <div class="railh" style="margin-top:12px">Garments</div>
    <div class="step on"><span class="num">001</span> Black Coat</div>
  </div>

  <div id="work">
    <div class="tabs" id="tabs"></div>
    <div id="stage"></div>
  </div>

  <div id="insp"></div>

  <div id="bot">
    <div id="tl"></div>
    <div id="sum"></div>
  </div>
</div>
<div id="tp"></div>
<script>
const $=s=>document.querySelector(s);
const STEPS=["Sources","Garments","Evidence","Structure","Materials","Pattern","Tech Pack"];
const VIEWS=["Front","Side","Back"];
const TABS=["Film","Search","3D"];
let D={spec:{confirmed:[],contested:[],inferred:[],open:[],counts:{}},parts:{}};
let SEL="collar", VIEW="Front", TAB="Film", STEP="Structure", ANIME=false;
const esc=s=>String(s??"").replace(/[<>&]/g,c=>({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]));
const SYM={OBSERVED:"✓",CONTESTED:"×",INFERRED:"△",PROPOSED:"·",
           UNKNOWN_NOT_OBSERVED:"?"};

function partState(part){
  // 部位の状態 = 最も弱い側面に引きずられる。強い方に丸めない。
  const st=(D.parts[part]||[]).map(a=>stateOf(part,a).state);
  if(st.includes("CONTESTED"))return "CONTESTED";
  if(st.every(s=>s==="OBSERVED")&&st.length)return "OBSERVED";
  if(st.includes("OBSERVED")||st.includes("INFERRED"))return "INFERRED";
  return "UNKNOWN_NOT_OBSERVED";
}
function stateOf(part,aspect){
  for(const k of ["confirmed","contested","inferred","open"])
    for(const s of D.spec[k]||[]) if(s.part===part&&s.aspect===aspect) return s;
  return {state:"UNKNOWN_NOT_OBSERVED",part,aspect};
}

/* ---- 中央: 服の図。部位をクリックすると右が変わる ---- */
/* 図に載せるのは**空間的な部位だけ**。fabric と lining は場所を持たない
   ので図から外し、下の材料帯に置く — 存在しない場所を指させると、
   読み手は「そこを見た」と誤解する。 */
const SHAPES={
 Front:[
  ["body","M104,74 C100,150 96,206 92,262 L208,262 C204,206 200,150 196,74 Z",[150,180]],
  ["collar","M126,52 L150,86 L118,110 L106,74 Z M174,52 L150,86 L182,110 L194,74 Z",[150,44]],
  ["sleeve","M104,74 L78,84 L60,224 L94,236 L100,150 Z",[70,160]],
  ["sleeve2","M196,74 L222,84 L240,224 L206,236 L200,150 Z",[230,160]],
  ["detail","M150,92 L150,258",[150,124]],
  ["pocket","M110,196 h34 v26 h-34 Z M156,196 h34 v26 h-34 Z",[150,236]]],
 Side:[
  ["body","M126,74 C122,150 118,206 116,262 L196,262 C194,206 192,150 188,74 Z",[156,180]],
  ["collar","M134,52 L172,66 L160,100 L128,80 Z",[150,44]],
  ["sleeve","M126,74 L100,86 L86,224 L120,236 L126,150 Z",[96,160]],
  ["pocket","M132,196 h40 v26 h-40 Z",[152,236]]],
 Back:[
  ["back","M104,74 C100,150 96,206 92,262 L208,262 C204,206 200,150 196,74 Z",[150,180]],
  ["collar","M120,54 L180,54 L188,80 L112,80 Z",[150,46]],
  ["sleeve","M104,74 L78,84 L60,224 L94,236 L100,150 Z",[70,160]],
  ["sleeve2","M196,74 L222,84 L240,224 L206,236 L200,150 Z",[230,160]],
  ["vent","M150,206 L150,262",[150,238]]]};
const ALIAS={sleeve2:"sleeve", vent:"back"};        // 図の別名 → 台帳の部位
const MATERIALS=["fabric","lining"];                 // 場所を持たない部位

function drawStage(){
  if(STEP==="Tech Pack"){openTP();STEP="Structure";}
  const shapes=SHAPES[VIEW]||SHAPES.Front;
  const svg=shapes.map(([key,d,lp])=>{
    const part=ALIAS[key]||key;
    const st=partState(part);
    const show=(key==="sleeve2"||key==="vent")?"":`${part} ${SYM[st]}`;
    return `<g class="hit st-${st} ${SEL===part?"sel":""}" onclick="pick('${part}')">
      <path class="sh" d="${d}"/>
      <text class="lbl" x="${lp[0]}" y="${lp[1]}" text-anchor="middle">${show}</text>
    </g>`;}).join("");
  const mats=MATERIALS.map(m=>{
    const st=partState(m);
    return `<span class="matchip ${SEL===m?"on":""} b-${st}" onclick="pick('${m}')">
      ${SYM[st]} ${m}</span>`;}).join("");
  const trip = ANIME ? `<div style="display:flex;gap:14px;align-items:center">
     <div style="text-align:center"><div class="lblbox">Original artwork</div>
       <svg width="150" height="200" viewBox="30 20 240 250" style="opacity:.5">${svg}</svg>
       <div class="hint">設定画・スクリーンショット</div></div>
     <div style="text-align:center"><div class="lblbox">Interpretation</div>
       <svg width="220" height="290" viewBox="30 20 240 250">${svg}</svg>
       <div class="hint">Veraが持っている構造</div></div>
     <div style="text-align:center"><div class="lblbox">Realization</div>
       <svg width="150" height="200" viewBox="30 20 240 250" style="opacity:.35">${svg}</svg>
       <div class="hint">実際に作れる服(未生成)</div></div></div>` :
    `<svg width="330" height="400" viewBox="30 20 240 250">${svg}</svg>`;
  $("#stage").innerHTML=`<div>
    ${trip}
    <div class="viewsw">${VIEWS.map(v=>`<span class="${v===VIEW?"on":""}" onclick="setView('${v}')">${v}</span>`).join("")}</div>
    <div class="mats">${mats}<span class="hint" style="margin-left:8px">
      材料は場所を持たないので図に載せない</span></div>
    <div class="hint" style="text-align:center;max-width:420px">
      色は状態です。緑=確定 / 赤=割れている / 橙=推論 / 灰=未観測。
      クリックすると右の構造インスペクタが変わります。
    </div></div>`;
  $("#tabs").innerHTML=TABS.map(t=>`<div class="tab ${t===TAB?"on":""}" onclick="setTab('${t}')">${t}</div>`).join("")
    + `<div style="flex:1"></div><div class="tab" onclick="openTP()">Tech Pack</div>`;
}
function setView(v){VIEW=v;drawStage();}
function setTab(t){TAB=t;drawStage();}
function pick(p){SEL=p;drawStage();drawInsp();}

/* ---- 右: 構造インスペクタ(チャットではない) ---- */
function drawInsp(){
  const aspects=D.parts[SEL]||[];
  const rows=aspects.map(a=>{
    const s=stateOf(SEL,a);
    let inner="";
    if(s.state==="OBSERVED"){
      inner=`<div class="v">${esc(s.value)}</div>
        <div class="why">${s.agreed} 件の独立した観測が一致${s.adopted_by?` · 採用: ${esc(s.adopted_by)}`:""}</div>
        <div class="ev">${(s.sources||[]).map(x=>`<a onclick="jump('${esc(x)}')">${esc(x)}</a>`).join(" · ")}</div>`;
    }else if(s.state==="CONTESTED"){
      inner=(s.sides||[]).map(x=>`<div class="v">${esc(x.value)}
        <span class="ev">← ${(x.sources||[]).map(y=>`<a onclick="jump('${esc(y)}')">${esc(y)}</a>`).join(" · ")}</span></div>`).join("")
        +`<div class="why">観測が食い違っている。片方を勝たせていない — 人が決める</div>`;
    }else if(s.state==="INFERRED"){
      inner=`<div class="v">${esc(s.value)}</div>
        <div class="why">構造から推した(観測ではない)</div>
        <div class="ev">根拠: ${(s.basis||[]).map(esc).join(" · ")}</div>`;
    }else{
      inner=`<div class="v" style="color:var(--dim)">—</div>
        <div class="why">直接の観測が無い</div>
        <div class="close"><div class="t">次に何をすれば閉じるか</div>
        <ul>${String(s.how_to_close||"").split(" / ").map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div>`;
    }
    const props=(s.proposals||[]).map(x=>`<div class="prop">
      <span class="ev">提案</span> <b>${esc(x.value)}</b>
      <div class="ev">${esc(x.source)}${x.note?" · "+esc(x.note)+"(出所の申告。事実ではない)":""}</div>
      <button onclick="adopt('${SEL}','${a}',${JSON.stringify(x.value)})">証拠として採用</button>
      </div>`).join("");
    return `<div class="asp"><div class="n">${a}
      <span class="badge b-${s.state}">${SYM[s.state]} ${s.state.replace("_NOT_OBSERVED","")}</span></div>
      ${inner}${props}</div>`;
  }).join("");
  $("#insp").innerHTML=`<div class="ih"><div class="p">${SEL.toUpperCase()}</div>
     <div class="s">${aspects.length} 側面 · 状態は最も弱い側面に合わせる</div></div>
     ${rows}
     <div class="form">
       <div class="n" style="color:var(--faint);font-size:10px;margin-bottom:5px">記録する</div>
       <select id="f-aspect">${aspects.map(a=>`<option>${a}</option>`).join("")}</select>
       <select id="f-kind">
         <option value="observation">観測</option>
         <option value="inference">推論</option>
         <option value="proposal">提案</option></select><br>
       <input id="f-value" placeholder="値" size="14">
       <input id="f-source" placeholder="出典 (cut 0:12:05 / URL)" size="18">
       <input id="f-note" placeholder="注記" size="10">
       <button class="pri" onclick="add()">置く</button>
     </div>`;
}

/* ---- 下段: 証拠のタイムラインと配分 ---- */
function drawBottom(){
  const tl=D.timeline||[];
  $("#tl").innerHTML=tl.length?tl.map(r=>`<div class="row" onclick="pick('${r.part}')">
     <span class="t">${r.at||"—"}</span>
     <span class="k">${esc(r.part)} / ${esc(r.aspect)}</span>
     <span>${esc(r.value)} <span class="badge b-${r.kind==="observation"?"OBSERVED":r.kind==="inference"?"INFERRED":"PROPOSED"}">${r.kind}</span></span>
     <span class="s">${esc(r.source)}</span></div>`).join("")
     :`<div class="hint">証拠がまだありません。右のインスペクタから記録してください。</div>`;
  const c=D.spec.counts||{};
  const tot=Math.max(1,(c.confirmed||0)+(c.contested||0)+(c.inferred||0)+(c.open||0));
  const bar=(name,n,col)=>`<div class="bar"><div class="l"><span>${name}</span><span>${n}</span></div>
    <div class="t"><div class="f" style="width:${(n/tot*100).toFixed(1)}%;background:${col}"></div></div></div>`;
  $("#sum").innerHTML=bar("OBSERVED",c.confirmed||0,"var(--ok)")
    +bar("CONTESTED",c.contested||0,"var(--bad)")
    +bar("INFERRED",c.inferred||0,"var(--warn)")
    +bar("UNKNOWN",c.open||0,"#3a3a4c")
    +`<div class="hint">確度はモデルの点数ではなく、<b>独立した観測が何本一致したか</b>です。
      UNKNOWN は失敗ではなく、次に探すもの。</div>`;
}

/* ---- Tech Pack ---- */
async function openTP(){
  const d=await (await fetch("/api/techpack")).json();
  $("#tp").style.display="block";
  $("#tp").innerHTML=`<h2>GARMENT TECH PACK</h2>
    <div class="hint">${esc(d.title)} · ${esc(d.note)}</div>
    ${(d.sections||[]).map(sec=>{
      let body="";
      if(sec.rows)body=`<table>${sec.rows.map(r=>`<tr><td class="k">${esc(r.label)}</td>
        <td>${esc(r.value)}${r.state?` <span class="badge b-${r.state}">${SYM[r.state]||""}</span>`:""}</td></tr>`).join("")}</table>`;
      if(sec.parts)body=`<table>${Object.entries(sec.parts).map(([p,list])=>
        (list||[]).map(s=>`<tr><td class="k">${esc(p)} / ${esc(s.aspect)}</td>
          <td>${esc(s.value|| (s.sides||[]).map(x=>x.value).join(" / "))}
          <span class="badge b-${s.state}">${SYM[s.state]}</span></td></tr>`).join("")).join("")}</table>`;
      if(sec.timeline)body=`<table>${sec.timeline.map(r=>`<tr><td class="k">${r.at||"—"}</td>
        <td>${esc(r.part)} / ${esc(r.aspect)} — ${esc(r.value)} <span class="ev">${esc(r.source)}</span></td></tr>`).join("")}</table>`;
      return `<h3>${sec.no} ${esc(sec.name)}</h3>${body||'<div class="hint">なし</div>'}`;
    }).join("")}
    <div style="margin-top:20px"><button onclick="document.getElementById('tp').style.display='none'">閉じる</button>
    <button class="pri" onclick="window.print()">印刷 / PDF</button></div>`;
}

function jump(src){
  const row=(D.timeline||[]).find(r=>r.source===src);
  if(row)pick(row.part);
}
async function add(){
  const body={part:SEL,aspect:$("#f-aspect").value,kind:$("#f-kind").value,
    value:$("#f-value").value,source:$("#f-source").value,note:$("#f-note").value};
  if(!body.value)return;
  await fetch("/api/add",{method:"POST",body:JSON.stringify(body)});
  await load();
}
async function adopt(part,aspect,value){
  const by=prompt("採用する人の名前(記録に残ります)");
  if(!by)return;
  await fetch("/api/adopt",{method:"POST",body:JSON.stringify({part,aspect,value,by})});
  await load();
}
async function load(){
  D=await (await fetch("/api/spec")).json();
  $("#proj").textContent="Project: "+(D.spec.title||"Black Coat");
  $("#steps").innerHTML=STEPS.map((s,i)=>`<div class="step ${s===STEP?"on":""}"
     onclick="STEP='${s}';load()"><span class="num">${String(i+1).padStart(2,"0")}</span>${s}</div>`).join("");
  drawStage();drawInsp();drawBottom();
}
$("#send").onclick=openTP;
$("#anime").onclick=()=>{ANIME=!ANIME;$("#anime").textContent=ANIME?"Film Mode":"Anime Mode";drawStage();};
load();
</script></html>"""


def _ledger() -> Ledger:
    return Ledger.load(LEDGER)


class _Handler(BaseHTTPRequestHandler):
    server_version = "VeraGarment"

    def log_message(self, *a):        # 静かに動く(現場の道具)
        pass

    def _lang(self) -> str:
        """Language for this request: ?lang= wins, otherwise the server default."""
        q = self.path.split("?", 1)[1] if "?" in self.path else ""
        for pair in q.split("&"):
            if pair.startswith("lang="):
                v = pair[5:]
                if v in i18n.LANGUAGES:
                    return v
        return LANG

    def _send(self, obj: Dict[str, Any], code: int = 200) -> None:
        obj = i18n.translate(obj, self._lang())
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:         # noqa: N802
        if self.path.startswith("/api/techpack"):
            self._send(_ledger().techpack())
            return
        if self.path.startswith("/api/pattern.svg"):
            self._pattern()
            return
        if self.path.startswith("/api/spec"):
            led = _ledger()
            self._send({"verdict": "ANSWER", "spec": led.spec(),
                        "timeline": led.timeline(),
                        "parts": PARTS, "where": str(LEDGER)})
            return
        lang = self._lang()
        html = i18n.page(PAGE, lang)
        if lang != "ja":
            html = html.replace('<html lang="ja">', f'<html lang="{lang}">')
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _pattern(self) -> None:
        """The pattern, drawn from the measurements on disk.

        Kept as its own route rather than folded into /api/spec because a
        pattern is a different kind of thing from a ledger: the ledger says
        what is known, the pattern is what you would cut. It refuses in its
        own words when the measurements are not there.
        """
        from . import garment_marks, garment_pattern
        from .garment_measure import Measures

        path = HOME / "measures.json"
        if not path.exists():
            self._send({"verdict": "UNKNOWN_NO_MEASUREMENTS",
                        "how_to_close": f"{path} に実測を入れる"}, 404)
            return
        ms = Measures.load(path)
        draft = garment_pattern.draft(ms)
        if draft.get("verdict") != "ANSWER":
            self._send(draft, 409)
            return
        svg = garment_pattern.to_svg(garment_marks.apply(draft))
        svg = i18n.svg(svg, self._lang())
        body = svg.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:        # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._send({"verdict": "UNKNOWN_BAD_REQUEST"}, 400)
            return
        led = _ledger()
        if self.path.startswith("/api/add"):
            kind = payload.get("kind", "observation")
            fn = {"observation": led.observe, "inference": led.infer,
                  "proposal": led.propose}.get(kind)
            if fn is None or not payload.get("value"):
                self._send({"verdict": "UNKNOWN_INCOMPLETE"}, 400)
                return
            fn(payload.get("part", ""), payload.get("aspect", ""),
               payload["value"], payload.get("source", "") or "(出典なし)",
               payload.get("note", ""))
            led.save(LEDGER)
            self._send({"verdict": "ANSWER"})
            return
        if self.path.startswith("/api/adopt"):
            # 採用は人の行為。押した人の名前が残らない採用は受け付けない。
            # 空白だけの名前もここで落とす — 台帳側も断るので、通れば
            # 500 になる。型のついた断りの方が読み手に何をすべきか伝わる。
            by = str(payload.get("by") or "").strip()
            if not by:
                self._send({"verdict": "UNKNOWN_NO_ADOPTER"}, 400)
                return
            e = led.adopt(payload.get("part", ""), payload.get("aspect", ""),
                          payload.get("value", ""), by=by)
            if e is None:
                self._send({"verdict": "UNKNOWN_NO_SUCH_PROPOSAL"}, 404)
                return
            led.save(LEDGER)
            self._send({"verdict": "ANSWER"})
            return
        self._send({"verdict": "UNKNOWN_NO_SUCH_ROUTE"}, 404)


def serve(port: int = _PORT, open_browser: bool = True,
          lan: bool = False, lang: str = "ja") -> int:
    import webbrowser

    global LANG
    if lang not in i18n.LANGUAGES:
        raise ValueError(f"UNKNOWN_LANGUAGE: {lang} — one of {i18n.LANGUAGES}")
    LANG = lang
    HOME.mkdir(parents=True, exist_ok=True)
    host = "0.0.0.0" if lan else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://127.0.0.1:{port}/" + ("" if lang == "ja" else f"?lang={lang}")
    print(("photoloset — " if lang != "ja" else "服飾台帳 — ") + url)
    print(("ledger: " if lang != "ja" else "台帳: ") + str(LEDGER))
    if lan:
        try:
            addr = socket.gethostbyname(socket.gethostname())
        except Exception:
            addr = "(この機械のLAN住所)"
        print(f"LAN 公開中 — 電話やタブレットから http://{addr}:{port}/")
        print("  この LAN にいる人は誰でも読めます。外の網には出ません。")
    else:
        print("この機械からのみ。外部接続なし。")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n終了しました。")
    finally:
        server.server_close()
    return 0
