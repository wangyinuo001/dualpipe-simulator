"""Exports produced exclusively from scheduled events."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .simulator import Simulation, result_dict


def write_event_csv(result: Simulation, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(("id", "type", "stage", "peer", "microbatch", "direction",
                         "start", "finish", "duration", "dependencies", "resources"))
        for event in sorted(result.events, key=lambda e: (e.start, e.stage, e.id)):
            writer.writerow((event.id, event.kind, event.stage,
                             "" if event.peer is None else event.peer, event.microbatch,
                             event.direction, event.start, event.finish, event.duration,
                             "|".join(event.deps), "|".join(event.resources)))


def write_result_json(results: tuple[Simulation, Simulation], path: Path) -> None:
    first, second = results
    a, b = first.metrics(), second.metrics()
    payload = {
        "runs": [result_dict(first), result_dict(second)],
        "fairness": {
            "same_config": first.config == second.config,
            "same_compute_work": abs(a["compute_work_total"] - b["compute_work_total"]) < 1e-9,
            "same_communication_work": abs(a["communication_time_total"] - b["communication_time_total"]) < 1e-9,
            "same_task_counts_by_type": a["event_count_by_type"] == b["event_count_by_type"],
            "same_event_count": a["event_count"] == b["event_count"],
            "backward_total_equals_B_input_plus_W": first.config.backward_total == (
                first.config.backward_input + first.config.weight),
        },
        "comparison": {
            "makespan_ratio_1f1b_over_dualpipe": a["makespan"] / b["makespan"],
            "throughput_ratio_dualpipe_over_1f1b": (
                b["throughput_microbatches_per_time"] /
                a["throughput_microbatches_per_time"]),
            "interpretation": "ratios are properties of this simplified event model, not measured GPU speedup",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def plot_gantt(result: Simulation, path: Path) -> None:
    # Import here so event scheduling and validation need no plotting dependency.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    pp = result.config.pp
    makespan = result.metrics()["makespan"]
    height = max(3.5, 0.85 * pp + 1.5)
    fig, ax = plt.subplots(figsize=(14, height))
    colors = {"F": "#2459a5", "B": "#2d8a64", "W": "#d58532", "COMM": "#8e929b"}
    split_lanes = result.config.allow_compute_comm_overlap
    for event in result.events:
        stages = (event.stage, event.peer) if event.peer is not None else (event.stage,)
        for stage in stages:
            y = pp - 1 - stage
            band = ((y - 0.37, 0.28) if event.kind == "COMM" else (y + 0.02, 0.35)) if split_lanes else (y - 0.36, 0.72)
            ax.broken_barh([(event.start, event.duration)], band,
                           facecolors=colors[event.kind],
                           edgecolors="white" if event.kind != "COMM" else "#545861",
                           linewidth=0.45, alpha=0.55 if event.kind == "COMM" else 1)
            if event.kind != "COMM":
                ax.text(event.start + event.duration / 2, y + 0.18 if split_lanes else y,
                        event.kind, ha="center", va="center",
                        fontsize=8, color="white", clip_on=True)
    ax.set_yticks(range(pp), [f"GPU {pp - 1 - y}" for y in range(pp)])
    ax.set_ylim(-0.6, pp - 0.4)
    ax.set_xlim(0, makespan * 1.01)
    ax.set_xlabel("Abstract time units")
    label = "1F1B" if result.method == "1f1b" else "Bidirectional scheduling model"
    mode = "independent compute/communication lanes" if split_lanes else "no overlap"
    ax.set_title(f"{label} | PP={pp}, M={result.config.microbatches} | {mode}")
    ax.grid(axis="x", alpha=0.18)
    ax.set_axisbelow(True)
    ax.legend(handles=[Patch(facecolor=colors[k], label=v, alpha=0.55 if k == "COMM" else 1)
                       for k, v in (("F", "Forward"), ("B", "Input gradient"),
                                    ("W", "Weight gradient"), ("COMM", "Communication"))],
              loc="upper right", ncol=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)
