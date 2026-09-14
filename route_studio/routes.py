"""Validated WGS84 routes, distance based playback and portable file formats."""
from __future__ import annotations

import bisect
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass

EARTH_RADIUS = 6_371_008.8
MAX_POINTS = 20_000
MAX_FILE_BYTES = 4_000_000


def number(value, name, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是数字")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是数字") from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name} 必须在 {minimum} 到 {maximum} 之间")
    return result


def validate_points(values):
    if not isinstance(values, list) or not 2 <= len(values) <= MAX_POINTS:
        raise ValueError(f"路线需要 2–{MAX_POINTS} 个坐标点")
    points = []
    for item in values:
        if not isinstance(item, dict):
            raise ValueError("坐标点必须包含 lat 和 lon")
        point = {
            "lat": number(item.get("lat"), "纬度", -85, 85),
            "lon": number(item.get("lon"), "经度", -180, 180),
        }
        if not points or distance(points[-1], point) > 0.01:
            points.append(point)
    if len(points) < 2:
        raise ValueError("路线至少需要两个不同的坐标点")
    return points


def distance(a, b):
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = p2 - p1
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return EARTH_RADIUS * 2 * math.asin(math.sqrt(min(1, max(0, h))))


def bearing(a, b):
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    return math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
        math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360


def interpolate(a, b, fraction):
    """Great-circle interpolation, including short antimeridian crossings."""
    arc = distance(a, b) / EARTH_RADIUS
    if arc < 1e-10:
        return dict(a)
    # Antipodal points do not determine a unique route.
    if math.pi - arc < 1e-6:
        raise ValueError("相邻坐标不能位于地球两端；请添加中间点")
    u, v = math.sin((1 - fraction) * arc) / math.sin(arc), math.sin(fraction * arc) / math.sin(arc)
    p1, p2, l1, l2 = map(math.radians, (a["lat"], b["lat"], a["lon"], b["lon"]))
    x = u * math.cos(p1) * math.cos(l1) + v * math.cos(p2) * math.cos(l2)
    y = u * math.cos(p1) * math.sin(l1) + v * math.cos(p2) * math.sin(l2)
    z = u * math.sin(p1) + v * math.sin(p2)
    return {"lat": math.degrees(math.atan2(z, math.hypot(x, y))), "lon": math.degrees(math.atan2(y, x))}


@dataclass
class Route:
    points: list
    speed: float = 2.5
    loops: int = 1
    interval: float = 1.0

    def __post_init__(self):
        self.points = validate_points(self.points)
        self.speed = number(self.speed, "速度 m/s", 0.2, 20)
        loops = number(self.loops, "重复次数（0 为无限）", 0, 10000)
        if loops != int(loops):
            raise ValueError("重复次数必须是整数")
        self.loops = int(loops)
        self.interval = number(self.interval, "更新间隔（秒）", 0.2, 3)
        self.infinite = self.loops == 0
        self.closed_automatically = (self.infinite or self.loops > 1) and distance(self.points[-1], self.points[0]) > 0.01
        if self.closed_automatically:
            self.points.append(dict(self.points[0]))
        self.cumulative = [0.0]
        for a, b in zip(self.points, self.points[1:]):
            segment = distance(a, b)
            if segment > 1_000_000:
                raise ValueError("相邻路径点距离超过 1000 公里，请检查坐标和坐标系")
            self.cumulative.append(self.cumulative[-1] + segment)
        self.lap_distance = self.cumulative[-1]
        if self.lap_distance < 1:
            raise ValueError("路线总长度至少为 1 米")
        self.total_distance = math.inf if self.infinite else self.lap_distance * self.loops
        self.duration = self.total_distance / self.speed
        if not self.infinite and self.duration > 24 * 3600:
            raise ValueError("单次回放时长不能超过 24 小时")

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("缺少路线设置")
        return cls(data.get("points"), data.get("speed", 2.5), data.get("loops", 1), data.get("interval", 1))

    def at(self, seconds):
        travelled = min(self.total_distance, max(0.0, seconds) * self.speed)
        finished = travelled >= self.total_distance
        local = self.lap_distance if finished else travelled % self.lap_distance
        index = min(len(self.points) - 2, bisect.bisect_right(self.cumulative, local) - 1)
        fraction = (local - self.cumulative[index]) / (self.cumulative[index + 1] - self.cumulative[index])
        point = interpolate(self.points[index], self.points[index + 1], fraction)
        point.update(speed=0.0 if finished else self.speed, bearing=bearing(self.points[index], self.points[index + 1]))
        return point, travelled


