"""MuMu's location CLI uses Baidu BD-09 input; routes stay WGS84."""
import math


def wgs_to_gcj(lat, lon):
    pi = math.pi
    if 72.004 <= lon <= 137.8347 and .8293 <= lat <= 55.8271:
        x, y = lon - 105, lat - 35
        dy = -100 + 2*x + 3*y + .2*y*y + .1*x*y + .2*math.sqrt(abs(x))
        dy += (20*math.sin(6*x*pi) + 20*math.sin(2*x*pi))*2/3
        dy += (20*math.sin(y*pi) + 40*math.sin(y*pi/3))*2/3
        dy += (160*math.sin(y*pi/12) + 320*math.sin(y*pi/30))*2/3
        dx = 300 + x + 2*y + .1*x*x + .1*x*y + .1*math.sqrt(abs(x))
        dx += (20*math.sin(6*x*pi) + 20*math.sin(2*x*pi))*2/3
        dx += (20*math.sin(x*pi) + 40*math.sin(x*pi/3))*2/3
        dx += (150*math.sin(x*pi/12) + 300*math.sin(x*pi/30))*2/3
        rad = lat*pi/180
        magic = 1 - .006693421622965943*math.sin(rad)**2
        root = math.sqrt(magic)
        lat += dy*180/((6378245*(1-.006693421622965943))/(magic*root)*pi)
        lon += dx*180/(6378245/root*math.cos(rad)*pi)
    return lat, lon


def wgs_to_bd(lat, lon):
    lat, lon = wgs_to_gcj(lat, lon)
    pi = math.pi
    # GCJ-02 -> BD-09, matching MuMu's built-in Baidu map input.
    x_pi = pi*3000/180
    z = math.hypot(lon, lat) + .00002*math.sin(lat*x_pi)
    theta = math.atan2(lat, lon) + .000003*math.cos(lon*x_pi)
    return z*math.sin(theta)+.006, z*math.cos(theta)+.0065


def _mumu_to_wgs(lat, lon):
    """MuMu uses the common one-step inverse, leaving a measurable metre error."""
    x, y = lon-.0065, lat-.006
    x_pi = math.pi*3000/180
    z = math.hypot(x, y)-.00002*math.sin(y*x_pi)
    theta = math.atan2(y, x)-.000003*math.cos(x*x_pi)
    lat, lon = z*math.sin(theta), z*math.cos(theta)
    glat, glon = wgs_to_gcj(lat, lon)
    return 2*lat-glat, 2*lon-glon


def wgs_to_mumu(lat, lon):
    """Compensate the CLI's approximate inverse, verified against actual GPS fixes.

    The route and map are unchanged. Only the external command input is adjusted
    so MuMu's resulting WGS84 fix matches the requested point.
    """
    target_lat, target_lon = lat, lon
    lat, lon = wgs_to_bd(lat, lon)
    for _ in range(5):
        actual_lat, actual_lon = _mumu_to_wgs(lat, lon)
        lat += target_lat-actual_lat
        lon += target_lon-actual_lon
    return lat, lon
