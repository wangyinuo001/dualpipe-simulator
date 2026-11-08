"""Run the three paired experiments promised by the classroom demonstration.

Only iteration-A mechanisms are used. Communication coverage is not measured.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from dualpipe_a import Config, simulate
from dualpipe_a.output import plot_gantt, write_event_csv, write_result_json


CASES = (
    ("baseline", Config(pp=4, microbatches=8, forward=1, backward_input=1, weight=1, comm=0.1)),
    ("high_comm", Config(pp=4, microbatches=8, forward=1, backward_input=1, weight=1, comm=1.0)),
    ("more_microbatches", Config(pp=4, microbatches=16, forward=1, backward_input=1, weight=1, comm=0.1)),
)


def main() -> int:
    out = Path("runs/sweep")
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for name, config in CASES:
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        runs = (simulate(config, "1f1b"), simulate(config, "dualpipe"))
        write_result_json(runs, folder / "results.json")
        for run in runs:
            write_event_csv(run, folder / f"{run.method}_events.csv")
            plot_gantt(run, folder / f"gantt_{run.method}.png")
            metrics = run.metrics()
            summary.append({
                "case": name,
                "pp": config.pp,
                "microbatches": config.microbatches,
                "forward": config.forward,
                "backward_input": config.backward_input,
                "weight": config.weight,
                "comm": config.comm,
                "method": run.method,
                "makespan": metrics["makespan"],
                "throughput_microbatches_per_time": metrics["throughput_microbatches_per_time"],
                "gpu_idle_fraction": metrics["gpu_idle_fraction"],
                "event_count": metrics["event_count"],
            })
            print(f"{name:18s} M={config.microbatches:2d} COMM={config.comm:.1f} "
                  f"{run.method:8s} makespan={metrics['makespan']:.1f} "
                  f"throughput={metrics['throughput_microbatches_per_time']:.4f} "
                  f"GPU idle={metrics['gpu_idle_fraction']:.2%}")
    with (out / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    (out / "summary.json").write_text(json.dumps({
        "runs": summary,
        "notes": [
            "Each case compares equal work and communication assumptions across the two methods.",
            "Changing M changes total work; compare throughput and idle fraction across M values.",
            "Communication occupies both endpoint GPUs; compute-communication overlap and coverage are not modeled.",
            "This is a simplified event scheduler, not a measured DeepSeek training run.",
        ],
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved six event traces, six Gantt charts and summary to {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
