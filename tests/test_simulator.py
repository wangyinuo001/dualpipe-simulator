from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from dualpipe_a import Config, Simulation, simulate, validate_schedule
from dualpipe_a.output import write_event_csv, write_result_json


class SchedulingTests(unittest.TestCase):
    def test_complete_fair_work_and_dependencies_across_sizes(self):
        for pp, m in ((2, 2), (4, 8), (4, 16), (8, 16)):
            for allow in (False, True):
                with self.subTest(pp=pp, microbatches=m, allow_overlap=allow):
                    config = Config(pp=pp, microbatches=m, forward=1.3,
                                    backward_input=0.8, weight=1.2, comm=0.25,
                                    allow_compute_comm_overlap=allow)
                    runs = [simulate(config, method) for method in ("1f1b", "dualpipe")]
                    expected = m * (3 * pp + 2 * (pp - 1))
                    self.assertEqual([len(r.events) for r in runs], [expected, expected])
                    for run in runs:
                        validate_schedule(run)
                        self.assertAlmostEqual(run.metrics()["compute_work_per_stage"],
                                               m * (config.forward + config.backward_total))

    def test_validator_rejects_dependency_violation(self):
        run = simulate(Config(), "dualpipe")
        events = list(run.events)
        index = next(i for i, event in enumerate(events) if event.kind == "B" and event.deps)
        events[index] = replace(events[index], start=0.0,
                                finish=events[index].duration)
        with self.assertRaises(AssertionError):
            validate_schedule(Simulation(run.method, run.config, tuple(events)))

    def test_validator_rejects_gpu_resource_overlap(self):
        run = simulate(Config(), "dualpipe")
        events = list(run.events)
        index = next(i for i, event in enumerate(events)
                     if event.kind == "F" and event.microbatch == 1 and event.stage == 0)
        events[index] = replace(events[index], start=0.0,
                                finish=events[index].duration)
        with self.assertRaises(AssertionError):
            validate_schedule(Simulation(run.method, run.config, tuple(events)))

    def test_exports_are_derived_from_events(self):
        runs = (simulate(Config(), "1f1b"), simulate(Config(), "dualpipe"))
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as temp:
            folder = Path(temp)
            write_event_csv(runs[0], folder / "events.csv")
            write_result_json(runs, folder / "results.json")
            rows = (folder / "events.csv").read_text(encoding="utf-8-sig").splitlines()
            data = json.loads((folder / "results.json").read_text(encoding="utf-8"))
            self.assertEqual(len(rows) - 1, len(runs[0].events))
            self.assertEqual(data["runs"][0]["metrics"]["makespan"],
                             max(e.finish for e in runs[0].events))
            self.assertTrue(all(data["fairness"].values()))

    def test_invalid_parameters(self):
        for params in ({"microbatches": 3}, {"comm": 0}, {"pp": 1}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                Config(**params)

    def test_ideal_overlap_is_measured_from_real_event_intersections(self):
        for method in ("1f1b", "dualpipe"):
            with self.subTest(method=method):
                config = Config(allow_compute_comm_overlap=True)
                run = simulate(config, method)
                metrics = run.metrics()
                self.assertGreater(metrics["communication_overlap_fraction"], 0)
                self.assertLessEqual(metrics["communication_overlap_fraction"], 1)
                self.assertAlmostEqual(
                    metrics["compute_gpu_fraction"] + metrics["communication_gpu_fraction"]
                    - metrics["compute_comm_overlap_gpu_fraction"] + metrics["gpu_idle_fraction"], 1)
                no_overlap = simulate(Config(), method)
                self.assertEqual(no_overlap.metrics()["communication_overlap_fraction"], 0)
                self.assertLessEqual(metrics["makespan"], no_overlap.metrics()["makespan"])

    def test_compute_tasks_still_exclusive_when_communication_can_overlap(self):
        run = simulate(Config(allow_compute_comm_overlap=True), "dualpipe")
        events = list(run.events)
        index = next(i for i, event in enumerate(events)
                     if event.kind == "F" and event.microbatch == 1 and event.stage == 0)
        events[index] = replace(events[index], start=0.0,
                                finish=events[index].duration)
        with self.assertRaises(AssertionError):
            validate_schedule(Simulation(run.method, run.config, tuple(events)))


if __name__ == "__main__":
    unittest.main()
