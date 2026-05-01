<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DMG Capital — Trading Tracker</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --green:     #168C67;
  --green-bg:  rgba(22,140,103,0.10);
  --orange:    #F7931A;
  --orange-bg: rgba(247,147,26,0.10);
  --red:       #e03d2f;
  --red-bg:    rgba(224,61,47,0.10);
  --ink:       #111;
  --mid:       #555;
  --muted:     #999;
  --faint:     #ccc;
  --border:    #e8e8e8;
  --card:      #fff;
}
body { font-family: 'DM Sans', sans-serif; background: transparent; color: var(--ink); -webkit-font-smoothing: antialiased; }
.root { width: 100%; }

.hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; flex-wrap: wrap; gap: 8px; }
.hdr-left { display: flex; align-items: center; gap: 10px; }
.mode-badge { font-family: 'DM Mono', monospace; font-size: 10px; font-weight: 500; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.06em; background: var(--green-bg); color: var(--green); }
.mode-badge.live { background: var(--red-bg); color: var(--red); }
.hdr-title { font-size: 11px; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); }
.hdr-meta  { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--faint); }

.stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); margin-bottom: 20px; }
.stat { background: var(--card); padding: 18px 16px; }
.stat-label { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.1em; color: var(--faint); margin-bottom: 8px; }
.stat-val { font-size: clamp(15px,2vw,22px); font-weight: 500; letter-spacing: -0.4px; line-height: 1; color: var(--ink); }
.stat-val.g { color: var(--green); }
.stat-val.r { color: var(--red); }
.stat-sub { font-size: 11px; color: var(--muted); margin-top: 5px; }

.card { background: var(--card); border: 1px solid var(--border); padding: 20px; margin-bottom: 16px; }
.card-hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid #f5f5f5; flex-wrap: wrap; gap: 8px; }
.card-title { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted); }
.card-sub { font-size: 11px; color: var(--faint); font-family: 'DM Mono', monospace; }

.pos-row { display: grid; grid-template-columns: 52px 1fr 88px 56px; align-items: center; padding: 9px 0; border-bottom: 1px solid #fafafa; gap: 10px; }
.pos-row:last-child { border-bottom: none; }
.pos-tk { font-family: 'DM Mono', monospace; font-size: 12px; font-weight: 500; }
.pos-bar-wrap { height: 3px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }
.pos-bar { height: 100%; border-radius: 2px; transition: width .5s; }
.pos-usd { font-size: 12px; font-weight: 500; text-align: right; }
.pos-wt  { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--muted); text-align: right; }

