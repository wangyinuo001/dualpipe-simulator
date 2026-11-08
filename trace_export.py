"""Export actual Python results into a self-contained, offline trace viewer."""
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import webbrowser

ROOT = Path(__file__).resolve().parent


def export_run(payload, label, open_browser=True):
    now = datetime.now(timezone.utc)
    payload['provenance']['generated_at_utc'] = now.isoformat()
    payload['run_id'] = now.strftime('%Y%m%dT%H%M%S%fZ')
    folder = ROOT / '运行结果' / f"{payload['run_id']}_{label}"
    folder.mkdir(parents=True, exist_ok=False)
    # Preserve exact source alongside the output, so later edits cannot obscure
    # which implementation generated these events.
    (folder / 'simulator_source.py').write_bytes((ROOT / 'dualpipe_a/simulator.py').read_bytes())
    (folder / 'entry_source.py').write_bytes((ROOT / '课堂演示.py').read_bytes())
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    (folder / 'events.json').write_text(text, encoding='utf-8')
    for mode, runs in payload['groups'].items():
        for run in runs:
            with (folder / f"{mode}_{run['method']}.csv").open('w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=list(run['events'][0]))
                writer.writeheader()
                for event in run['events']:
                    writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, tuple)) else v
                                     for k, v in event.items()})
    web = ROOT / 'web'
    html = (web / 'index.html').read_text(encoding='utf-8')
    html = html.replace('<link rel="stylesheet" href="/style.css">',
                        '<style>' + (web / 'style.css').read_text(encoding='utf-8') + '</style>')
    js = (web / 'app.js').read_text(encoding='utf-8')
    html = html.replace('<script src="/app.js"></script>',
                        '<script>window.TRACE_DATA=' + text.replace('<', '\\u003c') + ';</script>\n'
                        + '<script>' + js.replace('</script', '<\\/script') + '</script>')
    (folder / '时间轴总览.html').write_text(html, encoding='utf-8')
    path = write_debug_view(folder, payload)
    if open_browser:
        webbrowser.open(path.as_uri())
    return folder


def write_debug_view(folder, payload):
    """Use the same code-and-state interface for command-line and browser entry."""
    web = ROOT / 'web'
    html = (web / 'debug.html').read_text(encoding='utf-8')
    html = html.replace('href="/overview"', 'href="时间轴总览.html"')
    html = html.replace('<link rel="stylesheet" href="/debug.css">',
                        '<style>' + (web / 'debug.css').read_text(encoding='utf-8') + '</style>')
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    js = (web / 'debug.js').read_text(encoding='utf-8')
    html = html.replace('<script src="/debug.js"></script>',
                        '<script>window.DEBUG_DATA=' + text + ';</script>\n'
                        + '<script>' + js.replace('</script', '<\\/script') + '</script>')
    path = folder / '时间轴.html'
    path.write_text(html, encoding='utf-8')
    return path
