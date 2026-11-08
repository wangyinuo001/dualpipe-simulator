"""Command-line entry point for iteration A."""

from __future__ import annotations

import argparse
from pathlib import Path

from dualpipe_a import Config, simulate
from dualpipe_a.output import plot_gantt, write_event_csv, write_result_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare 1F1B with a simplified bidirectional scheduler")
    parser.add_argument("--pp", type=int, default=4, help="physical GPU / pipeline stage count")
    parser.add_argument("--microbatches", type=int, default=8, help="even number, same total in both runs")
    parser.add_argument("--forward", type=float, default=1.0)
    parser.add_argument("--backward-input", type=float, default=1.0)
    parser.add_argument("--weight", type=float, default=1.0)
    parser.add_argument("--comm", type=float, default=0.1)
    parser.add_argument("--allow-overlap", action="store_true",
                        help="idealized independent compute/communication lanes on each GPU")
    parser.add_argument("--output", type=Path, default=Path("runs/default"))
    parser.add_argument("--no-plot", action="store_true", help="skip PNG export")
    args = parser.parse_args(argv)
    try:
        config = Config(args.pp, args.microbatches, args.forward,
                        args.backward_input, args.weight, args.comm, args.allow_overlap)
        runs = (simulate(config, "1f1b"), simulate(config, "dualpipe"))
    except (ValueError, RuntimeError, AssertionError) as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, exist_ok=True)
    for result in runs:
        write_event_csv(result, args.output / f"{result.method}_events.csv")
        if not args.no_plot:
            plot_gantt(result, args.output / f"gantt_{result.method}.png")
    write_result_json(runs, args.output / "results.json")
    for result in runs:
        metrics = result.metrics()
        print(f"{result.method:8s} makespan={metrics['makespan']:.4f}  "
              f"throughput={metrics['throughput_microbatches_per_time']:.4f}  "
              f"GPU idle={metrics['gpu_idle_fraction']:.2%}  "
              f"comm overlap={metrics['communication_overlap_fraction']:.2%}")
    print(f"Saved event CSV, results JSON and Gantt charts to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
