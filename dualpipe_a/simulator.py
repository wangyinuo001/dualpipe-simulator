"""Small discrete-event model of 1F1B and a bidirectional DualPipe baseline.

This is a scheduling model, not DeepSeek's GPU implementation. In iteration A,
communication occupies both endpoint GPUs, so compute/communication overlap is
deliberately absent. Every microbatch performs the same F, B_input and W work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import heapq
import math
from collections import Counter
from typing import Literal

Method = Literal["1f1b", "dualpipe"]
EPS = 1e-9


def _union_duration(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    intervals.sort()
    start, finish = intervals[0]
    total = 0.0
    for next_start, next_finish in intervals[1:]:
        if next_start > finish:
            total += finish - start
            start, finish = next_start, next_finish
        else:
            finish = max(finish, next_finish)
    return total + finish - start


@dataclass(frozen=True)
class Config:
    pp: int = 4
    microbatches: int = 8
    forward: float = 1.0
    backward_input: float = 1.0
    weight: float = 1.0
    comm: float = 0.1
    allow_compute_comm_overlap: bool = False

    def __post_init__(self) -> None:
        if self.pp < 2 or self.microbatches < 2:
            raise ValueError("pp and microbatches must both be at least 2")
        if self.microbatches % 2:
            raise ValueError("microbatches must be even for the bidirectional comparison")
        for name in ("forward", "backward_input", "weight", "comm"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not isinstance(self.allow_compute_comm_overlap, bool):
            raise ValueError("allow_compute_comm_overlap must be a boolean")

    @property
    def backward_total(self) -> float:
        return self.backward_input + self.weight


@dataclass(frozen=True)
class Task:
    id: str
    kind: str
    stage: int
    microbatch: int
    direction: int
    duration: float
    deps: tuple[str, ...]
    resources: tuple[str, ...]
    peer: int | None = None


@dataclass(frozen=True)
class Event:
    id: str
    kind: str
    stage: int
    microbatch: int
    direction: int
    start: float
    finish: float
    duration: float
    peer: int | None
    deps: tuple[str, ...]
    resources: tuple[str, ...]


@dataclass(frozen=True)
class Simulation:
    method: Method
    config: Config
    events: tuple[Event, ...]

    def metrics(self) -> dict:
        makespan = max(event.finish for event in self.events)
        counts = Counter(event.kind for event in self.events)
        compute = sum(e.duration for e in self.events if e.kind != "COMM")
        comm_time = sum(e.duration for e in self.events if e.kind == "COMM")
        comm_gpu = 2 * comm_time
        compute_by_stage = {stage: [e for e in self.events
                                    if e.stage == stage and e.kind != "COMM"]
                            for stage in range(self.config.pp)}
        overlap_gpu = sum(max(0.0, gap) if gap > EPS else 0.0
                          for comm in self.events if comm.kind == "COMM"
                          for stage in (comm.stage, comm.peer)
                          for comp in compute_by_stage[stage]
                          for gap in (min(comm.finish, comp.finish) - max(comm.start, comp.start),))
        capacity = self.config.pp * makespan
        by_stage = []
        for stage in range(self.config.pp):
            used = _union_duration([(e.start, e.finish) for e in self.events
                                    if e.stage == stage or e.peer == stage])
            by_stage.append({"stage": stage, "idle_time": max(0.0, makespan - used),
                             "idle_fraction": max(0.0, 1 - used / makespan)})
        return {
            "makespan": makespan,
            "throughput_microbatches_per_time": self.config.microbatches / makespan,
            "compute_gpu_fraction": compute / capacity,
            "communication_gpu_fraction": comm_gpu / capacity,
            "compute_comm_overlap_gpu_fraction": overlap_gpu / capacity,
            "communication_overlap_fraction": overlap_gpu / comm_gpu,
            "gpu_idle_fraction": sum(item["idle_time"] for item in by_stage) / capacity,
            "per_stage": by_stage,
            "event_count": len(self.events),
            "event_count_by_type": dict(counts),
            "compute_work_total": compute,
            "communication_time_total": comm_time,
            "compute_work_per_stage": self.config.microbatches * (
                self.config.forward + self.config.backward_total),
            "backward_total": self.config.backward_total,
        }


def _task_id(kind: str, mb: int, stage: int, peer: int | None = None) -> str:
    return f"{kind}:{mb}:{stage}" if peer is None else f"{kind}:{mb}:{stage}:{peer}"


def build_tasks(config: Config, method: Method) -> dict[str, Task]:
    if method not in ("1f1b", "dualpipe"):
        raise ValueError("method must be '1f1b' or 'dualpipe'")
    tasks: dict[str, Task] = {}

    def add(kind: str, mb: int, stage: int, direction: int, duration: float,
            deps: tuple[str, ...], peer: int | None = None) -> str:
        key = _task_id(kind, mb, stage, peer)
        if peer is None:
            resources = (f"compute:{stage}" if config.allow_compute_comm_overlap else f"gpu:{stage}",)
        elif config.allow_compute_comm_overlap:
            resources = (f"communication:{stage}", f"communication:{peer}",
                         f"link:{min(stage, peer)}")
        else:
            resources = (f"gpu:{stage}", f"gpu:{peer}", f"link:{min(stage, peer)}")
        if key in tasks:
            raise AssertionError(f"duplicate task {key}")
        tasks[key] = Task(key, kind, stage, mb, direction, duration, deps, resources, peer)
        return key

    for mb in range(config.microbatches):
        direction = 0 if method == "1f1b" or mb < config.microbatches // 2 else 1
        path = list(range(config.pp)) if direction == 0 else list(reversed(range(config.pp)))
        f_ids: dict[int, str] = {}
        b_ids: dict[int, str] = {}
        for pos, stage in enumerate(path):
            if pos == 0:
                deps: tuple[str, ...] = ()
            else:
                deps = (_task_id("COMM", mb, path[pos - 1], stage),)
            f_ids[stage] = add("F", mb, stage, direction, config.forward, deps)
            if pos:
                add("COMM", mb, path[pos - 1], direction, config.comm,
                    (f_ids[path[pos - 1]],), stage)
        for pos in reversed(range(config.pp)):
            stage = path[pos]
            deps = (f_ids[stage],) if pos == config.pp - 1 else (
                f_ids[stage], _task_id("COMM", mb, path[pos + 1], stage))
            b_ids[stage] = add("B", mb, stage, direction, config.backward_input, deps)
            add("W", mb, stage, direction, config.weight, (b_ids[stage],))
            if pos > 0:
                add("COMM", mb, stage, direction, config.comm,
                    (b_ids[stage],), path[pos - 1])
    return tasks


def _one_f_one_b_queues(config: Config) -> dict[int, list[str]]:
    queues: dict[int, list[str]] = {}
    for stage in range(config.pp):
        warmup = min(config.pp - stage - 1, config.microbatches)
        queue = [_task_id("F", mb, stage) for mb in range(warmup)]
        for mb in range(config.microbatches):
            if mb + warmup < config.microbatches:
                queue.append(_task_id("F", mb + warmup, stage))
            queue.extend((_task_id("B", mb, stage), _task_id("W", mb, stage)))
        queues[stage] = queue
    return queues


def simulate(config: Config, method: Method) -> Simulation:
    tasks = build_tasks(config, method)
    queues = _one_f_one_b_queues(config) if method == "1f1b" else {}
    queue_pos = {stage: 0 for stage in range(config.pp)}
    completed: set[str] = set()
    started: set[str] = set()
    occupied: set[str] = set()
    running: list[tuple[float, int, str]] = []
    events: list[Event] = []
    time = 0.0
    sequence = 0

    while len(completed) < len(tasks):
        while running and running[0][0] <= time + EPS:
            _, _, key = heapq.heappop(running)
            completed.add(key)
            occupied.difference_update(tasks[key].resources)

        while True:
            candidates = []
            for task in tasks.values():
                if task.id in started or not all(dep in completed for dep in task.deps):
                    continue
                if any(resource in occupied for resource in task.resources):
                    continue
                if method == "1f1b" and task.kind != "COMM":
                    stage_queue = queues[task.stage]
                    if queue_pos[task.stage] >= len(stage_queue) or task.id != stage_queue[queue_pos[task.stage]]:
                        continue
                # Transfer first. DualPipe's ready-task preference is B, F, W.
                priority = {"COMM": 0, "B": 1, "F": 2, "W": 3}[task.kind]
                candidates.append((priority, task.microbatch, task.stage, task.id))
            if not candidates:
                break
            task = tasks[min(candidates)[-1]]
            started.add(task.id)
            occupied.update(task.resources)
            if method == "1f1b" and task.kind != "COMM":
                queue_pos[task.stage] += 1
            finish = time + task.duration
            events.append(Event(task.id, task.kind, task.stage, task.microbatch,
                                task.direction, time, finish, task.duration,
                                task.peer, task.deps, task.resources))
            heapq.heappush(running, (finish, sequence, task.id))
            sequence += 1

        if running:
            time = running[0][0]
        elif len(completed) < len(tasks):
            remaining = sorted(set(tasks) - completed)
            raise RuntimeError(f"scheduler deadlock at t={time:g}; remaining={remaining[:12]}")

    result = Simulation(method, config, tuple(events))
    validate_schedule(result)
    return result


def validate_schedule(result: Simulation) -> None:
    """Raise on missing work, broken dependencies, or resource collisions."""
    expected = build_tasks(result.config, result.method)
    actual = {event.id: event for event in result.events}
    if len(actual) != len(result.events) or set(actual) != set(expected):
        raise AssertionError("missing, duplicate, or unexpected task events")
    for key, task in expected.items():
        event = actual[key]
        if (event.kind, event.stage, event.microbatch, event.direction, event.peer) != (
                task.kind, task.stage, task.microbatch, task.direction, task.peer):
            raise AssertionError(f"task identity mismatch: {key}")
        if event.deps != task.deps or event.resources != task.resources:
            raise AssertionError(f"task graph or resource mismatch: {key}")
        if abs(event.duration - task.duration) > EPS or abs(event.finish - event.start - event.duration) > EPS:
            raise AssertionError(f"duration mismatch: {key}")
        if event.start < -EPS:
            raise AssertionError(f"negative start: {key}")
        for dep in task.deps:
            if actual[dep].finish > event.start + EPS:
                raise AssertionError(f"dependency violation: {dep} -> {key}")
    for resource in {r for task in expected.values() for r in task.resources}:
        intervals = sorted((e.start, e.finish, e.id) for e in result.events
                           if resource in expected[e.id].resources)
        for before, after in zip(intervals, intervals[1:]):
            if before[1] > after[0] + EPS:
                raise AssertionError(f"resource overlap on {resource}: {before[2]}, {after[2]}")
    if result.method == "1f1b":
        for stage, queue in _one_f_one_b_queues(result.config).items():
            actual_queue = [e.id for e in sorted(result.events, key=lambda e: (e.start, e.finish))
                            if e.stage == stage and e.kind != "COMM"]
            if actual_queue != queue:
                raise AssertionError(f"1F1B order mismatch on stage {stage}")


def result_dict(result: Simulation) -> dict:
    return {"method": result.method, "config": asdict(result.config),
            "metrics": result.metrics(), "model": {
                "communication": ("compute and communication use independent per-GPU resources; "
                                  "each GPU has one communication slot and adjacent links are exclusive"
                                  if result.config.allow_compute_comm_overlap else
                                  "COMM occupies sender GPU, receiver GPU and link; no compute/COMM overlap"),
                "dualpipe": "simplified two-direction task scheduler; not official DualPipe runtime",
                "units": "abstract time units",
            }}
