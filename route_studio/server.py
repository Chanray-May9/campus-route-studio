"""Loopback-only desktop UI server with per-launch authentication."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sys
import threading
import webbrowser
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .adapters import adb_path, connect_android, install_android_helper, list_android_devices
from .playback import Playback
from .routes import export_route, import_route
from .library import RouteLibrary


class Application:
    def __init__(self):
        self.playback = Playback()
        self.device_lock = threading.Lock()
        self.library = RouteLibrary()

    def devices(self):
        result = {"android": [], "ios": [], "dependencies": {"adb": False, "ios": False}, "errors": []}
        try:
            adb_path()
            result["dependencies"]["adb"] = True
        except RuntimeError as exc:
            result["errors"].append(str(exc))
        result["dependencies"]["ios"] = importlib.util.find_spec("pymobiledevice3") is not None
        if not result["dependencies"]["ios"]:
            result["errors"].append("iOS 扫描不可用：启动程序所用 Python 没有安装 pymobiledevice3。请使用 start.cmd 启动以安装依赖；安装 Apple 驱动不能替代此依赖。")
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = {}
            if result["dependencies"]["adb"]:
                jobs["android"] = pool.submit(list_android_devices)
            if result["dependencies"]["ios"]:
                from .ios_adapter import list_ios_devices
                jobs["ios"] = pool.submit(list_ios_devices)
            for key, future in jobs.items():
                try:
                    result[key] = future.result()
                except Exception as exc:
                    result["errors"].append(f"{key}: {exc}")
        return result

    def get(self, path):
        if path == '/api/library':
            return {'entries': self.library.list()}
        if path == "/api/status":
            return {"run": self.playback.status(), "info": {"name": "Campus Route Studio", "version": __version__}}
        if path == "/api/devices":
            # Serialise device discovery against setup and other discovery requests.
            if not self.device_lock.acquire(blocking=False):
                raise ValueError("正在检查或配置设备，请稍后重试")
            try:
                return self.devices()
            finally:
                self.device_lock.release()
        raise LookupError("接口不存在")

    def post(self, path, data):
        if not isinstance(data, dict):
            raise ValueError("请求内容应为 JSON 对象")
        if path == '/api/library/save':
            return self.library.save(data)
        if path == '/api/library/load':
            return self.library.load(data.get('id'))
        if path == '/api/library/delete':
            return self.library.delete(data.get('id'))
        if path == "/api/start":
            with self.device_lock:
                return {"run": self.playback.start(data)}
        if path == "/api/control":
            return {"run": self.playback.control(data.get("action"))}
        if path == '/api/tuning':
            return {'run': self.playback.tune(data)}
        if path == "/api/import":
            return import_route(data.get("text"), data.get("format"))
        if path == "/api/export":
            return export_route(data)
        if path in ("/api/connect", "/api/android/setup"):
            with self.device_lock:
                if self.playback.status()["state"] in Playback.ACTIVE:
                    raise ValueError("请先停止回放再配置设备")
                if path == "/api/connect":
                    return connect_android(data.get("address"))
                return install_android_helper(data.get("serial"))
        raise LookupError("接口不存在")


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address=("127.0.0.1", 0), application=None):
        if address[0] != "127.0.0.1":
            raise ValueError("本地服务器只能绑定 127.0.0.1")
        self.token = secrets.token_urlsafe(32)
        self.application = application or Application()
        self.web_root = Path(__file__).resolve().parent / "web"
        super().__init__(address, Handler)
        self.host_header = f"127.0.0.1:{self.server_port}"
        self.origin = "http://" + self.host_header

    def finish(self):
        self.application.playback.shutdown()
        self.shutdown()


class Handler(BaseHTTPRequestHandler):
    server_version = "CampusRouteStudio"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Do not put auth tokens, device identifiers or route coordinates in console logs.
        pass

    def _headers(self, status, mime, length):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://*.tile.openstreetmap.org https://tile.openstreetmap.org; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")

    def json_response(self, status, data):
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def authenticated(self):
        if self.headers.get("Host") != self.server.host_header:
            return False
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            item = cookies.get("campus_route_session")
            return item is not None and secrets.compare_digest(item.value, self.server.token)
        except Exception:
            return False

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == "/" and "token" in parse_qs(parts.query):
            value = parse_qs(parts.query)["token"][0]
            if self.headers.get("Host") == self.server.host_header and secrets.compare_digest(value, self.server.token):
                self.send_response(303)
                self.send_header("Set-Cookie", "campus_route_session=" + self.server.token + "; HttpOnly; SameSite=Strict; Path=/")
                self.send_header("Location", "/")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
        if not self.authenticated():
            self.json_response(403, {"error": "会话无效。请使用启动程序打开的页面。"})
            return
        try:
            if parts.path.startswith("/api/"):
                self.json_response(200, self.server.application.get(parts.path))
                return
            path = self.server.web_root / ("index.html" if parts.path == "/" else parts.path.lstrip("/"))
            path = path.resolve()
            if not path.is_relative_to(self.server.web_root.resolve()) or not path.is_file():
                raise LookupError("文件不存在")
            payload = path.read_bytes()
            mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            if path.suffix == ".js":
                mime = "text/javascript"
            self._headers(200, mime, len(payload))
            self.end_headers()
            self.wfile.write(payload)
        except LookupError as exc:
            self.json_response(404, {"error": str(exc)})
        except (ValueError, RuntimeError, RecursionError) as exc:
            self.json_response(400, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.json_response(500, {"error": str(exc)})

    def do_POST(self):
        if not self.authenticated() or self.headers.get("Origin") != self.server.origin:
            self.json_response(403, {"error": "拒绝外部页面或失效会话的设备操作"})
            return
        if self.headers.get_content_type() != "application/json":
            self.json_response(415, {"error": "需要 application/json"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4_500_000:
                raise ValueError("请求内容为空或超过 4.5 MB")
            data = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if path == "/api/quit":
                self.json_response(200, {"message": "正在停止回放并退出程序"})
                threading.Thread(target=self.server.finish, daemon=True).start()
            else:
                self.json_response(200, self.server.application.post(path, data))
        except LookupError as exc:
            self.json_response(404, {"error": str(exc)})
        except (ValueError, RuntimeError, RecursionError) as exc:
            self.json_response(400, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.json_response(500, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="Campus Route Studio — 本地路线工作台")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=18765, help="本地端口，默认 18765，保持浏览器保存位置；可指定其他端口")
    args = parser.parse_args()
    server = LocalServer(("127.0.0.1", args.port))
    url = server.origin + "/?token=" + server.token
    print("Campus Route Studio " + __version__, flush=True)
    print("本地界面：" + url, flush=True)
    print("停止回放后使用界面退出按钮或 Ctrl+C 退出。关闭浏览器标签页不会退出后台。", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.application.playback.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
