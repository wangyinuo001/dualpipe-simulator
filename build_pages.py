"""Build a static website that runs the unchanged Python engine in the browser."""
from pathlib import Path
import inspect
import shutil

from demo import parse_parameters, run_comparison

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'docs'


def build():
    OUT.mkdir(exist_ok=True)
    web = ROOT / 'web'
    for source, destination in [('debug.html', 'index.html'), ('index.html', 'overview.html')]:
        html = (web / source).read_text()
        for name in ['debug.css', 'debug.js', 'style.css', 'app.js']:
            html = html.replace('"/' + name + '"', '"./' + name + '"')
        html = html.replace('href="/overview"', 'href="./overview.html"')
        script = './debug.js' if source == 'debug.html' else './app.js'
        html = html.replace('<script src="' + script + '"></script>',
                            '<script src="./browser-api.js"></script>\n<script src="' + script + '"></script>')
        (OUT / destination).write_text(html)
    for name in ['debug.css', 'debug.js', 'style.css', 'app.js', 'browser-api.js', 'python-worker.mjs']:
        shutil.copy2(web / name, OUT / name)
    shutil.copytree(web / 'vendor', OUT / 'vendor', dirs_exist_ok=True)
    python = OUT / 'python'
    (python / 'dualpipe_a').mkdir(parents=True, exist_ok=True)
    for name in ['__init__.py', 'simulator.py']:
        shutil.copy2(ROOT / 'dualpipe_a' / name, python / 'dualpipe_a' / name)
    shutil.copy2(ROOT / 'debug_trace.py', python / 'debug_trace.py')
    bridge = '''import json
import time
from dataclasses import asdict
from dualpipe_a.simulator import Config, simulate, result_dict
from debug_trace import debug_comparison

'''
    bridge += inspect.getsource(parse_parameters) + '\n\n' + inspect.getsource(run_comparison)
    bridge += '''

def execute_json(raw):
    request = json.loads(raw)
    values = request['values']
    params = parse_parameters(values)
    if request['path'] == '/api/debug':
        overlap = values.get('overlap', True)
        if not isinstance(overlap, bool):
            raise ValueError('overlap 必须是布尔值')
        result = debug_comparison(params, overlap)
    elif request['path'] == '/api/run':
        result = run_comparison(values)
    else:
        raise ValueError('Unknown request')
    result['run_id'] = time.time_ns()
    return json.dumps(result, ensure_ascii=False, allow_nan=False)
'''
    (python / 'browser_bridge.py').write_text(bridge)
    (OUT / '.nojekyll').touch()
    print('Built:', OUT)


if __name__ == '__main__':
    build()
