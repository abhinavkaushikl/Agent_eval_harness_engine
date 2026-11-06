"""The live dashboard: what was tested, what broke and why, plus the dancers, served by the session.

Served by the session's HTTP server at the bot's port. No framework, no external assets, no build
step: one self-contained page. It has two views behind a top bar:

* **Results** leads with the verdict for the latest change (what failed, in which file, with the
  evidence inline), then the session's totals, the checks that need attention, the pipeline graph
  for the latest run (change -> situation -> technique -> result), every check with why it ran,
  the run history, and what EvalLoop can evaluate. Content is re-rendered only when the data
  actually changes, so it never flickers under the poll.
* **Dancers** has the stage where the characters on the floor dance to the bot's mood (or to a
  previewed mood), the cast, and an inspector for the selected dancer: its dance, skin tone and
  outfit colour, whether it is on the floor, and which one is the desktop pet. It draws from
  ``/avatars.json`` with a JavaScript port of :mod:`evalloop.session.avatars` (between the
  ``AVATAR-ENGINE`` markers, so a test runs it against the Python engine) and saves choices with
  ``POST /avatar``.

The look is deliberately quiet: system fonts (nothing is fetched), zinc greys on off-black with a
fine grain, white as the only accent, and colour kept for meaning (pass, fail, undecided). A faint
glow at the top takes the colour of the current verdict.
"""

from __future__ import annotations

__all__ = ["dashboard_html"]

