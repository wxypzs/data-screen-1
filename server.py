# -*- coding: utf-8 -*-
"""数据中心运行监控大屏 · 后端服务 (直连 MySQL, 实时聚合)。

启动:  python server.py            # 默认 http://localhost:8000
可选:  PORT=9000 python server.py

页面(index.html) 通过 GET /api/dashboard 实时获取聚合数据, 前端每 30s 轮询刷新。
依赖:  pymysql   (pip install pymysql)
MySQL: 见 docker-compose.yml (data_screen, 端口 3307)
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import db_queries

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._serve_file("template.html", "text/html; charset=utf-8")
        elif path in ("/echarts.min.js", "/echarts-gl.min.js"):
            self._serve_file(path.lstrip("/"), "application/javascript; charset=utf-8")
        elif path == "/api/dashboard":
            try:
                data = db_queries.build_dashboard_data()
                self._send(200, data)
            except Exception as e:  # 数据库连接/查询失败 -> 明确报错
                self._send(500, {"error": str(e)})
        else:
            self._send(404, {"error": "not found"})

    def _serve_file(self, name, ctype):
        fp = os.path.join(ROOT, name)
        if not os.path.exists(fp):
            self._send(404, {"error": "%s not found" % name})
            return
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)

    def log_message(self, fmt, *args):
        pass  # 静默访问日志


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("大屏后端已启动: http://localhost:%d  (Ctrl+C 退出)" % PORT)
    print("MySQL 数据源: data_screen @ 127.0.0.1:3307")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
