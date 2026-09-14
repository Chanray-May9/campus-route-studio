import json
import math
import unittest

from route_studio.routes import Route, distance, export_route, import_route, validate_points


class RouteTests(unittest.TestCase):
    def test_infinite_route_closes_and_preserves_speed_across_laps(self):
        route = Route([{'lat': 0, 'lon': 0}, {'lat': 0, 'lon': 0.001}], speed=2, loops=0)
        self.assertTrue(route.infinite)
        self.assertEqual(route.points[0], route.points[-1])
        point, travelled = route.at(route.lap_distance * 3 / route.speed)
        self.assertEqual(point['speed'], 2)
        self.assertAlmostEqual(point['lon'], 0)
        self.assertAlmostEqual(travelled, route.lap_distance * 3)

    def test_position_depends_on_distance_not_vertex_count(self):
        sparse = Route([{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.001}], speed=2)
        dense = Route([{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.0001},
                       {"lat": 0, "lon": 0.001}], speed=2)
        seconds = sparse.duration / 4
        point, travelled = dense.at(seconds)
        self.assertAlmostEqual(point["lon"], 0.00025, places=10)
        self.assertAlmostEqual(travelled, seconds * 2, places=8)
        self.assertAlmostEqual(point["bearing"], 90)
        self.assertAlmostEqual(point["lon"], sparse.at(seconds)[0]["lon"], places=10)

    def test_antimeridian_uses_short_crossing(self):
        route = Route([{"lat": 0, "lon": 179.9}, {"lat": 0, "lon": -179.9}], speed=20)
        middle, travelled = route.at(route.duration / 2)
        self.assertLess(route.total_distance, 23_000)
        self.assertAlmostEqual(abs(middle["lon"]), 180, places=8)
        self.assertAlmostEqual(travelled, route.total_distance / 2)

    def test_endpoints_clamp_and_finish_has_zero_speed(self):
        route = Route([{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.001}])
        beginning, distance_before = route.at(-3)
        ending, distance_after = route.at(route.duration + 100)
        self.assertAlmostEqual(beginning["lon"], 0)
        self.assertEqual(distance_before, 0)
        self.assertAlmostEqual(ending["lon"], 0.001)
        self.assertEqual(distance_after, route.total_distance)
        self.assertEqual(ending["speed"], 0)

    def test_multiple_laps_close_before_repetition_without_teleport(self):
        points = [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.001}, {"lat": 0.001, "lon": 0.001}]
        route = Route(points, speed=2, loops=3)
        self.assertTrue(route.closed_automatically)
        self.assertEqual(route.points[-1], points[0])
        self.assertEqual(len(points), 3)  # Input is not extended in place.
        lap_seconds = route.lap_distance / route.speed
        before = route.at(lap_seconds - 0.1)[0]
        after = route.at(lap_seconds + 0.1)[0]
        self.assertLess(distance(before, after), 0.41)
        self.assertAlmostEqual(route.total_distance, route.lap_distance * 3)
        self.assertAlmostEqual(route.at(route.duration)[0]["lon"], 0)

    def test_adjacent_duplicates_removed_but_zero_length_route_rejected(self):
        points = [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1e-12}, {"lat": 0, "lon": 0.001}]
        self.assertEqual(len(validate_points(points)), 2)
        with self.assertRaises(ValueError):
            Route([points[0], points[0]])
        with self.assertRaises(ValueError):
            Route([points[0], {"lat": 0, "lon": 1e-6}])

    def test_invalid_numeric_input_is_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf"), True, None, "bad", 181):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Route([{"lat": 0, "lon": value}, {"lat": 0, "lon": 1}])
        for option in ({"speed": math.nan}, {"loops": 1.5}, {"loops": True}, {"interval": 0}):
            with self.subTest(option=option), self.assertRaises(ValueError):
                Route([{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.001}], **option)

    def test_gpx_and_geojson_roundtrip_preserve_coordinates(self):
        points = [{"lat": 31.12345678, "lon": 121.87654321}, {"lat": 31.12456789, "lon": 121.87765432}]
        for fmt in ("gpx", "geojson"):
            with self.subTest(format=fmt):
                exported = export_route({"points": points, "format": fmt})
                restored = import_route(exported["text"], fmt)["points"]
                for original, actual in zip(points, restored):
                    self.assertAlmostEqual(original["lat"], actual["lat"], places=8)
                    self.assertAlmostEqual(original["lon"], actual["lon"], places=8)
        geojson = json.loads(export_route({"points": points, "format": "geojson"})["text"])
        self.assertEqual(geojson["geometry"]["coordinates"][0], [points[0]["lon"], points[0]["lat"]])

    def test_multisegment_gpx_and_multiline_geojson_rejected(self):
        segment = '<trkseg><trkpt lat="0" lon="0"/><trkpt lat="0" lon="0.01"/></trkseg>'
        with self.assertRaisesRegex(ValueError, "多段"):
            import_route("<gpx><trk>" + segment * 2 + "</trk></gpx>", "gpx")
        with self.assertRaises(ValueError):
            import_route(json.dumps({"type": "MultiLineString", "coordinates": [[[0, 0], [1, 0]]]}), "geojson")
        with self.assertRaises(ValueError):
            import_route(json.dumps({"type": "FeatureCollection", "features": [{}, {}]}), "geojson")

    def test_gpx_entity_declarations_and_malformed_files_rejected(self):
        payload = '<!DOCTYPE gpx [<!ENTITY xxe SYSTEM "file:///never-read">]><gpx>&xxe;</gpx>'
        with self.assertRaisesRegex(ValueError, "DTD"):
            import_route(payload, "gpx")
        for text, fmt in (("<gpx>", "gpx"), ("{", "geojson"), ("null", "json"),
                          ('{"type":"LineString","coordinates":[[0,NaN],[1,0]]}', "geojson")):
            with self.subTest(format=fmt, text=text), self.assertRaises(ValueError):
                import_route(text, fmt)


if __name__ == "__main__":
    unittest.main()
