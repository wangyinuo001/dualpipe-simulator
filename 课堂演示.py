"""在编辑器里打开这个文件，然后实际运行；浏览器只查看运行结果。

python3 课堂演示.py --case baseline
python3 课堂演示.py --case high_comm
python3 课堂演示.py --case more_microbatches

本程序使用组员提供的简化双向调度器，不是官方 DualPipe 完整复现。
"""

# %% 1. 参数：三组对照每次只改一个量
import argparse
import hashlib
import inspect
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

from dualpipe_a.simulator import Config, simulate, validate_schedule, result_dict
from trace_export import export_run
from debug_trace import trace_simulation

BASELINE = Config(
    pp=4,                    # 4 张 GPU / 4 个流水线阶段
    microbatches=8,           # 两种调度都处理 8 个微批
    forward=1.0,             # F：前向计算时间
    backward_input=1.0,      # B：输入梯度计算时间
    weight=1.0,              # W：权重梯度计算时间
    comm=0.1,               # 相邻流水线阶段之间的通信时间
)

CASES = {
    "baseline": BASELINE,
    "high_comm": replace(BASELINE, comm=1.0),
    "more_microbatches": replace(BASELINE, microbatches=16),
}


# %% 2. 调度：进入 simulate() 可以看到任务就绪、资源检查和事件推进
# 源文件 dualpipe_a/simulator.py 中可重点展示：
# build_tasks()：前向依赖前一阶段传输；反向依赖本层前向及后一阶段梯度。
# simulate()：依赖全部完成且资源未占用，任务才会进入候选集合。
# 1F1B 按固定队列取任务；简化双向模型按 COMM → B → F → W 的优先级取任务。
# 当没有新任务可启动，time 跳到最近一个正在执行的任务的完成时刻。
def run_experiment(config):
    groups = {}
    for overlap in (False, True):
        resource_config = replace(config, allow_compute_comm_overlap=overlap)
        runs = [trace_simulation(resource_config, method)
                for method in ("1f1b", "dualpipe")]

        # %% 3. 校验：不能只比较一张更紧凑的图
        # trace_simulation 内部实际调用 simulate，并执行 validate_schedule。
        a, b = [run["metrics"] for run in runs]
        assert abs(a["compute_work_total"] - b["compute_work_total"]) < 1e-8
        assert abs(a["communication_time_total"] - b["communication_time_total"]) < 1e-8

        # %% 4. 结果来自事件：最后一个事件结束的时刻就是总完成时间
        mode = "overlap" if overlap else "serial"
        groups[mode] = []
        for run in runs:
            makespan = max(event["finish"] for event in run["events"])
            print(f"{mode:8s} {run['method']:8s}  events={len(run['events']):3d}"
                  f"  T={makespan:.2f}")
            groups[mode].append(run)
        print(f"同一资源模式下加速比：{a['makespan'] / b['makespan']:.3f}x\n")
    return groups


# %% 5. 现场执行：打印真实事件，再打开这些事件对应的可视化
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=[*CASES, "all"], default="baseline")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    selected = CASES if args.case == "all" else {args.case: CASES[args.case]}
    for name, config in selected.items():
        print(f"\n===== {name} =====\n参数：{asdict(config)}")
        started = perf_counter()
        groups = run_experiment(config)
        wall_seconds = perf_counter() - started
        print("依赖与资源校验通过，两种方法的工作量一致。")
        print("\n微批 0 的实际事件（简化双向、计算通信可并行）：")
        trace = groups["overlap"][1]["events"]
        for event in trace:
            if event["microbatch"] == 0:
                print(f"  {event['id']:15s} {event['start']:6.2f} -> {event['finish']:6.2f}"
                      f"  deps={event['deps']}")
        print(f"\nPython 调度用时 {wall_seconds:.4f} 秒；此值不作为 GPU 仿真耗时。")
        source = Path(inspect.getsourcefile(simulate))
        payload = {
            "config": asdict(config), "groups": groups, "validated": True,
            "provenance": {
                "case": name, "entry": Path(__file__).name,
                "simulator": "dualpipe_a/simulator.py",
                "simulator_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "entry_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "python_wall_seconds": wall_seconds,
            },
        }
        result = export_run(payload, name, open_browser=not args.no_open)
        print(f"\n本次事件：{result / 'events.json'}")
        print(f"本次可视化：{result / '时间轴.html'}\n")


if __name__ == "__main__":
    main()
