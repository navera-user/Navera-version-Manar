#!/usr/bin/env python3
"""trace_matrix.py — the NAVERA traceability matrix, generated from the repository so it stays current.

    python3 navera_tools/trace_matrix.py                 # writes docs/certification/TRACEABILITY.md
    python3 navera_tools/trace_matrix.py --check         # verify only (no write); exit 1 on a broken link
    python3 navera_tools/trace_matrix.py --stdout        # print instead of writing
    python3 navera_tools/trace_matrix.py --json out.json # machine-readable copy

It writes two pages: docs/certification/REQUIREMENTS.md (the requirements by category, status,
strongest evidence) and docs/certification/TRACEABILITY.md (the matrix).

Inputs (no ROS, no build needed — files are only parsed, never imported or run):

  docs/certification/requirements.yaml   the requirements: id, text, code references
                                         (path::Symbol), explicit tests (path::test), test
                                         patterns (regular expressions), evidence (level, value,
                                         where it is written down)
  the tests of the repository            */test/test_*.py (ament linters excluded), every script
                                         of navera_tools/tests/, and the deployment checks listed
                                         in requirements.yaml (extra_tests)

A "test unit" is a pytest function (test_*: its name + docstring) or, for a script test without
test functions (the integration / SITL scripts), the whole script: its module docstring + the
failure labels it can print (strings passed to failures.append / fail / print("FAIL ...")).
A requirement is traced to every test unit one of its patterns matches (case-insensitive, on
"path::name" + the text above) and to its explicit tests. So a new test that is named or
documented after what it checks joins the matrix without editing anything.

Code references are checked: the file must exist and the symbol (function, class, Class.method,
module-level name, shell function) must be defined in it. A broken reference or a missing
explicit test is reported (--check: exit 1). Requirements with no test unit are listed.
"""
import argparse
import ast
import datetime
import glob
import json
import os
import re
import subprocess
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO, 'docs', 'certification', 'requirements.yaml')
OUTPUT = os.path.join(REPO, 'docs', 'certification', 'TRACEABILITY.md')
REQ_OUTPUT = os.path.join(REPO, 'docs', 'certification', 'REQUIREMENTS.md')
SKIP_DIRS = ('build', 'install', 'log', 'archive', 'vision_pkg', '.claude', '.git')
LINTERS = re.compile(r'test_(flake8|pep257|copyright)(_[a-z0-9_]+)?\.py$')
LEVELS = ['A', 'UT', 'SIM', 'BENCH', 'PUB', 'HW', 'FLT']   # weakest -> strongest


# ----------------------------------------------------------------------------- tests

