from dataclasses import asdict
import unittest

from debug_trace import trace_simulation
from dualpipe_a.simulator import Config, simulate


class ExecutionTraceTests(unittest.TestCase):
    def test_observation_preserves_results_and_records_real_mutations(self):
        for overlap in (False, True):
            for method in ('1f1b', 'dualpipe'):
                config = Config(pp=2, microbatches=4, comm=.3,
                                allow_compute_comm_overlap=overlap)
                observed = trace_simulation(config, method)
                direct = simulate(config, method)
                self.assertEqual(observed['events'], [asdict(e) for e in direct.events])
                completed, started = set(), set()
                events = {e.id: e for e in direct.events}
                previous_time = 0
                for step in observed['steps']:
                    key = step['task']
                    self.assertGreaterEqual(step['time'], previous_time)
                    previous_time = step['time']
                    if step['phase'] == 'choose':
                        self.assertNotIn(key, started)
                        self.assertTrue(set(events[key].deps) <= completed)
                        self.assertFalse(set(events[key].resources) & set(step['occupied']))
                    if step['phase'] == 'start':
                        self.assertNotIn(key, started)
                        self.assertEqual(step['time'], events[key].start)
                        started.add(key)
                    if step['phase'] == 'complete':
                        self.assertNotIn(key, completed)
                        self.assertAlmostEqual(step['time'], events[key].finish)
                        completed.add(key)
                    self.assertEqual(set(step['running']), started - completed)
                    resources = [res for task in step['running'] for res in events[task].resources]
                    self.assertEqual(len(resources), len(set(resources)))
                    self.assertEqual(set(step['occupied']), set(resources))
                    self.assertEqual(step['started_count'], len(started))
                    self.assertEqual(step['completed_count'], len(completed))
                self.assertEqual(completed, set(events))


if __name__ == '__main__':
    unittest.main()
