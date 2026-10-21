#!/usr/bin/env python3
"""Generate an interactive HTML dashboard for 71 monitored stocks."""
import json, os

DATA_PATH = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily") + "/stock_portfolio_enriched.json"
OUT_PATH = os.environ.get("HERMES_WORKSPACE", "/Users/xiashuang/harness/stock_daily") + "/portfolio_dashboard.html"

with open(DATA_PATH) as f:
    stocks = json.load(f)

normed = []
for s in stocks:
    ex = s["exchange"]
    cur = s.get("jsonl_current_price")
    lp = s.get("latest_close")
    if cur is None:
        cur = lp
    normed.append({
        "name": s["stock_name"],
        "code": s["stock_code"],
        "exchange": ex,
        "sector": s.get("sector") or "其他",
        "current_price": cur,
        "latest_close": lp,
        "pe": s.get("pe_ttm"),
        "pb": s.get("pb"),
        "buy_low": s.get("buy_low"),
        "buy_high": s.get("buy_high"),
        "sell_low": s.get("sell_low"),
        "sell_high": s.get("sell_high"),
        "buy_raw": s.get("buy_range_raw"),
        "sell_raw": s.get("sell_range_raw"),
        "chg5": s.get("chg_5d_pct"),
        "has_kline": bool(s.get("has_kline_data")),
    })

total = len(normed)
with_kline = sum(1 for x in normed if x["has_kline"])
ex_counts = {}
for x in normed:
    ex_counts[x["exchange"]] = ex_counts.get(x["exchange"], 0) + 1

sec_counts = {}
for x in normed:
    sec_counts[x["sector"]] = sec_counts.get(x["sector"], 0) + 1
all_sectors = sorted(sec_counts.keys())

scatter = []
for x in normed:
    if x["pe"] is not None and x["pb"] is not None and x["pe"] > 0:
        scatter.append([x["pe"], x["pb"], x["current_price"] or 0, x["name"], x["sector"], x["exchange"]])

range_stocks = [x for x in normed if x["buy_low"] is not None]

table_rows = []
for x in sorted(normed, key=lambda z: z["name"]):
    cp = x["current_price"] if x["current_price"] is not None else "—"
    lc = x["latest_close"] if x["latest_close"] is not None else "—"
    pe = x["pe"] if x["pe"] is not None else "—"
    pb = x["pb"] if x["pb"] is not None else "—"
    c5 = x["chg5"]
    c5s = f'{c5:+.1f}%' if c5 is not None else "—"
    c5c = "up" if c5 is not None and c5 > 0 else ("dn" if c5 is not None and c5 < 0 else "")
    kl = "<span class='kline-yes'>✓</span>" if x["has_kline"] else "—"
    table_rows.append(
        f'<tr><td>{x["name"]}</td><td>{x["code"]}</td><td>{x["exchange"]}</td>'
        f'<td>{x["sector"]}</td><td>{lc}</td><td>{cp}</td><td>{pe}</td><td>{pb}</td>'
        f'<td class="{c5c}">{c5s}</td><td>{kl}</td></tr>'
    )

stock_json = json.dumps(normed, ensure_ascii=False)
scat_json = json.dumps(scatter, ensure_ascii=False)
ex_items = [{"name": k, "value": v} for k, v in ex_counts.items()]
ex_json = json.dumps(ex_items, ensure_ascii=False)
sec_labels_json = json.dumps(all_sectors, ensure_ascii=False)
range_json = json.dumps(
    [
        {
            "name": r["name"],
            "code": r["code"],
            "buy_low": r["buy_low"],
            "buy_high": r["buy_high"],
            "sell_low": r["sell_low"],
            "sell_high": r["sell_high"],
            "current": r["current_price"],
            "close": r["latest_close"],
            "buy_raw": r["buy_raw"],
            "sell_raw": r["sell_raw"],
        }
        for r in range_stocks
    ],
    ensure_ascii=False,
)
table_html = "\n".join(table_rows)
a_cnt = ex_counts.get("SH", 0) + ex_counts.get("SZ", 0) + ex_counts.get("BJ", 0)

