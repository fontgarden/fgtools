"""Run agent harnesses on the drafting evaluation and compare them.

    fgtools evaluate-drafting run TASK RUN --harness NAME [--model M] [--max-time S]
                                 prepare RUN, run the harness in it, score it
    fgtools evaluate-drafting table RUN ...
                                 one line for each run: harness, model, task,
                                 overlap, distance, compatibility, time, cost

The harnesses and their command lines are in harnesses.toml. Each harness
gets the same prompt: read TASK.md and do the task. It runs in RUN with
RUN as its working directory, with the fgtools command on PATH. The command
writes RUN/harness.json (harness, model, version, exit status, seconds, cost)
and RUN/harness.log (the output of the harness), then scores the run.

A harness can read files outside RUN if its permissions allow it. A run is
valid only if the harness kept to RUN; read harness.log to check.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

HARNESSES = tomllib.loads((Path(__file__).with_name('harnesses.toml')).read_text())
PROMPT = ('Read TASK.md in the current directory and do the task it describes. '
          'Work only in the current directory.')


def command(harness, model, max_time):
    """The command line of a harness, with the placeholders filled in."""
    values = {'prompt': PROMPT, 'model': model or '', 'max_time': str(max_time)}
    parts, skip = [], False
    for part in HARNESSES[harness]['command']:
        if skip:
            skip = False
            continue
        if '{model}' in part and not model:
            continue
        if not model and part == '--model':
            skip = True
            continue
        parts.append(part.format(**values))
    return parts


def cost(harness, output):
    """The cost in US dollars from the JSON output of a harness, if it gives one."""
    field = HARNESSES[harness].get('cost')
    if not field:
        return None
    try:
        return json.loads(output).get(field)
    except (json.JSONDecodeError, AttributeError):
        return None


def run(task, run_dir, harness, model=None, max_time=3600):
    from fontgarden import evaluate_drafting
    if harness not in HARNESSES:
        sys.exit(f'Unknown harness {harness}. Known: {", ".join(HARNESSES)}.')
    run_dir = Path(run_dir).resolve()
    evaluate_drafting.prepare(task, run_dir)
    env = dict(os.environ, PATH=os.pathsep.join([str(Path(sys.executable).parent),
                                                 os.environ.get('PATH', '')]))
    try:
        version = subprocess.run(HARNESSES[harness]['version'], capture_output=True,
                                 text=True, env=env, timeout=60).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        version = ''
    start = time.monotonic()
    try:
        result = subprocess.run(command(harness, model, max_time), cwd=run_dir, env=env,
                                capture_output=True, text=True, timeout=max_time + 60)
        status, output = result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired as error:
        status, output = 'timeout', (error.stdout or b'').decode(errors='replace')
    seconds = round(time.monotonic() - start)
    (run_dir / 'harness.log').write_text(output)
    record = dict(harness=harness, model=model, version=version, exit=status,
                  seconds=seconds, cost_usd=cost(harness, result.stdout if status != 'timeout' else ''))
    (run_dir / 'harness.json').write_text(json.dumps(record, indent=1) + '\n')
    print(f'{harness}: exit {status} after {seconds} s')
    evaluate_drafting.score(run_dir)


def table(runs):
    print(f"{'run':<24}{'harness':<10}{'model':<18}{'task':<11}{'iou':>6}{'dist':>7}"
          f"{'compat':>8}{'seconds':>9}{'cost':>8}")
    for run_dir in runs:
        run_dir = Path(run_dir)
        record = json.loads((run_dir / 'harness.json').read_text()) if (run_dir / 'harness.json').exists() else {}
        summary = json.loads((run_dir / 'scores.json').read_text())['summary']
        cost_usd = record.get('cost_usd')
        print(f"{run_dir.name:<24}{record.get('harness', '-'):<10}{str(record.get('model') or '-'):<18}"
              f"{summary['task']:<11}{str(summary['mean_iou']):>6}{str(summary['mean_distance']):>7}"
              f"{f"{summary['compatible']}/{summary['scored']}":>8}{str(record.get('seconds', '-')):>9}"
              f"{'-' if cost_usd is None else f'{cost_usd:.2f}':>8}")