def import_route(text, fmt):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("路线文件不能超过 4 MB")
    if fmt == "gpx":
        # Forbid entity declarations even though ElementTree does not resolve external entities.
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("GPX 不能包含 DTD 或实体声明")
        try:
            root = ET.fromstring(text)
            if root.tag.split("}")[-1] != "gpx":
                raise ValueError("文件不是 GPX")
            segments = [node for node in root.iter() if node.tag.split("}")[-1] in ("trkseg", "rte")]
            if len(segments) > 1:
                raise ValueError("一次只能导入一条连续轨迹；请先拆分多段 GPX")
            values = [{"lat": n.get("lat"), "lon": n.get("lon")} for n in root.iter()
                      if n.tag.split("}")[-1] in ("trkpt", "rtept")]
        except ET.ParseError:
            raise ValueError("无法解析 GPX XML") from None
    elif fmt in ("geojson", "json"):
        try:
            obj = json.loads(text)
        except (ValueError, RecursionError):
            raise ValueError("无法解析 JSON") from None
        if isinstance(obj, dict) and obj.get("type") == "FeatureCollection":
            features = obj.get("features", [])
            if not isinstance(features, list) or len(features) != 1:
                raise ValueError("GeoJSON 必须仅包含一条 LineString")
            obj = features[0]
        if isinstance(obj, dict) and obj.get("type") == "Feature":
            obj = obj.get("geometry")
        if isinstance(obj, dict) and obj.get("type") == "LineString":
            coords = obj.get("coordinates")
            if not isinstance(coords, list) or not all(isinstance(p, list) and len(p) >= 2 for p in coords):
                raise ValueError("GeoJSON 坐标格式错误")
            values = [{"lat": p[1], "lon": p[0]} for p in coords]
        elif fmt == "json":
            values = obj.get("points") if isinstance(obj, dict) else obj
        else:
            raise ValueError("只支持 GeoJSON LineString")
    else:
        raise ValueError("仅支持 GPX、GeoJSON 和路线 JSON")
    return {"points": validate_points(values)}


def export_route(data):
    points = validate_points(data.get("points"))
    fmt = data.get("format", "gpx")
    if fmt == "geojson":
        obj = {"type": "Feature", "properties": {"name": "Campus Route Studio", "coordinateSystem": "WGS84"},
               "geometry": {"type": "LineString", "coordinates": [[p["lon"], p["lat"]] for p in points]}}
        content, mime = json.dumps(obj, ensure_ascii=False, indent=2), "application/geo+json"
    elif fmt == "gpx":
        root = ET.Element("gpx", {"version": "1.1", "creator": "Campus Route Studio", "xmlns": "http://www.topografix.com/GPX/1/1"})
        track = ET.SubElement(root, "trk")
        ET.SubElement(track, "name").text = "Campus Route Studio"
        segment = ET.SubElement(track, "trkseg")
        for p in points:
            ET.SubElement(segment, "trkpt", {"lat": f'{p["lat"]:.8f}', "lon": f'{p["lon"]:.8f}'})
        ET.indent(root)
        content, mime = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode"), "application/gpx+xml"
    else:
        raise ValueError("仅支持导出 GPX 或 GeoJSON")
    return {"filename": "campus-route." + fmt, "text": content, "mime": mime}
