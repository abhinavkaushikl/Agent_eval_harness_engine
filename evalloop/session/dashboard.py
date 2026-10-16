"""The live dashboard: one self-contained, premium page the bot opens when clicked.

No framework, no CDN, no build step (the project's standalone rule applies to the UI too): a single
string of HTML + CSS + vanilla JS that polls ``/status.json`` and re-renders with fluid transitions.
It reports what EvalLoop is evaluating *now*, everything it has evaluated, and every per-case
verdict — styled as an Apple-grade surface (system font, glass, soft depth, light/dark), not a
utility page. The on-screen character lives in :mod:`evalloop.session.overlay`; this is where the
detail is.
"""

from __future__ import annotations

__all__ = ["dashboard_html"]

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EvalLoop</title>
<style>
  :root{
    --bg:#f5f5f7; --surface:rgba(255,255,255,.72); --surface-solid:#fff;
    --ink:#1d1d1f; --dim:#6e6e73; --hair:rgba(0,0,0,.08);
    --ok:#30d158; --bad:#ff453a; --meh:#ff9f0a; --accent:#5e5ce6;
    --shadow:0 1px 2px rgba(0,0,0,.04),0 8px 30px rgba(0,0,0,.08);
    --radius:22px;
  }
  @media (prefers-color-scheme:dark){
    :root{--bg:#000; --surface:rgba(28,28,30,.72); --surface-solid:#1c1c1e;
      --ink:#f5f5f7; --dim:#98989d; --hair:rgba(255,255,255,.10);
      --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 40px rgba(0,0,0,.5);}
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  body{background:var(--bg);color:var(--ink);min-height:100vh;
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Helvetica Neue",sans-serif;
    background-image:radial-gradient(1200px 600px at 80% -10%,rgba(94,92,230,.12),transparent 60%);}
  .wrap{max-width:860px;margin:0 auto;padding:48px 24px 80px}

  header{display:flex;align-items:center;gap:16px;margin-bottom:28px}
  .glyph{width:46px;height:46px;border-radius:13px;flex:0 0 auto;
    background:linear-gradient(145deg,#6e6cf0,#4a48d0);box-shadow:var(--shadow);
    display:grid;place-items:center;color:#fff;font-size:22px}
  h1{font-size:26px;letter-spacing:-.02em;font-weight:650}
  .path{color:var(--dim);font-size:13px;margin-top:2px;font-variant-numeric:tabular-nums}
  .live{margin-left:auto;display:flex;align-items:center;gap:9px;padding:8px 14px;border-radius:999px;
    background:var(--surface);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
    border:1px solid var(--hair);font-size:13px;font-weight:550;box-shadow:var(--shadow)}
  .pulse{width:9px;height:9px;border-radius:50%;background:var(--accent);position:relative}
  .pulse::after{content:"";position:absolute;inset:-4px;border-radius:50%;background:inherit;opacity:.45;
    animation:ping 1.6s cubic-bezier(0,0,.2,1) infinite}
  @keyframes ping{0%{transform:scale(.6);opacity:.5}100%{transform:scale(2.4);opacity:0}}

  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
  .stat{background:var(--surface);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
    border:1px solid var(--hair);border-radius:16px;padding:16px 18px;box-shadow:var(--shadow)}
  .stat .n{font-size:28px;font-weight:650;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
  .stat .l{font-size:12px;color:var(--dim);margin-top:2px}
  .stat.ok .n{color:var(--ok)} .stat.bad .n{color:var(--bad)} .stat.meh .n{color:var(--meh)}

  .now{background:linear-gradient(135deg,rgba(94,92,230,.14),rgba(94,92,230,.04));
    border:1px solid rgba(94,92,230,.25);border-radius:var(--radius);padding:20px 22px;margin-bottom:24px;
    display:flex;align-items:center;gap:14px;box-shadow:var(--shadow)}
  .now .spin{width:22px;height:22px;border-radius:50%;border:2.5px solid rgba(94,92,230,.25);
    border-top-color:var(--accent);animation:spin .8s linear infinite;flex:0 0 auto}
  @keyframes spin{to{transform:rotate(360deg)}}
  .now b{font-weight:600} .now .files{color:var(--dim);font-size:13px;margin-top:2px}

  .run{background:var(--surface);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
    border:1px solid var(--hair);border-radius:var(--radius);padding:20px 22px;margin-bottom:14px;
    box-shadow:var(--shadow);animation:rise .45s cubic-bezier(.16,1,.3,1) both}
  @keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
  .rhead{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  .chip{font-size:12px;font-weight:600;padding:4px 11px;border-radius:999px;letter-spacing:.01em}
  .chip.clean{color:#0a7d2c;background:rgba(48,209,88,.16)}
  .chip.problem{color:#c01a12;background:rgba(255,69,58,.16)}
  .chip.undecided{color:#9a5a00;background:rgba(255,159,10,.18)}
  .chip.errored{color:#c01a12;background:rgba(255,69,58,.16)}
  @media (prefers-color-scheme:dark){
    .chip.clean{color:#4ee07a} .chip.problem,.chip.errored{color:#ff6961} .chip.undecided{color:#ffb84d}}
  .when{color:var(--dim);font-size:12.5px;margin-left:auto;font-variant-numeric:tabular-nums}
  .trig{color:var(--dim);font-size:13px;margin-top:10px}
  .trig code,.sit code{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-size:12px;
    background:var(--hair);padding:1.5px 6px;border-radius:6px}
  .sit{font-size:13px;margin-top:6px;color:var(--dim)}
  .cases{margin-top:14px;border-top:1px solid var(--hair)}
  .case{display:flex;align-items:center;gap:12px;padding:11px 2px;border-bottom:1px solid var(--hair)}
  .case:last-child{border-bottom:0}
  .dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto}
  .dot.passed{background:var(--ok)} .dot.failed{background:var(--bad)} .dot.inconclusive{background:var(--meh)}
  .case .art{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-size:13px;font-weight:550}
  .case .rec{color:var(--dim);font-size:12.5px}
  .case .det{margin-left:auto;color:var(--dim);font-size:12.5px;text-align:right;max-width:46%}
  .err{margin-top:12px;font-family:"SF Mono",ui-monospace,Menlo,monospace;font-size:12.5px;color:var(--bad);
    background:rgba(255,69,58,.08);border-radius:12px;padding:12px 14px;white-space:pre-wrap;word-break:break-word}
  .empty{text-align:center;color:var(--dim);padding:64px 0;font-size:15px}
  .empty .big{font-size:40px;margin-bottom:12px;opacity:.6}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="glyph">◆</div>
    <div>
      <h1>EvalLoop</h1>
      <div class="path" id="path">connecting…</div>
    </div>
    <div class="live"><span class="pulse" id="pulse"></span><span id="mood">…</span></div>
  </header>

  <div class="stats" id="stats"></div>
  <div id="now"></div>
  <div id="runs"></div>
</div>

<script>
const MOOD={idle:"Watching",evaluating:"Evaluating",happy:"All clean",alarmed:"Problem found",unsure:"Undecided",errored:"Run errored"};
const DOT={idle:"var(--accent)",evaluating:"var(--accent)",happy:"var(--ok)",alarmed:"var(--bad)",unsure:"var(--meh)",errored:"var(--bad)"};
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const ago=t=>{const d=Date.now()/1000-t;if(d<5)return"just now";if(d<60)return Math.floor(d)+"s ago";
  if(d<3600)return Math.floor(d/60)+"m ago";return Math.floor(d/3600)+"h ago";};

function stat(n,l,cls){return `<div class="stat ${cls||''}"><div class="n">${n}</div><div class="l">${l}</div></div>`;}

function render(s){
  document.getElementById("path").textContent=(s.watching?"Watching ":"Stopped · ")+s.root;
  document.getElementById("mood").textContent=MOOD[s.mascot]||s.mascot;
  document.getElementById("pulse").style.background=DOT[s.mascot]||"var(--dim)";

  const runs=s.runs||[];
  let p=0,f=0,i=0;
  runs.forEach(r=>r.cases.forEach(c=>{if(c.verdict==="passed")p++;else if(c.verdict==="failed")f++;else i++;}));
  document.getElementById("stats").innerHTML=
    stat(runs.length,"evaluations")+stat(p,"passed","ok")+stat(f,"failed","bad")+stat(i,"inconclusive","meh");

  const now=document.getElementById("now");
  if(s.mascot==="evaluating"){
    const cur=s.current||[];
    const t=cur.length?cur.map(esc).join(", "):"the repository";
    now.innerHTML=`<div class="now"><div class="spin"></div><div><b>Evaluating…</b><div class="files">running the techniques for ${t}</div></div></div>`;
  } else now.innerHTML="";

  const host=document.getElementById("runs");
  if(!runs.length){host.innerHTML=`<div class="empty"><div class="big">◆</div>Nothing evaluated yet.<br>Edit a file in the watched repo — I’ll take it from there.</div>`;return;}
  host.innerHTML=runs.map((r,idx)=>{
    const trig=r.trigger.length?r.trigger.map(x=>`<code>${esc(x)}</code>`).join(" "):"first look";
    if(r.outcome==="errored")
      return `<div class="run" style="animation-delay:${idx*30}ms"><div class="rhead"><span class="chip errored">errored</span><span class="when">${ago(r.at)}</span></div>`+
        `<div class="trig">on change: ${trig}</div><div class="err">${esc(r.error||"evaluation raised")}</div></div>`;
    const sit=r.situations.length?r.situations.map(x=>`<code>${esc(x)}</code>`).join(" "):"—";
    const cases=r.cases.length?`<div class="cases">`+r.cases.map(c=>
      `<div class="case"><span class="dot ${esc(c.verdict)}"></span><span class="art">${esc(c.artifact)}</span>`+
      `<span class="rec">${esc(c.record)}${c.rung!=null?" · rung "+c.rung:""}</span><span class="det">${esc(c.det||c.detail||"")}</span></div>`
    ).join("")+`</div>`:`<div class="trig">nothing was graded in this run</div>`;
    const perms=r.permission_requests.length?`<div class="trig">needs: ${r.permission_requests.map(esc).join("; ")}</div>`:"";
    return `<div class="run" style="animation-delay:${idx*30}ms"><div class="rhead"><span class="chip ${esc(r.outcome)}">${esc(r.outcome)}</span>`+
      `<span class="when">${ago(r.at)}</span></div><div class="trig">on change: ${trig}</div>`+
      `<div class="sit">situation: ${sit}</div>${perms}${cases}</div>`;
  }).join("");
}
async function poll(){try{const r=await fetch("/status.json?t="+Date.now());render(await r.json());}catch(e){}setTimeout(poll,1400);}
poll();
</script>
</body>
</html>
"""


def dashboard_html() -> str:
    """The complete, self-contained dashboard page. Served as-is by the session's HTTP server."""
    return _HTML
