"""Persistent named routes, independent of browser storage and local server port."""
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import uuid
from .routes import Route
from .motion import Motion


class RouteLibrary:
    def __init__(self, path=None):
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share')))
        self.path = Path(path) if path else base / 'CampusRouteStudio' / 'routes.sqlite3'

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        db.execute('CREATE TABLE IF NOT EXISTS routes (id TEXT PRIMARY KEY, name TEXT NOT NULL, updated TEXT NOT NULL, payload TEXT NOT NULL, distance REAL NOT NULL, points INTEGER NOT NULL)')
        return db

    def list(self):
        db = self.connect()
        try:
            return [dict(row) for row in db.execute('SELECT id,name,updated,distance,points FROM routes ORDER BY updated DESC')]
        finally:
            db.close()

    def save(self, data):
        name = data.get('name')
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            raise ValueError('轨迹名称需要 1–80 个字符')
        raw = data.get('route')
        route = Route.from_dict(raw)
        motion = Motion(data.get('motion'), route.speed)
        payload = json.dumps({'route': {'points': raw['points'], 'speed': route.speed, 'loops': route.loops, 'interval': route.interval}, 'motion': motion.as_dict()}, ensure_ascii=False, allow_nan=False)
        ident = data.get('id')
        db = self.connect()
        try:
            with db:
                if ident:
                    if not db.execute('SELECT 1 FROM routes WHERE id=?', (ident,)).fetchone():
                        raise ValueError('要更新的轨迹不存在')
                else:
                    if db.execute('SELECT COUNT(*) FROM routes').fetchone()[0] >= 100:
                        raise ValueError('最多保存 100 条轨迹，请先删除不需要的轨迹')
                    ident = str(uuid.uuid4())
                db.execute('INSERT INTO routes VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,updated=excluded.updated,payload=excluded.payload,distance=excluded.distance,points=excluded.points',
                           (ident, name.strip(), datetime.now(timezone.utc).isoformat(), payload, route.lap_distance, len(raw['points'])))
            return {'id': ident, 'name': name.strip()}
        finally:
            db.close()

    def load(self, ident):
        if not isinstance(ident, str):
            raise ValueError('请选择轨迹')
        db = self.connect()
        try:
            row = db.execute('SELECT id,name,payload FROM routes WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise ValueError('轨迹不存在')
            return {'id': row['id'], 'name': row['name'], **json.loads(row['payload'])}
        finally:
            db.close()

    def delete(self, ident):
        db = self.connect()
        try:
            with db:
                result = db.execute('DELETE FROM routes WHERE id=?', (ident,))
                if not result.rowcount:
                    raise ValueError('轨迹不存在')
            return {'deleted': True}
        finally:
            db.close()
