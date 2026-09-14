"""Launch with a stable interpreter instead of an unrelated PATH Python."""
import importlib.util
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
if importlib.util.find_spec('pymobiledevice3') is None:
    print('首次启动：正在安装 iPhone 连接依赖，请保持联网。', flush=True)
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(root / 'requirements-ios.txt')])
    if result.returncode:
        print('iPhone 依赖安装失败。请检查网络后重试；也可使用 python -m route_studio 启动仅预览模式。')
        sys.exit(result.returncode)
subprocess.run([sys.executable, '-m', 'route_studio'], cwd=root)
