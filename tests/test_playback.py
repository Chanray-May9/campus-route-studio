import threading
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from route_studio import playback as module
from route_studio.routes import Route


POINTS = [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.001}]


class FakeAdapter:
    def __init__(self, open_error=None, send_error=None, close_error=None):
        self.open_error, self.send_error, self.close_error = open_error, send_error, close_error
        self.opens = self.closes = 0
        self.sent = []

    def open(self):
        self.opens += 1
        if self.open_error:
            raise self.open_error

    def send(self, point):
        self.sent.append(deepcopy(point))
        if self.send_error:
            raise self.send_error

    def close(self):
        self.closes += 1
        if self.close_error:
            raise self.close_error


class ScriptedCondition:
    """Advance the worker's clock at waits, with no real waiting or scheduling race."""
    def __init__(self, owner, steps):
        self.owner = owner
        self.steps = iter(steps)

    def __enter__(self):
        self.owner.lock.acquire()
        return self

    def __exit__(self, *args):
        self.owner.lock.release()

    def notify_all(self):
        pass

    def wait(self, timeout=None):
        next(self.steps)()


class PlaybackTests(unittest.TestCase):
    def test_infinite_replay_crosses_laps_without_completing_and_stops(self):
        import json
        worker, adapter = module.Playback(), FakeAdapter()
        clock = [0.0]
        worker.condition = ScriptedCondition(worker, [lambda: clock.__setitem__(0, 1000), lambda: clock.__setitem__(0, 2000), lambda: worker.control('stop')])
        route = Route(POINTS, speed=2, loops=0)
        with patch.object(module, 'time', SimpleNamespace(monotonic=lambda: clock[0], perf_counter=lambda: clock[0], time=lambda: clock[0])):
            worker._run(route, adapter)
        self.assertEqual(worker.status()['state'], 'idle')
        self.assertGreater(worker.status()['completedLaps'], 1)
        self.assertEqual(worker.status()['distance'], 4000)
        self.assertEqual(adapter.sent[-1]['speed'], 2)
        self.assertEqual(adapter.closes, 1)
        json.dumps(worker.status(), allow_nan=False)

    def test_live_speed_change_preserves_accumulated_distance(self):
        worker, adapter = module.Playback(), FakeAdapter()
        clock = [0.0]
        def change():
            clock[0] = 1
            worker.tune({'speed': 4})
        worker.data['state'] = 'running'
        worker.condition = ScriptedCondition(worker, [change, lambda: clock.__setitem__(0, 2), lambda: worker.control('stop')])
        with patch.object(module, 'time', SimpleNamespace(monotonic=lambda: clock[0], perf_counter=lambda: clock[0], time=lambda: clock[0])):
            worker._run(Route(POINTS, speed=2), adapter)
        self.assertAlmostEqual(worker.status()['distance'], 6)
        self.assertEqual([p['speed'] for p in adapter.sent], [2, 4, 4])
        self.assertGreater(adapter.sent[2]['lon'], adapter.sent[1]['lon'])

    def test_pause_freezes_time_but_sends_heartbeats_then_resumes(self):
        worker, adapter = module.Playback(), FakeAdapter()
        clock = [0.0]
        snapshots = []
        def step(seconds, action=None):
            def execute():
                snapshots.append(worker.status())
                clock[0] += seconds
                if action:
                    worker.control(action)
            return execute
        worker.condition = ScriptedCondition(worker, [
            step(0.5, "pause"), step(10), step(10, "resume"), step(1), step(0, "stop")])
        with patch.object(module, "time", SimpleNamespace(monotonic=lambda: clock[0], perf_counter=lambda: clock[0], time=lambda: clock[0])):
            worker._run(Route(POINTS, speed=2), adapter)
        self.assertEqual(len(adapter.sent), 5)
        self.assertEqual([p["speed"] for p in adapter.sent], [2, 0, 0, 2, 2])
        self.assertEqual([s["elapsed"] for s in snapshots], [0, 0.5, 0.5, 0.5, 1.5])
        self.assertEqual(adapter.sent[1]["lon"], adapter.sent[2]["lon"])
        self.assertEqual(adapter.sent[2]["lon"], adapter.sent[3]["lon"])
        self.assertGreater(adapter.sent[4]["lon"], adapter.sent[3]["lon"])
        self.assertEqual(adapter.closes, 1)
        self.assertEqual(worker.status()["state"], "idle")

    def test_natural_completion_sends_endpoint_and_cleans_once(self):
        worker, adapter = module.Playback(), FakeAdapter()
        clock = [0]
        worker.condition = ScriptedCondition(worker, [lambda: clock.__setitem__(0, 1)])
        with patch.object(module, "time", SimpleNamespace(monotonic=lambda: clock[0], perf_counter=lambda: clock[0], time=lambda: clock[0])):
            worker._run(Route([{"lat": 0, "lon": 0}, {"lat": 0, "lon": 0.00002}], speed=20), adapter)
        self.assertEqual(worker.status()["state"], "completed")
        self.assertEqual(adapter.sent[-1]["speed"], 0)
        self.assertAlmostEqual(adapter.sent[-1]["lon"], 0.00002)
        self.assertEqual(adapter.closes, 1)
        self.assertEqual(worker.status()["sentUpdates"], len(adapter.sent))

    def test_open_and_send_failures_cleanup_exactly_once(self):
        for errors in ({"open_error": RuntimeError("cannot open")}, {"send_error": RuntimeError("cannot send")}):
            with self.subTest(errors=errors):
                worker, adapter = module.Playback(), FakeAdapter(**errors)
                worker._run(Route(POINTS), adapter)
                state = worker.status()
                self.assertEqual(state["state"], "error")
                self.assertIn("cannot", state["error"])
                self.assertEqual(adapter.closes, 1)

    def test_cleanup_error_is_preserved_with_original_send_failure(self):
        worker = module.Playback()
        adapter = FakeAdapter(send_error=RuntimeError("lost device"), close_error=RuntimeError("GPS restoration failed"))
        worker._run(Route(POINTS), adapter)
        self.assertEqual(worker.status()["error"], "lost device")
        self.assertEqual(worker.status()["cleanupError"], "GPS restoration failed")
        self.assertEqual(adapter.closes, 1)

    def test_concurrent_start_denied_and_stop_during_open_cleans_once(self):
        entered, release = threading.Event(), threading.Event()
        class GatedAdapter(FakeAdapter):
            def open(self):
                super().open()
                entered.set()
                if not release.wait(timeout=2):
                    raise RuntimeError("test gate timed out")
        adapter = GatedAdapter()
        worker = module.Playback(factory=lambda config: adapter)
        self.addCleanup(worker.shutdown)
        self.addCleanup(release.set)
        config = {"route": {"points": POINTS}, "mode": "preview"}
        worker.start(config)
        self.assertTrue(entered.wait(timeout=1))
        with self.assertRaisesRegex(ValueError, "已有回放"):
            worker.start(config)
        worker.control("stop")
        release.set()
        worker.thread.join(timeout=1)
        self.assertFalse(worker.thread.is_alive())
        self.assertEqual(adapter.opens, 1)
        self.assertEqual(adapter.closes, 1)
        self.assertEqual(adapter.sent, [])
        worker.shutdown()
        self.assertEqual(adapter.closes, 1)
        with self.assertRaisesRegex(ValueError, "正在退出"):
            worker.start(config)

    def test_status_is_a_snapshot(self):
        worker = module.Playback()
        worker.data["point"] = {"lat": 1, "lon": 2}
        snapshot = worker.status()
        snapshot["point"]["lat"] = 99
        self.assertEqual(worker.status()["point"]["lat"], 1)


if __name__ == "__main__":
    unittest.main()
