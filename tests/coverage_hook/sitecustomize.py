"""Start coverage inside subprocesses spawned by the tests.

The interactive tests drive a real ``python -m dtcalc`` child through a pty.
Coverage only sees a child if it starts measuring before the child imports
anything, which is what ``COVERAGE_PROCESS_START`` plus this hook arranges.

Without it ``repl.py`` measures at 56% and looks barely tested, when it is in
fact driven end to end -- the lines simply run in a process nobody was
watching. This directory is put on ``PYTHONPATH`` by the coverage make
targets and by nothing else, so it cannot shadow anything during a normal
test run.
"""

from __future__ import annotations

import os

if os.environ.get("COVERAGE_PROCESS_START"):
    import coverage

    coverage.process_startup()