.sigs { display: flex; flex-wrap: wrap; gap: 6px; }
.sig { font-family: 'DM Mono', monospace; font-size: 11px; padding: 4px 10px; border-radius: 20px; }
.sig-gate-open  { background: var(--green); color: #fff; }
.sig-gate-close { background: var(--red-bg); color: var(--red); border: 1px solid rgba(224,61,47,.2); }
.sig-paxg  { background: var(--orange-bg); color: var(--orange); }
.sig-buy   { background: var(--green-bg); color: var(--green); }
.sig-sell  { background: #f5f5f5; color: var(--muted); }

.tabs { display: flex; gap: 2px; margin-bottom: 14px; }
.tab { font-size: 11px; font-weight: 500; padding: 4px 10px; border: none; background: transparent; color: var(--muted); cursor: pointer; border-radius: 6px; }
.tab:hover { color: var(--mid); }
.tab.on { background: #f0f0f0; color: var(--ink); }

.tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.tbl th { text-align: left; padding: 0 8px 10px 0; font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; color: var(--faint); border-bottom: 1px solid #f0f0f0; white-space: nowrap; }
.tbl th.r { text-align: right; }
.tbl td { padding: 9px 8px 9px 0; border-bottom: 1px solid #fafafa; vertical-align: middle; }
.tbl tr:last-child td { border-bottom: none; }
.tbl tr:hover td { background: #fdfdfd; }
.td-date { font-family: 'DM Mono', monospace; font-size: 11px; color: var(--muted); white-space: nowrap; }
.td-r { text-align: right; font-family: 'DM Mono', monospace; }
.td-val { font-weight: 500; }
.act { display: inline-block; font-family: 'DM Mono', monospace; font-size: 10px; padding: 2px 7px; border-radius: 4px; font-weight: 500; }
.act-buy  { background: var(--green-bg); color: var(--green); }
.act-sell { background: var(--red-bg);   color: var(--red); }
.act-hold { background: #f5f5f5;         color: var(--muted); }
.no-data { color: var(--muted); font-size: 13px; padding: 16px 0; }
.loading { color: var(--muted); font-size: 13px; padding: 40px 0; text-align: center; }
.pager { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
.pg-btn { font-size: 11px; padding: 4px 10px; border: 1px solid var(--border); background: var(--card); border-radius: 6px; cursor: pointer; color: var(--mid); }
.pg-btn:hover { background: #f5f5f5; }
.pg-btn:disabled { opacity: .4; cursor: default; }
.pg-info { font-size: 11px; color: var(--muted); font-family: 'DM Mono', monospace; }

.chart-wrap { position: relative; }
.chart-tip {
  display: none; position: absolute; top: 4px; left: 50%; transform: translateX(-50%);
  background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 8px 14px;
  pointer-events: none; white-space: nowrap; z-index: 10; box-shadow: 0 2px 12px rgba(0,0,0,.08);
  flex-direction: column; align-items: center; gap: 3px;
}
.tip-date { font-family:'DM Mono',monospace; font-size:10px; color:var(--muted); letter-spacing:.06em; text-transform:uppercase; }
.tip-val  { font-size:14px; font-weight:600; color:var(--ink); }
.tip-ret  { font-size:11px; font-weight:500; }

.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.two-col .card { margin-bottom: 0; }

@media (max-width: 640px) {
  .stats { grid-template-columns: 1fr 1fr; }
  .two-col { grid-template-columns: 1fr; }
  .pos-row { grid-template-columns: 48px 1fr 80px; }
  .pos-wt { display: none; }
}
</style>
</head>
<body>
<div class="root">
  <div id="loading" class="loading">Loading trade history…</div>
  <div id="content" style="display:none;">

    <div class="hdr">
      <div class="hdr-left">
        <div class="hdr-title">DMG Capital</div>
        <span class="mode-badge" id="mode-badge">PAPER</span>
      </div>
      <div class="hdr-meta" id="updated-at">—</div>
    </div>

    <div class="stats">
      <div class="stat">
        <div class="stat-label">Portfolio Value</div>
        <div class="stat-val" id="s-val">—</div>
        <div class="stat-sub">From $100,000 (2018)</div>
      </div>
      <div class="stat">
        <div class="stat-label">Total Return</div>
        <div class="stat-val g" id="s-ret">—</div>
        <div class="stat-sub">Since Jan 2018</div>
      </div>
      <div class="stat">
        <div class="stat-label">Fees Paid</div>
        <div class="stat-val" id="s-fees">—</div>
        <div class="stat-sub">0.26% per trade</div>
      </div>
      <div class="stat">
        <div class="stat-label">Total Trades</div>
        <div class="stat-val" id="s-ntrades">—</div>
        <div class="stat-sub" id="s-ntrades-sub">—</div>
      </div>
      <div class="stat">
        <div class="stat-label">BTC Gate</div>
        <div class="stat-val" id="s-gate">—</div>
        <div class="stat-sub" id="s-gate-sub">—</div>
      </div>
    </div>

    <!-- Chart -->
    <div class="card">
      <div class="card-hdr">
        <div class="card-title">Portfolio Growth — Backtest (2018) + Live Paper</div>
        <div class="tabs" style="margin-bottom:0;">
          <button class="tab on" onclick="chartRange('all')">All</button>
          <button class="tab" onclick="chartRange('1y')">1Y</button>
          <button class="tab" onclick="chartRange('6m')">6M</button>
          <button class="tab" onclick="chartRange('3m')">3M</button>
        </div>
      </div>
      <div class="chart-wrap">
        <div class="chart-tip" id="tip">
          <div class="tip-date" id="tip-date">—</div>
          <div class="tip-val"  id="tip-val">—</div>
          <div class="tip-ret"  id="tip-ret">—</div>
        </div>
        <svg id="chart-svg" viewBox="0 0 900 220" style="width:100%;display:block;overflow:visible;"></svg>
      </div>
    </div>

    <!-- Positions + Signals -->
    <div class="two-col">
      <div class="card">
        <div class="card-hdr"><div class="card-title">Current Positions</div><div class="card-sub" id="pos-total">—</div></div>
        <div id="pos-list"></div>
      </div>
      <div class="card">
        <div class="card-hdr"><div class="card-title">Current Signals</div><div class="card-sub" id="sig-date">—</div></div>
        <div class="sigs" id="sig-list"></div>
      </div>
    </div>

    <!-- Trade history -->
    <div class="card">
      <div class="card-hdr">
        <div class="card-title">Full Trade History — Backtest + Live</div>
        <div class="card-sub" id="trade-count">—</div>
      </div>
      <div class="tabs">
        <button class="tab on" onclick="filterLog('all')">All</button>
        <button class="tab" onclick="filterLog('buy')">Buys</button>
        <button class="tab" onclick="filterLog('sell')">Sells</button>
        <button class="tab" onclick="filterLog('hold')">Holds</button>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>Date</th>
            <th>Action</th>
            <th>Asset</th>
            <th>Reason / Signal</th>
            <th class="r">Value</th>
            <th class="r">Fee</th>
            <th class="r">Portfolio</th>
          </tr>
        </thead>
        <tbody id="tbl-body"></tbody>
      </table>
      <div class="pager">
        <button class="pg-btn" id="pg-prev" onclick="page(-1)">← Prev</button>
        <span class="pg-info" id="pg-info">—</span>
        <button class="pg-btn" id="pg-next" onclick="page(1)">Next →</button>
      </div>
    </div>

  </div>
</div>

<script>
const REPO    = "https://raw.githubusercontent.com/dygo3739/dmg-capital/main";
const SIGNALS = "https://raw.githubusercontent.com/callingmarkets/signals/main/portfolios.json";
const PG_SIZE = 30;

let allTrades=[], filtTrades=[], equity=[], pgIdx=0;

const fmt$  = v => v==null?"—":"$"+Math.round(v).toLocaleString();
const fmtP  = (v,d=1) => v==null?"—":(v>=0?"+":"")+v.toFixed(d)+"%";
const fmtDt = iso => new Date(iso).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"});

// ── Chart ─────────────────────────────────────────────────────────────────────
function spline(pts) {
  if(pts.length<2)return"";
  const t=0.35;let d=`M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  for(let i=0;i<pts.length-1;i++){
    const p0=pts[Math.max(i-1,0)],p1=pts[i],p2=pts[i+1],p3=pts[Math.min(i+2,pts.length-1)];
    const c1x=p1[0]+(p2[0]-p0[0])*t/3,c1y=p1[1]+(p2[1]-p0[1])*t/3;
    const c2x=p2[0]-(p3[0]-p1[0])*t/3,c2y=p2[1]-(p3[1]-p1[1])*t/3;
    d+=` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }return d;
}

function drawChart(range) {
  document.querySelectorAll("#content .card:nth-child(3) .tab").forEach(b=>{
    b.classList.toggle("on", b.textContent.toLowerCase()===range||(range==="all"&&b.textContent==="All"));
  });
  let data=equity;
  if(range==="1y") data=equity.slice(-52);
  else if(range==="6m") data=equity.slice(-26);
  else if(range==="3m") data=equity.slice(-13);
  if(data.length<2)return;

  const W=900,H=220,pt=16,pb=30,iH=H-pt-pb;
  const vals=data.map(e=>e.value);
  const minV=Math.min(...vals)*0.97,maxV=Math.max(...vals)*1.02,rng=maxV-minV||1;
  const xS=i=>(i/(data.length-1||1))*W;
  const yS=v=>pt+iH-((v-minV)/rng)*iH;

  const step=Math.max(1,Math.floor(data.length/250));
  const samp=data.filter((_,i)=>i%step===0||i===data.length-1);
  const pts=samp.map((_,i)=>[xS(Math.min(i*step,data.length-1)),yS(samp[i].value)]);
  const line=spline(pts);
  const area=line+` L${xS(data.length-1).toFixed(1)},${(pt+iH).toFixed(1)} L0,${(pt+iH).toFixed(1)} Z`;

  let grids="",ylbls="",xlbls="";
  [0.25,0.5,0.75].forEach(p=>{
    const y=(pt+iH*(1-p)).toFixed(1),v=minV+rng*p;
    const lbl=v>=1000000?`$${(v/1000000).toFixed(1)}M`:v>=1000?`$${Math.round(v/1000)}K`:`$${Math.round(v)}`;
    grids+=`<line x1="0" y1="${y}" x2="${W}" y2="${y}" stroke="#f5f5f5" stroke-width="1"/>`;
    ylbls+=`<text x="4" y="${(parseFloat(y)-4).toFixed(1)}" fill="#ddd" font-size="9" font-family="DM Mono,monospace">${lbl}</text>`;
  });
  [0,.25,.5,.75,1].forEach(p=>{
    const i=Math.min(Math.round(p*(data.length-1)),data.length-1);
    const x=parseFloat(xS(i).toFixed(1));
    const a=p===0?"start":p===1?"end":"middle";
    xlbls+=`<text x="${p===0?Math.max(x,30):p===1?Math.min(x,W-10):x}" y="${H-8}" fill="#ccc" font-size="10" font-family="DM Sans,sans-serif" text-anchor="${a}">${data[i].date.slice(0,7)}</text>`;
  });

  const hs=Math.max(1,Math.floor(data.length/180));
  let hL="",hR="";
  for(let i=0;i<data.length;i+=hs){
    const x=xS(i).toFixed(1),y=yS(data[i].value).toFixed(1);
    const rw=Math.max((W/data.length)*hs+2,8).toFixed(1);
    const rx=Math.max(0,parseFloat(x)-parseFloat(rw)/2).toFixed(1);
    hL+=`<g id="ch${i}" style="display:none;pointer-events:none;">
      <line x1="${x}" y1="${pt}" x2="${x}" y2="${pt+iH}" stroke="#168C67" stroke-width="1" stroke-dasharray="3,2" opacity=".3"/>
      <circle cx="${x}" cy="${y}" r="4" fill="#168C67" stroke="#fff" stroke-width="2.5"/>
    </g>`;
    hR+=`<rect x="${rx}" y="${pt}" width="${rw}" height="${iH}" fill="transparent" style="cursor:crosshair"
      onmouseenter="chHov(${i},${Math.round(data[i].value)},'${data[i].date}')" onmouseleave="chOut()"/>`;
  }

  const lx=xS(data.length-1).toFixed(1),ly=yS(data[data.length-1].value).toFixed(1);
  document.getElementById("chart-svg").innerHTML=`
    <defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#168C67" stop-opacity=".13"/>
      <stop offset="100%" stop-color="#168C67" stop-opacity="0"/>
    </linearGradient></defs>
    ${grids}${ylbls}
    <path d="${area}" fill="url(#cg)"/>
    <path d="${line}" fill="none" stroke="#168C67" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${lx}" cy="${ly}" r="3.5" fill="#168C67" stroke="#fff" stroke-width="2.5"/>
    ${hL}${xlbls}${hR}`;
}

window.chartRange=r=>drawChart(r);
window.chHov=(i,val,date)=>{
  document.querySelectorAll('[id^="ch"]').forEach(e=>e.style.display="none");
  const el=document.getElementById("ch"+i);if(el)el.style.display="";
  const tip=document.getElementById("tip");if(!tip)return;
  const pct=((val/100000-1)*100).toFixed(1);
  document.getElementById("tip-date").textContent=date;
  document.getElementById("tip-val").textContent=fmt$(val);
  const re=document.getElementById("tip-ret");
  re.textContent=fmtP(parseFloat(pct));
  re.style.color=parseFloat(pct)>=0?"var(--green)":"var(--red)";
  tip.style.display="flex";
};
window.chOut=()=>{
  document.querySelectorAll('[id^="ch"]').forEach(e=>e.style.display="none");
  const t=document.getElementById("tip");if(t)t.style.display="none";
};

// ── Trade log ─────────────────────────────────────────────────────────────────
window.filterLog=function(f){
  pgIdx=0;
  document.querySelectorAll(".tabs .tab").forEach(b=>{
    const map={all:"All",buy:"Buys",sell:"Sells",hold:"Holds"};
    b.classList.toggle("on",map[f]===b.textContent);
  });
  filtTrades=f==="all"?allTrades
    :f==="buy" ?allTrades.filter(t=>t.action==="BUY")
    :f==="sell"?allTrades.filter(t=>t.action==="SELL")
    :allTrades.filter(t=>t.action==="HOLD");
  renderPage();
};

function renderPage(){
  const start=pgIdx*PG_SIZE,end=Math.min(start+PG_SIZE,filtTrades.length);
  document.getElementById("pg-info").textContent=`${filtTrades.length?start+1:0}–${end} of ${filtTrades.length}`;
  document.getElementById("pg-prev").disabled=pgIdx===0;
  document.getElementById("pg-next").disabled=end>=filtTrades.length;

  const rows=filtTrades.slice(start,end).map(t=>{
    const ac=t.action==="BUY"?"act-buy":t.action==="SELL"?"act-sell":"act-hold";
    const tc=t.action==="BUY"?"var(--green-bg)":t.action==="SELL"?"var(--red-bg)":"#f5f5f5";
    const txc=t.action==="BUY"?"var(--green)":t.action==="SELL"?"var(--red)":"var(--muted)";
    const tkCell=t.ticker
      ?`<span style="display:inline-block;font-family:DM Mono,monospace;font-size:10px;padding:2px 6px;border-radius:4px;background:${tc};color:${txc};">${t.ticker}</span>`
      :`<span style="color:var(--muted);font-size:11px;">${t.note||"—"}</span>`;
    const reason=(t.reason||t.signal||"").replace("Signal → ","").slice(0,35);
    const src=t.source==="paper"?`<span style="font-family:DM Mono,monospace;font-size:9px;color:var(--muted);margin-left:4px;">PAPER</span>`:"";
    return `<tr>
      <td class="td-date">${fmtDt(t.date)}</td>
      <td><span class="act ${ac}">${t.action==="HOLD"?"—":t.action}</span>${src}</td>
      <td>${tkCell}</td>
      <td style="font-size:11px;color:var(--muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${reason}</td>
      <td class="td-r td-val">${t.value?fmt$(t.value):"—"}</td>
      <td class="td-r" style="color:var(--muted);">${t.fee?fmt$(t.fee):"—"}</td>
      <td class="td-r td-val">${t.portfolio_value?fmt$(t.portfolio_value):"—"}</td>
    </tr>`;
  }).join("");
  document.getElementById("tbl-body").innerHTML=rows||`<tr><td colspan="7" class="no-data">No trades match this filter.</td></tr>`;
}
window.page=d=>{pgIdx=Math.max(0,pgIdx+d);renderPage();};

// ── Positions ─────────────────────────────────────────────────────────────────
function renderPositions(state){
  const el=document.getElementById("pos-list");
  if(!state?.positions){el.innerHTML='<div class="no-data">No position data</div>';return;}
  const total=state.total_value||0;
  const maxV=Math.max(...Object.values(state.positions).filter(v=>v>0));
  document.getElementById("pos-total").textContent=fmt$(total);
  el.innerHTML=Object.entries(state.positions).sort((a,b)=>b[1]-a[1]).map(([tk,v])=>{
    if(v<0.01)return"";
    const pct=total>0?(v/total*100):0,bw=maxV>0?(v/maxV*100):0;
    const col=tk==="USD"?"#ddd":tk==="PAXG"?"var(--orange)":"var(--green)";
    return `<div class="pos-row">
      <div class="pos-tk">${tk}</div>
      <div class="pos-bar-wrap"><div class="pos-bar" style="width:${bw}%;background:${col};"></div></div>
      <div class="pos-usd">${fmt$(v)}</div>
      <div class="pos-wt">${pct.toFixed(1)}%</div>
    </div>`;
  }).join("");
}

// ── Signals ───────────────────────────────────────────────────────────────────
function renderSignals(portfolio){
  const el=document.getElementById("sig-list");
  const gEl=document.getElementById("s-gate"),gSub=document.getElementById("s-gate-sub");
  if(!portfolio?.current_signals){el.innerHTML='<span class="no-data">—</span>';return;}
  const sigs=portfolio.current_signals;
  const btc=sigs["BTC"]||"—",paxg=sigs["PAXG"]||"—";
  gEl.textContent=btc; gEl.className="stat-val "+(btc==="BUY"?"g":"r");
  gSub.textContent=btc==="BUY"?"Gate open":(paxg==="BUY"?"→ PAXG":"→ USDT");
  const pills=[`<span class="sig ${btc==="BUY"?"sig-gate-open":"sig-gate-close"}">BTC Gate: ${btc}</span>`];
  if(paxg) pills.push(`<span class="sig sig-paxg">PAXG: ${paxg}</span>`);
  Object.entries(sigs).forEach(([t,s])=>{
    if(t==="BTC"||t==="PAXG")return;
    pills.push(`<span class="sig ${s==="BUY"?"sig-buy":"sig-sell"}">${s==="BUY"?"▲ ":""}${t}</span>`);
  });
  el.innerHTML=pills.join("");
  if(portfolio.generated) document.getElementById("sig-date").textContent=fmtDt(portfolio.generated);
}

// ── Main ──────────────────────────────────────────────────────────────────────
async function load(){
  const [hR,sR,sigR]=await Promise.allSettled([
    fetch(`${REPO}/trade_history.json?t=${Date.now()}`).then(r=>r.ok?r.json():null).catch(()=>null),
    fetch(`${REPO}/paper_state.json?t=${Date.now()}`).then(r=>r.ok?r.json():null).catch(()=>null),
    fetch(`${SIGNALS}?t=${Date.now()}`).then(r=>r.ok?r.json():null).catch(()=>null),
  ]);
  const hist=hR.value,state=sR.value;
  const sigData=sigR.value;
  const portfolio=sigData?(sigData.portfolios||[]).find(p=>p.id==="crypto-rotation"):null;

  // Equity curve — backtest + stitch live paper value
  equity=hist?.equity_curve||portfolio?.equity_curve||[];
  if(state?.total_value&&state?.timestamp){
    const ld=state.timestamp.slice(0,10);
    if(!equity.find(e=>e.date===ld)) equity=[...equity,{date:ld,value:state.total_value}];
  }

  // Stats
  const finalVal=state?.total_value||hist?.final_value||portfolio?.final_value;
  const totalRet=hist?.total_return_pct||portfolio?.total_return_pct;
  if(finalVal) document.getElementById("s-val").textContent=fmt$(finalVal);
  const rEl=document.getElementById("s-ret");
  if(totalRet!=null){rEl.textContent=fmtP(totalRet,1);rEl.className="stat-val "+(totalRet>=0?"g":"r");}
  if(hist?.total_fees!=null) document.getElementById("s-fees").textContent=fmt$(hist.total_fees);

  // Build trade list
  if(hist?.trades?.length){
    const eqMap={};
    (hist.equity_curve||[]).forEach(e=>{eqMap[e.date]=e.value;});
    allTrades=[...hist.trades].reverse().map(t=>({...t,portfolio_value:eqMap[t.date]||null,source:"backtest"}));
    const b=allTrades.filter(t=>t.action==="BUY").length;
    const s=allTrades.filter(t=>t.action==="SELL").length;
    const h=allTrades.filter(t=>t.action==="HOLD").length;
    document.getElementById("s-ntrades").textContent=b+s;
    document.getElementById("s-ntrades-sub").textContent=`${b} buys · ${s} sells · ${h} holds`;
    document.getElementById("trade-count").textContent=`${allTrades.length} total records`;
  } else {
    document.getElementById("trade-count").textContent="Push crypto_portfolio.py to generate trade history";
    document.getElementById("s-ntrades").textContent="—";
  }

  filtTrades=allTrades;
  renderPage();
  renderPositions(state);
  renderSignals(portfolio);
  drawChart("all");

  const ts=state?.timestamp||hist?.generated||portfolio?.generated;
  if(ts) document.getElementById("updated-at").textContent="Updated "+fmtDt(ts);

  document.getElementById("loading").style.display="none";
  document.getElementById("content").style.display="block";
}

load().catch(e=>{
  document.getElementById("loading").textContent="⚠ Could not load — ensure repo is public.";
  console.error(e);
});
</script>
</body>
</html>
