import unittest

from watchdog import Target, decide_action, select_group_recovery_target


class WatchdogDecisionTests(unittest.TestCase):
    def setUp(self):
        self.target = Target("example", max_age_minutes=60, max_runtime_minutes=30, parameters={}, group=None)
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

    def test_group_with_one_running_job_does_not_start_another(self):
        targets = [
            Target("one", 20, 30, {}, "chain"),
            Target("two", 20, 30, {}, "chain"),
        ]
        data = {
            "one": {"lastBuild": {"building": True, "timestamp": self.now - 5 * 60_000}},
            "two": {"lastCompletedBuild": {"timestamp": self.now - 90 * 60_000}},
        }
        self.assertIsNone(select_group_recovery_target(targets, data, set(), "https://jenkins.example", self.now))

    def test_group_with_one_queued_job_does_not_start_another(self):
        targets = [
            Target("one", 20, 30, {}, "chain"),
            Target("two", 20, 30, {}, "chain"),
        ]
        data = {
            "one": {"lastCompletedBuild": {"timestamp": self.now - 90 * 60_000}},
            "two": {"lastCompletedBuild": {"timestamp": self.now - 90 * 60_000}},
        }
        queued = {"one"}
        self.assertIsNone(select_group_recovery_target(targets, data, queued, "https://jenkins.example", self.now))

    def test_group_with_job_in_queue_flag_does_not_start_another(self):
        targets = [
            Target("one", 20, 30, {}, "chain"),
            Target("two", 20, 30, {}, "chain"),
        ]
        data = {
            "one": {"inQueue": True, "lastCompletedBuild": {"timestamp": self.now - 90 * 60_000}},
            "two": {"lastCompletedBuild": {"timestamp": self.now - 90 * 60_000}},
        }
        self.assertIsNone(select_group_recovery_target(targets, data, set(), "https://jenkins.example", self.now))

    def test_group_recovers_only_first_job(self):
        targets = [
            Target("one", 20, 30, {}, "chain"),
            Target("two", 20, 30, {}, "chain"),
        ]
        data = {
            "one": {"lastCompletedBuild": {"timestamp": self.now - 90 * 60_000}},
            "two": {"lastCompletedBuild": {"timestamp": self.now - 100 * 60_000}},
        }
        self.assertEqual(select_group_recovery_target(targets, data, set(), "https://jenkins.example", self.now).job, "one")


if __name__ == "__main__":
    unittest.main()
