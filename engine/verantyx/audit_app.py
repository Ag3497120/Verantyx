"""Drop documents in, read what the engine actually did — offline, no deps.

This exists so somebody OTHER THAN the person who wrote the fixes can check
the output. Every "true by reading" judgement recorded so far was made by the
same party that changed the code afterwards, which is the weakest form of
verification there is. A tool that puts the worksheet in front of the document
owner is worth more than another corpus read the same way.

Three decisions the tool takes on purpose:

    it runs locally      A disaster tool that needs a server is a tool that
                         does not work in a disaster. stdlib http.server, no
                         framework, no CDN, no outbound request. The files
                         never leave the machine, which also means a municipal
                         officer can point it at an unpublished draft.

    it leads with what   Coverage, intake verdict and opposable pairs come
    it could NOT do      first, before any finding. A detection count without
                         them is unreadable: zero findings over a corpus with
                         zero opposable pairs is arithmetic, not performance.

    it does not score    Findings are shown with their evidence and an empty
    itself               true/false box. The ratio is computed after a person
                         fills it in. The module produces the worksheet; it
                         does not grade its own paper.

Run:  python3 -m verantyx.cli audit --serve
"""
from __future__ import annotations

import base64
import json
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List

from .corpus_audit import audit_paths
from .defect_report import build as build_defect, render as render_defect
from .document_loaders import SUPPORTED

_MAX_BYTES = 64 * 1024 * 1024

#: Where the local defect log lives. Local, like the documents: the loop is
#: worth running on one machine even if nothing is ever sent anywhere.
_GAP_HOME = Path.home() / ".verantyx-audit"


def analyse(files: List[Dict[str, str]]) -> Dict[str, Any]:
    """`[{name, b64}]` in, the whole audit out.

    Written to a temporary directory rather than parsed in memory because the
    loaders take paths, and a second ingestion path is a second thing that can
    disagree with the first — the class of defect this project keeps finding.
    """
    if not files:
        return {"verdict": "UNKNOWN_NO_DOCUMENTS",
                "reason": "no files were sent"}

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        written, refused = [], []
        for f in files:
            name = Path(f.get("name", "")).name
            if not name:
                continue
            if Path(name).suffix.lower() not in SUPPORTED:
                refused.append({"name": name, "reason": "no loader for this format",
                                "supported": sorted(SUPPORTED)})
                continue
            try:
                data = base64.b64decode(f.get("b64", ""))
            except Exception:
                refused.append({"name": name, "reason": "could not be decoded"})
                continue
            (root / name).write_bytes(data)
            written.append(name)

        if not written:
            return {"verdict": "UNKNOWN_NO_READABLE_DOCUMENTS",
                    "refused": refused,
                    "supported": sorted(SUPPORTED)}

        a = audit_paths([str(root)])

    out = asdict(a)
    out["verdict"] = "ANSWER"
    out["coverage"] = round(a.coverage, 4)
    out["refused"] = refused
    out["accepted"] = written
    return out


_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>Vera — document audit</title>
<style>
:root{--bg:#0b0d13;--fg:#e8eaf0;--dim:#8b93a7;--line:#232838;--accent:#4aa8e0;
      --warn:#e0a83c;--ok:#5ec98a}
@media (prefers-color-scheme:light){:root{--bg:#fbfcfd;--fg:#0f172a;
      --dim:#5b6474;--line:#e2e6ee;--accent:#1f7fc0}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,
     "Hiragino Sans","Noto Sans JP",system-ui,sans-serif;padding:28px 20px 80px}
main{max-width:860px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 6px}
.sub{color:var(--dim);font-size:.86rem;margin-bottom:26px;line-height:1.9}
#drop{border:1.5px dashed var(--line);border-radius:14px;padding:34px 20px;
      text-align:center;color:var(--dim);cursor:pointer;transition:.2s}
#drop.on,#drop:hover{border-color:var(--accent);color:var(--fg)}
#files{margin:12px 0 0;font-size:.8rem;color:var(--dim)}
button{background:var(--accent);color:#fff;border:0;border-radius:10px;
       padding:11px 22px;font-size:.9rem;font-weight:600;cursor:pointer;
       margin-top:16px}
button:disabled{opacity:.45;cursor:default}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
      gap:12px;margin:26px 0}
