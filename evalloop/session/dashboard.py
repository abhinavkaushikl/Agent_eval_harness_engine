"""The live dashboard: a stable, space-themed page with a physics starfield and a table of cases.

Served by the session's HTTP server at the bot's port. No framework, no CDN, no build step. It is
built to be *stable*: the content is re-rendered only when the data actually changes (so it never
flickers under the poll), while an animated starfield + constellation runs continuously behind it.
Every run shows which file in which project was tested, the cases in a table (status / test /
technique / confidence / result), and each row expands to the full "why this ran and what broke".
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
    --bg:#05060d; --ink:#eef0f8; --dim:#8b91a6; --faint:#6a7085; --hair:rgba(255,255,255,.07);
    --panel:rgba(18,20,32,.55); --ok:#2fd36b; --bad:#ff4d4d; --meh:#ffb020; --accent:#7b78ff;
    --radius:16px;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html{-webkit-font-smoothing:antialiased}
  body{background:var(--bg);color:var(--ink);min-height:100vh;overflow-x:hidden;
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",sans-serif;}
  #sky{position:fixed;inset:0;z-index:0;display:block}
  .wrap{position:relative;z-index:1;max-width:980px;margin:0 auto;padding:44px 26px 100px}
  code,.mono{font-family:"SF Mono",ui-monospace,SFMono-Regular,Menlo,monospace}

  /* header */
  header{display:flex;align-items:center;gap:15px;margin-bottom:8px}
  .mark{width:40px;height:40px;border-radius:12px;flex:0 0 auto;display:grid;place-items:center;
    background:conic-gradient(from 210deg,#8f8dff,#5753e6,#8f8dff);color:#fff;font-size:19px;
    box-shadow:0 0 0 1px rgba(255,255,255,.08),0 8px 30px rgba(90,80,255,.35)}
  h1{font-size:22px;letter-spacing:-.02em;font-weight:640}
  .live{margin-left:auto;display:flex;align-items:center;gap:9px;padding:8px 14px;border-radius:999px;
    background:var(--panel);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
    border:1px solid var(--hair);font-size:12.5px;font-weight:600}
  .pulse{width:8px;height:8px;border-radius:50%;background:var(--accent);position:relative}
  .pulse::after{content:"";position:absolute;inset:-5px;border-radius:50%;background:inherit;opacity:.5;
    animation:ping 1.8s cubic-bezier(0,0,.2,1) infinite}
  @keyframes ping{0%{transform:scale(.6);opacity:.5}100%{transform:scale(2.6);opacity:0}}

  /* context bar: project + file being tested + stats */
  .ctx{display:flex;align-items:center;gap:10px;flex-wrap:wrap;color:var(--dim);font-size:13px;
    margin:14px 2px 26px}
  .ctx .b{color:var(--ink);font-weight:600}
  .ctx .sep{color:var(--faint)}
  .pill{display:inline-flex;gap:6px;align-items:center;padding:5px 11px;border-radius:999px;
    background:var(--panel);border:1px solid var(--hair);font-size:12px;font-weight:600}
  .pill .n{font-variant-numeric:tabular-nums}
  .pill.ok{color:var(--ok)} .pill.bad{color:var(--bad)} .pill.meh{color:var(--meh)}
  .spin{width:14px;height:14px;border-radius:50%;border:2px solid rgba(123,120,255,.3);
    border-top-color:var(--accent);animation:spin .8s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}

  .lab{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);
    font-weight:700;margin:30px 2px 12px}

  /* categories: a tidy single-row strip, not stacked cards */
  .cats{display:flex;gap:8px;flex-wrap:wrap}
  .cat{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:11px;
    background:var(--panel);border:1px solid var(--hair);font-size:12.5px}
  .cat .ic{width:20px;height:20px;border-radius:6px;display:grid;place-items:center;font-size:12px;
    background:rgba(123,120,255,.16);color:#b9b7ff}
  .cat.on{border-color:rgba(47,211,107,.4)} .cat.on .ic{background:rgba(47,211,107,.16);color:#7af0a6}
  .cat .nm{font-weight:600} .cat .st{color:var(--faint);font-size:10px;font-weight:700}

  /* a run = a slim header + a table of its cases */
  .run{background:var(--panel);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
    border:1px solid var(--hair);border-radius:var(--radius);margin-bottom:14px;overflow:hidden}
  .run.new{animation:rise .45s cubic-bezier(.16,1,.3,1) both}
  @keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
  .rh{display:flex;align-items:center;gap:11px;padding:14px 18px;border-bottom:1px solid var(--hair)}
  .chip{font-size:11px;font-weight:700;padding:4px 10px;border-radius:999px;letter-spacing:.02em}
  .chip.clean{color:#5fe093;background:rgba(47,211,107,.15)}
  .chip.problem,.chip.errored{color:#ff7d7d;background:rgba(255,77,77,.15)}
  .chip.undecided{color:#ffc357;background:rgba(255,176,32,.16)}
  .rh .file{font-weight:600;font-size:13px}
  .rh .file code{font-size:12px;background:rgba(255,255,255,.06);padding:1px 7px;border-radius:6px}
  .rh .rate{margin-left:auto;display:flex;align-items:baseline;gap:7px;font-variant-numeric:tabular-nums}
  .rh .rate .pct{font-size:15px;font-weight:700}
  .rh .rate .ci{font-size:11px;color:var(--faint);font-family:"SF Mono",ui-monospace,Menlo,monospace}
  .rh .when{color:var(--faint);font-size:12px;font-variant-numeric:tabular-nums;margin-left:14px}

  table.ct{width:100%;border-collapse:collapse;font-size:13px}
  table.ct th{text-align:left;color:var(--faint);font-weight:600;font-size:11px;letter-spacing:.04em;
    text-transform:uppercase;padding:9px 18px;border-bottom:1px solid var(--hair)}
  .crow{cursor:pointer;transition:background .15s}
  .crow:hover{background:rgba(255,255,255,.03)}
  .crow td{padding:11px 18px;border-bottom:1px solid var(--hair);vertical-align:middle}
  .crow:last-child td{border-bottom:none}
  .dot{width:8px;height:8px;border-radius:50%;display:inline-block}
  .dot.passed{background:var(--ok)} .dot.failed{background:var(--bad)} .dot.inconclusive{background:var(--meh)}
  .crow .cn{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-weight:600;color:var(--ink)}
  .crow .tech{color:var(--dim)}
  .crow .res{font-weight:700;font-size:12px}
  .res.passed{color:var(--ok)} .res.failed{color:var(--bad)} .res.inconclusive{color:var(--meh)}
  .chev{color:var(--faint);transition:transform .2s;display:inline-block}
  .crow.open .chev{transform:rotate(90deg)}
  .conf{font-size:10px;font-weight:700;padding:2px 7px;border-radius:5px;letter-spacing:.03em}
  .conf.high{color:#6fe39a;background:rgba(47,211,107,.14)}
  .conf.low{color:#ffc357;background:rgba(255,176,32,.16)}
  .conf.na{color:var(--faint);background:rgba(255,255,255,.05)}

  .detrow td{padding:0 18px 16px;border-bottom:1px solid var(--hair)}
  .why{font-size:13px;color:#cdd0e4;line-height:1.65;background:rgba(123,120,255,.08);
    border-left:2px solid var(--accent);border-radius:9px;padding:11px 13px;margin:4px 0 10px}
  .why code{background:rgba(255,255,255,.08);padding:1px 6px;border-radius:5px;font-size:11px}
  .kv{display:flex;gap:10px;font-size:12.5px;margin:5px 0}
  .kv .k{color:var(--faint);min-width:92px;flex:0 0 auto}
  .evidence{font-family:"SF Mono",ui-monospace,Menlo,monospace;font-size:12px;color:#ffb3ae;
    background:rgba(255,77,77,.08);border-left:2px solid var(--bad);border-radius:9px;
    padding:10px 12px;margin-top:6px;white-space:pre-wrap;word-break:break-word}
  .empty{text-align:center;color:var(--dim);padding:60px 0;font-size:15px}
  @media (prefers-reduced-motion:reduce){.pulse::after,.spin,.run.new{animation:none}}
</style>
</head>
<body>
<canvas id="sky"></canvas>
<div class="wrap">
  <header>
    <div class="mark">◆</div>
    <h1>EvalLoop</h1>
    <div class="live"><span class="pulse" id="pulse"></span><span id="mood">…</span></div>
  </header>
  <div class="ctx" id="ctx"></div>

  <div class="lab">What it evaluates</div>
  <div class="cats" id="cats"></div>

  <div class="lab">Runs</div>
  <div id="runs"></div>
</div>

<script>
const CATS=[
 {id:"code",ic:"λ",name:"Code execution",sit:["code_generation"],desc:"Runs your function against tests in a sandbox."},
 {id:"author",ic:"✎",name:"Authored tests",sit:["code_generation"],desc:"Writes tests with an LLM when none exist (LOW confidence)."},
 {id:"sql",ic:"⌗",name:"SQL match",sit:["sql_generation"],desc:"Runs a query vs a reference on a real DB; compares result sets."},
 {id:"rag",ic:"⌕",name:"RAG recall",sit:["rag_answer"],desc:"recall@k over retrieved passages, with a confidence interval."},
 {id:"agent",ic:"◎",name:"Agent end-state",sit:["agent_action"],desc:"Verifies the real resulting state; ignores the agent's claim."},
 {id:"db",ic:"⛁",name:"Data access",sit:["db_access"],desc:"Extracts your file's SQL and runs it read-only against a snapshot: no writes, schema-grounded, executes."},
 {id:"stats",ic:"∿",name:"Honesty",sit:[],desc:"Intervals on every rate; never calls a fluke a win."},
];
const TECH={
 A1_execution_based:{l:"Execution grading",d:"the code was run against the test in a sandbox"},
 sql:{l:"SQL execution-match",d:"the query was run on the database and its rows compared to the reference"},
 rag:{l:"RAG recall@k",d:"gold passages checked against what was retrieved, with an interval"},
 agent:{l:"Agent end-state",d:"the real database / filesystem state was verified"},
 db_access:{l:"Read-only DB validation",d:"your file's SQL was run read-only against a snapshot — only reads, schema-grounded, executes"},
};
const MOOD={idle:"Watching",evaluating:"Evaluating",happy:"All clean",alarmed:"Problem found",unsure:"Undecided",errored:"Run errored"};
const DOT={idle:"var(--accent)",evaluating:"var(--accent)",happy:"var(--ok)",alarmed:"var(--bad)",unsure:"var(--meh)",errored:"var(--bad)"};
const VWORD={passed:"PASS",failed:"FAIL",inconclusive:"PENDING"};
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const base=p=>String(p||"").replace(/[\/\\]+$/,"").split(/[\/\\]/).pop()||"—";
const ago=t=>{const d=Date.now()/1000-t;if(d<5)return"just now";if(d<60)return Math.floor(d)+"s ago";if(d<3600)return Math.floor(d/60)+"m ago";return Math.floor(d/3600)+"h ago";};

const OPEN=new Set(); let LAST=null, SIG="";
function toggleCase(k){OPEN.has(k)?OPEN.delete(k):OPEN.add(k); if(LAST)paint(LAST);}

function why(c,run){
  const sit=(run.situations||[])[0]?String(run.situations[0]).split(" (")[0]:"your change";
  const trig=(run.trigger||[]).join(", ")||"a file";
  const t=TECH[c.record]||{l:c.record,d:""};
  let src;
  if(c.kind==="spec") src=`this case comes from the eval spec <code>${esc(c.artifact)}</code> you added`;
  else if(c.kind==="generated"||c.confidence==="low") src=`no test existed, so one was <b>written by the model</b> and run — <b>LOW confidence</b> (a generated test, not ground truth)`;
  else src=`the test was <b>harvested from a real test in your repo</b> — <b>${esc((c.confidence||"high").toUpperCase())} confidence</b>`;
  return `You changed <code>${esc(trig)}</code>. EvalLoop read it as <b>${esc(sit)}</b>, which calls for <b>${esc(t.l)}</b> — ${esc(t.d)}. For this case, ${src}.`;
}

function detail(c,run){
  const t=TECH[c.record]||{l:c.record,d:""};
  let h=`<div class="why">${why(c,run)}</div>`;
  h+=kv("Test",`<code>${esc(c.name||"case")}</code>`);
  h+=kv("Technique",esc(t.l));
  if(c.rung!=null) h+=kv("Ladder rung",`${esc(c.rung)} — lower is stronger (1 = execution)`);
  if(c.oracle) h+=kv("Oracle",`<code>${esc(c.oracle)}</code>`);
  if(c.verdict==="failed") h+=`<div class="kv"><span class="k">What broke</span></div><div class="evidence">${esc(c.detail||"no evidence")}</div>`;
  else if(c.verdict==="passed") h+=kv("Result",`✓ ${esc(c.detail&&c.detail!=="ok"?c.detail:"the check held")}`);
  else h+=kv("Result",esc(c.detail||"could not decide"));
  return h;
}
function kv(k,v){return `<div class="kv"><span class="k">${k}</span><span>${v}</span></div>`;}

function paint(s){
  const mood=s.mascot||"idle";
  document.getElementById("mood").textContent=MOOD[mood]||mood;
  document.getElementById("pulse").style.background=DOT[mood]||"var(--dim)";

  const runs=s.runs||[];
  let p=0,f=0,i=0; const seen=new Set();
  runs.forEach(r=>{(r.situations||[]).forEach(x=>seen.add(String(x).split(" ")[0]));
    (r.cases||[]).forEach(c=>{if(c.verdict==="passed")p++;else if(c.verdict==="failed")f++;else i++;});});

  const project=base(s.root);
  const cur=(s.current||[]);
  const triggered=runs.filter(r=>(r.trigger||[]).length);
  // the run that caused the current mood (the worst of the latest tick), so this line agrees with
  // the mood pill and the pet — not merely the most recently recorded card.
  const MOODOC={happy:"clean",alarmed:"problem",unsure:"undecided",errored:"errored"};
  const latest=triggered.find(r=>r.outcome===MOODOC[mood])||triggered[0];
  const file=cur.length?cur.map(base).join(", "):(latest?(latest.trigger||[]).map(base).join(", "):"—");
  let nowBit;
  if(mood==="evaluating"&&cur.length){
    nowBit=`<span class="pill"><span class="spin"></span>now testing <span class="b">${esc(file)}</span></span>`;
  }else if(latest){
    const oc=latest.outcome||"";
    const col={clean:"var(--ok)",problem:"var(--bad)",undecided:"var(--meh)",errored:"var(--bad)"}[oc]||"var(--dim)";
    const word={clean:"clean",problem:"problem found",undecided:"undecided",errored:"errored"}[oc]||oc;
    nowBit=`<span>last tested <span class="b">${esc(file)}</span> <span style="color:${col};font-weight:700">· ${esc(word)}</span></span>`;
  }else{
    nowBit=`<span>watching <span class="b">${esc(project)}</span> — edit a file and I’ll test it</span>`;
  }
  document.getElementById("ctx").innerHTML=
    `<span>project <span class="b">${esc(project)}</span></span><span class="sep">·</span>${nowBit}`+
    `<span style="flex:1"></span>`+
    `<span class="pill"><span class="n">${runs.length}</span> runs</span>`+
    `<span class="pill ok"><span class="n">${p}</span> pass</span>`+
    `<span class="pill bad"><span class="n">${f}</span> fail</span>`+
    `<span class="pill meh"><span class="n">${i}</span> pending</span>`;

  document.getElementById("cats").innerHTML=CATS.map(c=>{
    const on=c.sit.some(x=>seen.has(x));
    return `<div class="cat ${on?'on':''}" title="${esc(c.desc)}"><span class="ic">${c.ic}</span>`+
      `<span class="nm">${c.name}</span><span class="st">${on?'ACTIVE':'READY'}</span></div>`;
  }).join("");

  const host=document.getElementById("runs");
  if(!runs.length){host.innerHTML=`<div class="run"><div class="empty">Nothing evaluated yet.<br>Edit a file — I’ll test it and lay out every case here.</div></div>`;return;}
  host.innerHTML=runs.map((r,ri)=>{
    if(r.outcome==="errored")
      return `<div class="run ${ri===0?'new':''}"><div class="rh"><span class="chip errored">errored</span><span class="file">a run failed</span><span class="when">${ago(r.at)}</span></div><div style="padding:14px 18px"><div class="evidence">${esc(r.error||"")}</div></div></div>`;
    const file=(r.trigger||[]).map(x=>`<code>${esc(base(x))}</code>`).join(" ")||"<code>first look</code>";
    const rows=(r.cases||[]).map((c,ci)=>{
      const t=TECH[c.record]||{l:c.record,d:""};
      const key=ri+":"+ci, open=OPEN.has(key);
      const conf=c.confidence?`<span class="conf ${esc(c.confidence)}">${esc(c.confidence.toUpperCase())}</span>`:`<span class="conf na">—</span>`;
      const resShort=c.verdict==="failed"?(c.failure_class||"failed"):(c.verdict==="passed"?"ok":"pending");
      let out=`<tr class="crow ${open?'open':''}" onclick="toggleCase('${key}')">`+
        `<td><span class="dot ${esc(c.verdict)}"></span></td>`+
        `<td class="cn">${esc(c.name||"case")}</td>`+
        `<td class="tech">${esc(t.l)}</td>`+
        `<td>${conf}</td>`+
        `<td><span class="res ${esc(c.verdict)}">${VWORD[c.verdict]||c.verdict}</span> <span style="color:var(--faint);font-weight:400">${esc(resShort)}</span> <span class="chev">▸</span></td></tr>`;
      if(open) out+=`<tr class="detrow"><td colspan="5">${detail(c,r)}</td></tr>`;
      return out;
    }).join("");
    const rt=r.rate;
    let rateEl="";
    if(rt){const pct=Math.round(rt.estimate*100), lo=Math.round(rt.lower*100), hi=Math.round(rt.upper*100);
      const col=rt.estimate>=.999?"var(--ok)":(rt.failed>0?"var(--bad)":"var(--meh)");
      rateEl=`<span class="rate" title="${Math.round((rt.confidence||.95)*100)}% Wilson interval over ${rt.n} decided cases">`+
        `<span class="pct" style="color:${col}">${pct}%</span><span class="ci">[${lo}–${hi}%] n=${rt.n}</span></span>`;}
    return `<div class="run ${ri===0?'new':''}"><div class="rh">`+
      `<span class="chip ${esc(r.outcome)}">${esc(r.outcome)}</span>`+
      `<span class="file">tested ${file}</span>${rateEl}<span class="when">${ago(r.at)}</span></div>`+
      `<table class="ct"><thead><tr><th></th><th>Test case</th><th>Technique</th><th>Conf</th><th>Result</th></tr></thead>`+
      `<tbody>${rows||'<tr><td colspan="5" style="padding:14px 18px;color:var(--dim)">nothing was graded</td></tr>'}</tbody></table></div>`;
  }).join("");
}

function signature(s){
  return JSON.stringify((s.runs||[]).map(r=>[r.run_id,r.outcome,r.at,(r.cases||[]).map(c=>c.verdict+c.name)]))
    +"|"+s.mascot+"|"+JSON.stringify(s.current||[])+"|"+[...OPEN].sort().join(",");
}
async function poll(){
  try{const s=await (await fetch("/status.json?t="+Date.now())).json();
    LAST=s; const g=signature(s); if(g!==SIG){SIG=g; paint(s);}  // only repaint on real change -> no flicker
  }catch(e){}
  setTimeout(poll,1200);
}
poll();

// ---- space background: drifting nebula + parallax starfield + a light constellation ----
(function(){
  const cv=document.getElementById("sky"),ctx=cv.getContext("2d");
  let W,H,stars=[],nodes=[],DPR=Math.min(2,devicePixelRatio||1);
  const reduce=matchMedia("(prefers-reduced-motion:reduce)").matches;
  function resize(){
    W=cv.width=innerWidth*DPR; H=cv.height=innerHeight*DPR;
    cv.style.width=innerWidth+"px"; cv.style.height=innerHeight+"px";
    const ns=Math.min(220,Math.floor(innerWidth*innerHeight/7000));
    stars=Array.from({length:ns},()=>({x:Math.random()*W,y:Math.random()*H,
      z:Math.random()*.8+.2, r:(Math.random()*1.3+.3)*DPR, tw:Math.random()*6.28, ts:Math.random()*.04+.01}));
    const nn=Math.min(36,Math.floor(innerWidth/42));
    nodes=Array.from({length:nn},()=>({x:Math.random()*W,y:Math.random()*H,
      vx:(Math.random()-.5)*.14*DPR, vy:(Math.random()-.5)*.14*DPR}));
  }
  addEventListener("resize",resize); resize();
  const R=150*DPR; let tms=0;
  function blob(x,y,rad,col){const g=ctx.createRadialGradient(x,y,0,x,y,rad);
    g.addColorStop(0,col);g.addColorStop(1,"rgba(5,6,13,0)");ctx.fillStyle=g;ctx.fillRect(0,0,W,H);}
  function frame(t){
    tms=t*0.001;
    ctx.clearRect(0,0,W,H);
    // nebula clouds, slowly drifting
    blob(W*(.3+.05*Math.sin(tms*.08)), H*(.2+.04*Math.cos(tms*.07)), H*.75, "rgba(93,74,255,.11)");
    blob(W*(.78+.05*Math.cos(tms*.06)), H*(.55+.05*Math.sin(tms*.05)), H*.6, "rgba(40,120,220,.08)");
    // parallax starfield with twinkle
    for(const s of stars){
      s.x-=s.z*.18*DPR; s.y+=s.z*.05*DPR;
      if(s.x< -2){s.x=W+2;s.y=Math.random()*H;} if(s.y>H+2){s.y=-2;}
      const a=(.45+.55*Math.sin(s.tw+=s.ts))*s.z;
      ctx.fillStyle="rgba(214,220,255,"+a.toFixed(3)+")";
      ctx.beginPath();ctx.arc(s.x,s.y,s.r,0,6.283);ctx.fill();
    }
    // light constellation on top
    for(const n of nodes){n.x+=n.vx;n.y+=n.vy;if(n.x<0||n.x>W)n.vx*=-1;if(n.y<0||n.y>H)n.vy*=-1;}
    for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
      const dx=nodes[i].x-nodes[j].x,dy=nodes[i].y-nodes[j].y,d=Math.hypot(dx,dy);
      if(d<R){ctx.strokeStyle="rgba(130,128,245,"+((1-d/R)*.16).toFixed(3)+")";ctx.lineWidth=DPR;
        ctx.beginPath();ctx.moveTo(nodes[i].x,nodes[i].y);ctx.lineTo(nodes[j].x,nodes[j].y);ctx.stroke();}
    }
    if(!reduce)requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
</script>
</body>
</html>
"""


def dashboard_html() -> str:
    """The complete, self-contained dashboard page. Served as-is by the session's HTTP server."""
    return _HTML
