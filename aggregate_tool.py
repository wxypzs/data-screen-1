#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间戳转换与按小时汇总工具 (纯 Python, 无第三方依赖).

四个关联表:
  disk_tsar.dat / pref_tsar.dat : 分钟级指标 (ts, hostid, type, mod, value, tag)
  host_detail.dat               : 主机元数据 (hostid, hostname, owner, model, location1, location2)
  mod_detail.dat                : 指标元数据 (mod, type, desc, unit, tag)

ts 为 epoch 毫秒。本工具:
  1) convert  : 时间戳 -> 可读时间 (自动识别秒/毫秒, 输出 UTC 与本地 UTC+8)
  2) aggregate: 分钟级指标按 (小时, hostid, mod) 汇总为每小时总指标
                 (平均/最大/最小/采样分钟数), 并关联主机与指标元数据
"""

import argparse
import csv
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta

LOCAL_TZ = timezone(timedelta(hours=8))   # 原始数据按北京时间
HOUR_MS = 3600 * 1000


def read_tsv(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            yield row


def load_lookup(path, key):
    lut = {}
    for row in read_tsv(path):
        k = row.get(key)
        if k is not None:
            lut[k] = row
    return lut


def to_ms(ts_raw):
    v = float(ts_raw)
    if v < 1e12:          # 秒级 -> 毫秒
        v *= 1000.0
    return int(v)


def ms_to_datetimes(ms):
    dt_utc = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    return dt_utc, dt_utc.astimezone(LOCAL_TZ)


def hour_bucket(ms):
    return (ms // HOUR_MS) * HOUR_MS


def cmd_convert(args):
    for ts_raw in args.ts:
        ms = to_ms(ts_raw)
        dt_utc, dt_local = ms_to_datetimes(ms)
        print(f"{ts_raw}")
        print(f"  epoch_ms   : {ms}")
        print(f"  UTC        : {dt_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print(f"  本地(+08:00): {dt_local.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  小时桶起始 : {ms_to_datetimes(hour_bucket(ms))[1].strftime('%Y-%m-%d %H:00')}")


def cmd_time_table(args):
    """从指标文件中抽取所有去重时间戳, 输出可读时间对照表."""
    base = args.dir
    metric_files = [os.path.join(base, n) for n in ("disk_tsar.dat", "pref_tsar.dat")]
    metric_files = [p for p in metric_files if os.path.exists(p)]

    seen = set()
    for path in metric_files:
        for row in read_tsv(path):
            try:
                ms = to_ms(row["ts"])
            except (ValueError, KeyError, TypeError):
                continue
            seen.add(ms)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "timestamps.csv")
    fields = ["ts_raw", "epoch_ms", "dt_utc", "dt_local", "hour_start", "hour_ts", "date", "hour"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for ms in sorted(seen):
            _, dt_local = ms_to_datetimes(ms)
            hb = hour_bucket(ms)
            w.writerow({
                "ts_raw": ms,
                "epoch_ms": ms,
                "dt_utc": ms_to_datetimes(ms)[0].strftime("%Y-%m-%d %H:%M:%S"),
                "dt_local": dt_local.strftime("%Y-%m-%d %H:%M:%S"),
                "hour_start": ms_to_datetimes(hb)[1].strftime("%Y-%m-%d %H:00"),
                "hour_ts": hb,
                "date": dt_local.strftime("%Y-%m-%d"),
                "hour": dt_local.strftime("%H"),
            })
    print("去重时间戳数 : %d" % len(seen))
    print("输出文件     : %s" % out_path)


def cmd_aggregate(args):
    base = args.dir
    disk_path = os.path.join(base, "disk_tsar.dat")
    pref_path = os.path.join(base, "pref_tsar.dat")
    host_path = os.path.join(base, "host_detail.dat")
    mod_path = os.path.join(base, "mod_detail.dat")

    hosts = load_lookup(host_path, "hostid")
    mods = load_lookup(mod_path, "mod")

    # key=(hour_ms, hostid, mod) -> [sum, count, min, max]
    agg = defaultdict(lambda: [0.0, 0, float("inf"), float("-inf")])

    metric_files = [p for p in (disk_path, pref_path) if os.path.exists(p)]
    total_rows = bad_rows = 0

    for path in metric_files:
        for row in read_tsv(path):
            try:
                ms = to_ms(row["ts"])
                val = float(row["value"])
            except (ValueError, KeyError, TypeError):
                bad_rows += 1
                continue
            hb = hour_bucket(ms)
            key = (hb, row["hostid"], row["mod"])
            s = agg[key]
            s[0] += val
            s[1] += 1
            if val < s[2]:
                s[2] = val
            if val > s[3]:
                s[3] = val
            total_rows += 1

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "hourly_metrics.csv")
    fields = [
        "hour_start", "hour_ts", "date", "hour",
        "hostid", "hostname", "owner", "model", "location1", "location2",
        "mod", "metric_desc", "unit", "tag",
        "avg_value", "max_value", "min_value", "sample_minutes",
    ]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for (hb, hostid, mod), (s, cnt, mn, mx) in sorted(agg.items()):
            _, dt_local = ms_to_datetimes(hb)
            h = hosts.get(hostid, {})
            m = mods.get(mod, {})
            w.writerow({
                "hour_start": dt_local.strftime("%Y-%m-%d %H:%M:%S"),
                "hour_ts": hb,
                "date": dt_local.strftime("%Y-%m-%d"),
                "hour": dt_local.strftime("%H"),
                "hostid": hostid,
                "hostname": h.get("hostname", ""),
                "owner": h.get("owner", ""),
                "model": h.get("model", ""),
                "location1": h.get("location1", ""),
                "location2": h.get("location2", ""),
                "mod": mod,
                "metric_desc": m.get("desc", ""),
                "unit": m.get("unit", ""),
                "tag": m.get("tag", ""),
                "avg_value": round(s / cnt, 4),
                "max_value": round(mx, 4),
                "min_value": round(mn, 4),
                "sample_minutes": cnt,
            })

    print(f"读取指标行数        : {total_rows}")
    print(f"跳过异常行          : {bad_rows}")
    print(f"小时-主机-指标 分组 : {len(agg)}")
    print(f"输出文件            : {out_path}")


def build_parser():
    p = argparse.ArgumentParser(description="时间戳转换与按小时汇总工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("convert", help="时间戳 -> 可读时间")
    c.add_argument("ts", nargs="+", help="epoch 时间戳 (毫秒或秒均可)")
    c.set_defaults(func=cmd_convert)

    a = sub.add_parser("aggregate", help="分钟级指标 -> 按小时总指标")
    a.add_argument("--dir", default=".", help="四个 .dat 文件所在目录 (默认当前目录)")
    a.add_argument("--out", default="output", help="输出目录 (默认 ./output)")
    a.set_defaults(func=cmd_aggregate)

    t = sub.add_parser("time-table", help="从指标文件生成时间戳转换对照表")
    t.add_argument("--dir", default=".", help="四个 .dat 文件所在目录 (默认当前目录)")
    t.add_argument("--out", default="output", help="输出目录 (默认 ./output)")
    t.set_defaults(func=cmd_time_table)
    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
