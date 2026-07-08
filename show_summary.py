import csv
from collections import Counter

rows = list(csv.DictReader(open('output/hourly_metrics.csv', encoding='utf-8-sig')))
print('总分组数 :', len(rows))
dates = sorted({r['date'] for r in rows})
print('覆盖日期 :', dates[0], '~', dates[-1], '(%d 天)' % len(dates))
print('主机数   :', len({r['hostid'] for r in rows}))
print('指标数   :', len({r['mod'] for r in rows}))
print('sample_minutes 分布:', dict(sorted(Counter(int(r['sample_minutes']) for r in rows).items())))
print()
print('=== 样例: 2026-07-01 00:00 host001 的若干指标 ===')
for r in rows:
    if (r['date'] == '2026-07-01' and r['hour'] == '00' and r['hostid'] == 'host001'
            and r['mod'] in ('cpu_usage', 'mem_used', 'net_in', 'load1')):
        line = '  %-10s avg=%-10s max=%-10s min=%-10s %s  样本%d分钟' % (
            r['mod'], r['avg_value'], r['max_value'], r['min_value'], r['unit'], int(r['sample_minutes']))
        print(line)