.cell{border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.cell .v{font-size:1.45rem;font-weight:700}
.cell .k{font-size:.72rem;color:var(--dim);margin-top:4px}
h2{font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;
   color:var(--dim);margin:34px 0 12px;font-weight:600}
.note{border-left:3px solid var(--line);padding:2px 0 2px 14px;color:var(--dim);
      font-size:.85rem;margin:14px 0}
.note.warn{border-color:var(--warn)}
.find{border:1px solid var(--line);border-radius:12px;padding:16px 18px;
      margin-bottom:12px}
.find h3{margin:0 0 10px;font-size:.98rem}
.side{font-size:.85rem;margin:6px 0}
.src{color:var(--dim);font-size:.76rem;font-family:ui-monospace,Menlo,monospace}
blockquote{margin:8px 0 0;padding-left:12px;border-left:2px solid var(--accent);
           color:var(--dim);font-size:.83rem}
.judge{margin-top:12px;display:flex;gap:8px;align-items:center;
       font-size:.8rem;color:var(--dim)}
.judge label{cursor:pointer}
#ratio{font-size:.9rem;margin-top:10px}
.empty{color:var(--dim);font-size:.88rem}
.rep{margin-top:10px}
.rep button{margin:0;padding:6px 12px;font-size:.76rem;background:transparent;
            color:var(--dim);border:1px solid var(--line)}
.rep button:hover{border-color:var(--accent);color:var(--fg)}
.rep pre{white-space:pre-wrap;word-break:break-all;background:rgba(127,127,127,.08);
         border:1px solid var(--line);border-radius:10px;padding:12px;
         font-size:.74rem;margin-top:8px;line-height:1.65}
.rep .why{font-size:.74rem;color:var(--dim);margin-top:6px}
code{font-family:ui-monospace,Menlo,monospace;font-size:.85em}
</style>
<main>
<h1>Vera — 文書監査 / document audit</h1>
<div class="sub">
文書をここに入れると、何が確定し、何が食い違い、<b>何を読めなかったか</b>を出します。
ファイルはこの端末から出ません。判定は人が行います — この道具は採点表を作るだけで、
自分の答案は採点しません。<br>
Files never leave this machine. The tool produces the worksheet; a person fills
in true/false. It does not grade its own paper.
</div>

<div id="drop">
  <div>ここにファイルをドロップ / drop files here</div>
  <div style="font-size:.78rem;margin-top:8px">PDF · Word · HTML · CSV · JSON · Markdown · text</div>
  <input id="pick" type="file" multiple hidden>
</div>
<div id="files"></div>
<button id="go" disabled>監査する / audit</button>

<div id="out"></div>
</main>
<script>
const drop=document.getElementById('drop'),pick=document.getElementById('pick'),
      go=document.getElementById('go'),list=document.getElementById('files'),
      out=document.getElementById('out');
let chosen=[];

drop.onclick=()=>pick.click();
pick.onchange=e=>take([...e.target.files]);
['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{
  e.preventDefault();drop.classList.add('on')}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{
  e.preventDefault();drop.classList.remove('on')}));
drop.addEventListener('drop',e=>take([...e.dataTransfer.files]));

function take(fs){chosen=fs;list.textContent=fs.length?
  fs.length+' file(s): '+fs.map(f=>f.name).join(', '):'';go.disabled=!fs.length}

const b64=f=>new Promise(r=>{const fr=new FileReader();
  fr.onload=()=>r(fr.result.split(',')[1]);fr.readAsDataURL(f)});

go.onclick=async()=>{
  go.disabled=true;go.textContent='読んでいます / reading…';
  const files=[];
  for(const f of chosen) files.push({name:f.name,b64:await b64(f)});
  const res=await fetch('/api/audit',{method:'POST',
    headers:{'content-type':'application/json'},body:JSON.stringify({files})});
  render(await res.json());
  go.disabled=false;go.textContent='監査する / audit';
};

