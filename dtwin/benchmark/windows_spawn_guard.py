"""Runtime guards for optional packages that break Windows spawn workers."""
from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PYARROW_GUARD_ID = "pyarrow_blocked_for_windows_spawn_v1"


@contextmanager
def block_optional_module_for_spawn(
    module_name: str,
    *,
    enabled: bool | None = None,
) -> Iterator[bool]:
    """Block an optional module only in newly spawned Python interpreters.

    On Windows, multiprocessing ``spawn`` starts a fresh interpreter. A
    temporary ``sitecustomize`` on ``PYTHONPATH`` installs an import blocker in
    those children, while leaving the current interpreter and site-packages
    untouched. Environment variables and the temporary directory are restored
    in ``finally``.
    """

    active = os.name == "nt" if enabled is None else bool(enabled)
    if not active:
        yield False
        return
    name = str(module_name).strip()
    if not name or not name.replace("_", "a").isalnum():
        raise ValueError("module_name deve ser um modulo Python simples.")
    temporary = Path(tempfile.mkdtemp(prefix="argos-spawn-guard-"))
    old_pythonpath = os.environ.get("PYTHONPATH")
    old_no_bytecode = os.environ.get("PYTHONDONTWRITEBYTECODE")
    code = f'''# Generated temporarily by ARGOS; removed after the guarded stage.\nimport importlib.abc\nimport sys\n\nclass _ArgosOptionalModuleBlocker(importlib.abc.MetaPathFinder):\n    def find_spec(self, fullname, path=None, target=None):\n        if fullname == {name!r} or fullname.startswith({name!r} + "."):\n            raise ModuleNotFoundError("{name} disabled in ARGOS Windows spawn worker")\n        return None\n\nsys.meta_path.insert(0, _ArgosOptionalModuleBlocker())\n'''
    try:
        (temporary / "sitecustomize.py").write_text(code, encoding="utf-8")
        os.environ["PYTHONPATH"] = (
            str(temporary) if not old_pythonpath
            else str(temporary) + os.pathsep + old_pythonpath
        )
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        yield True
    finally:
        if old_pythonpath is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = old_pythonpath
        if old_no_bytecode is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = old_no_bytecode
        shutil.rmtree(temporary, ignore_errors=True)