def _strings(node):
    """Constant text of a string / f-string expression (f-string holes dropped)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp):
        return _strings(node.left) + _strings(node.right)
    return ''


def _failure_labels(tree):
    """Labels a script test prints or records when a check fails."""
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not n.args:
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else '')
        text = _strings(n.args[0])
        if not text:
            continue
        if name in ('append', 'fail', 'check', 'expect', 'ok', 'report') and (
                name != 'append' or (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                                     and 'fail' in f.value.id.lower())):
            out.append(text)
        elif name == 'print' and text.lstrip().upper().startswith(('FAIL', 'PASS', 'OK ')):
            out.append(text)
    return out


def _kind(rel):
    """unit / integration / sitl / deploy, from where the test lives."""
    if rel.startswith('deploy/'):
        return 'deploy'
    if rel.startswith('navera_tools/tests/'):
        return 'sitl' if os.path.basename(rel).startswith(('sitl_', 'star_camera')) else 'integration'
    return 'unit'


def _ignored_pkg(rel):
    top = rel.split('/')[0]
    return (top in SKIP_DIRS or top.startswith('isaac_')
            or os.path.exists(os.path.join(REPO, top, 'COLCON_IGNORE')))


def collect_tests(extra):
    """Return [{id, file, name, kind, text}] for every test unit of the repository."""
    files = set()
    for p in glob.glob(os.path.join(REPO, '*', 'test', 'test_*.py')):
        rel = os.path.relpath(p, REPO)
        if not LINTERS.search(rel) and not _ignored_pkg(rel):
            files.add(rel)
    for p in glob.glob(os.path.join(REPO, 'navera_tools', 'tests', '*.py')):
        rel = os.path.relpath(p, REPO)
        if not os.path.basename(rel).startswith('_'):
            files.add(rel)
    files.update(e for e in extra if os.path.isfile(os.path.join(REPO, e)))
    units = []
    for rel in sorted(files):
        path = os.path.join(REPO, rel)
        kind = _kind(rel)
        if rel.endswith('.sh'):
            head = []
            for line in open(path, encoding='utf-8', errors='replace'):
                if line.startswith('#'):
                    head.append(line.lstrip('#').strip())
                elif head and not line.strip().startswith('#'):
                    break
            units.append(dict(id=f'{rel}::<script>', file=rel, name='<script>', kind=kind, text='\n'.join(head)))
            continue
        try:
            tree = ast.parse(open(path, encoding='utf-8').read(), filename=rel)
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f'warning: cannot parse {rel}: {e}', file=sys.stderr)
            continue
        found = []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test_'):
                found.append((n.name, ast.get_docstring(n) or ''))
            elif isinstance(n, ast.ClassDef) and n.name.startswith('Test'):
                for m in n.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith('test_'):
                        found.append((f'{n.name}.{m.name}', ast.get_docstring(m) or ''))
        if found:
            for name, doc in found:
                units.append(dict(id=f'{rel}::{name}', file=rel, name=name, kind=kind,
                                  text=name.replace('_', ' ') + '\n' + doc))
        else:
            text = (ast.get_docstring(tree) or '') + '\n' + '\n'.join(_failure_labels(tree))
            units.append(dict(id=f'{rel}::<script>', file=rel, name='<script>', kind=kind, text=text))
    return units


# ----------------------------------------------------------------------------- code references

_defs_cache = {}


def _definitions(rel):
    """Names defined in a file: functions, classes, Class.method, module names, shell functions."""
    if rel in _defs_cache:
        return _defs_cache[rel]
    path = os.path.join(REPO, rel)
    names = set()
    if rel.endswith('.py'):
        try:
            tree = ast.parse(open(path, encoding='utf-8').read())
        except SyntaxError:
            tree = None
        if tree is not None:
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(n.name)
                    if isinstance(n, ast.ClassDef):
                        for m in n.body:
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                names.add(f'{n.name}.{m.name}')
                elif isinstance(n, (ast.Assign, ast.AnnAssign)):
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                        if isinstance(t, ast.Name):
                            names.add(t.id)
    else:
        text = open(path, encoding='utf-8', errors='replace').read()
        names.update(re.findall(r'^\s*([A-Za-z_][\w-]*)\s*\(\)\s*\{', text, re.M))       # shell functions
        names.update(re.findall(r'^([A-Za-z_][\w-]*)=', text, re.M))                       # KEY= lines
        names.update(re.findall(r'^\[?([A-Za-z][\w]*)\]?$', text, re.M))                   # [Section]
    _defs_cache[rel] = names
    return names


def check_code_ref(ref):
    """Return None when `path[::Symbol]` resolves, else the reason."""
    rel, _, sym = ref.partition('::')
    if not os.path.isfile(os.path.join(REPO, rel)):
        return f'file not found: {rel}'
    if not sym:
        return None
    if sym in _definitions(rel):
        return None
    text = open(os.path.join(REPO, rel), encoding='utf-8', errors='replace').read()
    if not rel.endswith('.py') and re.search(r'(^|\W)' + re.escape(sym) + r'(\W|$)', text):
        return None                                   # a key / option named in a unit or script
    return f'symbol not defined: {sym} in {rel}'


# ----------------------------------------------------------------------------- matrix

def build(cfg, tests):
    """Trace every requirement; return (rows, broken links, untraced tests)."""
    by_id = {t['id']: t for t in tests}
    by_file_script = {t['file']: t for t in tests if t['name'] == '<script>'}
    traced = set()
    rows, broken = [], []
    for r in cfg['requirements']:
        rid = r['id']
        code_bad = []
        for c in r.get('code', []) or []:
            why = check_code_ref(c)
            if why:
                code_bad.append(c)
                broken.append((rid, 'code', c, why))
        hits = {}
        for t in r.get('tests', []) or []:
            tid = t if '::' in t else t + '::<script>'
            unit = by_id.get(tid) or (by_file_script.get(t) if '::' not in t else None)
            if unit is None:
                broken.append((rid, 'test', t, 'test not found'))
            else:
                hits[unit['id']] = unit
        for pat in r.get('match', []) or []:
            rx = re.compile(pat, re.I | re.S)
            for u in tests:
                if rx.search(u['id'] + '\n' + u['text']):
                    hits[u['id']] = u
        traced.update(hits)
        ev = r.get('evidence', []) or []
        # evidence marked `against: true` (a test that failed, a gap found) never raises the level
        levels = [e.get('level') for e in ev if e.get('level') in LEVELS and not e.get('against')]
        if hits and 'UT' not in levels:
            levels.append('UT')
        best = max(levels, key=LEVELS.index) if levels else None
        rows.append(dict(id=rid, title=r.get('title', ''), category=r.get('category', ''), text=r.get('text', ''),
                         code=r.get('code', []) or [], code_bad=code_bad,
                         tests=sorted(hits.values(), key=lambda u: u['id']), evidence=ev, best=best,
                         status=r.get('status', ''), note=r.get('note', '')))
    untraced = [t for t in tests if t['id'] not in traced]
    return rows, broken, untraced


def _git(*args):
    try:
        return subprocess.run(['git', '-C', REPO] + list(args), capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ''


def _cell(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


def render(cfg, rows, broken, untraced, tests):
    """The Markdown page."""
    commit = _git('rev-parse', '--short', 'HEAD') or 'unknown'
    generated = ('docs/certification/TRACEABILITY.md', 'docs/certification/REQUIREMENTS.md')
    dirty = ' (+ uncommitted changes)' if any(
        ln[3:] not in generated for ln in _git('status', '--porcelain').splitlines()) else ''
    cats = cfg.get('categories', {})
    lv = cfg.get('levels', {})
    no_test = [r for r in rows if not r['tests']]
    kinds = {}
    for t in tests:
        kinds[t['kind']] = kinds.get(t['kind'], 0) + 1
    out = []
    w = out.append
    w('# NAVERA — Traceability matrix (generated)')
    w('')
    w(f'Generated by `navera_tools/trace_matrix.py` from `docs/certification/requirements.yaml` and the '
      f'tests of the repository at commit `{commit}`{dirty}, {datetime.date.today().isoformat()}. '
      '**Do not edit by hand**: edit the requirements file or the tests, then run the script.')
    w('')
    w('## Summary')
    w('')
    w(f'- Requirements: **{len(rows)}**; with at least one automated test: **{len(rows) - len(no_test)}**; '
      f'**without any test: {len(no_test)}** (listed below).')
    w(f'- Test units found: {len(tests)} (' + ', '.join(f'{k} {v}' for k, v in sorted(kinds.items())) +
      f'); not traced to any requirement: {len(untraced)}.')
    w(f'- Broken links (code symbol or explicit test not found): **{len(broken)}**.')
    best = {}
    for r in rows:
        best[r['best'] or '—'] = best.get(r['best'] or '—', 0) + 1
    w('- Strongest evidence per requirement: ' + ', '.join(
        f'{k} {best[k]}' for k in LEVELS + ['—'] if k in best) + '.')
    w('')
    w('Evidence levels (weakest to strongest): ' + '; '.join(f'**{k}** {lv.get(k, "")}' for k in LEVELS) + '.')
    w('A test unit is software evidence (UT); it never stands for a flight. No requirement has FLT evidence: '
      'NAVERA has not flown.')
    w('')
    w('## Requirements without any automated test')
    w('')
    if no_test:
        w('| ID | Requirement | Strongest evidence | Note |')
        w('|---|---|---|---|')
        for r in no_test:
            w(f"| {r['id']} | {_cell(r['title'])} | {r['best'] or '—'} | {_cell(r['note'] or r['status'])} |")
    else:
        w('None.')
    w('')
    if broken:
        w('## Broken links')
        w('')
        w('| Requirement | Kind | Reference | Problem |')
        w('|---|---|---|---|')
        for rid, kind, ref, why in broken:
            w(f'| {rid} | {kind} | `{_cell(ref)}` | {_cell(why)} |')
        w('')
    w('## Matrix')
    w('')
    for cat in cats or sorted({r['category'] for r in rows}):
        sub = [r for r in rows if r['category'] == cat]
        if not sub:
            continue
        w(f'### {cats.get(cat, cat)}')
        w('')
        w('| ID | Requirement | Code | Tests | Evidence | Level |')
        w('|---|---|---|---|---|---|')
        for r in sub:
            code = '<br>'.join(f'`{_cell(c)}`' + (' ⚠ not found' if c in r['code_bad'] else '')
                               for c in r['code']) or '—'
            if r['tests']:
                shown = r['tests'][:3]
                tcell = f"**{len(r['tests'])}**: " + '<br>'.join(f"`{_cell(t['id'])}`" for t in shown)
                if len(r['tests']) > 3:
                    tcell += f"<br>+{len(r['tests']) - 3} more (details below)"
            else:
                tcell = '**none**'
            ev = '<br>'.join(f"{e.get('level', '?')}{' (against)' if e.get('against') else ''}: "
                             f"{_cell(e.get('value', ''))}"
                             + (f" ({_cell(e['ref'])})" if e.get('ref') else '') for e in r['evidence']) or '—'
            w(f"| {r['id']} | **{_cell(r['title'])}** — {_cell(r['text'])} | {code} | {tcell} | {ev} | "
              f"{r['best'] or '—'} |")
        w('')
    w('## Tests per requirement (complete)')
    w('')
    for r in rows:
        if len(r['tests']) <= 3:
            continue
        w(f"<details><summary>{r['id']} — {len(r['tests'])} test units</summary>")
        w('')
        for t in r['tests']:
            w(f"- `{t['id']}` ({t['kind']})")
        w('')
        w('</details>')
        w('')
    w('## Test units not traced to a requirement')
    w('')
    w('Mostly field / bench tooling tests (navera_tools/field, camera drivers of the field kit) and '
      'helpers below requirement level. Per file:')
    w('')
    per = {}
    for t in untraced:
        per[t['file']] = per.get(t['file'], 0) + 1
    w('| File | Untraced units |')
    w('|---|---|')
    for f, n in sorted(per.items()):
        w(f'| `{f}` | {n} |')
    w('')
    return '\n'.join(out)


def render_requirements(cfg, rows):
    """The requirements page: every requirement by category with its status and evidence level."""
    commit = _git('rev-parse', '--short', 'HEAD') or 'unknown'
    cats = cfg.get('categories', {})
    lv = cfg.get('levels', {})
    out = []
    w = out.append
    w('# NAVERA — System requirements (generated)')
    w('')
    w(f'Generated by `navera_tools/trace_matrix.py` from `docs/certification/requirements.yaml` '
      f'(commit `{commit}`, {datetime.date.today().isoformat()}). Edit the YAML, not this page. '
      'Performance requirements state **measured** numbers only, with the data they were measured on; '
      'where no target is agreed yet the requirement says so. Trace to code and tests: '
      '[TRACEABILITY.md](TRACEABILITY.md).')
    w('')
    w('Evidence levels: ' + '; '.join(f'**{k}** {lv.get(k, "")}' for k in LEVELS) + '.')
    w('')
    status = {}
    for r in rows:
        status[r['status'] or '—'] = status.get(r['status'] or '—', 0) + 1
    w('Status count: ' + ', '.join(f'{k} {v}' for k, v in sorted(status.items())) + '.')
    w('')
    for cat in cats or sorted({r['category'] for r in rows}):
        sub = [r for r in rows if r['category'] == cat]
        if not sub:
            continue
        w(f'## {cats.get(cat, cat)}')
        w('')
        w('| ID | Requirement | Status | Strongest evidence | Tests | Note |')
        w('|---|---|---|---|---|---|')
        for r in sub:
            w(f"| {r['id']} | **{_cell(r['title'])}** — {_cell(r['text'])} | {_cell(r['status'])} | "
              f"{r['best'] or '—'} | {len(r['tests']) or '**0**'} | {_cell(r['note'])} |")
        w('')
    return '\n'.join(out)


def main(argv=None):
    """Generate the matrix; return 1 with --check when a link is broken."""
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--config', default=CONFIG)
    ap.add_argument('--out', default=OUTPUT)
    ap.add_argument('--req-out', default=REQ_OUTPUT)
    ap.add_argument('--stdout', action='store_true', help='print the page instead of writing it')
    ap.add_argument('--json', help='also write the matrix as JSON here')
    ap.add_argument('--check', action='store_true', help='exit 1 when a code reference or test is broken')
    args = ap.parse_args(argv)
    with open(args.config, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    tests = collect_tests(cfg.get('extra_tests', []) or [])
    rows, broken, untraced = build(cfg, tests)
    page = render(cfg, rows, broken, untraced, tests)
    if args.stdout:
        print(page)
    elif not args.check:                      # --check only verifies: it never rewrites the pages
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(page + '\n')
        with open(args.req_out, 'w', encoding='utf-8') as f:
            f.write(render_requirements(cfg, rows) + '\n')
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as f:
            json.dump(dict(requirements=[dict(r, tests=[t['id'] for t in r['tests']]) for r in rows],
                           broken=broken, untraced=[t['id'] for t in untraced]), f, indent=1)
    no_test = [r['id'] for r in rows if not r['tests']]
    print(f'{len(rows)} requirements, {len(tests)} test units, {len(no_test)} requirement(s) without a test'
          + (f": {', '.join(no_test)}" if no_test else '') + f'; {len(broken)} broken link(s)', file=sys.stderr)
    for rid, kind, ref, why in broken:
        print(f'  BROKEN {rid} {kind} {ref}: {why}', file=sys.stderr)
    return 1 if (args.check and broken) else 0


if __name__ == '__main__':
    sys.exit(main())
