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

from .garment import PARTS, Ledger

HOME = Path.home() / ".vera_garment"
LEDGER = HOME / "ledger.json"
_PORT = 8910

PAGE = """<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>服飾台帳 — 何がどこまで分かっているか</title>
<style>
:root{--bg:#14141a;--fg:#e8e8ef;--dim:#8b8b9c;--line:#2a2a36;
--ok:#5ec27a;--warn:#e0a34a;--bad:#e06a6a;--info:#6aa8e0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,BlinkMacSystemFont,"Hiragino Sans",sans-serif}
header{padding:14px 18px;border-bottom:1px solid var(--line);
display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
h1{font-size:15px;margin:0;font-weight:650}
.sub{color:var(--dim);font-size:12px}
main{padding:18px;max-width:1100px;margin:0 auto}
section{margin-bottom:26px}
h2{font-size:13px;margin:0 0 4px;font-weight:650}
h2 .n{color:var(--dim);font-weight:400}
.hint{color:var(--dim);font-size:11px;margin:0 0 10px}
.row{border:1px solid var(--line);border-left-width:3px;border-radius:6px;
padding:8px 11px;margin-bottom:7px;background:#191921}
.row.ok{border-left-color:var(--ok)}
.row.bad{border-left-color:var(--bad)}
.row.warn{border-left-color:var(--warn)}
.row.open{border-left-color:var(--dim)}
.k{color:var(--dim);font-size:11px;font-family:ui-monospace,monospace}
.v{font-weight:600}
.src{color:var(--dim);font-size:11px;margin-top:2px}
.prop{margin-top:6px;padding:6px 8px;border:1px dashed var(--line);
border-radius:5px;background:#15151d}
button{background:#232331;color:var(--fg);border:1px solid var(--line);
border-radius:5px;padding:4px 10px;font-size:12px;cursor:pointer}
button:hover{background:#2c2c3d}
form{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px}
input,select{background:#12121a;color:var(--fg);border:1px solid var(--line);
border-radius:5px;padding:5px 8px;font-size:12px}
.warnbox{border:1px solid var(--warn);border-radius:6px;padding:9px 12px;
color:var(--warn);font-size:12px;margin-bottom:16px}
</style>
<header>
  <h1>服飾台帳</h1>
  <span class="sub">服を作る装置ではなく、<b>何がどこまで分かっているか</b>を持つ装置</span>
  <span class="sub" id="where"></span>
</header>
<main>
  <div class="warnbox">確定(緑)以外を裁断の根拠にしないでください。
  推論と提案は観測ではありません。</div>
  <section><h2>確定 <span class="n" id="c-confirmed"></span></h2>
    <p class="hint">観測が一致した。裁ってよい</p><div id="confirmed"></div></section>
  <section><h2>割れている <span class="n" id="c-contested"></span></h2>
    <p class="hint">観測が食い違った。片方を勝たせていない — 人が決める</p>
    <div id="contested"></div></section>
  <section><h2>推論 <span class="n" id="c-inferred"></span></h2>
    <p class="hint">構造から推した。観測ではないので確認が要る</p>
    <div id="inferred"></div></section>
  <section><h2>未確定 <span class="n" id="c-open"></span></h2>
    <p class="hint">裁断前に潰すことの一覧。それぞれに閉じ方が付く</p>
    <div id="open"></div></section>
  <section><h2>記録する</h2>
    <form id="add">
      <select id="part"></select><select id="aspect"></select>
      <select id="kind">
        <option value="observation">観測(映像で見えた)</option>
        <option value="inference">推論(構造から推した)</option>
        <option value="proposal">提案(検索・モデル・人)</option>
      </select>
      <input id="value" placeholder="値(例: ノッチドラペル)" size="22">
      <input id="source" placeholder="出典(例: cut 0:12:05 / URL)" size="24">
      <input id="note" placeholder="注記(モデルの点数はここ)" size="22">
      <button type="submit">置く</button>
    </form>
  </section>
</main>
<script>
const $=s=>document.querySelector(s);
let PARTS={};
function esc(s){return String(s??"").replace(/[<>&]/g,c=>({"<":"&lt;",">":"&gt;","&":"&amp;"}[c]))}
function propHtml(p,part,aspect){
  if(!p||!p.length)return"";
  return p.map(x=>`<div class="prop"><span class="k">提案</span>
   <b>${esc(x.value)}</b> <span class="src">${esc(x.source)}${x.note?" · "+esc(x.note):""}</span>
   <button onclick="adopt('${part}','${aspect}',${JSON.stringify(x.value)})">採用する</button></div>`).join("");
}
async function load(){
  const r=await fetch("/api/spec");const d=await r.json();
  PARTS=d.parts||{};$("#where").textContent=d.where||"";
  for(const [id,cls] of [["confirmed","ok"],["contested","bad"],["inferred","warn"],["open","open"]]){
    const rows=d.spec[id]||[];$("#c-"+id).textContent=rows.length;
    $("#"+id).innerHTML=rows.map(s=>{
      const head=`<span class="k">${esc(s.part)} / ${esc(s.aspect)}</span>`;
      if(id==="confirmed")return `<div class="row ok">${head}
        <div class="v">${esc(s.value)}</div>
        <div class="src">出典: ${(s.sources||[]).map(esc).join(" · ")}${s.adopted_by?" · 採用: "+esc(s.adopted_by):""} · 一致 ${s.agreed}</div>
        ${propHtml(s.proposals,s.part,s.aspect)}</div>`;
      if(id==="contested")return `<div class="row bad">${head}
        ${(s.sides||[]).map(x=>`<div class="v">${esc(x.value)} <span class="src">← ${(x.sources||[]).map(esc).join(" · ")}</span></div>`).join("")}
        ${propHtml(s.proposals,s.part,s.aspect)}</div>`;
      if(id==="inferred")return `<div class="row warn">${head}
        <div class="v">${esc(s.value)}</div>
        <div class="src">根拠: ${(s.basis||[]).map(esc).join(" · ")}(観測ではない)</div>
        ${propHtml(s.proposals,s.part,s.aspect)}</div>`;
      return `<div class="row open">${head}
        <div class="v">${esc(s.state)}</div>
        <div class="src">閉じ方: ${esc(s.how_to_close||"")}</div>
        ${propHtml(s.proposals,s.part,s.aspect)}</div>`;
    }).join("")||`<div class="src">なし</div>`;
  }
  const ps=$("#part");
  if(!ps.options.length){
    ps.innerHTML=Object.keys(PARTS).map(p=>`<option>${p}</option>`).join("");
    ps.onchange=()=>{$("#aspect").innerHTML=(PARTS[ps.value]||[]).map(a=>`<option>${a}</option>`).join("")};
    ps.onchange();
  }
}
async function adopt(part,aspect,value){
  const by=prompt("採用する人の名前(記録に残ります)");
  if(!by)return;
  await fetch("/api/adopt",{method:"POST",body:JSON.stringify({part,aspect,value,by})});
  load();
}
$("#add").onsubmit=async e=>{
  e.preventDefault();
  await fetch("/api/add",{method:"POST",body:JSON.stringify({
    part:$("#part").value,aspect:$("#aspect").value,kind:$("#kind").value,
    value:$("#value").value,source:$("#source").value,note:$("#note").value})});
  $("#value").value="";$("#source").value="";$("#note").value="";
  load();
};
load();
</script></html>"""


