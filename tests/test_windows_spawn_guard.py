from __future__ import annotations

import os
import subprocess
import sys

from dtwin.benchmark.windows_spawn_guard import block_optional_module_for_spawn


def test_spawn_guard_blocks_only_child_and_restores_environment():
    old_pythonpath = os.environ.get("PYTHONPATH")
    old_no_bytecode = os.environ.get("PYTHONDONTWRITEBYTECODE")
    with block_optional_module_for_spawn("pyarrow", enabled=True) as active:
        assert active is True
        child = subprocess.run(
            [sys.executable, "-c", "import pyarrow"],
            text=True, capture_output=True, check=False,
        )
        assert child.returncode != 0
        assert "disabled in ARGOS Windows spawn worker" in child.stderr
        # The current interpreter was not modified by sitecustomize.
        __import__("pyarrow")
    assert os.environ.get("PYTHONPATH") == old_pythonpath
    assert os.environ.get("PYTHONDONTWRITEBYTECODE") == old_no_bytecode


def test_spawn_guard_restores_environment_after_exception():
    old_pythonpath = os.environ.get("PYTHONPATH")
    try:
        with block_optional_module_for_spawn("pyarrow", enabled=True):
            raise RuntimeError("forced")
    except RuntimeError:
        pass
    assert os.environ.get("PYTHONPATH") == old_pythonpath
