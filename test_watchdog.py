import unittest

from watchdog import Target, decide_action


class WatchdogDecisionTests(unittest.TestCase):
    def setUp(self):
        self.target = Target("example", max_age_minutes=60, max_runtime_minutes=30, parameters={})
        self.now = 3_600_000

    def test_running_build_is_not_restarted(self):
        data = {"lastBuild": {"building": True, "timestamp": self.now - 10 * 60_000}}
        self.assertEqual(decide_action(data, self.now, self.target), "running")

    def test_overdue_completed_build_is_triggered(self):
        data = {"lastBuild": {"building": False}, "lastCompletedBuild": {"timestamp": self.now - 61 * 60_000}}
        self.assertEqual(decide_action(data, self.now, self.target), "trigger")

    def test_recent_completed_build_is_healthy(self):
        data = {"lastCompletedBuild": {"timestamp": self.now - 10 * 60_000}}
        self.assertEqual(decide_action(data, self.now, self.target), "healthy")

    def test_long_running_build_is_reported(self):
        data = {"lastBuild": {"building": True, "timestamp": self.now - 31 * 60_000}}
        self.assertEqual(decide_action(data, self.now, self.target), "running-too-long")


if __name__ == "__main__":
    unittest.main()