def _ledger() -> Ledger:
    return Ledger.load(LEDGER)


class _Handler(BaseHTTPRequestHandler):
    server_version = "VeraGarment"

    def log_message(self, *a):        # 静かに動く(現場の道具)
        pass

    def _send(self, obj: Dict[str, Any], code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:         # noqa: N802
        if self.path.startswith("/api/spec"):
            led = _ledger()
            self._send({"verdict": "ANSWER", "spec": led.spec(),
                        "parts": PARTS, "where": str(LEDGER)})
            return
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
            if not payload.get("by"):
                self._send({"verdict": "UNKNOWN_NO_ADOPTER"}, 400)
                return
            e = led.adopt(payload.get("part", ""), payload.get("aspect", ""),
                          payload.get("value", ""), by=payload["by"])
            if e is None:
                self._send({"verdict": "UNKNOWN_NO_SUCH_PROPOSAL"}, 404)
                return
            led.save(LEDGER)
            self._send({"verdict": "ANSWER"})
            return
        self._send({"verdict": "UNKNOWN_NO_SUCH_ROUTE"}, 404)


def serve(port: int = _PORT, open_browser: bool = True,
          lan: bool = False) -> int:
    import webbrowser

    HOME.mkdir(parents=True, exist_ok=True)
    host = "0.0.0.0" if lan else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"服飾台帳 — {url}")
    print(f"台帳: {LEDGER}")
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
