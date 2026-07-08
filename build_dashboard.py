# -*- coding: utf-8 -*-
"""生成 数据中心运行监控大屏 (data-screen-1).

读取 aggregate_tool.py 产出的 output/hourly_metrics.csv 以及四张原始表,
计算各类聚合指标, 输出一个自带数据、可离线打开的单文件 index.html。
"""
import csv
import json
from collections import defaultdict

BASE = "output/hourly_metrics.csv"
DISK_UTIL_MODS = {"sda_util", "sdb_util", "sdc_util", "sdd_util", "sde_util"}
MEM_MODS = {"mem_used", "mem_free", "mem_buff", "mem_cache"}


def load():
    with open(BASE, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fnum(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0


def main():
    rows = load()

    # ---- 主机元数据 (去重) ----
    host_meta = {}
    for r in rows:
        h = r["hostid"]
        if h not in host_meta:
            host_meta[h] = {
                "hostid": h,
                "hostname": r["hostname"],
                "owner": r["owner"],
                "model": r["model"],
                "location1": r["location1"],
                "location2": r["location2"],
            }

    # ---- 累加器 ----
    cpu_date = defaultdict(lambda: [0.0, 0.0])          # date -> [w_sum, w]
    mem_date = defaultdict(lambda: [0.0, 0.0])
    net_in_date = defaultdict(lambda: [0.0, 0.0])
    net_out_date = defaultdict(lambda: [0.0, 0.0])
    load_hour = defaultdict(lambda: [0.0, 0.0])         # hour -> [w_sum, w]
    cpu_loc = defaultdict(lambda: [0.0, 0.0])           # loc1 -> [w_sum, w]
    disk_util_host = defaultdict(lambda: [0.0, 0.0])    # host -> [w_sum, w]
    cpu_host = defaultdict(lambda: [0.0, 0.0])
    load_host = defaultdict(lambda: [0.0, 0.0])
    mem_host_used = defaultdict(float)
    mem_host_total = defaultdict(float)
    load_max_host = defaultdict(float)
    cpu_max_host = defaultdict(float)
    disk_util_max_host = defaultdict(float)
    total_samples = 0

    dates = set()
    for r in rows:
        mod = r["mod"]
        val = fnum(r["avg_value"])
        mx = fnum(r["max_value"])
        w = fnum(r["sample_minutes"])
        total_samples += w
        d = r["date"]
        dates.add(d)
        host = r["hostid"]

        if mod == "cpu_usage":
            cpu_date[d][0] += val * w; cpu_date[d][1] += w
            cpu_loc[r["location1"]][0] += val * w; cpu_loc[r["location1"]][1] += w
            cpu_host[host][0] += val * w; cpu_host[host][1] += w
            if mx > cpu_max_host[host]:
                cpu_max_host[host] = mx
        elif mod == "mem_used":
            mem_host_used[host] += val * w
            mem_host_total[host] += val * w
        elif mod in ("mem_free", "mem_buff", "mem_cache"):
            mem_host_total[host] += val * w
        elif mod == "net_in":
            net_in_date[d][0] += val * w; net_in_date[d][1] += w
        elif mod == "net_out":
            net_out_date[d][0] += val * w; net_out_date[d][1] += w
        elif mod == "load1":
            h = int(r["hour"])
            load_hour[h][0] += val * w; load_hour[h][1] += w
            load_host[host][0] += val * w; load_host[host][1] += w
            if mx > load_max_host[host]:
                load_max_host[host] = mx
        elif mod in DISK_UTIL_MODS:
            disk_util_host[host][0] += val * w; disk_util_host[host][1] += w
            if mx > disk_util_max_host[host]:
                disk_util_max_host[host] = mx

    # mem_date: 用主机加权累计反推日期权重较复杂, 这里用主机层近似后按日期聚合
    # 简化: 以 (date) 维度从 mem_host 无法区分, 改为在行级累计 mem_used/total 加权
    # 由于 mem 拆分到不同 mod 行, 采用可用的 budget: 用 host 层比率 * 主机数近似不可行,
    # 因此使用逐行更简单的方式: 重新扫描做日期级 mem 累计
    mem_date_b = defaultdict(lambda: [0.0, 0.0])
    bucket_used = defaultdict(float)
    bucket_total = defaultdict(float)
    for r in rows:
        mod = r["mod"]
        if mod in MEM_MODS:
            w = fnum(r["sample_minutes"])
            key = (r["date"], r["hostid"])
            v = fnum(r["avg_value"]) * w
            bucket_total[key] += v
            if mod == "mem_used":
                bucket_used[key] += v
    for (d, _h), u in bucket_used.items():
        t = bucket_total.get((d, _h), 0.0)
        if t > 0:
            mem_date_b[d][0] += (u / t) * 100.0
            mem_date_b[d][1] += 1.0

    def wavg(a):
        return round(a[0] / a[1], 2) if a[1] else 0.0

    # ---- 维度分布 ----
    model_cnt = defaultdict(int)
    loc1_cnt = defaultdict(int)
    owner_cnt = defaultdict(int)
    for h, m in host_meta.items():
        model_cnt[m["model"]] += 1
        loc1_cnt[m["location1"]] += 1
        owner_cnt[m["owner"]] += 1

    # ---- 日期序列 ----
    # 注意: pref 类指标(CPU/内存/网络/负载)仅部分日期有采样, 磁盘类覆盖全量日期。
    # 趋势图与 CPU/内存 KPI 只使用有 pref 采样的日期, 避免缺失日被填 0 导致指标失真。
    date_list = sorted(dates)
    pref_dates = sorted(cpu_date.keys())
    cpu_trend = [wavg(cpu_date[d]) for d in pref_dates]
    mem_trend = [wavg(mem_date_b[d]) for d in pref_dates]
    net_in_trend = [wavg(net_in_date[d]) for d in pref_dates]
    net_out_trend = [wavg(net_out_date[d]) for d in pref_dates]

    load_curve = [wavg(load_hour[h]) for h in range(24)]

    cpu_loc_list = sorted(cpu_loc.keys())
    cpu_loc_val = [wavg(cpu_loc[k]) for k in cpu_loc_list]

    # ---- 磁盘 TOP10 ----
    disk_rank = []
    for h, a in disk_util_host.items():
        disk_rank.append((host_meta[h]["hostname"], wavg(a)))
    disk_rank.sort(key=lambda x: x[1], reverse=True)
    disk_top = disk_rank[:10][::-1]   # 横向条形, 底部最大

    # ---- 负责人负载 (平均CPU) ----
    owner_cpu = defaultdict(lambda: [0.0, 0.0])
    for host, a in cpu_host.items():
        o = host_meta[host]["owner"]
        owner_cpu[o][0] += a[0]; owner_cpu[o][1] += a[1]
    owner_list = sorted(owner_cnt.keys())
    owner_cpu_val = [wavg(owner_cpu[o]) for o in owner_list]

    # ---- 主机明细表 ----
    table = []
    alert_hosts = 0
    for h, m in host_meta.items():
        cpu = wavg(cpu_host[h])
        used = mem_host_used[h]; tot = mem_host_total[h]
        mem = round(used / tot * 100, 1) if tot > 0 else 0.0
        disk = wavg(disk_util_host[h])
        loadmx = round(load_max_host[h], 2)
        loadavg = wavg(load_host[h])
        cpumx = round(cpu_max_host[h], 1)
        diskmx = round(disk_util_max_host[h], 1)
        status = "正常"
        if disk >= 54 or cpu >= 46 or loadavg >= 17:
            status = "告警"; alert_hosts += 1
        elif disk >= 50 or cpu >= 44 or loadavg >= 16.5:
            status = "关注"
        table.append({
            "host": m["hostname"], "owner": m["owner"], "model": m["model"],
            "loc": m["location1"] + "-" + m["location2"],
            "cpu": cpu, "mem": mem, "disk": disk, "load": loadmx,
            "cpumx": cpumx, "diskmx": diskmx, "status": status,
        })
    table.sort(key=lambda x: x["cpu"], reverse=True)

    # ---- KPI ----
    avg_cpu = round(sum(cpu_trend) / len(cpu_trend), 1) if cpu_trend else 0
    avg_mem = round(sum(mem_trend) / len(mem_trend), 1) if mem_trend else 0

    data = {
        "meta": {
            "n_hosts": len(host_meta),
            "n_days": len(date_list),
            "n_pref_days": len(pref_dates),
            "date_start": date_list[0],
            "date_end": date_list[-1],
            "total_samples": int(total_samples),
            "avg_cpu": avg_cpu,
            "avg_mem": avg_mem,
            "alert_hosts": alert_hosts,
        },
        "dates": pref_dates,
        "cpu_trend": cpu_trend,
        "mem_trend": mem_trend,
        "net_in_trend": net_in_trend,
        "net_out_trend": net_out_trend,
        "load_curve": load_curve,
        "model": {"keys": list(model_cnt.keys()), "vals": list(model_cnt.values())},
        "loc1": {"keys": list(loc1_cnt.keys()), "vals": list(loc1_cnt.values())},
        "owner": {"keys": owner_list, "vals": owner_cnt, "cpu": owner_cpu_val},
        "cpu_loc": {"keys": cpu_loc_list, "vals": cpu_loc_val},
        "disk_top": {"hosts": [x[0] for x in disk_top], "vals": [x[1] for x in disk_top]},
        "table": table,
    }

    html = build_html(data)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成 index.html  主机数=%d 天数=%d 样本=%d 告警=%d" %
          (data["meta"]["n_hosts"], data["meta"]["n_days"],
           data["meta"]["total_samples"], data["meta"]["alert_hosts"]))


def build_html(data):
    payload = json.dumps(data, ensure_ascii=False)
    return HTML_TEMPLATE.replace("/*__DATA__*/", payload)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>数据中心运行监控大屏 | data-screen-1</title>
<script src="echarts.min.js"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:100%; height:100%; background:#050b1a; overflow:hidden;
    font-family:"Microsoft YaHei","PingFang SC",-apple-system,sans-serif; color:#cfe6ff; }
  #screen { position:absolute; left:50%; top:50%; width:1920px; height:1080px;
    transform-origin:center center; background:
      radial-gradient(1200px 600px at 50% -10%, rgba(24,94,168,.35), transparent 60%),
      radial-gradient(900px 500px at 10% 100%, rgba(14,116,144,.25), transparent 60%),
      radial-gradient(900px 500px at 90% 100%, rgba(96,42,168,.22), transparent 60%),
      linear-gradient(180deg,#070e22 0%, #050b1a 100%); }
  .panel { position:relative; background:linear-gradient(180deg, rgba(16,38,78,.55), rgba(9,20,44,.55));
    border:1px solid rgba(54,143,222,.35); border-radius:6px;
    box-shadow:inset 0 0 24px rgba(28,108,196,.12); }
  .panel::before,.panel::after{content:"";position:absolute;width:14px;height:14px;border:2px solid #2fd6ff;}
  .panel::before{left:-1px;top:-1px;border-right:none;border-bottom:none;}
  .panel::after{right:-1px;bottom:-1px;border-left:none;border-top:none;}
  .ptitle{font-size:16px;font-weight:700;letter-spacing:2px;color:#7fe3ff;padding:8px 14px 4px;
    display:flex;align-items:center;gap:8px;}
  .ptitle::before{content:"";width:4px;height:15px;background:linear-gradient(#2fd6ff,#2f7bff);border-radius:2px;box-shadow:0 0 8px #2fd6ff;}
  .chart{width:100%;height:calc(100% - 34px);}

  /* header */
  #hd{height:74px;display:flex;align-items:center;justify-content:center;position:relative;}
  #hd h1{font-size:34px;font-weight:800;letter-spacing:8px;
    background:linear-gradient(90deg,#8fe9ff,#2f9bff,#9b7bff);-webkit-background-clip:text;background-clip:text;color:transparent;
    text-shadow:0 0 22px rgba(47,154,255,.35);}
  #hd .en{position:absolute;font-size:12px;letter-spacing:5px;color:#4f7bb0;top:54px;}
  #hd .clock{position:absolute;right:26px;top:20px;text-align:right;}
  #hd .clock .t{font-size:22px;color:#9fe0ff;font-weight:700;letter-spacing:1px;}
  #hd .clock .d{font-size:12px;color:#5f86b8;}
  #hd .tag{position:absolute;left:26px;top:22px;font-size:13px;color:#5f86b8;letter-spacing:2px;}

  /* kpi */
  #kpi{height:96px;display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-top:6px;}
  .kpi{display:flex;flex-direction:column;align-items:center;justify-content:center;}
  .kpi .v{font-size:34px;font-weight:800;line-height:1;
    background:linear-gradient(180deg,#bff0ff,#39a7ff);-webkit-background-clip:text;background-clip:text;color:transparent;}
  .kpi .v small{font-size:14px;font-weight:600;color:#6fb3e6;margin-left:3px;-webkit-text-fill-color:#6fb3e6;}
  .kpi .l{font-size:13px;color:#7fa6cf;margin-top:8px;letter-spacing:1px;}
  .kpi .bar{width:60%;height:3px;margin-top:8px;background:linear-gradient(90deg,#2fd6ff,#2f7bff);border-radius:2px;opacity:.8;}

  /* main grid */
  #main{height:624px;margin-top:10px;display:grid;
    grid-template-columns:438px 1fr 438px;grid-template-rows:1fr 1fr;gap:14px;}
  #c_model{grid-row:1;grid-column:1;} #c_loc{grid-row:2;grid-column:1;}
  #c_trend{grid-row:1;grid-column:2;} #c_net{grid-row:2;grid-column:2;}
  #c_cpuloc{grid-row:1;grid-column:3;} #c_disk{grid-row:2;grid-column:3;}

  /* table */
  #band{height:250px;margin-top:10px;}
  #tbl{width:100%;height:calc(100% - 30px);overflow:auto;}
  #tbl::-webkit-scrollbar{width:6px;}
  #tbl::-webkit-scrollbar-thumb{background:rgba(54,143,222,.4);border-radius:3px;}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  thead th{color:#7fe3ff;background:rgba(28,86,156,.35);padding:6px 8px;font-weight:600;text-align:center;letter-spacing:1px;}
  tbody td{padding:5px 8px;text-align:center;color:#bcd8f5;border-bottom:1px solid rgba(54,143,222,.12);}
  tbody tr:nth-child(even){background:rgba(20,52,98,.25);}
  .ok{color:#36e3a0;} .warn{color:#ffd24d;} .alarm{color:#ff5d6c;font-weight:700;}

  .scan{position:absolute;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,#2fd6ff,transparent);
    animation:scan 6s linear infinite;opacity:.5;}
  @keyframes scan{0%{top:0}100%{top:100%}}
</style>
</head>
<body>
<div id="screen">
  <div id="hd">
    <div class="tag">DATA CENTER · OPERATION MONITORING</div>
    <h1>数据中心运行监控大屏</h1>
    <div class="en">DATA SCREEN · 1</div>
    <div class="clock"><div class="t" id="clk">--:--:--</div><div class="d" id="dt">----</div></div>
  </div>

  <div id="kpi">
    <div class="panel kpi"><div class="v" id="k_hosts"></div><div class="l">监控主机</div><div class="bar"></div></div>
    <div class="panel kpi"><div class="v" id="k_days"></div><div class="l">覆盖天数</div><div class="bar"></div></div>
    <div class="panel kpi"><div class="v" id="k_samp"></div><div class="l">采集样本(万)</div><div class="bar"></div></div>
    <div class="panel kpi"><div class="v" id="k_cpu"></div><div class="l">平均CPU使用率</div><div class="bar"></div></div>
    <div class="panel kpi"><div class="v" id="k_mem"></div><div class="l">平均内存使用率</div><div class="bar"></div></div>
    <div class="panel kpi"><div class="v" id="k_alarm"></div><div class="l">高负载告警主机</div><div class="bar"></div></div>
  </div>

  <div id="main">
    <div class="panel" id="c_model"><div class="ptitle">主机型号构成</div><div class="chart" id="ch_model"></div><div class="scan"></div></div>
    <div class="panel" id="c_loc"><div class="ptitle">机房主机分布</div><div class="chart" id="ch_loc"></div></div>
    <div class="panel" id="c_trend"><div class="ptitle" id="pt_trend">核心资源日趋势 · CPU / 内存使用率(%)</div><div class="chart" id="ch_trend"></div><div class="scan"></div></div>
    <div class="panel" id="c_net"><div class="ptitle">网络流量日趋势 · 入站/出站(MB/s)</div><div class="chart" id="ch_net"></div></div>
    <div class="panel" id="c_cpuloc"><div class="ptitle">各机房平均CPU对比(%)</div><div class="chart" id="ch_cpuloc"></div></div>
    <div class="panel" id="c_disk"><div class="ptitle">磁盘使用率 TOP10 主机(%)</div><div class="chart" id="ch_disk"></div></div>
  </div>

  <div class="panel" id="band">
    <div class="ptitle">主机运行明细 · 实时聚合</div>
    <div id="tbl"><table><thead><tr>
      <th>主机</th><th>负责人</th><th>型号</th><th>机柜</th>
      <th>CPU均值%</th><th>内存%</th><th>磁盘%</th><th>峰值负载</th>
      <th>CPU峰值%</th><th>磁盘峰值%</th><th>状态</th>
    </tr></thead><tbody id="tbody"></tbody></table></div>
  </div>
</div>

<script>
const DATA = /*__DATA__*/;
const C = { cyan:'#2fd6ff', blue:'#2f7bff', teal:'#1fd6c2', purple:'#9b7bff',
  green:'#36e3a0', yellow:'#ffd24d', red:'#ff5d6c', orange:'#ff9f45' };
const axis = { axisLine:{lineStyle:{color:'rgba(90,150,210,.4)'}},
  axisLabel:{color:'#8fb4d8'}, splitLine:{lineStyle:{color:'rgba(60,120,180,.12)'}} };
const tip = { backgroundColor:'rgba(8,22,46,.92)', borderColor:'rgba(54,143,222,.5)',
  textStyle:{color:'#cfe6ff'} };

function mk(id){ const c=echarts.init(document.getElementById(id)); charts.push(c); return c; }
const charts=[];

// KPI
const m=DATA.meta;
k_hosts.innerHTML=m.n_hosts;
k_days.innerHTML=m.n_days;
k_samp.innerHTML=(m.total_samples/10000).toFixed(1);
k_cpu.innerHTML=m.avg_cpu+'<small>%</small>';
k_mem.innerHTML=m.avg_mem+'<small>%</small>';
k_alarm.innerHTML=m.alert_hosts;

// model pie
mk('ch_model').setOption({
  tooltip:{...tip,trigger:'item',formatter:'{b}: {c} 台 ({d}%)'},
  legend:{bottom:4,textStyle:{color:'#9fc4e8',fontSize:11},itemWidth:10,itemHeight:10},
  color:[C.cyan,C.blue,C.teal,C.purple,C.green,C.orange],
  series:[{type:'pie',radius:['42%','66%'],center:['50%','46%'],
    itemStyle:{borderColor:'#07152e',borderWidth:2},
    label:{color:'#bcd8f5',fontSize:11,formatter:'{b}\n{c}'},
    data:DATA.model.keys.map((k,i)=>({name:k,value:DATA.model.vals[i]}))}]
});

// loc bar
mk('ch_loc').setOption({
  tooltip:{...tip,trigger:'axis',axisPointer:{type:'shadow'}},
  grid:{left:50,right:24,top:18,bottom:24},
  xAxis:{type:'category',data:DATA.loc1.keys,...axis},
  yAxis:{type:'value',...axis},
  series:[{type:'bar',data:DATA.loc1.vals,barWidth:'46%',
    itemStyle:{borderRadius:[4,4,0,0],
      color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:C.cyan},{offset:1,color:C.blue}])},
    label:{show:true,position:'top',color:'#bcd8f5'}}]
});

// trend line
// trend title: 标注采样天数
document.getElementById('pt_trend').textContent =
  '核心资源日趋势 · CPU / 内存使用率(%)  采样 ' + DATA.meta.n_pref_days + ' 天';

mk('ch_trend').setOption({
  tooltip:{...tip,trigger:'axis'},
  legend:{top:0,right:10,textStyle:{color:'#9fc4e8',fontSize:11},itemWidth:14,itemHeight:8},
  grid:{left:46,right:18,top:34,bottom:54},
  xAxis:{type:'category',data:DATA.dates,boundaryGap:false,
    axisLabel:{color:'#8fb4d8',fontSize:10,interval:Math.floor(DATA.dates.length/12)},...axis},
  yAxis:{type:'value',max:100,...axis},
  series:[
    {name:'CPU使用率',type:'line',smooth:true,data:DATA.cpu_trend,symbol:'none',
      lineStyle:{width:2,color:C.cyan},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(47,214,255,.35)'},{offset:1,color:'rgba(47,214,255,0)'}])}},
    {name:'内存使用率',type:'line',smooth:true,data:DATA.mem_trend,symbol:'none',
      lineStyle:{width:2,color:C.purple},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(155,123,255,.30)'},{offset:1,color:'rgba(155,123,255,0)'}])}}
  ]
});

// net line
mk('ch_net').setOption({
  tooltip:{...tip,trigger:'axis'},
  legend:{top:0,right:10,textStyle:{color:'#9fc4e8',fontSize:11},itemWidth:14,itemHeight:8},
  grid:{left:50,right:18,top:34,bottom:54},
  xAxis:{type:'category',data:DATA.dates,boundaryGap:false,
    axisLabel:{color:'#8fb4d8',fontSize:10,interval:Math.floor(DATA.dates.length/12)},...axis},
  yAxis:{type:'value',...axis},
  series:[
    {name:'网络入站',type:'line',smooth:true,data:DATA.net_in_trend,symbol:'none',lineStyle:{width:2,color:C.teal}},
    {name:'网络出站',type:'line',smooth:true,data:DATA.net_out_trend,symbol:'none',lineStyle:{width:2,color:C.orange}}
  ]
});

// cpu by loc
mk('ch_cpuloc').setOption({
  tooltip:{...tip,trigger:'axis',axisPointer:{type:'shadow'}},
  grid:{left:40,right:18,top:18,bottom:24},
  xAxis:{type:'category',data:DATA.cpu_loc.keys,...axis},
  yAxis:{type:'value',max:100,...axis},
  series:[{type:'bar',data:DATA.cpu_loc.vals,barWidth:'46%',
    itemStyle:{borderRadius:[4,4,0,0],
      color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:C.purple},{offset:1,color:C.blue}])},
    label:{show:true,position:'top',color:'#bcd8f5',formatter:'{c}%'}}]
});

// disk top10
mk('ch_disk').setOption({
  tooltip:{...tip,trigger:'axis',axisPointer:{type:'shadow'}},
  grid:{left:120,right:36,top:8,bottom:18},
  xAxis:{type:'value',max:100,...axis},
  yAxis:{type:'category',data:DATA.disk_top.hosts,...axis,axisLabel:{color:'#8fb4d8',fontSize:10}},
  series:[{type:'bar',data:DATA.disk_top.vals,barWidth:'58%',
    itemStyle:{borderRadius:[0,4,4,0],
      color:new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:C.blue},{offset:1,color:C.red}])},
    label:{show:true,position:'right',color:'#bcd8f5',formatter:'{c}%'}}]
});

// table
const tb=document.getElementById('tbody');
DATA.table.forEach(r=>{
  const s = r.status==='告警'?'<span class="alarm">告警</span>'
    : r.status==='关注'?'<span class="warn">关注</span>':'<span class="ok">正常</span>';
  const tr=document.createElement('tr');
  tr.innerHTML=`<td>${r.host}</td><td>${r.owner}</td><td>${r.model}</td><td>${r.loc}</td>
    <td>${r.cpu}</td><td>${r.mem}</td><td>${r.disk}</td><td>${r.load}</td>
    <td>${r.cpumx}</td><td>${r.diskmx}</td><td>${s}</td>`;
  tb.appendChild(tr);
});

// clock
function tick(){
  const d=new Date();
  const p=n=>String(n).padStart(2,'0');
  clk.textContent=`${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  dt.textContent=`${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}  数据区间 ${m.date_start} ~ ${m.date_end}`;
}
tick(); setInterval(tick,1000);

// responsive scale
function fit(){
  const s=Math.min(window.innerWidth/1920, window.innerHeight/1080);
  document.getElementById('screen').style.transform=`translate(-50%,-50%) scale(${s})`;
}
window.addEventListener('resize',()=>{fit();charts.forEach(c=>c.resize());});
fit();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
