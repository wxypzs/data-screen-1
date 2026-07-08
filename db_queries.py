# -*- coding: utf-8 -*-
"""从 MySQL(data_screen) 实时聚合大屏所需数据。

表结构见 mysql/init/01_schema.sql:
  host_detail / mod_detail / disk_tsar / pref_tsar  (+ 视图 v_*_metrics)
返回结构与前端期望的 JSON 完全一致, 由 server.py 通过 /api/dashboard 暴露。
"""
import pymysql

CONFIG = dict(
    host="127.0.0.1", port=3307,
    user="root", password="root123456",
    db="data_screen", charset="utf8mb4",
    init_command="SET time_zone='+08:00'",
    connect_timeout=5,
)

DISK_UTIL_MODS = ("sda_util", "sdb_util", "sdc_util", "sdd_util", "sde_util")
MEM_MODS = ("mem_used", "mem_free", "mem_buff", "mem_cache")


def _connect():
    return pymysql.connect(**CONFIG)


def _kv(rows):
    return {"keys": [r[0] for r in rows], "vals": [round(float(r[1]), 2) for r in rows]}


def _kv_int(rows):
    return {"keys": [r[0] for r in rows], "vals": [int(r[1]) for r in rows]}


def build_dashboard_data():
    conn = _connect()
    try:
        cur = conn.cursor()

        def q(sql, args=None):
            cur.execute(sql, args)
            return cur.fetchall()

        # 主机元数据
        host_meta = {}
        for r in q("SELECT hostid,hostname,owner,model,location1,location2 FROM host_detail"):
            host_meta[r[0]] = dict(hostid=r[0], hostname=r[1], owner=r[2],
                                  model=r[3], location1=r[4], location2=r[5])

        # 样本量与时间范围
        n_pref = q("SELECT COUNT(*) FROM pref_tsar")[0][0]
        n_disk = q("SELECT COUNT(*) FROM disk_tsar")[0][0]
        total_samples = int(n_pref + n_disk)
        dmin, dmax = q("""SELECT MIN(d), MAX(d) FROM (
            SELECT DATE(FROM_UNIXTIME(ts/1000)) d FROM pref_tsar
            UNION ALL SELECT DATE(FROM_UNIXTIME(ts/1000)) d FROM disk_tsar) t""")[0]

        # 平均 CPU / 内存使用率
        avg_cpu = round(float(q("SELECT AVG(value) FROM pref_tsar WHERE `mod`='cpu_usage'")[0][0] or 0), 1)
        avg_mem = round(float(q("""SELECT AVG(pct) FROM (
            SELECT SUM(CASE WHEN `mod`='mem_used' THEN value END)/SUM(value)*100 AS pct
            FROM pref_tsar WHERE `mod` IN %s
            GROUP BY hostid, DATE(FROM_UNIXTIME(ts/1000))) x""", (MEM_MODS,))[0][0] or 0), 1)

        # 有 pref 采样的日期(CPU/内存/网络趋势基准)
        pref_dates = [str(r[0]) for r in
                      q("SELECT DISTINCT DATE(FROM_UNIXTIME(ts/1000)) d FROM pref_tsar "
                        "WHERE `mod`='cpu_usage' ORDER BY d")]

        def trend(mod):
            rows = {str(r[0]): round(float(r[1]), 2) for r in
                    q("SELECT DATE(FROM_UNIXTIME(ts/1000)) d, AVG(value) FROM pref_tsar "
                      "WHERE `mod`=%s GROUP BY d", (mod,))}
            return [rows.get(d, 0.0) for d in pref_dates]

        cpu_trend = trend("cpu_usage")
        net_in_trend = trend("net_in")
        net_out_trend = trend("net_out")
        # 内存日趋势(按 主机-日 计算使用率后取日均值)
        mem_rows = {str(r[0]): round(float(r[1]), 2) for r in
                    q("""SELECT d, AVG(pct) FROM (
            SELECT DATE(FROM_UNIXTIME(ts/1000)) d,
                   SUM(CASE WHEN `mod`='mem_used' THEN value END)/SUM(value)*100 pct
            FROM pref_tsar WHERE `mod` IN %s
            GROUP BY hostid, DATE(FROM_UNIXTIME(ts/1000))) x GROUP BY d""", (MEM_MODS,))}
        mem_trend = [mem_rows.get(d, 0.0) for d in pref_dates]

        # 24 小时平均负载曲线
        ld = {int(r[0]): round(float(r[1]), 2) for r in
              q("SELECT HOUR(FROM_UNIXTIME(ts/1000)) h, AVG(value) FROM pref_tsar "
                "WHERE `mod`='load1' GROUP BY h")}
        load_curve = [ld.get(h, 0.0) for h in range(24)]

        # 维度分布
        model = _kv_int(q("SELECT model, COUNT(*) FROM host_detail GROUP BY model"))
        loc1 = _kv_int(q("SELECT location1, COUNT(*) FROM host_detail GROUP BY location1"))
        owner_cnt = {r[0]: int(r[1]) for r in q("SELECT owner, COUNT(*) FROM host_detail GROUP BY owner")}

        # 各机房平均 CPU
        cpu_loc = _kv(q("""SELECT h.location1, AVG(p.value) FROM pref_tsar p
            JOIN host_detail h ON p.hostid=h.hostid
            WHERE p.`mod`='cpu_usage' GROUP BY h.location1"""))

        # 负责人平均 CPU
        owner_cpu = {r[0]: round(float(r[1]), 1) for r in
                     q("""SELECT h.owner, AVG(p.value) FROM pref_tsar p
            JOIN host_detail h ON p.hostid=h.hostid
            WHERE p.`mod`='cpu_usage' GROUP BY h.owner""")}
        owner_list = sorted(owner_cnt.keys())
        owner_cpu_val = [owner_cpu.get(o, 0) for o in owner_list]

        # 磁盘使用率 TOP10 主机
        disk_rows = [(r[0], round(float(r[1]), 1)) for r in
                     q("""SELECT h.hostname, AVG(p.value) FROM disk_tsar p
            JOIN host_detail h ON p.hostid=h.hostid
            WHERE p.`mod` IN %s GROUP BY h.hostname ORDER BY AVG(p.value) DESC LIMIT 10""", (DISK_UTIL_MODS,))]
        disk_top = disk_rows[::-1]   # 横向条形, 底部最大

        # 主机明细表
        cpu_map = {r[0]: (round(float(r[1]), 1), round(float(r[2]), 1)) for r in
                   q("SELECT hostid, AVG(value), MAX(value) FROM pref_tsar "
                     "WHERE `mod`='cpu_usage' GROUP BY hostid")}
        disk_map = {r[0]: (round(float(r[1]), 1), round(float(r[2]), 1)) for r in
                    q("SELECT hostid, AVG(value), MAX(value) FROM disk_tsar "
                      "WHERE `mod` IN %s GROUP BY hostid", (DISK_UTIL_MODS,))}
        load_map = {r[0]: round(float(r[1]), 2) for r in
                    q("SELECT hostid, MAX(value) FROM pref_tsar WHERE `mod`='load1' GROUP BY hostid")}
        load_avg_map = {r[0]: round(float(r[1]), 2) for r in
                        q("SELECT hostid, AVG(value) FROM pref_tsar WHERE `mod`='load1' GROUP BY hostid")}
        mem_map = {r[0]: round(float(r[1]), 1) for r in
                   q("""SELECT hostid, SUM(used)/SUM(tot)*100 FROM (
            SELECT hostid, CASE WHEN `mod`='mem_used' THEN value END used, value tot
            FROM pref_tsar WHERE `mod` IN %s) x GROUP BY hostid""", (MEM_MODS,))}

        table = []
        alert_hosts = 0
        for h, m in host_meta.items():
            ca, cm = cpu_map.get(h, (0, 0))
            da, dm = disk_map.get(h, (0, 0))
            lm = load_map.get(h, 0)
            lm_avg = load_avg_map.get(h, 0)
            mm = mem_map.get(h, 0)
            status = "正常"
            if da >= 54 or ca >= 46 or lm_avg >= 17:
                status = "告警"; alert_hosts += 1
            elif da >= 50 or ca >= 44 or lm_avg >= 16.5:
                status = "关注"
            table.append({
                "host": m["hostname"], "owner": m["owner"], "model": m["model"],
                "loc": m["location1"] + "-" + m["location2"],
                "cpu": ca, "mem": mm, "disk": da, "load": lm,
                "cpumx": cm, "diskmx": dm, "status": status,
            })
        table.sort(key=lambda x: x["cpu"], reverse=True)

        data = {
            "meta": {
                "n_hosts": len(host_meta),
                "n_days": (dmax - dmin).days + 1 if dmin and dmax else 0,
                "n_pref_days": len(pref_dates),
                "date_start": str(dmin) if dmin else "",
                "date_end": str(dmax) if dmax else "",
                "total_samples": total_samples,
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
            "model": model,
            "loc1": loc1,
            "owner": {"keys": owner_list, "vals": owner_cnt, "cpu": owner_cpu_val},
            "cpu_loc": cpu_loc,
            "disk_top": {"hosts": [x[0] for x in disk_top], "vals": [x[1] for x in disk_top]},
            "table": table,
        }
        return data
    finally:
        conn.close()
