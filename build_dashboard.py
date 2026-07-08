# -*- coding: utf-8 -*-
"""由 template.html 生成 index.html (三主题数据大屏的单文件产物)。

大屏通过 server.py 的 /api/dashboard 直连 MySQL 实时获取数据, 前端每 30s 刷新。
template.html 为唯一数据源; index.html 为其生成副本(便于直接打开/部署)。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    src = os.path.join(HERE, "template.html")
    dst = os.path.join(HERE, "index.html")
    with open(src, "r", encoding="utf-8") as f:
        html = f.read()
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    print("已生成 index.html (三主题可切换大屏, 由 template.html 生成)")
    print("启动: python server.py  ->  http://localhost:8000")


if __name__ == "__main__":
    main()