html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>医药股票投资组合看板</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
    background:#0d1117; color:#c9d1d9;
    font-family:-apple-system,"Segoe UI",Roboto,"Helvetica Neue","PingFang SC","Microsoft YaHei",sans-serif;
    min-height:100vh;
}
.wrap { max-width:1440px; margin:0 auto; padding:16px; }
h1 { font-size:1.4rem; color:#e6edf3; margin-bottom:4px; }
.sub { color:#8b949e; font-size:.85rem; margin-bottom:18px; }
.stats {
    display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:18px;
}
.card {
    background:#161b22; border:1px solid #30363d; border-radius:10px; padding:14px 16px;
}
.card .label { color:#8b949e; font-size:.75rem; text-transform:uppercase; letter-spacing:.5px; }
.card .value { font-size:1.8rem; font-weight:700; margin-top:4px; }
.accent { color:#00d4aa; } .warn { color:#ff9500; } .bad { color:#ff5a5f; }
.grid { display:grid; grid-template-columns:repeat(12,1fr); gap:14px; }
.col-6 { grid-column:span 6; }
.col-4 { grid-column:span 4; }
.col-12 { grid-column:span 12; }
@media (max-width:900px) { .col-6,.col-4 { grid-column:span 12; } }
.chart-card { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:14px; }
.chart-card h3 { font-size:.95rem; color:#e6edf3; margin-bottom:6px; }
.chart { width:100%; height:300px; }
.chart.tall { height:360px; }
.range-list { display:flex; flex-direction:column; gap:14px; }
.range-item { padding:8px 0; border-bottom:1px solid #21262d; }
.range-item:last-child { border:0; }
.range-name { font-weight:600; color:#e6edf3; font-size:.9rem; }
.range-meta { color:#8b949e; font-size:.78rem; margin-top:2px; }
.bar-wrap {
    position:relative; height:26px; margin-top:8px;
    background:linear-gradient(90deg,#161b22,#21262d);
    border-radius:6px; overflow:hidden;
}
.bar-bg { position:absolute; top:0; height:100%; }
.bar-buy { background:rgba(0,212,170,.25); }
.bar-sell { background:rgba(255,90,95,.25); }
.bar-cursor {
    position:absolute; top:-3px; bottom:-3px; width:3px; background:#fff;
    box-shadow:0 0 8px #fff; border-radius:2px;
}
.bar-labels { display:flex; justify-content:space-between; font-size:.7rem; color:#8b949e; margin-top:4px; }
.status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; vertical-align:middle; }
.dot-green { background:#00d4aa; box-shadow:0 0 6px #00d4aa; }
.dot-red { background:#ff5a5f; box-shadow:0 0 6px #ff5a5f; }
.dot-yellow { background:#ff9500; box-shadow:0 0 6px #ff9500; }
.dot-gray { background:#484f58; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; font-size:.82rem; }
thead th {
    background:#21262d; color:#c9d1d9; padding:8px 10px; text-align:right;
    cursor:pointer; user-select:none; white-space:nowrap;
}
thead th:first-child, thead th:nth-child(3), thead th:nth-child(4), thead th:nth-child(5) { text-align:left; }
thead th:hover { background:#30363d; }
thead th .arrow { margin-left:4px; color:#8b949e; font-size:.7rem; }
tbody tr { border-bottom:1px solid #21262d; }
tbody tr:hover { background:#1c2129; }
tbody td { padding:7px 10px; text-align:right; }
tbody td:first-child { text-align:left; font-weight:500; color:#e6edf3; }
tbody td:nth-child(3), tbody td:nth-child(4), tbody td:nth-child(5) { text-align:left; color:#8b949e; }
.up { color:#00d4aa; } .dn { color:#ff5a5f; }
.kline-yes { color:#00d4aa; font-weight:700; }
.search {
    width:100%; padding:8px 12px; background:#0d1117; border:1px solid #30363d;
    color:#c9d1d9; border-radius:6px; font-size:.85rem; margin-bottom:10px;
}
.search:focus { outline:none; border-color:#00d4aa; }
.footer { color:#484f58; font-size:.72rem; text-align:center; margin-top:18px; }
</style>
</head>
<body>
<div class="wrap">
<h1>📊 医药投资组合看板</h1>
<p class="sub">71 只监控股票 · 含 A 股 / 港股 / 北交所 · 数据更新: 2026-07-08</p>

<div class="stats">
    <div class="card"><div class="label">监控总数</div><div class="value accent">''' + str(total) + '''</div></div>
    <div class="card"><div class="label">有K线数据</div><div class="value">''' + str(with_kline) + '''</div></div>
    <div class="card"><div class="label">A股 (SH+SZ+BJ)</div><div class="value">''' + str(a_cnt) + '''</div></div>
    <div class="card"><div class="label">港股 HK</div><div class="value warn">''' + str(ex_counts.get("HK",0)) + '''</div></div>
    <div class="card"><div class="label">行业数</div><div class="value">''' + str(len(all_sectors)) + '''</div></div>
    <div class="card"><div class="label">有买卖区间</div><div class="value warn">''' + str(len(range_stocks)) + '''</div></div>
</div>

<div class="grid">
    <div class="col-4 chart-card"><h3>交易所分布</h3><div id="chartEx" class="chart"></div></div>
    <div class="col-8 chart-card"><h3>行业分布</h3><div id="chartSec" class="chart"></div></div>
    <div class="col-6 chart-card"><h3>估值散点 (PE vs PB)</h3><div id="chartScat" class="chart tall"></div></div>
    <div class="col-6 chart-card"><h3>价格区间分布</h3><div id="chartHist" class="chart tall"></div></div>
    <div class="col-6 chart-card"><h3>买卖区间进度 (4只)</h3><div class="range-list" id="rangeList"></div></div>
    <div class="col-6 chart-card"><h3>行业价格堆叠分布</h3><div id="chartStack" class="chart tall"></div></div>
    <div class="col-12 chart-card">
        <h3>全部 ''' + str(total) + ''' 只股票 <span style="color:#8b949e;font-weight:400;font-size:.8rem">(点击表头排序)</span></h3>
        <input id="search" class="search" type="text" placeholder="搜索股票名称、代码、行业…">
        <div class="table-wrap"><table id="stkTable">
        <thead><tr>
            <th data-i="0">股票名称<span class="arrow">▲</span></th>
            <th data-i="1">代码</th><th data-i="2">交易所</th><th data-i="3">行业</th>
            <th data-i="4">最新收盘</th><th data-i="5">JSONL现价</th><th data-i="6">PE-TTM</th>
            <th data-i="7">PB</th><th data-i="8">5日涨跌</th><th data-i="9">K线</th>
        </tr></thead>
        <tbody id="tbody">''' + table_html + '''</tbody>
        </table></div>
    </div>
</div>
<p class="footer">Generated by generate_portfolio_dashboard.py · ECharts 5.5 · SenseNova</p>
</div>

<script>
const STK = ''' + stock_json + ''';
const SCAT = ''' + scat_json + ''';
const EX_DATA = ''' + ex_json + ''';
const SEC_LABELS = ''' + sec_labels_json + ''';
const RANGE = ''' + range_json + ''';

const TXT = '#c9d1d9';
const FONT = '-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif';

// 1. Exchange donut
echarts.init(document.getElementById('chartEx')).setOption({
    backgroundColor:'transparent', textStyle:{color:TXT, fontFamily:FONT},
    legend:{bottom:0, textStyle:{color:'#8b949e', fontSize:11}, itemWidth:10, itemHeight:10},
    series:[{
        type:'pie', radius:['48%','72%'], center:['50%','45%'],
        label:{color:TXT, fontSize:11, formatter:'{b}\\n{c}只 ({d}%)'},
        data: EX_DATA.map(function(d){
            var c = d.name==='HK' ? '#ff9500' : '#00d4aa';
            return {name:d.name, value:d.value, itemStyle:{color:c}};
        })
    }]
});

// 2. Sector horizontal bar
var secSorted = SEC_LABELS.slice().sort(function(a,b){
    var ca=STK.filter(function(x){return x.sector===a;}).length;
    var cb=STK.filter(function(x){return x.sector===b;}).length;
    return ca-cb;
});
echarts.init(document.getElementById('chartSec')).setOption({
    backgroundColor:'transparent', textStyle:{color:TXT, fontFamily:FONT},
    grid:{left:80,right:40,top:10,bottom:10},
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'}, formatter:function(p){return p[0].name+' · '+p[0].value+'只'}},
    xAxis:{type:'value',axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
    yAxis:{type:'category',data:secSorted,axisLabel:{color:TXT,fontSize:10}},
    series:[{type:'bar',barWidth:10,data:secSorted.map(function(s){return STK.filter(function(x){return x.sector===s;}).length;}),
        itemStyle:{color:'#00d4aa',borderRadius:[0,4,4,0]}}]
});

// 3. PE/PB scatter
var exColors = {SH:'#00d4aa',SZ:'#ff9500',HK:'#ff5a5f',BJ:'#d2a8ff'};
var scatByEx = {SH:[],SZ:[],HK:[],BJ:[]};
SCAT.forEach(function(d){ scatByEx[d[5]].push([d[0],d[1],d[2],d[3]]); });
echarts.init(document.getElementById('chartScat')).setOption({
    backgroundColor:'transparent', textStyle:{color:TXT, fontFamily:FONT},
    legend:{data:['SH','SZ','HK','BJ'],bottom:0,textStyle:{color:'#8b949e',fontSize:10}},
    grid:{left:50,right:30,top:15,bottom:30},
    tooltip:{trigger:'item',formatter:function(p){
        var d=p.data; return '<b>'+d[3]+'</b><br/>PE: '+d[0].toFixed(1)+'<br/>PB: '+d[1].toFixed(2)+'<br/>现价: '+d[2].toFixed(2);
    }},
    xAxis:{name:'PE-TTM',nameTextStyle:{color:'#8b949e'},type:'log',min:0.5,max:200,
        axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
    yAxis:{name:'PB',nameTextStyle:{color:'#8b949e'},type:'log',min:0.3,max:20,
        axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
    series:[
        {name:'SH',type:'scatter',data:scatByEx.SH,symbolSize:function(p){return Math.max(6,Math.sqrt(p[2]));},itemStyle:{color:'#00d4aa',opacity:0.75}},
        {name:'SZ',type:'scatter',data:scatByEx.SZ,symbolSize:function(p){return Math.max(6,Math.sqrt(p[2]));},itemStyle:{color:'#ff9500',opacity:0.75}},
        {name:'HK',type:'scatter',data:scatByEx.HK,symbolSize:function(p){return Math.max(6,Math.sqrt(p[2]));},itemStyle:{color:'#ff5a5f',opacity:0.75}},
        {name:'BJ',type:'scatter',data:scatByEx.BJ,symbolSize:function(p){return Math.max(6,Math.sqrt(p[2]));},itemStyle:{color:'#d2a8ff',opacity:0.75}}
    ]
});

// 4. Price histogram
var buckets = ["0–10","10–20","20–30","30–50","50–100","100+"];
function inBucket(p,b){
    if(p==null) return false;
    if(b==="0–10") return p<10;
    if(b==="10–20") return p>=10&&p<20;
    if(b==="20–30") return p>=20&&p<30;
    if(b==="30–50") return p>=30&&p<50;
    if(b==="50–100") return p>=50&&p<100;
    return p>=100;
}
var bucketCounts = buckets.map(function(b){
    return STK.filter(function(x){return inBucket(x.current_price,b);}).length;
});
echarts.init(document.getElementById('chartHist')).setOption({
    backgroundColor:'transparent', textStyle:{color:TXT, fontFamily:FONT},
    grid:{left:45,right:20,top:20,bottom:30},
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},
    xAxis:{type:'category',data:buckets,axisLabel:{color:'#8b949e',fontSize:10},name:'价格(元)',nameTextStyle:{color:'#8b949e'}},
    yAxis:{type:'value',axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}},name:'数量'},
    series:[{type:'bar',data:bucketCounts,itemStyle:{
        color:function(p){var colors=['#58a6ff','#79c0ff','#00d4aa','#00d4aa','#ff9500','#ff5a5f'];return colors[p.dataIndex]||'#00d4aa';},
        borderRadius:[4,4,0,0]},
        label:{show:true,position:'top',color:TXT,fontSize:10}}]
});

// 5. Sector price stacked bar
var stackSeries = buckets.map(function(b,bi){
    var colors=['#58a6ff','#79c0ff','#00d4aa','#00d4aa','#ff9500','#ff5a5f'];
    return {
        name:b, type:'bar', stack:'total', barWidth:35,
        data: secSorted.map(function(s){
            return STK.filter(function(x){return x.sector===s&&inBucket(x.current_price,b);}).length;
        }),
        itemStyle:{color:colors[bi]}
    };
});
echarts.init(document.getElementById('chartStack')).setOption({
    backgroundColor:'transparent', textStyle:{color:TXT, fontFamily:FONT},
    legend:{bottom:0,textStyle:{color:'#8b949e',fontSize:9},itemWidth:10,itemHeight:10},
    grid:{left:70,right:15,top:10,bottom:30},
    tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},
    xAxis:{type:'value',axisLabel:{color:'#8b949e'},splitLine:{lineStyle:{color:'#21262d'}}},
    yAxis:{type:'category',data:secSorted,axisLabel:{color:TXT,fontSize:10}},
    series:stackSeries
});

// 6. Buy/sell range progress bars
(function(){
    var list = document.getElementById('rangeList');
    RANGE.forEach(function(r){
        var price = r.close != null ? r.close : r.current;
        var minV = Math.min(r.buy_low, r.sell_low) * 0.7;
        var maxV = r.sell_high * 1.15;
        var pct = function(v){ return ((v-minV)/(maxV-minV))*100; };
        var buyL = pct(r.buy_low), buyR = pct(r.buy_high);
        var sellL = pct(r.sell_low), sellR = pct(r.sell_high);
        var cur = pct(price);
        var stxt='未设区间', dot='dot-gray';
        if(price>=r.buy_low&&price<=r.buy_high){ stxt='买入区间'; dot='dot-green'; }
        else if(price>=r.sell_low&&price<=r.sell_high){ stxt='卖出区间'; dot='dot-red'; }
        else if(price>=r.buy_low-2&&price<=r.buy_low+2 || price>=r.sell_low-2&&price<=r.sell_low+2){ stxt='临近区间'; dot='dot-yellow'; }
        var html = '<div class="range-item">'
            + '<div class="range-name"><span class="status-dot '+dot+'"></span>'
            + r.name+' ('+r.code+') <span style="color:#8b949e;font-weight:400;font-size:.78rem">'+stxt+' · 现价 ¥'+(price!=null?price.toFixed(2):'—')+'</span></div>'
            + '<div class="range-meta">买入 '+r.buy_raw+' · 卖出 '+r.sell_raw+'</div>'
            + '<div class="bar-wrap">'
            + '<div class="bar-bg bar-buy" style="left:'+buyL.toFixed(1)+'%;width:'+(buyR-buyL).toFixed(1)+'%"></div>'
            + '<div class="bar-bg bar-sell" style="left:'+sellL.toFixed(1)+'%;width:'+(sellR-sellL).toFixed(1)+'%"></div>'
            + '<div class="bar-cursor" style="left:'+cur.toFixed(1)+'%"></div>'
            + '</div>'
            + '<div class="bar-labels">'
            + '<span>¥'+minV.toFixed(0)+'</span><span>¥'+r.buy_low+'</span><span>¥'+r.buy_high+'</span>'
            + '<span>¥'+r.sell_low+'</span><span>¥'+r.sell_high+'</span><span>¥'+maxV.toFixed(0)+'</span>'
            + '</div></div>';
        list.insertAdjacentHTML('beforeend', html);
    });
})();

// 7. Table sorting + search
(function(){
    var table = document.getElementById('stkTable');
    var theadThs = table.querySelectorAll('thead th');
    var sortCol = 0, sortAsc = true;
    theadThs.forEach(function(th){
        th.addEventListener('click', function(){
            var i = +th.dataset.i;
            if(i===sortCol) sortAsc=!sortAsc;
            else { sortCol=i; sortAsc=true; }
            render();
        });
    });
    function render(){
        var q = (document.getElementById('search').value||'').toLowerCase();
        var rows = [...document.querySelectorAll('#tbody tr')];
        if(q) rows = rows.filter(function(tr){ return tr.textContent.toLowerCase().includes(q); });
        var cells = rows.map(function(tr){ return [...tr.querySelectorAll('td')]; });
        cells.sort(function(a,b){
            var va=a[sortCol].textContent.trim(), vb=b[sortCol].textContent.trim();
            var na=parseFloat(va.replace(/[^0-9.\-]/g,'')), nb=parseFloat(vb.replace(/[^0-9.\-]/g,''));
            if(!isNaN(na)&&!isNaN(nb)) return sortAsc?na-nb:nb-na;
            return sortAsc?va.localeCompare(vb,'zh'):vb.localeCompare(va,'zh');
        });
        var tbody = document.getElementById('tbody');
        tbody.innerHTML = '';
        cells.forEach(function(c){
            var tr=document.createElement('tr');
            c.forEach(function(td){ tr.appendChild(td.cloneNode(true)); });
            tbody.appendChild(tr);
        });
        theadThs.forEach(function(th){
            var arr=th.querySelector('.arrow');
            if(arr) arr.textContent = th.dataset.i==sortCol ? (sortAsc?'▲':'▼') : '▲';
        });
    }
    document.getElementById('search').addEventListener('input', render);
})();

window.addEventListener('resize', function(){
    ['chartEx','chartSec','chartScat','chartHist','chartStack'].forEach(function(id){
        var el=document.getElementById(id); if(el&&el._echarts) el._echarts.resize();
    });
});
</script>
</body>
</html>'''

os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
with open(OUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

size = os.path.getsize(OUT_PATH)
print(f"DONE: {OUT_PATH} — {size:,} bytes")
print(f"Stocks={total}, K-line={with_kline}, Scatter points={len(scatter)}")
print(f"Charts: 5 ECharts + 1 custom progress bar + 1 sortable table")
print(f"Range stocks: {[r['name'] for r in range_stocks]}")
print(f"Exchange split: {ex_counts}")
print(f"Sectors ({len(all_sectors)}): {all_sectors}")
