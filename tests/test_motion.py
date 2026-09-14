import unittest
from route_studio.motion import Motion
from route_studio.routes import distance


class MotionTests(unittest.TestCase):
    def test_alternating_speed_integrates_across_switches(self):
        m = Motion({'mode': 'alternating', 'low': 2, 'high': 4, 'period': 10})
        self.assertEqual([m.speed_at(t) for t in (0, 4.99, 5, 9.99, 10)], [2, 2, 4, 4, 2])
        self.assertEqual(m.integral(10), 30)
        self.assertEqual(m.integral(11), 32)
        self.assertEqual(m.integral(6) - m.integral(4), 6)

    def test_smooth_average_and_extrema(self):
        m = Motion({'mode': 'smooth', 'low': 2, 'high': 4, 'period': 10})
        self.assertAlmostEqual(m.speed_at(0), 2)
        self.assertAlmostEqual(m.speed_at(5), 4)
        self.assertAlmostEqual(m.integral(20), 60)

    def test_sway_is_bounded_and_fades_at_endpoints(self):
        m = Motion({'sway': 2, 'swayPeriod': 4})
        point = {'lat': 30, 'lon': 120, 'bearing': 0, 'speed': 2}
        shifted = m.offset(point, 1, 10, 100)
        self.assertAlmostEqual(distance(point, shifted), 2, places=3)
        self.assertEqual(m.offset(point, 1, 0, 100), point)
        self.assertEqual(m.offset(point, 1, 100, 100), point)

    def test_invalid_parameters_rejected(self):
        for params in ({'low': 4, 'high': 2}, {'sway': 4}, {'speed': 0}, {'period': 0}, {'mode': 'unknown'}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                Motion(params)
