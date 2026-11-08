# DualPipe 调度可视化仿真

[在线演示](https://wangyinuo001.github.io/dualpipe-simulator/)

用于《计算机系统结构》课程的离散事件调度演示。上半屏为 1F1B，下半屏为简化双向调度；每组左侧显示实际 Python 调度源码，右侧显示 GPU 状态和任务时间轴。

两组使用同一仿真时钟、同一时间轴尺度与相同工作量。基础参数下，简化双向调度在 26.2 完成，1F1B 在 30.6 完成。完成次序由运行结果决定，通信较重时可能反转。

## 使用

打开在线演示，选择实验并点击“运行对照实验”。首次运行会下载 Python 浏览器运行环境，之后可以改参数重新计算。支持同步播放、单步回看、突出微批、计算通信重叠定位、先完成时刻和 JSON 导出。默认 30× 仅表示回放速度。

在线版使用 Pyodide 在浏览器的 Web Worker 内运行仓库中的同一份 Python 源码，执行依赖、资源和任务完整性校验。运行环境随网站一起托管，不依赖独立 Python 服务器，也不使用预存指标代替计算。

本地运行（Python 3.9+）：

```sh
python3 demo.py
```

从编辑器运行并导出离线页面：

```sh
python3 课堂演示.py --case baseline
python3 课堂演示.py --case high_comm
python3 课堂演示.py --case more_microbatches
```

生成的 `运行结果/*/时间轴.html` 可离线打开，包含当次执行状态；`时间轴总览.html` 用于查看完整图并导出图片。

## 实验范围

当前 `dualpipe` 实现为双向微批注入和 COMM → B → F → W 的就绪任务优先级策略，**不是官方 DualPipe 的完整复现**。模型包含 F、输入梯度 B、权重梯度 W 和相邻阶段通信。并行模式提供独立的计算和通信资源，不模拟 MoE All-to-All、SM/显存带宽争用、显存容量或调度执行开销。

1F1B 受各阶段固定队列约束，简化双向策略还改变了任务选择规则。因此两者的收益差异不能全部归因于“双向”这一项机制。仿真结果用于说明模型内的等待、依赖、重叠和参数敏感性，不能视为真实 GPU 测时或官方 DualPipe 性能结论。

计算空闲比例包含通信等待，不只表示首尾流水线气泡。源码中的 B 表示输入梯度部分，完整反向耗时为 B + W。

参考：[DeepSeek 官方 DualPipe](https://github.com/deepseek-ai/DualPipe)、[DeepSeek-V3 技术报告](https://arxiv.org/abs/2412.19437)。

## 开发与验证

```sh
pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 build_pages.py
python3 -m http.server 8000 --directory docs
```

`dualpipe_a/simulator.py` 为仿真核心，`debug_trace.py` 捕获实际执行状态，`web/debug.js` 按共同模型时钟呈现结果。`build_pages.py` 复制相同源码并生成浏览器接口，不维护第二套调度算法。推送 main 后由 GitHub Actions 测试、构建并部署 GitHub Pages。

浏览器运行环境固定为 Pyodide 0.27.7，第三方许可见 `web/vendor/pyodide/LICENSE`。仓库未包含课程 PPT、讲稿、视频或内部规划材料。
