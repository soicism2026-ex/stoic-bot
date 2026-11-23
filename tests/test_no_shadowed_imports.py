"""A function must not re-import a module that the file already imports at top level.

`import x` anywhere inside a function makes `x` a local name for the WHOLE
function, so any earlier use of the module-level `x` raises UnboundLocalError.
On 2026-11-22 a stray `import airday` deep in daily_post.main() crashed every
run at its first use of `airday` (line ~663): no post for ~29 hours.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted(list((ROOT / "scripts").glob("*.py")) + list((ROOT / "src").glob("*.py")))


def _bound(node):
    return [(a.asname or a.name).split(".")[0] for a in node.names]


def _shadowed(path):
    tree = ast.parse(path.read_text())
    top = set()
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            top.update(_bound(n))
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for n in ast.walk(fn):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for name in _bound(n):
                    if name in top:
                        bad.append((fn.name, name, n.lineno))
    return bad


def test_no_function_reimports_a_module_level_name():
    problems = {p.name: _shadowed(p) for p in FILES}
    problems = {k: v for k, v in problems.items() if v}
    assert not problems, problems
