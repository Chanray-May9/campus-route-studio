"""Frozen Windows launcher; contains the runtime and device dependencies."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback
import webbrowser
import urllib.request
from urllib.parse import urlsplit, parse_qs


def main():
    from route_studio.server import LocalServer
    import msvcrt

    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--quit', action='store_true', help='Gracefully close the existing instance for upgrades')
    parser.add_argument('--port', type=int, default=18765)
    args = parser.parse_args()
    state_dir = Path(os.environ['LOCALAPPDATA']) / 'CampusRouteStudio'
    state_dir.mkdir(parents=True, exist_ok=True)
    lock = (state_dir / 'desktop.lock').open('a+b')
    # Inspect size without reading another process's locked byte (Windows rejects
    # such reads before the intended duplicate-instance exception handler).
    if (state_dir / 'desktop.lock').stat().st_size == 0:
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    session = state_dir / 'desktop-session.json'
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        # A second shortcut click returns to this user's existing local session.
        for _ in range(25):
            try:
                url = json.loads(session.read_text('utf-8'))['url']
                if args.quit:
                    parts = urlsplit(url)
                    if parts.scheme != 'http' or parts.hostname != '127.0.0.1' or not parts.port:
                        raise RuntimeError('本机程序会话地址无效')
                    origin = f'http://127.0.0.1:{parts.port}'
                    token = parse_qs(parts.query)['token'][0]
                    request = urllib.request.Request(origin + '/api/quit', data=b'{}', headers={
                        'Cookie': 'campus_route_session=' + token, 'Origin': origin, 'Content-Type': 'application/json'})
                    urllib.request.urlopen(request, timeout=10).close()
                    for _ in range(100):
                        if not session.exists():
                            return
                        time.sleep(.2)
                    raise RuntimeError('程序尚未退出，请先在界面结束跑步并退出')
                if not args.no_browser:
                    webbrowser.open(url)
                return
            except (OSError, ValueError, KeyError):
                time.sleep(.2)
        raise RuntimeError('程序正在启动，请稍后再次打开快捷方式。')
    server = None
    try:
        if args.quit:
            return
        server = LocalServer(('127.0.0.1', args.port))
        url = server.origin + '/?token=' + server.token
        session.write_text(json.dumps({'url': url}), 'utf-8')
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever(poll_interval=.2)
    finally:
        if server:
            server.application.playback.shutdown()
            server.server_close()
        session.unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        log = Path(os.environ.get('LOCALAPPDATA', '.')) / 'CampusRouteStudio' / 'startup-error.log'
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(traceback.format_exc(), 'utf-8')
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, f'启动失败：{error}\n\n详情保存在：{log}', '校园乐跑助手', 0x10)
        sys.exit(1)
