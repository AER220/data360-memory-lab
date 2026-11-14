"""Regenerate lab/starter/memory_lab.py from lab/solutions/memory_lab.py.

Every block between '# BEGIN SOLUTION' and '# END SOLUTION' becomes a NotImplementedError,
so starter and solutions can never drift apart.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "lab/solutions/memory_lab.py").read_text()
pattern = re.compile(r"(?P<indent>[ \t]*)# BEGIN SOLUTION\n.*?# END SOLUTION\n", re.S)
count = 0


def repl(m):
    global count
    count += 1
    ind = m.group("indent")
    return f'{ind}# YOUR CODE HERE (see the TODO above)\n{ind}raise NotImplementedError("TODO: implement this function")\n'


out = pattern.sub(repl, src)
(ROOT / "lab/starter/memory_lab.py").write_text(out)
print(f"starter written with {count} TODO blocks")
