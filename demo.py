"""Local presentation UI. All displayed traces come from the supplied simulator."""
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import inspect
import json
import time
import webbrowser

from dualpipe_a.simulator import Config, simulate, result_dict

ROOT = Path(__file__).resolve().parent


def parse_parameters(values):
    if not isinstance(values, dict):
        raise ValueError('参数必须是对象')
    params = {}
    for name, default in [('pp', 4), ('microbatches', 8)]:
        value = values.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ValueError(f'{name} 必须是整数')
        params[name] = int(value)
    if not 2 <= params['pp'] <= 8 or not 2 <= params['microbatches'] <= 32:
        raise ValueError('现场演示支持 2—8 个阶段、2—32 个偶数微批')
    for name, default in [('forward', 1), ('backward_input', 1), ('weight', 1), ('comm', .1)]:
        value = values.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not .01 <= value <= 10:
            raise ValueError(f'{name} 必须在 0.01—10 之间')
        params[name] = float(value)
    return params


def run_comparison(values):
    params = parse_parameters(values)
    # This is also the call displayed in the UI: no hard-coded timing results.
    groups = {}
    for overlap in (False, True):
        config = Config(**params, allow_compute_comm_overlap=overlap)
        runs = [simulate(config, method) for method in ('1f1b', 'dualpipe')]
        work = [r.metrics() for r in runs]
        assert abs(work[0]['compute_work_total'] - work[1]['compute_work_total']) < 1e-7
        assert abs(work[0]['communication_time_total'] - work[1]['communication_time_total']) < 1e-7
        groups['overlap' if overlap else 'serial'] = [
            {**result_dict(r), 'events': [asdict(e) for e in r.events]} for r in runs]
    return {'config': params, 'groups': groups, 'validated': True,
            'model': '简化双向调度；非官方 DualPipe 完整复现。时间为抽象单位。',
            'assumption': '并行模式使用独立的计算与通信资源，未模拟 SM、显存带宽争用和 MoE All-to-All。'}


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, data, kind='application/json; charset=utf-8'):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        route = self.path.split('?', 1)[0]
        if route == '/api/source':
            return self.reply(200, {'source': inspect.getsource(simulate)})
        files = {'/': ('debug.html', 'text/html; charset=utf-8'),
                 '/debug': ('debug.html', 'text/html; charset=utf-8'),
                 '/overview': ('index.html', 'text/html; charset=utf-8'),
                 '/debug.js': ('debug.js', 'text/javascript; charset=utf-8'),
                 '/debug.css': ('debug.css', 'text/css; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if route not in files:
            return self.reply(404, {'error': 'Not found'})
        file, mime = files[route]
        self.reply(200, (ROOT / 'web' / file).read_bytes(), mime)

    def do_POST(self):
        if self.path not in ('/api/run', '/api/debug'):
            return self.reply(404, {'error': 'Not found'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 0 < length <= 4096:
                raise ValueError('参数长度无效')
            values = json.loads(self.rfile.read(length))
            if self.path == '/api/debug':
                from debug_trace import debug_comparison
                params = parse_parameters(values)
                overlap = values.get('overlap', True)
                if not isinstance(overlap, bool):
                    raise ValueError('overlap 必须是布尔值')
                result = debug_comparison(params, overlap)
            else:
                result = run_comparison(values)
            result['run_id'] = time.time_ns()
            self.reply(200, result)
        except (ValueError, TypeError, OverflowError) as error:
            self.reply(400, {'error': str(error)})
        except Exception:
            import traceback
            traceback.print_exc()
            self.reply(500, {'error': '仿真未通过校验，请查看终端；未生成展示结果。'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError:
        from urllib.request import urlopen
        url = f'http://127.0.0.1:{args.port}'
        try:
            with urlopen(url, timeout=2) as response:
                ours = 'DualPipe' in response.read().decode('utf-8')
        except Exception:
            ours = False
        if ours:
            print(f'演示已经在运行：{url}', flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            return
        parser.error('端口已被其他程序占用，请用 --port 8766 重新启动。')
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'现场演示已启动：{url}\n按 Ctrl+C 退出。', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