const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function render(d){
  if(d.verdict!=='ANSWER'){
    out.innerHTML='<h2>結果 / result</h2><div class="note warn"><b>'+
      esc(d.verdict)+'</b><br>'+esc(d.reason||'')+
      (d.supported?'<br>読める形式: '+d.supported.join(', '):'')+'</div>';
    return;
  }
  const pct=(d.coverage*100).toFixed(1);
  let h='<h2>読めた量 / what was read</h2><div class="grid">'+
    cell(d.files,'文書 documents')+
    cell(d.chars.toLocaleString(),'文字 characters')+
    cell(pct+'%','被覆率 coverage')+
    cell(d.polar_claims,'極性を持つ主張')+
    cell(d.opposable_pairs,'矛盾になり得た組')+
    cell(d.topics.toLocaleString(),'話題 topics')+'</div>';

  h+='<div class="note'+(d.intake&&d.intake.verdict!=='INTAKE_OK'?' warn':'')+
     '"><b>'+esc((d.intake&&d.intake.verdict)||'?')+'</b> — '+
     esc((d.intake&&d.intake.reason)||'')+'</div>';

  if(d.opposable_pairs===0){
    h+='<div class="note warn">矛盾になり得た組が <b>0</b> です。'+
       '同じ話題の同じ観点について、異なる出典が異なる状態を述べた箇所がありません。'+
       '<b>この結果から精度は測れません。</b><br>'+
       'Zero opposable pairs: no detection was possible, so a count of zero '+
       'says nothing about the detector.</div>';
  }
  if(d.corpus_kind==='prescriptive'){
    h+='<div class="note">この文書群は <b>規範</b>を述べています(指針・規程・仕様)。'+
       '改定は追加であって反転ではないので、矛盾は原理的に出にくい種類です。</div>';
  }

  h+='<h2>所見 / findings — '+(d.detections.length)+'</h2>';
  if(!d.detections.length){
    h+='<div class="empty">食い違いは見つかりませんでした。'+
       '上の被覆率と組数を見てから、この 0 の意味を判断してください。</div>';
  }
  d.detections.forEach((x,i)=>{
    h+='<div class="find"><h3>'+(i+1)+'. '+esc(x.topic)+' — '+esc(x.aspect)+'</h3>';
    (x.sides||[]).forEach(s=>{
      h+='<div class="side"><b>'+esc(s.claim)+'</b> '+
         '<span class="src">'+esc((s.sources||[]).join(', '))+'</span></div>';
    });
    (x.evidence||[]).forEach(e=>{h+='<blockquote>'+esc(e)+'</blockquote>'});
    h+='<div class="judge">この所見は正しいですか / is this real? '+
       '<label><input type="radio" name="j'+i+'" value="true"> true</label>'+
       '<label><input type="radio" name="j'+i+'" value="false"> false</label>'+
       '</div>'+
       '<div class="rep" id="rep'+i+'"></div></div>';
  });
  if(d.detections.length) h+='<div id="ratio" class="empty">判定を入れると精度が出ます。</div>';

  h+='<h2>測っていないもの / not measured</h2><div class="note">'+
     '<b>再現率(見逃し)はこの画面では出せません。</b>'+
     '実文書には「本当はどこが食い違っているか」の正解が付いておらず、'+
     '人が全文を読んで印を付けない限り分母が存在しないためです。'+
     '<br>Recall cannot be produced here. Real documents carry no answer key, '+
     'so there is no denominator until a person reads the whole thing.</div>';

  out.innerHTML=h;

  // Marking a finding false is the moment a defect becomes reportable, so the
  // offer appears there and nowhere else.
  out.addEventListener('change',(ev)=>{
    const m=/^j(\d+)$/.exec(ev.target.name||'');
    if(!m) return;
    const i=+m[1], box=document.getElementById('rep'+i);
    if(ev.target.value!=='false'){box.innerHTML='';return}
    box.innerHTML='<button data-i="'+i+'">この誤りを報告用に整形する / '+
                  'build a defect report</button>'+
                  '<div class="why">文書の中身は入りません。内容語はすべて ◻ に置き換え、'+
                  '送る前に全文を表示します。</div>';
  });

  out.addEventListener('click',async(ev)=>{
    const b=ev.target.closest('.rep button'); if(!b) return;
    const i=+b.dataset.i, x=d.detections[i];
    b.disabled=true;b.textContent='整形中…';
    const res=await fetch('/api/defect',{method:'POST',
      headers:{'content-type':'application/json'},
      body:JSON.stringify({kind:'false_positive',aspect:x.aspect,
        value:(x.sides&&x.sides[0]&&x.sides[0].claim)||'',
        sentences:x.evidence||[],coverage:d.coverage,
        corpus_kind:d.corpus_kind})});
    const r=await res.json();
    const box=document.getElementById('rep'+i);
    if(r.verdict!=='ANSWER'){
      box.innerHTML='<div class="why"><b>'+esc(r.verdict)+'</b> — '+
        esc(r.reason||'')+'</div>';
      return;
    }
    let g='';
    if(r.gap){
      g='<div class="why" style="margin-top:10px">'+
        '<b>'+(r.gap.status==='created'?'新しい穴として記録':'既知の穴を補強')+
        '</b>  <code>'+esc(r.gap.kind)+'</code>'+
        (r.gap.seen>1?'  ・報告 '+r.gap.seen+' 件目':'')+
        '<br>'+esc(r.what_next||'')+'</div>';
    }
    if(r.proposal){
      g+='<div class="why" style="margin-top:8px"><b>語彙の提案</b>(適用されません。'+
         '受け入れる前に、鳴ってはいけない文で確認してください)</div>'+
         '<pre>'+esc(JSON.stringify(r.proposal.overlay,null,2))+'</pre>'+
         '<div class="why">'+esc(r.proposal.control_check)+'</div>';
    }
    box.innerHTML='<div class="why">これが報告の全文です。読んでから、'+
      'あなたの判断で送ってください。</div><pre>'+esc(r.report)+'</pre>'+
      '<button data-copy="1">コピー / copy</button>'+g;
    box.querySelector('[data-copy]').onclick=()=>{
      navigator.clipboard.writeText(r.report);
      box.querySelector('[data-copy]').textContent='コピーしました';
    };
  });

  out.addEventListener('change',()=>{
    const n=d.detections.length;let t=0,f=0;
    for(let i=0;i<n;i++){
      const v=document.querySelector('input[name=j'+i+']:checked');
      if(v) (v.value==='true'?t++:f++);
    }
    const el=document.getElementById('ratio');
    if(el) el.textContent = (t+f)===0 ? '判定を入れると精度が出ます。'
      : '精度 '+t+' / '+(t+f)+' = '+Math.round(100*t/(t+f))+'%'+
        ((t+f)<n?'  (未判定 '+(n-t-f)+'件)':'');
  });
}
function cell(v,k){return '<div class="cell"><div class="v">'+esc(v)+
  '</div><div class="k">'+esc(k)+'</div></div>'}
