"""Observe the actual simulator with Python line tracing; do not replace its policy."""
from dataclasses import asdict
import hashlib
import inspect
import sys

from dualpipe_a.simulator import Config, simulate, build_tasks, result_dict


def trace_simulation(config, method):
    source, first = inspect.getsourcelines(simulate)
    lines = {first + i: line.rstrip('\n') for i, line in enumerate(source)}

    def locate(fragment):
        return next(n for n, text in lines.items() if fragment in text)

    anchors = {
        'initialize': [locate('tasks = build_tasks'), locate('time = 0.0')],
        'choose': [locate('not all(dep in completed'), locate('any(resource in occupied'),
                   locate('if method == "1f1b" and task.kind'), locate('priority ='),
                   locate('task = tasks[min(candidates)')],
        'start': [locate('started.add'), locate('occupied.update'), locate('finish = time'),
                  locate('events.append'), locate('heapq.heappush')],
        'complete': [locate('heapq.heappop'), locate('completed.add'), locate('occupied.difference_update')],
        'advance': [locate('time = running[0][0]')],
        'done': [locate('validate_schedule(result)'), locate('return result')],
    }
    release_line = locate('occupied.difference_update')
    advance_line = locate('time = running[0][0]')
    initialized_line = locate('sequence = 0')
    choose_line = locate('started.add')
    start_line = locate('sequence += 1')
    previous_line = None
    steps = []

    def snapshot(frame, phase, task_id=None):
        state = frame.f_locals
        steps.append({
            'phase': phase, 'time': state['time'], 'task': task_id,
            'source_lines': anchors[phase],
            'running': [key for _, _, key in sorted(state['running'])],
            'occupied': sorted(state['occupied']),
            'completed_count': len(state['completed']),
            'started_count': len(state['started']),
            'candidates': [c[-1] for c in sorted(state.get('candidates', []))] if phase == 'choose' else [],
            'queue_position': dict(state['queue_pos']),
        })

    def local_trace(frame, event, arg):
        nonlocal previous_line
        if event in ('line', 'return'):
            # A line callback occurs before its line executes. Observe these
            # mutations at the following callback, after execution has finished.
            if previous_line == release_line:
                snapshot(frame, 'complete', frame.f_locals['key'])
            elif previous_line == advance_line:
                snapshot(frame, 'advance')
            elif previous_line == initialized_line:
                snapshot(frame, 'initialize')
            if event == 'line' and frame.f_lineno == choose_line:
                snapshot(frame, 'choose', frame.f_locals['task'].id)
            elif event == 'line' and frame.f_lineno == start_line:
                snapshot(frame, 'start', frame.f_locals['task'].id)
            elif event == 'return' and arg is not None:
                snapshot(frame, 'done')
            previous_line = frame.f_lineno if event == 'line' else None
        return local_trace

    def global_trace(frame, event, arg):
        if event == 'call' and frame.f_code is simulate.__code__:
            return local_trace
        return None

    old_trace = sys.gettrace()
    try:
        sys.settrace(global_trace)
        run = simulate(config, method)
    finally:
        sys.settrace(old_trace)
    # Counts and observed mutations must exactly agree with the returned trace.
    assert len([s for s in steps if s['phase'] == 'start']) == len(run.events)
    assert len([s for s in steps if s['phase'] == 'complete']) == len(run.events)
    assert steps[-1]['completed_count'] == len(run.events)
    return {
        **result_dict(run), 'events': [asdict(e) for e in run.events],
        'tasks': {k: asdict(v) for k, v in build_tasks(config, method).items()},
        'steps': steps,
        'source': [{'number': number, 'text': text} for number, text in lines.items()],
        'source_file': 'dualpipe_a/simulator.py',
        'source_sha256': hashlib.sha256(''.join(source).encode()).hexdigest(),
    }


def debug_comparison(params, overlap=True):
    config = Config(**params, allow_compute_comm_overlap=overlap)
    runs = [trace_simulation(config, method) for method in ('1f1b', 'dualpipe')]
    assert abs(runs[0]['metrics']['compute_work_total']-runs[1]['metrics']['compute_work_total']) < 1e-8
    assert abs(runs[0]['metrics']['communication_time_total']-runs[1]['metrics']['communication_time_total']) < 1e-8
    return {'config': asdict(config), 'runs': runs,
            'execution': 'Python sys.settrace captures actual simulator state; playback is discrete, not GPU wall time.'}
