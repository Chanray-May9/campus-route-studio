"""Explicit synthetic route variations, with distance integrated continuously."""
import math
from .routes import EARTH_RADIUS, number


class Motion:
    def __init__(self, data=None, speed=2.5):
        data = data or {}
        self.mode = data.get('mode', 'fixed')
        if self.mode not in ('fixed', 'smooth', 'alternating'):
            raise ValueError('速度模式无效')
        self.speed = number(data.get('speed', speed), '速度', 0.2, 20)
        self.low = number(data.get('low', self.speed), '最低速度', 0.2, 20)
        self.high = number(data.get('high', self.speed), '最高速度', self.low, 20)
        self.period = number(data.get('period', 10), '速度周期（秒）', 2, 120)
        self.sway = number(data.get('sway', 0), '左右摆幅（米）', 0, 3)
        self.sway_period = number(data.get('swayPeriod', 4), '摆动周期（秒）', 2, 30)

    def speed_at(self, t):
        if self.mode == 'fixed':
            return self.speed
        if self.mode == 'alternating':
            return self.low if t % self.period < self.period / 2 else self.high
        return (self.low + self.high) / 2 - (self.high - self.low) / 2 * math.cos(2 * math.pi * t / self.period)

    def integral(self, t):
        if self.mode == 'fixed':
            return self.speed * t
        mean = (self.low + self.high) / 2
        if self.mode == 'smooth':
            return mean * t - (self.high - self.low) * self.period / (4 * math.pi) * math.sin(2 * math.pi * t / self.period)
        cycles = math.floor(t / self.period)
        rem = t - cycles * self.period
        return cycles * mean * self.period + min(rem, self.period / 2) * self.low + max(0, rem - self.period / 2) * self.high

    def offset(self, point, t, travelled, total):
        # Fade in/out near endpoints, so the route starts and finishes at its specified points.
        lateral = self.sway * math.sin(2 * math.pi * t / self.sway_period) * min(1, travelled / 5, (total - travelled) / 5)
        if not lateral:
            return point
        angle = math.radians(point['bearing'] + 90)
        lat = point['lat'] + math.degrees(lateral * math.cos(angle) / EARTH_RADIUS)
        lon = point['lon'] + math.degrees(lateral * math.sin(angle) / (EARTH_RADIUS * math.cos(math.radians(point['lat']))))
        return {**point, 'lat': lat, 'lon': (lon + 180) % 360 - 180}

    def as_dict(self):
        return dict(mode=self.mode, speed=self.speed, low=self.low, high=self.high, period=self.period, sway=self.sway, swayPeriod=self.sway_period)