</script>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        # Local-only tool: nothing is fetched from anywhere else, and saying
        # so in a header means a stray CDN reference cannot creep in later.
        self.send_header("content-security-policy",
                         "default-src 'self'; style-src 'unsafe-inline'; "
                         "script-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def _defect(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = _report_body(payload)
        except Exception as exc:  # noqa: BLE001
            result = {"verdict": "UNKNOWN_UNREADABLE",
                      "reason": f"{type(exc).__name__}: {exc}"}
        self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        if self.path == "/api/defect":
            self._defect()
            return
        if self.path != "/api/audit":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("content-length") or 0)
        if length > _MAX_BYTES:
            self._send(413, json.dumps(
                {"verdict": "UNKNOWN_TOO_LARGE",
                 "reason": f"over {_MAX_BYTES // (1024*1024)} MB"}
            ).encode("utf-8"), "application/json")
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = analyse(payload.get("files") or [])
        except Exception as exc:  # noqa: BLE001 — a browser gets a typed reason
            result = {"verdict": "UNKNOWN_UNREADABLE",
                      "reason": f"{type(exc).__name__}: {exc}"}
        self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")


def _report_body(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build a defect report, or say why it refused.

    Runs on the server rather than in the page because the redaction has to
    use the SAME segmenter the engine uses: a browser-side approximation of
    what counts as a content word would be a second opinion about what is
    private, and the wrong second opinion leaks.
    """
    try:
        d = build_defect(
            payload.get("kind") or "false_positive",
            payload.get("sentences") or [],
            aspect=payload.get("aspect") or "",
            value=payload.get("value") or "",
            note=payload.get("note") or "",
            coverage=payload.get("coverage"),
            corpus_kind=payload.get("corpus_kind") or "",
        )
    except ValueError as exc:
        return {"verdict": "UNKNOWN_REDACTION_FAILED", "reason": str(exc)}
    # File it as a gap in the same call. The report is a typed failure and
    # `gap_graph` is where typed failures live; keeping them apart would mean
    # a reporter's second sighting of one defect looks like a second defect.
    #
    # The graph is local, like everything else here — the loop is useful to
    # the operator on their own machine even if they never send anything.
    from .gap_graph import GapGraph, gap_graph_path
    from .defect_gaps import GAP_KINDS, proposal, record

    # Its own directory, not the store's. The audit tool has no store — it
    # reads documents into a temporary one and throws it away — and writing
    # into whatever store happened to be beside it would put an operator's
    # defect log into a knowledge base they did not choose.
    path = gap_graph_path(_GAP_HOME / "audit.json")
    _GAP_HOME.mkdir(parents=True, exist_ok=True)
    graph = GapGraph.load(path)
    filed = record(graph, d, payload.get("sentences") or [])
    graph.save(path)

    return {"verdict": "ANSWER", "report": render_defect(d),
            "shapes": d.shapes, "gap": filed,
            "what_next": GAP_KINDS.get(filed["kind"], ""),
            "proposal": proposal(d)}


def serve(port: int = 8899, open_browser: bool = True) -> int:
    # 127.0.0.1, never 0.0.0.0: the files being audited may be unpublished
    # drafts, and binding to every interface would put them on the network.
    server = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Vera document audit — {url}")
    print("files stay on this machine; Ctrl-C to stop")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0
