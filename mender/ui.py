"""`mender ui`: a small local review page (stdlib only, bound to 127.0.0.1).

Same queue and same guarded approve path as `mender review`.
"""
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import actions, config, queue, stats

_WRITE_LOCK = threading.Lock()


def state() -> dict:
    items = []
    for it in queue.pending():
        items.append({
            "id": it.memory_id, "kind": it.kind, "old_text": it.old_text,
            "files": it.files, "why": it.triage_why, "diff": it.diff,
            "draft": ({"new_text": it.draft.new_text, "reason": it.draft.reason,
                       "confidence": it.draft.confidence,
                       "evidence": it.draft.evidence,
                       "warnings": it.draft.warnings} if it.draft else None),
            "drifted": it.kind != "manual" and queue.drifted(it),
        })
    return {"repo": str(config.REPO), "items": items,
            "routing": stats.routing(), "models": stats.summarize()}


def make_handler(token: str, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj).encode())

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in allowed_hosts  # blocks DNS rebinding

        def do_GET(self):
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            if self.path in ("/", "/index.html"):
                page = PAGE.replace("__TOKEN__", token)
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if self.path == "/api/state":
                return self._json(200, state())
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or self.headers.get("X-Mender-Token") != token:
                return self._json(403, {"error": "forbidden"})
            if "application/json" not in self.headers.get("Content-Type", ""):
                return self._json(415, {"error": "json only"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(n) or b"{}")
                mid = str(data["id"])
            except (ValueError, KeyError):
                return self._json(400, {"error": "bad request"})
            with _WRITE_LOCK:
                try:
                    if self.path == "/api/approve":
                        msg = actions.approve(mid, data.get("text"))
                        return self._json(200, {"ok": True, "message": msg})
                    if self.path == "/api/retire":
                        return self._json(200, {"ok": True, "message": actions.retire(mid)})
                    if self.path == "/api/reject":
                        actions.reject(mid)
                        return self._json(200, {"ok": True, "message": f"{mid} rejected"})
                except actions.Drifted as e:
                    return self._json(409, {"error": str(e)})
                except (LookupError, ValueError) as e:
                    return self._json(400, {"error": str(e)})
                except Exception as e:
                    return self._json(500, {"error": f"{type(e).__name__}: {e}"})
            self._json(404, {"error": "not found"})

    return Handler


def serve(port: int = 7391, open_browser: bool = True) -> None:
    token = secrets.token_urlsafe(24)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token, port))
    url = f"http://127.0.0.1:{port}/"
    print(f"Mender review UI: {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        srv.server_close()


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mender review</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--mut:#8b949e;--acc:#58a6ff;
--add:#2ea04326;--addf:#7ee787;--del:#f8514926;--delf:#ff7b72;--ok:#238636;--warn:#d29922}
@media (prefers-color-scheme:light){:root{--bg:#f6f8fa;--card:#fff;--line:#d0d7de;--fg:#1f2328;
--mut:#59636e;--acc:#0969da;--add:#dafbe1;--addf:#116329;--del:#ffebe9;--delf:#82071e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:880px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:20px;margin:0}.sub{color:var(--mut);font-size:13px;margin:2px 0 16px}
.bar{display:flex;flex-wrap:wrap;gap:8px 18px;padding:10px 14px;border:1px solid var(--line);
border-radius:10px;background:var(--card);font-size:13px;color:var(--mut);margin-bottom:18px}
.bar b{color:var(--fg)}
.card{border:1px solid var(--line);background:var(--card);border-radius:12px;padding:16px;margin-bottom:16px}
.top{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:8px}
.id{font-weight:600}.tag{font-size:11px;letter-spacing:.04em;text-transform:uppercase;
padding:2px 8px;border-radius:99px;border:1px solid var(--line);color:var(--mut)}
.lbl{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--mut);margin:12px 0 4px}
.old{color:var(--mut);text-decoration:line-through;text-decoration-color:var(--delf)}
.why{font-size:13px;color:var(--mut)}
pre.diff{margin:0;overflow:auto;border:1px solid var(--line);border-radius:8px;
font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;max-height:260px}
pre.diff span{display:block;padding:0 10px;white-space:pre}
.a{background:var(--add);color:var(--addf)}.d{background:var(--del);color:var(--delf)}.h{color:var(--acc)}
.draft{border-left:3px solid var(--acc);padding:6px 12px;background:color-mix(in srgb,var(--acc) 8%,transparent);
border-radius:0 8px 8px 0}.draft small{display:block;color:var(--mut);margin-top:4px}
.conf{display:inline-block;height:6px;width:90px;background:var(--line);border-radius:3px;
vertical-align:middle;margin:0 6px}.conf i{display:block;height:100%;border-radius:3px;background:var(--acc)}
textarea{width:100%;min-height:70px;background:var(--bg);color:var(--fg);border:1px solid var(--line);
border-radius:8px;padding:8px;font:inherit;margin-top:8px}
.row{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
button{font:inherit;cursor:pointer;border-radius:8px;border:1px solid var(--line);background:transparent;
color:var(--fg);padding:6px 14px}button.p{background:var(--ok);border-color:var(--ok);color:#fff}
button:disabled{opacity:.45;cursor:not-allowed}
.warn{color:var(--warn);font-size:13px;margin-top:10px}
#msg{position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:var(--card);
border:1px solid var(--line);padding:8px 16px;border-radius:8px;display:none;max-width:90vw}
.evs{font-size:13px;border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.ev{padding:3px 0}.ev b{font-weight:600}.src{margin-left:14px;font-size:12px}
.snip{color:var(--mut);font-size:12px}
.src a{color:var(--acc);text-decoration:none}.src a:hover{text-decoration:underline}
.empty{text-align:center;color:var(--mut);padding:48px 0}
</style></head><body><main>
<h1>Mender review</h1><div class="sub" id="repo"></div>
<div class="bar" id="bar"></div><div id="list"></div></main><div id="msg"></div>
<script>
const TOKEN="__TOKEN__";
const $=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!==undefined)e.textContent=x;return e};
function toast(m){const e=document.getElementById("msg");e.textContent=m;e.style.display="block";
setTimeout(()=>e.style.display="none",3500)}
async function post(path,body){const r=await fetch(path,{method:"POST",headers:{
"Content-Type":"application/json","X-Mender-Token":TOKEN},body:JSON.stringify(body)});
const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
function diffEl(t){const p=$("pre","diff");t.split("\n").forEach(l=>{
const s=$("span",l.startsWith("+")&&!l.startsWith("+++")?"a":l.startsWith("-")&&!l.startsWith("---")?"d":
l.startsWith("@@")?"h":"",l||" ");p.appendChild(s)});return p}
function card(it){
const c=$("div","card"),top=$("div","top"),left=$("div");
left.appendChild($("span","id",it.id));top.appendChild(left);top.appendChild($("span","tag",it.kind));c.appendChild(top);
c.appendChild($("div","lbl","Saved memory"));c.appendChild($("div",it.kind==="replace"?"old":"",it.old_text));
c.appendChild($("div","why","Why flagged: "+it.why));
if(it.files.length)c.appendChild($("div","why","Linked files: "+it.files.join(", ")));
if(it.diff){c.appendChild($("div","lbl","Change"));c.appendChild(diffEl(it.diff))}
let ta=null;
if(it.kind==="replace"&&it.draft){
c.appendChild($("div","lbl","Drafted memory"));const d=$("div","draft");d.appendChild($("div","",it.draft.new_text));
const s=$("small","");s.appendChild(document.createTextNode(it.draft.reason+"  ·  confidence (self-reported) "));
const b=$("span","conf"),i=$("i");i.style.width=Math.round(it.draft.confidence*100)+"%";b.appendChild(i);s.appendChild(b);
s.appendChild(document.createTextNode(it.draft.confidence.toFixed(2)));d.appendChild(s);c.appendChild(d);
(it.draft.warnings||[]).forEach(w=>c.appendChild($("div","warn","\u26a0 Unverified: "+w)));
const ev=it.draft.evidence||[];
if(ev.length){c.appendChild($("div","lbl","Evidence (what the agent actually looked at)"));
const ul=$("div","evs");ev.forEach(e=>{const r=$("div","ev");
const name={tavily_search:"Web search",grep_repo:"Repo search",read_file:"Read file",git_log:"Git history"}[e.tool]||e.tool;
r.appendChild($("b","",name+": "));r.appendChild(document.createTextNode(e.arg+"  \u2192 "+e.summary));
(e.sources||[]).forEach(x=>{if(!/^https?:\/\//.test(x.url))return;const a=$("a","",x.title||x.url);
a.href=x.url;a.target="_blank";a.rel="noopener noreferrer";const li=$("div","src");li.appendChild(a);if(x.snippet)li.appendChild($("div","snip",x.snippet));r.appendChild(li)});
ul.appendChild(r)});c.appendChild(ul)}
else if(it.draft.reason)c.appendChild($("div","why","No tool calls were recorded for this draft."));
ta=$("textarea");ta.value=it.draft.new_text;ta.style.display="none";c.appendChild(ta)}
else if(it.kind==="confirm")c.appendChild($("div","draft","The change looks unrelated to this memory, so it is probably still true."));
else c.appendChild($("div","warn","Every linked file was deleted. Retire the memory if it no longer applies."));
if(it.drifted)c.appendChild($("div","warn","Files changed since this was drafted. Run `mender run` to re-draft."));
const row=$("div","row");
const act=(path,body)=>async()=>{try{const j=await post(path,body());toast(j.message);load()}catch(e){toast(e.message);load()}};
if(it.kind!=="manual"){
const ap=$("button","p",it.kind==="confirm"?"Mark still true":"Approve");ap.disabled=it.drifted;
ap.onclick=act("/api/approve",()=>({id:it.id,text:ta&&ta.style.display!=="none"?ta.value:undefined}));row.appendChild(ap);
if(ta){const ed=$("button","","Edit");ed.disabled=it.drifted;ed.onclick=()=>{ta.style.display=ta.style.display==="none"?"block":"none"};row.appendChild(ed)}}
if(it.kind==="manual"){const rt=$("button","p","Retire memory");rt.onclick=act("/api/retire",()=>({id:it.id}));row.appendChild(rt)}
const rj=$("button","",it.kind==="manual"?"Dismiss":"Reject");rj.onclick=act("/api/reject",()=>({id:it.id}));row.appendChild(rj);
c.appendChild(row);return c}
async function load(){
const s=await (await fetch("/api/state")).json();
document.getElementById("repo").textContent=s.repo;
const bar=document.getElementById("bar");bar.textContent="";
const r=s.routing,seen=r.harmless+r.drafted+r.still_true+r.manual;
const add=(k,v)=>{const e=$("span","");const b=$("b","",v);e.appendChild(b);e.appendChild(document.createTextNode(" "+k));bar.appendChild(e)};
add("pending",s.items.length);
if(seen){add("decisions",seen);add("handled by Nano alone",r.harmless);add("sent to Ultra",r.drafted+r.still_true)}
Object.entries(s.models).forEach(([m,v])=>add("tokens, "+m.split("/").pop()+" ("+v.calls+" calls)",(v.prompt+v.completion).toLocaleString()));
const list=document.getElementById("list");list.textContent="";
if(!s.items.length)list.appendChild($("div","empty","Nothing to review. Run `mender run` after code changes."));
s.items.forEach(it=>list.appendChild(card(it)))}
load();
</script></body></html>
"""
