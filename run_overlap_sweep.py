"""Compare no-overlap and ideal overlap resources without preset results."""

from __future__ import annotations

import csv
from dataclasses import replace
import json
from pathlib import Path

from dualpipe_a import simulate
from dualpipe_a.output import plot_gantt, write_event_csv, write_result_json
from run_sweep import CASES


def main() -> int:
    out = Path("runs/overlap_sweep")
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for name, base in CASES:
        by_mode = {}
        for mode, enabled in (("serial", False), ("ideal_overlap", True)):
            config = replace(base, allow_compute_comm_overlap=enabled)
            folder = out / name / mode
            folder.mkdir(parents=True, exist_ok=True)
            runs = (simulate(config, "1f1b"), simulate(config, "dualpipe"))
            write_result_json(runs, folder / "results.json")
            by_mode[mode] = {run.method: run for run in runs}
            for run in runs:
                write_event_csv(run, folder / f"{run.method}_events.csv")
                plot_gantt(run, folder / f"gantt_{run.method}.png")
        for method in ("1f1b", "dualpipe"):
            old = by_mode["serial"][method].metrics()
            new = by_mode["ideal_overlap"][method].metrics()
            row = {
                "case": name,
                "method": method,
                "pp": base.pp,
                "microbatches": base.microbatches,
                "comm": base.comm,
                "serial_makespan": old["makespan"],
                "ideal_overlap_makespan": new["makespan"],
                "ideal_overlap_throughput": new["throughput_microbatches_per_time"],
                "communication_overlap_fraction": new["communication_overlap_fraction"],
                "ideal_overlap_gpu_idle_fraction": new["gpu_idle_fraction"],
                "compute_work_equal": old["compute_work_total"] == new["compute_work_total"],
                "communication_work_equal": old["communication_time_total"] == new["communication_time_total"],
            }
            summary.append(row)
            print(f"{name:18s} {method:8s} M={base.microbatches:2d} COMM={base.comm:.1f} "
                  f"serial={old['makespan']:.1f} overlap={new['makespan']:.1f} "
                  f"temporal coverage={new['communication_overlap_fraction']:.2%}")
    with (out / "summary.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    (out / "summary.json").write_text(json.dumps({
        "rows": summary,
        "definition": "temporal coverage = GPU-endpoint communication time coinciding with compute on the same GPU / total GPU-endpoint communication time",
        "assumption": "idealized separate compute and communication resource on each GPU, one communication slot per GPU and exclusive adjacent link; no SM or memory-bandwidth contention",
        "scope": "abstract event-model results, not official DualPipe kernel measurements or real GPU speedup",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved twelve traces and six paired comparisons to {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