_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="EvalLoop: what was tested, what broke, and why, live from your session.">
<title>EvalLoop</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' fill='%230b0b0d'/%3E%3Cpath d='M10 11.5a4.5 4.5 0 1 0 0 9c3.2 0 8.8-9 12-9a4.5 4.5 0 1 1 0 9c-3.2 0-8.8-9-12-9z' fill='none' stroke='%23ededef' stroke-width='2.2' stroke-linecap='round'/%3E%3C/svg%3E">
<style>
  :root{
    color-scheme:dark;
    --bg:#0b0b0d; --surface:#131316; --surface2:#18181c; --surface3:#1f1f24;
    --line:rgba(255,255,255,.065); --line2:rgba(255,255,255,.12);
    --ink:#ededef; --ink2:#a1a1aa; --ink3:#71717a; --ink4:#4b4b53;
    --pass:#3ecf8e; --fail:#f0565b; --warn:#e7a33e;
    --glow:rgba(255,255,255,.035);
    --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,"Helvetica Neue",sans-serif;
    --display:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
    --r-xl:22px; --r-lg:16px; --r-md:11px;
    --z-bg:0; --z-content:1; --z-top:10;
    --ease:cubic-bezier(.2,.8,.2,1);
  }
  body.s-problem,body.s-errored{--glow:rgba(240,86,91,.11)}
  body.s-clean{--glow:rgba(62,207,142,.085)}
  body.s-undecided{--glow:rgba(231,163,62,.085)}
  body.s-evaluating{--glow:rgba(255,255,255,.06)}
  *{box-sizing:border-box;margin:0;padding:0}
  [hidden]{display:none!important}
  html{-webkit-font-smoothing:antialiased;scroll-behavior:smooth}
  body{background:var(--bg);color:var(--ink);font:14px/1.5 var(--sans);min-height:100dvh;overflow-x:hidden}
  body::before{content:"";position:fixed;inset:0;z-index:var(--z-bg);pointer-events:none;
    background:radial-gradient(1100px 520px at 10% -14%,var(--glow),transparent 62%),
               radial-gradient(760px 400px at 100% -6%,rgba(255,255,255,.022),transparent 60%)}
  body::after{content:"";position:fixed;inset:0;z-index:var(--z-bg);pointer-events:none;opacity:.06;mix-blend-mode:overlay;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
  :focus-visible{outline:2px solid rgba(255,255,255,.7);outline-offset:2px;border-radius:6px}
  code{font-family:var(--mono)}
  .skip{position:absolute;left:-999px;top:8px;z-index:var(--z-top);padding:8px 12px;border-radius:8px;background:var(--ink);color:var(--bg)}
  .skip:focus{left:12px}

  /* top bar */
  .top{position:sticky;top:0;z-index:var(--z-top);background:rgba(11,11,13,.74);border-bottom:1px solid var(--line);
    backdrop-filter:saturate(140%) blur(14px);-webkit-backdrop-filter:saturate(140%) blur(14px)}
  .top-in{max-width:1120px;margin:0 auto;padding:0 32px;height:60px;display:flex;align-items:center;gap:30px}
  .brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;font:600 15px/1 var(--display);letter-spacing:-.01em}
  .brand svg{width:26px;height:26px;flex:0 0 auto}
  .tabs{display:flex;gap:2px;align-self:stretch}
  .tab{position:relative;display:flex;align-items:center;gap:8px;padding:0 12px;color:var(--ink3);text-decoration:none;
    font-weight:500;font-size:14px;transition:color .2s}
  .tab:hover{color:var(--ink)}
  .tab[aria-current="page"]{color:var(--ink)}
  .tab[aria-current="page"]::after{content:"";position:absolute;left:12px;right:12px;bottom:-1px;height:2px;border-radius:2px;background:var(--ink)}
  .tab .cnt{font:600 11px/1 var(--mono);color:var(--bg);background:var(--fail);border-radius:6px;padding:3px 5px}
  .live{margin-left:auto;display:flex;align-items:center;gap:9px;color:var(--ink2);font-size:13px;font-weight:500;white-space:nowrap}
  .ldot{width:7px;height:7px;border-radius:50%;background:var(--ink3);box-shadow:0 0 0 4px rgba(255,255,255,.04);transition:background .4s}
  .s-problem .ldot,.s-errored .ldot{background:var(--fail);box-shadow:0 0 0 4px rgba(240,86,91,.14)}
  .s-clean .ldot{background:var(--pass);box-shadow:0 0 0 4px rgba(62,207,142,.12)}
  .s-undecided .ldot{background:var(--warn);box-shadow:0 0 0 4px rgba(231,163,62,.12)}
  .s-evaluating .ldot{background:var(--ink);animation:breathe 1.2s ease-in-out infinite}
  @keyframes breathe{50%{box-shadow:0 0 0 7px rgba(255,255,255,.0);opacity:.55}}

  .view{position:relative;z-index:var(--z-content);max-width:1120px;margin:0 auto;padding:52px 32px 120px;animation:enter .35s var(--ease)}
  .view[hidden]{display:none}
  @keyframes enter{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}

  /* hero: the verdict */
  .hero{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:48px;align-items:end;padding-bottom:36px}
  .eyebrow{display:flex;align-items:center;gap:10px;color:var(--ink3);font-size:13px;margin-bottom:18px}
  .eyebrow code{font-size:12.5px;font-weight:500;color:var(--ink2);background:var(--surface2);border:1px solid var(--line);padding:3px 8px;border-radius:7px}
  .hero h1{font:650 46px/1.04 var(--display);letter-spacing:-.037em;text-wrap:balance;display:flex;align-items:center;gap:16px}
  .hero h1 .sdot{width:13px;height:13px}
  .lede{margin-top:16px;max-width:66ch;color:var(--ink2);font-size:16px;line-height:1.6;text-wrap:pretty}
  .lede code{font-size:14px;color:var(--ink);font-weight:500}
  .rate{text-align:right;padding-bottom:4px}
  .rate .big{font:600 60px/1 var(--display);letter-spacing:-.045em;font-variant-numeric:tabular-nums}
  .rate .cap{margin-top:10px;color:var(--ink3);font-size:12.5px;font-variant-numeric:tabular-nums;line-height:1.5}
  .sweep{margin-top:22px;height:2px;max-width:420px;border-radius:2px;overflow:hidden;background:var(--line)}
  .sweep::after{content:"";display:block;height:100%;width:40%;background:linear-gradient(90deg,transparent,rgba(255,255,255,.75),transparent);
    animation:sweep 1.3s var(--ease) infinite}
  @keyframes sweep{from{transform:translateX(-100%)}to{transform:translateX(250%)}}
  .steps{list-style:none;counter-reset:s;margin-top:34px;display:grid;gap:2px;max-width:620px}
  .steps li{counter-increment:s;display:grid;grid-template-columns:44px 1fr;gap:4px 0;padding:14px 0;border-top:1px solid var(--line)}
  .steps li::before{content:counter(s,decimal-leading-zero);grid-row:span 2;font:500 13px/1.5 var(--mono);color:var(--ink4)}
  .steps b{font-weight:600}
  .steps span{color:var(--ink3);font-size:13.5px}
  .cmd{margin-top:22px;display:inline-flex;gap:12px;align-items:center;font:500 13px var(--mono);color:var(--ink2);padding:11px 15px;border-radius:var(--r-md);background:var(--surface);border:1px solid var(--line)}
  .cmd i{font-style:normal;color:var(--ink4);font-family:var(--sans)}

  /* the numbers */
  .metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);overflow:hidden}
  .metric{padding:18px 22px 20px;border-left:1px solid var(--line)}
  .metric:first-child{border-left:none}
  .metric .v{font:600 28px/1.1 var(--display);letter-spacing:-.025em;font-variant-numeric:tabular-nums}
  .metric .k{margin-top:5px;color:var(--ink3);font-size:12.5px}
  .metric.fail .v{color:var(--fail)} .metric.pass .v{color:var(--pass)} .metric.warn .v{color:var(--warn)}
  .notice{margin-top:18px;display:flex;align-items:center;gap:12px;padding:12px 16px;border-radius:var(--r-md);font-size:13.5px;
    background:rgba(231,163,62,.07);border:1px solid rgba(231,163,62,.2);color:#efcd96}
  .notice.neutral{background:var(--surface);border-color:var(--line);color:var(--ink2)}

  /* sections */
  .block{margin-top:48px}
  .bh{display:flex;align-items:baseline;gap:12px;margin-bottom:14px;flex-wrap:wrap}
  .bh h2{font:600 16px/1.3 var(--display);letter-spacing:-.01em}
  .bh .sub{color:var(--ink3);font-size:13px}
  .bh .sub code{font-size:12px;color:var(--ink2)}
  .panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);overflow:hidden}
  .muted{color:var(--ink3);font-size:13.5px;padding:22px}
  .sdot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ink3);flex:0 0 auto}
  .sdot.passed,.sdot.clean{background:var(--pass)}
  .sdot.failed,.sdot.problem,.sdot.errored{background:var(--fail)}
  .sdot.inconclusive,.sdot.undecided{background:var(--warn)}

  /* needs attention */
  .issues{display:grid;gap:10px}
  .issue{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 20px 14px 22px;overflow:hidden}
  .issue::before{content:"";position:absolute;left:0;top:16px;bottom:16px;width:3px;border-radius:0 3px 3px 0;background:var(--fail)}
  .issue.inconclusive::before{background:var(--warn)}
  .ih{display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap}
  .ih code{font-size:13.5px;font-weight:600}
  .ih .meta{color:var(--ink3);font-size:12.5px}
  .evidence{margin-top:12px;font:12.5px/1.6 var(--mono);color:#f3b5b7;background:rgba(240,86,91,.055);border:1px solid rgba(240,86,91,.15);
    border-radius:var(--r-md);padding:12px 14px;white-space:pre-wrap;word-break:break-word;max-height:240px;overflow:auto}
  .issue.inconclusive .evidence,.evidence.warn{color:#efcf9c;background:rgba(231,163,62,.055);border-color:rgba(231,163,62,.15)}
  .linkbtn{margin-top:10px;background:none;border:none;color:var(--ink3);font:500 12.5px var(--sans);cursor:pointer;padding:4px 0;
    display:inline-flex;gap:6px;align-items:center;transition:color .2s}
  .linkbtn:hover{color:var(--ink)}
  .linkbtn .chev{transition:transform .2s var(--ease)}
  .linkbtn.open .chev{transform:rotate(90deg)}
  .whybox{margin-top:8px;padding:14px 16px;border-radius:var(--r-md);background:var(--surface2)}
  .why{color:var(--ink2);line-height:1.65;font-size:13px;margin-bottom:8px}
  .why code,.kv code{font-size:12px;font-weight:500;background:var(--surface3);padding:2px 6px;border-radius:5px;color:var(--ink)}
  .why b{color:var(--ink);font-weight:600}
  .kv{display:flex;gap:14px;font-size:13px;margin:6px 0}
  .kv .k{color:var(--ink3);min-width:104px;flex:0 0 auto}

  /* the pipeline */
  .dagwrap{padding:16px 18px 12px;overflow-x:auto}
  svg.dag{display:block;min-width:760px}
  .dag .dlab{fill:var(--ink3);font:500 12px var(--sans)}
  .dag .dedge{fill:none;stroke:rgba(255,255,255,.12);stroke-width:1.2}
  .dag .dedge.passed{stroke:rgba(62,207,142,.33)} .dag .dedge.failed{stroke:rgba(240,86,91,.6)} .dag .dedge.inconclusive{stroke:rgba(231,163,62,.42)}
  .dag .dnode rect{fill:var(--surface2);stroke:var(--line2)}
  .dag .dnode text{fill:var(--ink);font:500 12.5px var(--sans)}
  .dag .dnode.file text{font:500 12px var(--mono)}
  .dag .dnode.passed rect{fill:rgba(62,207,142,.07);stroke:rgba(62,207,142,.33)}
  .dag .dnode.failed rect{fill:rgba(240,86,91,.1);stroke:rgba(240,86,91,.55)}
  .dag .dnode.inconclusive rect{fill:rgba(231,163,62,.08);stroke:rgba(231,163,62,.42)}
  .dag .dnode.click{cursor:pointer}
  .dag .dnode.click:hover rect{stroke:rgba(255,255,255,.45)}

  /* every check */
  table.checks{width:100%;border-collapse:collapse;font-size:13.5px}
  .checks th{text-align:left;color:var(--ink3);font-weight:500;font-size:12.5px;padding:12px 18px;border-bottom:1px solid var(--line)}
  .checks td{padding:12px 18px;border-bottom:1px solid var(--line);vertical-align:middle}
  .checks tbody tr:last-child td{border-bottom:none}
  .crow{cursor:pointer;transition:background .15s}
  .crow:hover{background:rgba(255,255,255,.022)}
  .crow code{font-size:13px;font-weight:500}
  .crow .tq{color:var(--ink2)}
  .res{font-weight:600} .res.passed{color:var(--pass)} .res.failed{color:var(--fail)} .res.inconclusive{color:var(--warn)}
  .conf{display:inline-flex;align-items:center;gap:7px;color:var(--ink2);font-size:12.5px}
  .conf::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--ink4)}
  .conf.high::before{background:var(--pass)} .conf.low::before{background:var(--warn)}
  .chev{display:inline-block;color:var(--ink4);transition:transform .2s var(--ease)}
  .crow.open .chev{transform:rotate(90deg);color:var(--ink2)}
  .detrow td{padding:2px 18px 18px;background:rgba(255,255,255,.012)}

  /* history + techniques */
  .list{list-style:none}
  .list li{border-bottom:1px solid var(--line)}
  .list li:last-child{border-bottom:none}
  .hist li{display:grid;grid-template-columns:auto 84px minmax(0,1fr) auto auto;gap:12px;align-items:center;padding:12px 18px;font-size:13px}
  .hist .w{font-weight:500}
  .hist code{font-size:12.5px;color:var(--ink2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .hist .n,.hist .t{color:var(--ink3);font-variant-numeric:tabular-nums;white-space:nowrap}
  .tech{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
  .tech li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:start;padding:14px 20px}
  .tech li:nth-child(odd){border-right:1px solid var(--line)}
  .tech li:nth-last-child(2):nth-child(even){border-bottom:1px solid var(--line)}
  .tech li:last-child:nth-child(odd){grid-column:1/-1;border-right:none}
  .tech .sdot{margin-top:6px;background:var(--ink4)}
  .tech li.on .sdot{background:var(--pass)}
  .tech b{font-weight:600;font-size:13px}
  .tech p{color:var(--ink3);font-size:12.5px;line-height:1.5;margin-top:2px}
  .tech .st{font-size:12px;color:var(--ink4);padding-top:1px}
  .tech li.on .st{color:var(--pass)}

  /* dancers */
  .dhead{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;flex-wrap:wrap;margin-bottom:26px}
  .dhead h1{font:650 46px/1.04 var(--display);letter-spacing:-.037em}
  .dhead p{margin-top:14px;color:var(--ink2);font-size:16px;line-height:1.6;max-width:56ch;text-wrap:pretty}
  .seg{display:inline-flex;padding:3px;border-radius:12px;background:var(--surface);border:1px solid var(--line);gap:2px}
  .seg button{font:500 13px var(--sans);color:var(--ink3);background:none;border:none;padding:8px 13px;border-radius:9px;cursor:pointer;
    transition:background .2s,color .2s,transform .15s var(--ease)}
  .seg button:hover{color:var(--ink)}
  .seg button:active{transform:scale(.97)}
  .seg button[aria-pressed="true"]{background:var(--surface3);color:var(--ink);box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
  .floor{position:relative;height:440px;border-radius:var(--r-xl);overflow:hidden;border:1px solid var(--line);
    background:radial-gradient(70% 55% at 50% 118%,rgba(255,255,255,.075),transparent 70%),linear-gradient(180deg,#121215 0%,#0e0e11 66%,#161619 100%);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
  #stage{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:pointer}
  .floorhint{position:absolute;left:20px;top:16px;font-size:12.5px;color:var(--ink3);pointer-events:none}
  .cast{display:grid;grid-template-columns:minmax(0,1fr) 384px;gap:20px;margin-top:20px;align-items:start}
  .castlist{display:grid;gap:8px}
  .mate{display:grid;grid-template-columns:64px minmax(0,1fr) auto;gap:16px;align-items:center;padding:8px 18px 8px 8px;width:100%;
    border-radius:var(--r-lg);background:var(--surface);border:1px solid var(--line);color:inherit;font:inherit;text-align:left;cursor:pointer;
    transition:border-color .2s,background .2s,transform .15s var(--ease)}
  .mate:hover{background:var(--surface2)}
  .mate:active{transform:scale(.995)}
  .mate[aria-selected="true"]{border-color:rgba(255,255,255,.3);background:var(--surface2)}
  .mate canvas{width:64px;height:72px;border-radius:12px;background:#0e0e11;display:block}
  .mate .nm{display:block;font:600 15px/1.3 var(--display)}
  .mate .sig{display:block;color:var(--ink3);font-size:12.5px;margin-top:2px}
  .tags{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
  .tag{font-size:11.5px;font-weight:500;color:var(--ink2);padding:3px 8px;border-radius:7px;background:var(--surface3);border:1px solid var(--line);white-space:nowrap}
  .tag.off{color:var(--ink4);background:none}
  .tag.pet{color:var(--bg);background:var(--ink);border-color:var(--ink)}
  .inspector{position:sticky;top:84px;padding:24px;border-radius:var(--r-xl);background:var(--surface);border:1px solid var(--line)}
  .inspector h3{font:650 26px/1.1 var(--display);letter-spacing:-.03em}
  .inspector .sig{color:var(--ink3);font-size:13px;margin-top:6px}
  .field{margin-top:24px}
  .field .fl{font-size:12.5px;color:var(--ink3);margin-bottom:10px}
  .btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:40px;padding:0 18px;border-radius:11px;width:100%;
    font:600 13.5px var(--sans);cursor:pointer;border:1px solid transparent;transition:transform .15s var(--ease),background .2s}
  .btn:active{transform:scale(.98)}
  .btn.primary{background:var(--ink);color:var(--bg)}
  .btn.primary:hover{background:#fff}
  .btn.done{background:var(--surface3);color:var(--ink2);border-color:var(--line);cursor:default}
  .switch{display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;font-size:13.5px}
  .switch input{appearance:none;-webkit-appearance:none;width:40px;height:24px;border-radius:12px;background:var(--surface3);border:1px solid var(--line2);
    position:relative;cursor:pointer;transition:background .2s;flex:0 0 auto}
  .switch input::after{content:"";position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:var(--ink3);
    transition:transform .2s var(--ease),background .2s}
  .switch input:checked{background:var(--pass);border-color:transparent}
  .switch input:checked::after{transform:translateX(16px);background:#fff}
  .dances{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:1fr;gap:8px}
  .dance{text-align:left;padding:11px 12px;border-radius:12px;background:var(--surface2);border:1px solid var(--line);color:var(--ink);cursor:pointer;
    font:inherit;transition:border-color .2s,background .2s,transform .15s var(--ease)}
  .dance:hover{border-color:var(--line2)}
  .dance:active{transform:scale(.98)}
  .dance[aria-pressed="true"]{border-color:rgba(255,255,255,.42);background:var(--surface3)}
  .dance b{display:block;font-weight:600;font-size:13px}
  .dance span{display:block;color:var(--ink3);font-size:12px;margin-top:2px}
  .swatches{display:flex;flex-wrap:wrap;gap:6px}
  .sw{width:26px;height:26px;border-radius:8px;border:1px solid rgba(255,255,255,.14);cursor:pointer;padding:0;transition:transform .15s var(--ease)}
  .sw:hover{transform:translateY(-1px)}
  .sw[aria-pressed="true"]{outline:2px solid var(--ink);outline-offset:2px}
  .sw.own{background:conic-gradient(from 200deg,#f6d5b8,#a86f4c,#e23b4a,#1f8fe0,#f6d5b8);opacity:.8}

  @media (max-width:880px){
    .top-in{padding:0 16px;gap:16px} .view{padding:34px 16px 80px}
    .hero{grid-template-columns:1fr;gap:24px} .rate{text-align:left}
    .hero h1,.dhead h1{font-size:34px}
    .metrics{grid-template-columns:repeat(2,minmax(0,1fr))} .metric:nth-child(3){border-left:none}
    .metric:nth-child(n+3){border-top:1px solid var(--line)}
    .cast,.tech{grid-template-columns:1fr} .tech li:nth-child(odd){border-right:none} .inspector{position:static}
    .floor{height:340px} .live span:last-child{display:none}
  }
  @media (max-width:600px){.checks .tq,.checks .cf{display:none} .checks td,.checks th{padding-left:14px;padding-right:14px}}
  @media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}html{scroll-behavior:auto}}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top">
  <div class="top-in">
    <a class="brand" href="#results" aria-label="EvalLoop results">
      <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="9" fill="#18181c" stroke="rgba(255,255,255,.12)"/><path d="M10 11.5a4.5 4.5 0 1 0 0 9c3.2 0 8.8-9 12-9a4.5 4.5 0 1 1 0 9c-3.2 0-8.8-9-12-9z" fill="none" stroke="#ededef" stroke-width="2.2" stroke-linecap="round"/></svg>
      <span>EvalLoop</span>
    </a>
    <nav class="tabs" aria-label="Views">
      <a class="tab" href="#results" data-view="results">Results <span class="cnt" id="failcnt" hidden></span></a>
      <a class="tab" href="#dancers" data-view="dancers">Dancers</a>
    </nav>
    <div class="live" aria-live="polite"><span class="ldot"></span><span id="mood">Connecting…</span></div>
  </div>
</header>

<main id="main">
  <div class="view" id="results">
    <section class="hero" id="hero"></section>
    <section class="metrics" id="metrics" aria-label="Session totals"></section>
    <div id="notice"></div>
    <section class="block" id="attention"></section>
    <section class="block" id="pipeline">
      <div class="bh"><h2>Latest run</h2><span class="sub" id="runmeta"></span></div>
      <div class="panel" id="runs"></div>
    </section>
    <section class="block" id="checks"></section>
    <section class="block" id="history"></section>
    <section class="block" id="cats"></section>
  </div>

  <div class="view" id="dancers" hidden>
    <section class="dhead">
      <div>
        <h1>Dancers</h1>
        <p>They dance to the bot's mood: full out while it checks your code, gently while it waits. Choose who is on the floor, what they dance, and who lives on your desktop.</p>
      </div>
      <div class="seg" id="moodseg" role="group" aria-label="Preview mood"></div>
    </section>
    <section class="floor" aria-label="Dance floor"><canvas id="stage"></canvas><div class="floorhint" id="floorhint"></div></section>
    <section class="cast">
      <div class="castlist" id="crew" role="listbox" aria-label="Dancers"></div>
      <aside class="inspector" id="inspector" aria-live="polite"></aside>
    </section>
  </div>
</main>

<script>
const CATS=[
 {id:"code",name:"Code execution",sit:["code_generation"],desc:"Runs your function against its tests in a sandbox."},
 {id:"author",name:"Authored tests",sit:["code_generation"],desc:"Writes a test with an LLM when none exists (low confidence)."},
 {id:"sql",name:"SQL match",sit:["sql_generation"],desc:"Runs a query and a reference on a real database and compares the rows."},
 {id:"rag",name:"RAG recall",sit:["rag_answer"],desc:"recall@k over the passages retrieved, with a confidence interval."},
 {id:"agent",name:"Agent end-state",sit:["agent_action"],desc:"Checks the real resulting state and ignores what the agent claims."},
 {id:"db",name:"Data access",sit:["db_access"],desc:"Runs your file's SQL read-only against a snapshot of the database."},
 {id:"stats",name:"Honest numbers",sit:[],desc:"Every rate carries an interval; a fluke is never called a win."},
];
const TECH={
 A1_execution_based:{l:"Execution grading",d:"the code was run against the test in a sandbox"},
 sql:{l:"SQL execution-match",d:"the query was run on the database and its rows compared to the reference"},
 rag:{l:"RAG recall@k",d:"gold passages checked against what was retrieved, with an interval"},
 agent:{l:"Agent end-state",d:"the real database / filesystem state was verified"},
 db_access:{l:"Read-only DB validation",d:"your file's SQL was run read-only against a snapshot: only reads, schema-grounded, executes"},
 agent_scaffold:{l:"Agent detected",d:"flagged as an agent (an LLM call in a tool-dispatch loop); fill in the end-state checks in the scaffold beside the file to grade it"},
};
const MOOD={idle:"Watching",evaluating:"Checking",happy:"All clear",alarmed:"Problem found",unsure:"Undecided",errored:"Run errored"};
const WORD={clean:"Clean",problem:"Problem",undecided:"Undecided",errored:"Errored"};
const VWORD={passed:"Pass",failed:"Fail",inconclusive:"Undecided"};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const base=p=>String(p||"").replace(/[\/\\]+$/,"").split(/[\/\\]/).pop()||"—";
const ellip=(s,n)=>{s=String(s);return s.length<=n?s:s.slice(0,n-1)+"…";};
const ago=t=>{const d=Date.now()/1000-t;if(d<5)return"just now";if(d<60)return Math.floor(d)+"s ago";if(d<3600)return Math.floor(d/60)+"m ago";return Math.floor(d/3600)+"h ago";};
const plural=(n,one,many)=>`${n} ${n===1?one:(many||one+"s")}`;
const files=list=>{const b=(list||[]).map(base);return b.length<=2?b.join(", "):`${b[0]} +${b.length-1}`;};

const OPEN=new Set(); let LAST=null, SIG="";
function toggleCase(k){OPEN.has(k)?OPEN.delete(k):OPEN.add(k); if(LAST)paint(LAST);}
function openCheck(k){OPEN.add(k); if(LAST)paint(LAST); const el=document.getElementById("row-"+k); if(el)el.scrollIntoView({behavior:"smooth",block:"center"});}

function why(c,run){
  const sit=(run.situations||[])[0]?String(run.situations[0]).split(" (")[0]:"your change";
  const trig=(run.trigger||[]).join(", ")||"a file";
  const t=TECH[c.record]||{l:c.record,d:""};
  let src;
  if(c.kind==="spec") src=`this case comes from the eval spec <code>${esc(c.artifact)}</code> you added`;
  else if(c.kind==="generated"||c.confidence==="low") src=`no test existed, so one was <b>written by the model</b> and run. That makes it <b>low confidence</b>: a generated test, not ground truth`;
  else src=`the test was <b>harvested from a real test in your repo</b>, so it is <b>${esc((c.confidence||"high").toLowerCase())} confidence</b>`;
  return `You changed <code>${esc(trig)}</code>. EvalLoop read it as <b>${esc(sit)}</b>, which calls for <b>${esc(t.l)}</b>: ${esc(t.d)}. For this case, ${src}.`;
}
function kv(k,v){return `<div class="kv"><span class="k">${k}</span><span>${v}</span></div>`;}
function detail(c,run,withEvidence){
  const t=TECH[c.record]||{l:c.record,d:""};
  let h=`<div class="why">${why(c,run)}</div>`;
  h+=kv("Check",`<code>${esc(c.name||"case")}</code>`);
  h+=kv("Technique",esc(t.l));
  if(c.rung!=null) h+=kv("Ladder rung",`${esc(c.rung)}, lower is stronger (1 is execution)`);
  if(c.oracle) h+=kv("Oracle",`<code>${esc(c.oracle)}</code>`);
  if(withEvidence){
    if(c.verdict==="failed") h+=`<div class="evidence">${esc(c.detail||"no evidence recorded")}</div>`;
    else if(c.verdict==="passed") h+=kv("Result",esc(c.detail&&c.detail!=="ok"?c.detail:"the check held"));
    else h+=kv("Result",esc(c.detail||"could not decide"));
  }
  return h;
}

function latestRun(runs,mood){
  const triggered=runs.filter(r=>(r.trigger||[]).length);
  // the run that caused the current mood (the worst of the latest tick), so the headline agrees
  // with the pet, not merely the most recently recorded card
  const MOODOC={happy:"clean",alarmed:"problem",unsure:"undecided",errored:"errored"};
  return triggered.find(r=>r.outcome===MOODOC[mood])||triggered[0]||runs[0];
}
// the functions a run found but had no test for, from its notes ("app.py::load_data: no test oracle")
function untested(run){
  const out=[];(run.notes||[]).forEach(n=>{const m=/^(.+?)::([\w.]+): no (?:test )?oracle/.exec(n);if(m)out.push(m[2]);});
  return out;
}
// a folder with no .py or eval-spec files: its one look has no trigger and nothing was ever graded
function nothingToCheck(runs,latest){
  return !!latest&&!(latest.trigger||[]).length&&!(latest.cases||[]).length&&!runs.some(r=>(r.cases||[]).length);
}
function counts(cases){
  let p=0,f=0,i=0;(cases||[]).forEach(c=>{if(c.verdict==="passed")p++;else if(c.verdict==="failed")f++;else i++;});
  return {p,f,i,n:p+f+i};
}

function heroHTML(s,runs,latest){
  if(!s.root){
    return `<div><div class="eyebrow">No project yet</div><h1>Not watching anything yet</h1>
      <p class="lede">Tell the bot which project to watch, and the verdict for every change you save lands here.</p>
      <ol class="steps">
        <li><b>Click the bot on your desktop</b><span>A small chat opens and asks what to watch.</span></li>
        <li><b>Paste your project folder</b><span>In VS Code, right-click the folder and choose Copy Path.</span></li>
        <li><b>Save a file</b><span>It tests what you changed and shows the result here.</span></li>
      </ol>
      <div class="cmd"><i>or run</i> evalloop start ~/code/your-project --bot</div></div><div></div>`;
  }
  const project=base(s.root), mood=s.mascot||"idle";
  const eyebrow=`<div class="eyebrow"><code title="${esc(s.root)}">${esc(project)}</code><span>${s.watching===false?"paused":"watching"}</span></div>`;
  let title, lede, extra="", rate="";
  if(mood==="evaluating"&&(s.current||[]).length){
    title=`Checking <code>${esc(files(s.current))}</code>`;
    lede="Running the checks that fit this change. The verdict appears here in a moment.";
    extra=`<div class="sweep"></div>`;
  }else if(!latest){
    title=`Watching ${esc(project)}`;
    lede="Save a file and I'll test it. The verdict shows up here as soon as the first check finishes.";
  }else if(nothingToCheck(runs,latest)){
    title=`Nothing to check in ${esc(project)}`;
    lede=`EvalLoop grades Python files (<code>.py</code>) and eval specs (<code>*.eval.json</code>), and this folder has neither. Point the bot at a code project, or add a spec here: a <code>sql</code> spec can test queries against a SQLite file in this folder.`;
  }else if(latest.outcome==="errored"){
    title=`<span class="sdot errored"></span>The last run errored`;
    lede=`Something broke inside the check itself, not necessarily your code.`;
    extra=`<div class="evidence" style="max-width:760px">${esc(latest.error||"no error text")}</div>`;
  }else{
    const k=counts(latest.cases), fileList=`<code>${esc(files(latest.trigger))}</code>`;
    const first=(latest.cases||[]).find(c=>c.verdict==="failed"), firstUnsure=(latest.cases||[]).find(c=>c.verdict!=="passed"&&c.verdict!=="failed");
    if(latest.outcome==="problem"){
      title=`<span class="sdot problem"></span>${k.f?plural(k.f,"check")+" failing":"Problem found"}`;
      lede=first?`<code>${esc(first.name||"a check")}</code> failed in ${fileList}. ${k.p?plural(k.p,"other check")+" passed.":""}`:`A problem was found in ${fileList}.`;
    }else if(latest.outcome==="clean"){
      title=`<span class="sdot clean"></span>${k.p?(k.p===1?"The check passes":`All ${k.p} checks pass`):"Clean"}`;
      lede=`Last tested ${fileList}, ${ago(latest.at)}. Nothing failed.`;
    }else if(!k.n){
      const missing=untested(latest),stem=base((latest.trigger||[])[0]||"app.py").replace(/\.py$/,"");
      const names=missing.map(f=>`<code>${esc(f)}</code>`).join(", ");
      title=`<span class="sdot undecided"></span>Nothing was checked`;
      lede=missing.length
        ?`EvalLoop found ${plural(missing.length,"function")} in ${fileList} (${names}) but no tests for ${missing.length===1?"it":"them"}, and it isn't allowed to write tests, so there was nothing to run. It never starts your app; it runs tests against your functions.`
        :`Nothing in ${fileList} had a check EvalLoop could run.${(latest.notes||[]).length?" "+esc((latest.notes||[]).slice(-1)[0])+".":""}`;
      const remote=((s.consent||{}).approvals||[]).filter(a=>!String(a.endpoint||"").startsWith("sqlite:"));
      extra=`<ol class="steps"><li><b>Add a test</b><span>Create <code>tests/test_${esc(stem)}.py</code> that imports from <code>${esc(stem)}</code> and asserts on what ${missing.length?`<code>${esc(missing[0])}</code>`:"a function"} returns. It runs the next time you save.</span></li>`+
        `<li><b>Or let EvalLoop write the tests</b><span>Restart the bot with <code>--author</code>. It needs a Groq key and sends this code to Groq; tests it writes are marked low confidence.</span></li></ol>`+
        (remote.length?`<p class="lede" style="font-size:14px">You allowed <code>${esc(remote[0].endpoint)}</code>${remote.length>1?` and ${remote.length-1} more`:""}. EvalLoop records that, but it can't connect to that database from a session yet; it only opens local SQLite files.</p>`:"");
    }else{
      title=`<span class="sdot undecided"></span>${k.i?plural(k.i,"check")+" undecided":"Undecided"}`;
      const need=((latest.notes||[]).find(n=>String(n).startsWith("needs packages: "))||"").slice(16);
      lede=need
        ?`Nothing failed in ${fileList}, but ${k.i===1?"its test":"its tests"} couldn't run: ${need.split(", ").map(x=>`<code>${esc(x)}</code>`).join(", ")} ${need.includes(",")?"aren't":"isn't"} installed. Allow the install in the bot's popup, or type <code>install packages</code> in its chat; it builds a separate environment and re-runs.`
        :`Nothing failed in ${fileList}, but ${k.i===1?"one check":"some checks"} couldn't be decided${firstUnsure&&firstUnsure.detail?": "+esc(ellip(firstUnsure.detail,140)):"."}`;
    }
    const rt=latest.rate;
    if(rt){
      const pct=Math.round(rt.estimate*100),lo=Math.round(rt.lower*100),hi=Math.round(rt.upper*100);
      const col=rt.estimate>=.999?"var(--pass)":(rt.failed>0?"var(--fail)":"var(--warn)");
      rate=`<div class="rate" title="${Math.round((rt.confidence||.95)*100)}% Wilson interval over ${rt.n} decided checks"><div class="big" style="color:${col}">${pct}%</div><div class="cap">pass rate · ${rt.n} decided<br>${Math.round((rt.confidence||.95)*100)}% interval ${lo}–${hi}%</div></div>`;
    }
  }
  return `<div>${eyebrow}<h1>${title}</h1><p class="lede">${lede}</p>${extra}</div>${rate||"<div></div>"}`;
}

function metricsHTML(runs){
  const all=[];runs.forEach(r=>(r.cases||[]).forEach(c=>all.push(c)));
  const k=counts(all);
  const m=(v,label,cls)=>`<div class="metric ${v>0?cls:""}"><div class="v">${v}</div><div class="k">${label}</div></div>`;
  return m(runs.length,"runs this session","")+m(k.p,"passed","pass")+m(k.f,"failed","fail")+m(k.i,"undecided","warn");
}

function noticeHTML(s){
  const pending=((s.consent||{}).pending||[]).length;
  let h="";
  if(s.switching_to) h+=`<div class="notice neutral">Switching to <code>${esc(base(s.switching_to))}</code> once the current check finishes.</div>`;
  if(pending) h+=`<div class="notice">${plural(pending,"permission request")} waiting. Answer ${pending===1?"it":"them"} in the bot's popup on your desktop; nothing is opened until you do.</div>`;
  return h;
}

function attentionHTML(run){
  const bad=(run&&run.cases||[]).map((c,ci)=>[c,ci]).filter(([c])=>c.verdict!=="passed");
  if(!bad.length) return "";
  bad.sort((a,b)=>(a[0].verdict==="failed"?0:1)-(b[0].verdict==="failed"?0:1));
  const items=bad.map(([c,ci])=>{
    const key="a"+ci, open=OPEN.has(key), t=TECH[c.record]||{l:c.record};
    const cls=c.verdict==="failed"?"failed":"inconclusive";
    const where=String(c.artifact||"").split("::")[0];
    return `<article class="issue ${cls}"><div class="ih"><span class="sdot ${cls}"></span><code>${esc(c.name||"check")}</code>`+
      `<span class="meta">${esc(base(where))} · ${esc(t.l)}${c.confidence==="low"?" · low confidence":""}</span></div>`+
      `<div class="evidence">${esc(c.detail||(c.verdict==="failed"?"no evidence recorded":"could not decide"))}</div>`+
      `<button class="linkbtn ${open?"open":""}" onclick="toggleCase('${key}')" aria-expanded="${open}"><span class="chev">›</span> Why this ran</button>`+
      (open?`<div class="whybox">${detail(c,run,false)}</div>`:"")+`</article>`;
  }).join("");
  const nf=bad.filter(([c])=>c.verdict==="failed").length, nu=bad.length-nf;
  const sub=[nf?plural(nf,"failing check"):"",nu?plural(nu,"undecided check"):""].filter(Boolean).join(" · ");
  return `<div class="bh"><h2>Needs attention</h2><span class="sub">${sub}</span></div><div class="issues">${items}</div>`;
}

function dagSVG(run){
  const fl=(run.trigger&&run.trigger.length)?run.trigger.map(base):["repository"];
  let sits=(run.situations||[]).map(x=>String(x).split(" (")[0]); if(!sits.length)sits=["unclassified"];
  const cases=run.cases||[];
  let techs=[...new Set(cases.map(c=>c.record))]; if(!techs.length)techs=["(none ready)"];
  const cols=[
    fl.map(fn=>({label:fn,cls:"file"})),
    sits.map(x=>({label:x,cls:"sit"})),
    techs.map(t=>({label:(TECH[t]&&TECH[t].l)||t,cls:"tech",rec:t})),
    cases.map((c,ci)=>({label:c.name||"case",cls:c.verdict,key:"n"+ci,cse:c}))
  ];
  const X=[96,336,578,850],W=[172,184,184,210],gap=42,top=40,nh=30;
  const rows=Math.max(1,...cols.map(c=>c.length));
  const H=top+rows*gap+2, mid=top+rows*gap/2;
  cols.forEach((col,ci)=>col.forEach((nd,k)=>{nd.x=X[ci];nd.w=W[ci];nd.y=mid+(k-(col.length-1)/2)*gap;}));
  let svg=`<svg class="dag" viewBox="0 0 960 ${H}" width="100%" height="${H}" preserveAspectRatio="xMidYMin meet" role="img" aria-label="How this run was evaluated">`;
  ["Change","Situation","Technique","Result"].forEach((lab,ci)=>{svg+=`<text class="dlab" x="${X[ci]-W[ci]/2}" y="18">${lab}</text>`;});
  const edges=(a,b,match)=>{let e="";a.forEach(na=>b.forEach(nb=>{if(match&&!match(na,nb))return;const x1=na.x+na.w/2,x2=nb.x-nb.w/2,mx=(x1+x2)/2;const cls=["passed","failed","inconclusive"].includes(nb.cls)?nb.cls:"";e+=`<path class="dedge ${cls}" d="M ${x1} ${na.y} C ${mx} ${na.y}, ${mx} ${nb.y}, ${x2} ${nb.y}"/>`;}));return e;};
  svg+=edges(cols[0],cols[1])+edges(cols[1],cols[2])+edges(cols[2],cols[3],(t,c)=>c.cse&&c.cse.record===t.rec);
  cols.forEach(col=>col.forEach(nd=>{
    const rx=nd.x-nd.w/2, ry=nd.y-nh/2;
    const click=nd.key?`class="dnode ${nd.cls} click" onclick="openCheck('${nd.key}')"`:`class="dnode ${nd.cls}"`;
    svg+=`<g ${click}><rect x="${rx}" y="${ry}" width="${nd.w}" height="${nh}" rx="8"/><text x="${nd.x}" y="${nd.y+4}" text-anchor="middle">${esc(ellip(nd.label,25))}</text></g>`;
  }));
  return svg+`</svg>`;
}

function checksHTML(run){
  const cases=(run&&run.cases)||[];
  if(!cases.length) return "";
  const rows=cases.map((c,ci)=>{
    const key="n"+ci, open=OPEN.has(key), t=TECH[c.record]||{l:c.record};
    const conf=c.confidence||"na";
    return `<tr class="crow ${open?"open":""}" id="row-${key}" onclick="toggleCase('${key}')"><td><span class="sdot ${esc(c.verdict)}"></span></td>`+
      `<td><code>${esc(c.name||"case")}</code></td><td class="tq">${esc(t.l)}</td>`+
      `<td class="cf"><span class="conf ${esc(conf)}">${conf==="na"?"—":esc(conf[0].toUpperCase()+conf.slice(1))}</span></td>`+
      `<td class="res ${esc(c.verdict)}">${VWORD[c.verdict]||esc(c.verdict)}</td><td><span class="chev">›</span></td></tr>`+
      (open?`<tr class="detrow"><td colspan="6">${detail(c,run,true)}</td></tr>`:"");
  }).join("");
  return `<div class="bh"><h2>Every check</h2><span class="sub">${plural(cases.length,"check")} in the latest run · click one for why it ran</span></div>`+
    `<div class="panel"><table class="checks"><thead><tr><th style="width:34px"></th><th>Check</th><th class="tq">Technique</th><th class="cf">Confidence</th><th>Result</th><th style="width:30px"></th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function historyHTML(runs){
  if(!runs.length) return `<div class="bh"><h2>History</h2></div><div class="panel"><div class="muted">No runs yet this session.</div></div>`;
  const items=runs.slice(0,12).map(r=>{
    const k=counts(r.cases),rt=r.rate;
    const n=k.n?`${plural(k.n,"check")}${rt?" · "+Math.round(rt.estimate*100)+"%":""}`:"no checks";
    return `<li><span class="sdot ${esc(r.outcome)}"></span><span class="w">${WORD[r.outcome]||esc(r.outcome)}</span>`+
      `<code title="${esc((r.trigger||[]).join(", "))}">${esc(files(r.trigger)||"first look")}</code><span class="n">${n}</span><span class="t">${ago(r.at)}</span></li>`;
  }).join("");
  return `<div class="bh"><h2>History</h2><span class="sub">${plural(runs.length,"run")} this session</span></div><div class="panel"><ul class="list hist">${items}</ul></div>`;
}

function catsHTML(runs){
  const seen=new Set();runs.forEach(r=>(r.situations||[]).forEach(x=>seen.add(String(x).split(" ")[0])));
  const items=CATS.map(c=>{const on=c.sit.some(x=>seen.has(x));
    return `<li class="${on?"on":""}"><span class="sdot"></span><div><b>${esc(c.name)}</b><p>${esc(c.desc)}</p></div><span class="st">${on?"Active":"Ready"}</span></li>`;}).join("");
  return `<div class="bh"><h2>What it can evaluate</h2></div><div class="panel"><ul class="list tech">${items}</ul></div>`;
}

function paint(s){
  const mood=s.mascot||"idle", runs=s.runs||[];
  const latest=latestRun(runs,mood);
  const focus=runs.find(r=>(r.cases||[]).length)||runs[0];
  const empty=!!s.root&&nothingToCheck(runs,latest);
  const state=(!s.root||empty)?"idle":(mood==="evaluating"?"evaluating":(latest?({clean:"clean",problem:"problem",undecided:"undecided",errored:"errored"}[latest.outcome]||"idle"):"idle"));
  document.body.className="s-"+state;
  const unchecked=!!latest&&mood!=="evaluating"&&latest.outcome==="undecided"&&!counts(latest.cases).n;
  document.getElementById("mood").textContent=!s.root?"Not watching":(s.watching===false?"Paused":(empty?"Nothing to check":(unchecked?"Nothing checked":(MOOD[mood]||mood))));
  const fails=focus?counts(focus.cases).f:0, fc=document.getElementById("failcnt");
  fc.hidden=!fails; fc.textContent=fails;

  document.getElementById("hero").innerHTML=heroHTML(s,runs,latest);
  const show=(id,on)=>{document.getElementById(id).hidden=!on;};
  show("metrics",!!s.root); show("pipeline",!!s.root);
  document.getElementById("metrics").innerHTML=s.root?metricsHTML(runs):"";
  document.getElementById("notice").innerHTML=noticeHTML(s);
  document.getElementById("attention").innerHTML=attentionHTML(focus);
  show("attention",!!document.getElementById("attention").innerHTML);

  const host=document.getElementById("runs"), meta=document.getElementById("runmeta");
  if(!focus){host.innerHTML=`<div class="muted">Nothing evaluated yet. Save a file and the pipeline for that change is drawn here.</div>`;meta.innerHTML="";}
  else if(focus.outcome==="errored"){host.innerHTML=`<div style="padding:18px"><div class="evidence">${esc(focus.error||"")}</div></div>`;meta.innerHTML=`errored · ${ago(focus.at)}`;}
  else if(!(focus.cases||[]).length){host.innerHTML=`<div class="muted">Nothing was graded in the latest run, so there is no pipeline to draw.</div>`;meta.innerHTML=`${WORD[focus.outcome]||esc(focus.outcome)} · ${ago(focus.at)}`;}
  else{
    host.innerHTML=`<div class="dagwrap">${dagSVG(focus)}</div>`;
    meta.innerHTML=`<span class="sdot ${esc(focus.outcome)}" style="margin-right:6px;vertical-align:1px"></span>${WORD[focus.outcome]||esc(focus.outcome)} · <code>${esc(files(focus.trigger)||"first look")}</code> · ${ago(focus.at)} · click a result to see it`;
  }
  document.getElementById("checks").innerHTML=checksHTML(focus);
  show("checks",!!document.getElementById("checks").innerHTML);
  document.getElementById("history").innerHTML=s.root?historyHTML(runs):"";
  document.getElementById("cats").innerHTML=catsHTML(runs);
}

function signature(s){
  return JSON.stringify((s.runs||[]).map(r=>[r.run_id,r.outcome,r.at,(r.cases||[]).map(c=>c.verdict+c.name)]))
    +"|"+s.mascot+"|"+JSON.stringify(s.current||[])+"|"+[...OPEN].sort().join(",")
    +"|"+s.root+"|"+s.watching+"|"+(s.switching_to||"")+"|"+(((s.consent||{}).pending||[]).length)
    +"|"+Math.floor(Date.now()/30000);  // refresh the "ago" times now and then
}
async function poll(){
  try{const s=await (await fetch("/status.json?t="+Date.now())).json();
    LAST=s; syncChoice(s.avatar);
    const g=signature(s); if(g!==SIG){SIG=g; paint(s);}  // only repaint on real change, so nothing flickers
  }catch(e){document.getElementById("mood").textContent="Session not reachable";}
  setTimeout(poll,1200);
}

/*AVATAR-ENGINE-START*/
const AV=(()=>{
  function catmull(a,b,c,d,u){return 0.5*(2*b+(-a+c)*u+(2*a-5*b+4*c-d)*u*u+(-a+3*b-3*c+d)*u*u*u);}
  function channels(cat,dance,phase,amp){
    const keys=dance.keys,base=dance.base||{},n=keys.length;
    const p=((phase%n)+n)%n,i=Math.floor(p),u=p-i,out={};
    for(const name of Object.keys(cat.rest)){
      const rest=cat.rest[name];
      const at=k=>{const key=keys[((k%n)+n)%n];return name in key?key[name]:(name in base?base[name]:rest);};
      if(cat.discrete.includes(name)){out[name]=at(i);continue;}
      const v=catmull(at(i-1),at(i),at(i+1),at(i+2),u);
      if(name==="sx"){const spin=Math.min(1,Math.max(0,(amp-0.8)/0.2));out[name]=1+spin*(v-1);}
      else out[name]=rest+amp*(v-rest);
    }
    out.drop=Math.max(0,out.drop);out.ft_l_y=Math.max(0,out.ft_l_y);out.ft_r_y=Math.max(0,out.ft_r_y);
    out.flare=Math.min(1,Math.max(0,out.flare));out.knee_out=Math.min(1,Math.max(0,out.knee_out));
    out.sx=Math.min(1,Math.max(-1,out.sx));
    return out;
  }
  class Animator{
    constructor(){this.phase=0;this.amp=0.5;this.alarm=0;this.doubt=0;this.t=0;}
    advance(cat,dt,dance,state){
      const ta=cat.tempo[state]||cat.tempo.idle,tempo=ta[0],amp=ta[1];
      dt=Math.min(0.25,Math.max(0,dt));this.t+=dt;
      const n=dance.keys.length;
      this.phase=(this.phase+dt*tempo/dance.key_seconds)%n;
      const ease=Math.min(1,dt*3);
      this.amp+=(amp-this.amp)*ease;
      this.alarm+=(((state==="alarmed"||state==="errored")?1:0)-this.alarm)*ease;
      this.doubt+=((state==="unsure"?1:0)-this.doubt)*ease;
      const ch=channels(cat,dance,this.phase,this.amp);
      ch.x+=1.3*this.alarm*Math.sin(this.t*38);
      ch.head+=9*this.doubt*Math.sin(this.t*1.4);
      if(this.alarm>0.5)ch.mouth=2;
      return ch;
    }
  }
  const F=(ox,oy,ang,sy)=>({ox,oy,ang,sy:sy===undefined?1:sy});
  function at(f,x,y){const r=f.ang*Math.PI/180,c=Math.cos(r),s=Math.sin(r);y=y*f.sy;return [f.ox+x*c-y*s,f.oy+x*s+y*c];}
  function knee(h,f,l1,l2,sign,out){
    const dx=f[0]-h[0],dy=f[1]-h[1],d=Math.sqrt(dx*dx+dy*dy);
    if(d>=l1+l2||d<1e-6){const k=l1/(l1+l2);return [h[0]+dx*k,h[1]+dy*k];}
    const cosA=(l1*l1+d*d-l2*l2)/(2*l1*d);
    const alpha=Math.acos(Math.min(1,Math.max(-1,cosA)));
    const theta=Math.atan2(dy,dx)+sign*alpha;
    const full=[h[0]+l1*Math.cos(theta),h[1]+l1*Math.sin(theta)];
    const t=((full[0]-h[0])*dx+(full[1]-h[1])*dy)/(d*d);
    const px=h[0]+t*dx,py=h[1]+t*dy;
    return [px+out*(full[0]-px),py+out*(full[1]-py)];
  }
  function skeleton(body,ch){
    const leg=body.thigh+body.shin,hx=ch.hip_x,hy=body.hip_y-ch.drop*leg;
    const pelvis=F(hx,hy,ch.pelvis),torso=F(hx,hy,ch.pelvis+ch.torso,Math.cos(ch.pitch*Math.PI/180));
    const nk=at(torso,ch.head_x,body.neck_y);
    const frames={pelvis,torso,head:F(nk[0],nk[1],torso.ang+ch.head)},legs={};
    for(const [side,sign] of [["r",1],["l",-1]]){
      const sh=at(torso,sign*body.shoulder_x,body.shoulder_y);
      const upper=F(sh[0],sh[1],torso.ang+sign*ch["sh_"+side]);
      const el=at(upper,0,-body.upper);
      const fore=F(el[0],el[1],upper.ang+sign*ch["el_"+side]);
      const wr=at(fore,0,-body.fore);
      frames["upper_"+side]=upper;frames["fore_"+side]=fore;
      frames["hand_"+side]=F(wr[0],wr[1],fore.ang+sign*ch["wr_"+side]);
      const hip=at(pelvis,sign*body.hip_x,0);
      const foot=[sign*(body.hip_x+ch["ft_"+side+"_x"]),body.ankle_y+ch["ft_"+side+"_y"]];
      legs[side]=[hip,knee(hip,foot,body.thigh,body.shin,sign,ch.knee_out),foot];
      frames["ankle_"+side]=F(foot[0],foot[1],sign*ch["toe_"+side]);
    }
    return [frames,legs];
  }
  const SIDE=["upper","fore","hand","ankle"];
  function copies(part){
    const on=part.on||"";
    if(SIDE.includes(on)){const sides=part.side?[part.side]:["r","l"];return sides.map(s=>[on+"_"+s,s==="r"?1:-1]);}
    return [[on,1]].concat(part.both?[[on,-1]]:[]);
  }
  function color(pal,name,hand){
    if(name===null||name===undefined)return null;
    const k=String(name);if(k==="$")return hand;if(k[0]==="#")return k;return pal[k]||"#ff00ff";
  }
  function visible(part,ch){
    if(part.face!=null&&((ch.sx>=0)!==(part.face==="front")))return false;
    if(part.when!=null&&Math.floor(ch[part.when[0]]+0.5)!==part.when[1])return false;
    return true;
  }
  function lookPalette(cat,id,skin,outfit){
    const pal=Object.assign({},cat.characters[id].palette);
    if(skin!=null&&skin>=0&&skin<cat.skins.length)Object.assign(pal,cat.skins[skin]);
    if(outfit!=null&&outfit>=0&&outfit<cat.outfits.length)Object.assign(pal,cat.outfits[outfit]);
    return pal;
  }
  function posePrims(cat,charId,ch,skin,outfit){
    const char=cat.characters[charId],pal=lookPalette(cat,charId,skin,outfit);
    const sk=skeleton(cat.bodies[char.body],ch),frames=sk[0],legs=sk[1];
    const ink=pal.ink,spin=ch.sx*(1+0.4*ch.squash),squash=1-ch.squash;
    const flat=pts=>{const out=[];for(const q of pts)out.push(ch.x+q[0]*spin,q[1]*squash+ch.bob);return out;};
    const prims=[];
    const wOf=(part,d)=>part.w===undefined?d:part.w;
    function emitLocal(part,frame,sign,hand){
      let dx=0,dy=0;
      if(part.shift!=null){dx=ch[part.shift[0]]*part.shift[1];dy=ch[part.shift[0]]*part.shift[2];}
      const raw=part.p,pts=[];
      for(let j=0;j<raw.length;j+=2)pts.push(at(frame,sign*raw[j]+dx,raw[j+1]+dy));
      const fill=color(pal,(sign<0&&part.fl)?part.fl:part.f,hand);
      if(part.t==="poly")prims.push({k:"poly",p:flat(pts),f:fill,o:color(pal,part.o,hand),w:wOf(part,1)});
      else if(part.t==="line")prims.push({k:"line",p:flat(pts),c:color(pal,part.c,hand)||ink,w:wOf(part,1),r:part.r===undefined?true:!!part.r});
      else if(part.t==="limb"){prims.push({k:"line",p:flat(pts),c:ink,w:part.w+1.3,r:true});
        prims.push({k:"line",p:flat(pts),c:fill||ink,w:part.w,r:true});}
    }
    const mix=(a,b,t)=>[a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])];
    for(const part of char.parts){
      if(!visible(part,ch))continue;
      if(part.t==="seg"){
        for(const side of (part.side?[part.side]:["r","l"])){
          const lg=legs[side];let upper=part.seg==="thigh"?lg[0]:lg[1],lower=part.seg==="thigh"?lg[1]:lg[2];
          const band=part.band;
          if(band!=null){const a=band[0],b=band[1];const nu=mix(lower,upper,b),nl=mix(lower,upper,a);upper=nu;lower=nl;}
          const fill=color(pal,(side==="l"&&part.fl)?part.fl:part.f),w=part.w;
          if(part.box){
            const ux=lower[0]-upper[0],uy=lower[1]-upper[1],length=Math.sqrt(ux*ux+uy*uy)||1;
            const nx=-uy/length*w/2,ny=ux/length*w/2;
            const quad=[[upper[0]+nx,upper[1]+ny],[lower[0]+nx,lower[1]+ny],[lower[0]-nx,lower[1]-ny],[upper[0]-nx,upper[1]-ny]];
            prims.push({k:"poly",p:flat(quad),f:fill,o:color(pal,part.o),w:part.ow===undefined?0.8:part.ow});
          }else{
            const seg=flat([upper,lower]);
            if(band==null)prims.push({k:"line",p:seg,c:ink,w:w+1.3,r:true});
            prims.push({k:"line",p:seg,c:fill||ink,w:w,r:band==null});
          }
        }
      }else if(part.t==="fan"){
        const crotch=at(frames.pelvis,0,-2.5),kl=legs.l[1],kr=legs.r[1];
        const bottom=[(kl[0]+kr[0])/2,(kl[1]+kr[1])/2-part.depth];
        prims.push({k:"poly",p:flat([crotch,kl,bottom,kr]),f:color(pal,part.f),o:color(pal,part.o),w:wOf(part,0.8)});
        const n=part.n;
        for(let j=1;j<n;j++){
          const u=j/n;let tip;
          if(u<=0.5){const v=u*2;tip=[kl[0]+v*(bottom[0]-kl[0]),kl[1]+v*(bottom[1]-kl[1])];}
          else{const v=(u-0.5)*2;tip=[bottom[0]+v*(kr[0]-bottom[0]),bottom[1]+v*(kr[1]-bottom[1])];}
          prims.push({k:"line",p:flat([crotch,tip]),c:color(pal,part.pleat)||ink,w:0.45,r:false});
        }
      }else if(part.t==="skirt"){
        const pelvis=frames.pelvis,flare=ch.flare;
        const halfHem=(part.hw+part.fw*flare)/2,halfWaist=part.ww/2,wy=part.wy,hy=part.hy+4*flare,n=part.n;
        const tiers=[[0,part.f],[2.6,part.trim]];
        for(let tier=0;tier<2;tier++){
          const inset=tiers[tier][0],col=tiers[tier][1],y0=hy+inset;
          const pts=tier===0?[[-halfWaist,wy],[halfWaist,wy]]:[[-halfHem+0.4,y0+2.2],[halfHem-0.4,y0+2.2]];
          for(let j=n*2;j>=0;j--){const x=-halfHem+(2*halfHem)*j/(n*2),dip=j%2===1?1.6:0;pts.push([x,y0-dip]);}
          prims.push({k:"poly",p:flat(pts.map(q=>at(pelvis,q[0],q[1]))),f:color(pal,col),o:color(pal,part.o),w:wOf(part,0.7)});
        }
      }else if(part.t==="hand"){
        for(const [bone,sign] of copies({on:"hand",side:part.side})){
          const side=bone[bone.length-1];
          const fill=color(pal,(side==="l"&&part.fl)?part.fl:part.f);
          for(const shape of cat.mudras[String(Math.floor(ch["mudra_"+side]+0.5))])emitLocal(shape,frames[bone],sign,fill);
        }
      }else{
        for(const [bone,sign] of copies(part))emitLocal(part,frames[bone],sign);
      }
    }
    return prims;
  }
  function draw(ctx,prims,ox,oy,s){
    ctx.lineJoin="round";
    for(const q of prims){
      const p=q.p;ctx.beginPath();ctx.moveTo(ox+p[0]*s,oy-p[1]*s);
      for(let i=2;i<p.length;i+=2)ctx.lineTo(ox+p[i]*s,oy-p[i+1]*s);
      if(q.k==="poly"){ctx.closePath();if(q.f){ctx.fillStyle=q.f;ctx.fill();}
        if(q.o){ctx.strokeStyle=q.o;ctx.lineWidth=Math.max(0.6,q.w*s);ctx.stroke();}}
      else{ctx.strokeStyle=q.c;ctx.lineWidth=Math.max(0.5,q.w*s);ctx.lineCap=q.r?"round":"butt";ctx.stroke();}
    }
  }
  return {channels,Animator,posePrims,draw,lookPalette};
})();
/*AVATAR-ENGINE-END*/

// ---- the dancers view: a stage, the cast, and an inspector for the one selected ----
let CAT=null,CHOICE=null,SAVING=0,SEL=null,PREVIEW="live",VIEW="results",RAF=0,LASTT=0;const ANIM={},THUMB={};
const DANCE_NOTE={moonwalk:"The backslide glide",twerk:"Squat bounce, hips up",bharatanatyam:"Aramandi, adavus, mudras",salsa:"On1 basic and a turn"};
const PREVIEWS=[["live","Follow the bot"],["evaluating","Full out"],["idle","Chill"],["alarmed","Alarmed"]];
try{PREVIEW=localStorage.getItem("evalloop.preview")||"live";SEL=localStorage.getItem("evalloop.selected");}catch(e){}
function moodNow(){return PREVIEW==="live"?((LAST&&LAST.mascot)||"idle"):PREVIEW;}
function syncChoice(a){
  if(!a||SAVING)return;
  if(JSON.stringify(a)!==JSON.stringify(CHOICE)){CHOICE=a;renderCrew();}
}
async function saveAvatar(next){
  CHOICE=next;renderCrew();SAVING++;
  try{const r=await fetch("/avatar",{method:"POST",headers:{"Content-Type":"application/json","X-EvalLoop-Bot":"1"},
      body:JSON.stringify({avatar:next})});const j=await r.json();if(j&&j.avatar){CHOICE=j.avatar;renderCrew();}}
  catch(e){}finally{SAVING--;}
}
function selected(){if(!CAT)return null;if(!SEL||!CAT.characters[SEL])SEL=(CHOICE&&CHOICE.pet)||CAT.order[0];return SEL;}
function renderCrew(){
  const list=document.getElementById("crew"),insp=document.getElementById("inspector"),seg=document.getElementById("moodseg");
  seg.innerHTML=PREVIEWS.map(([v,l])=>`<button data-preview="${v}" aria-pressed="${PREVIEW===v}">${l}</button>`).join("");
  if(!CAT||!CHOICE){list.innerHTML=`<div class="panel"><div class="muted">${CAT===false?"This session is too old to serve the dancers. Restart evalloop to get them.":"Loading the dancers…"}</div></div>`;insp.innerHTML="";return;}
  const on=new Set(CHOICE.stage||[]),id=selected();
  list.innerHTML=CAT.order.map(cid=>{
    const c=CAT.characters[cid],mine=CHOICE.chars[cid]||{},d=CAT.dances[mine.dance]||CAT.dances[c.dance];
    const tags=(CHOICE.pet===cid?`<span class="tag pet">Desktop pet</span>`:"")+(on.has(cid)?`<span class="tag">On stage</span>`:`<span class="tag off">Off stage</span>`);
    return `<button class="mate" role="option" data-sel="${cid}" aria-selected="${cid===id}"><canvas data-thumb="${cid}" width="128" height="144"></canvas>`+
      `<span><span class="nm">${esc(c.name)}</span><span class="sig">${esc(d.name)}${mine.dance===c.dance?" · signature":""}</span></span><span class="tags">${tags}</span></button>`;
  }).join("");
  const c=CAT.characters[id],mine=CHOICE.chars[id]||{},pet=CHOICE.pet===id;
  const sw=(list,key,label)=>`<div class="field"><div class="fl">${label}</div><div class="swatches">`+
    `<button class="sw own" data-act="${key}" data-id="${id}" data-v="" aria-pressed="${mine[key]==null}" title="${esc(c.name)}'s own" aria-label="${esc(c.name)}'s own ${label.toLowerCase()}"></button>`+
    list.map((x,i)=>`<button class="sw" style="background:${x[key]}" data-act="${key}" data-id="${id}" data-v="${i}" aria-pressed="${mine[key]===i}" aria-label="${label} ${i+1}"></button>`).join("")+`</div></div>`;
  insp.innerHTML=`<h3>${esc(c.name)}</h3><div class="sig">Signature dance: ${esc(CAT.dances[c.dance].name)}</div>`+
    `<div class="field"><button class="btn ${pet?"done":"primary"}" data-act="pet" data-id="${id}" ${pet?"disabled":""}>${pet?"✓ Your desktop pet":"Make desktop pet"}</button></div>`+
    `<div class="field"><label class="switch"><span>On the dance floor</span><input type="checkbox" data-act="stage" data-id="${id}" ${on.has(id)?"checked":""}></label></div>`+
    `<div class="field"><div class="fl">Dance</div><div class="dances">`+CAT.dance_order.map(dn=>
      `<button class="dance" data-act="dance" data-id="${id}" data-v="${dn}" aria-pressed="${mine.dance===dn}"><b>${esc(CAT.dances[dn].name)}${dn===c.dance?" ★":""}</b><span>${esc(DANCE_NOTE[dn]||"")}</span></button>`).join("")+`</div></div>`+
    sw(CAT.skins,"skin","Skin tone")+sw(CAT.outfits,"outfit","Outfit colour");
}
document.getElementById("dancers").addEventListener("click",e=>{
  const pv=e.target.closest("[data-preview]");
  if(pv){PREVIEW=pv.dataset.preview;try{localStorage.setItem("evalloop.preview",PREVIEW);}catch(x){}renderCrew();return;}
  const pick=e.target.closest("[data-sel]");
  if(pick){SEL=pick.dataset.sel;try{localStorage.setItem("evalloop.selected",SEL);}catch(x){}renderCrew();return;}
  const b=e.target.closest("button[data-act]");if(!b||!CHOICE)return;
  const next=JSON.parse(JSON.stringify(CHOICE)),id=b.dataset.id,act=b.dataset.act;
  if(act==="pet")next.pet=id;
  else if(act==="dance")next.chars[id].dance=b.dataset.v;
  else next.chars[id][act]=b.dataset.v===""?null:Number(b.dataset.v);
  saveAvatar(next);
});
document.getElementById("dancers").addEventListener("change",e=>{
  const el=e.target;if(!el.dataset||el.dataset.act!=="stage"||!CHOICE)return;
  const next=JSON.parse(JSON.stringify(CHOICE)),id=el.dataset.id,s=new Set(next.stage);
  el.checked?s.add(id):s.delete(id);next.stage=CAT.order.filter(x=>s.has(x));
  saveAvatar(next);
});
document.getElementById("stage").addEventListener("click",e=>{
  const crew=(CHOICE&&CHOICE.stage)||[];if(!crew.length)return;
  const r=e.currentTarget.getBoundingClientRect(),i=Math.min(crew.length-1,Math.floor((e.clientX-r.left)/(r.width/crew.length)));
  SEL=crew[i];try{localStorage.setItem("evalloop.selected",SEL);}catch(x){}renderCrew();
});
function frame(now){
  if(VIEW!=="dancers"||!CAT||!CHOICE){RAF=0;return;}
  const reduce=matchMedia("(prefers-reduced-motion:reduce)").matches;
  const dt=reduce?0:Math.min(0.1,(now-LASTT)/1000);LASTT=now;
  const mood=moodNow(),cv=document.getElementById("stage"),ctx=cv.getContext("2d");
  const DPR=Math.min(2,devicePixelRatio||1),W=cv.clientWidth,H=cv.clientHeight;
  if(cv.width!==Math.round(W*DPR)||cv.height!==Math.round(H*DPR)){cv.width=Math.round(W*DPR);cv.height=Math.round(H*DPR);}
  ctx.setTransform(DPR,0,0,DPR,0,0);ctx.clearRect(0,0,W,H);
  // arms out, a dancer is about 80 units wide; size them so neighbours never collide
  const crew=CHOICE.stage||[],floor=H-62,slot=W/Math.max(1,crew.length),s=Math.min(3.1,(H-112)/100,slot/62),roomy=slot>=150;
  document.getElementById("floorhint").textContent=crew.length?(PREVIEW==="live"?`Dancing to the bot's mood: ${MOOD[mood]||mood}`:"Previewing a mood · the bot itself is unaffected"):"Nobody is on the floor. Pick a dancer below and switch on “On the dance floor”.";
  crew.forEach((id,i)=>{
    const mine=CHOICE.chars[id],dance=CAT.dances[mine.dance];if(!dance)return;
    const ox=slot*(i+0.5),anim=ANIM[id]||(ANIM[id]=new AV.Animator());
    const prims=AV.posePrims(CAT,id,anim.advance(CAT,dt,dance,mood),mine.skin,mine.outfit);
    const g=ctx.createRadialGradient(ox,floor,2,ox,floor,52*s);
    g.addColorStop(0,id===SEL?"rgba(255,255,255,.16)":"rgba(255,255,255,.08)");g.addColorStop(1,"rgba(255,255,255,0)");
    ctx.fillStyle=g;ctx.beginPath();ctx.ellipse(ox,floor,52*s,10*s,0,0,6.2832);ctx.fill();
    ctx.save();ctx.globalAlpha=.1;ctx.translate(0,2*floor);ctx.scale(1,-1);AV.draw(ctx,prims,ox,floor,s);ctx.restore();
    AV.draw(ctx,prims,ox,floor,s);
  });
  const fade=ctx.createLinearGradient(0,floor,0,H);fade.addColorStop(0,"rgba(22,22,25,0)");fade.addColorStop(.55,"rgba(22,22,25,.92)");fade.addColorStop(1,"rgba(22,22,25,1)");
  ctx.fillStyle=fade;ctx.fillRect(0,floor,W,H-floor);
  ctx.textAlign="center";
  crew.forEach((id,i)=>{
    const ox=slot*(i+0.5),mine=CHOICE.chars[id],dance=CAT.dances[mine.dance];if(!dance)return;
    ctx.fillStyle=id===SEL?"#ededef":"rgba(237,237,239,.82)";ctx.font="600 13px -apple-system,BlinkMacSystemFont,sans-serif";
    ctx.fillText(CAT.characters[id].name+(!roomy&&CHOICE.pet===id?" ·":""),ox,roomy?H-30:H-20);
    if(roomy){ctx.fillStyle="#71717a";ctx.font="500 12px -apple-system,BlinkMacSystemFont,sans-serif";
      ctx.fillText(dance.name+(CHOICE.pet===id?" · on your desktop":""),ox,H-13);}
  });
  document.querySelectorAll("canvas[data-thumb]").forEach(t=>{
    const id=t.dataset.thumb,mine=CHOICE.chars[id];if(!mine)return;
    const dance=CAT.dances[mine.dance],anim=THUMB[id]||(THUMB[id]=new AV.Animator()),c2=t.getContext("2d");
    c2.setTransform(1,0,0,1,0,0);c2.clearRect(0,0,t.width,t.height);
    AV.draw(c2,AV.posePrims(CAT,id,anim.advance(CAT,dt,dance,mood),mine.skin,mine.outfit),64,138,1.24);
  });
  RAF=requestAnimationFrame(frame);
}
function route(){
  VIEW=location.hash==="#dancers"?"dancers":"results";
  document.getElementById("results").hidden=VIEW!=="results";
  document.getElementById("dancers").hidden=VIEW!=="dancers";
  document.querySelectorAll(".tab").forEach(t=>{if(t.dataset.view===VIEW)t.setAttribute("aria-current","page");else t.removeAttribute("aria-current");});
  document.title=VIEW==="dancers"?"Dancers · EvalLoop":"EvalLoop";
  if(VIEW==="dancers"&&!RAF){LASTT=performance.now();RAF=requestAnimationFrame(frame);}
}
addEventListener("hashchange",()=>{route();window.scrollTo(0,0);});
route();
poll();
(async function(){
  try{CAT=await (await fetch("/avatars.json")).json();}catch(e){CAT=false;renderCrew();return;}
  if(!CHOICE){try{const s=await (await fetch("/status.json?t="+Date.now())).json();CHOICE=s.avatar||null;}catch(e){}}
  renderCrew();route();
})();
</script>
</body>
</html>
"""


def dashboard_html() -> str:
    """The complete, self-contained dashboard page. Served as-is by the session's HTTP server."""
    return _HTML
