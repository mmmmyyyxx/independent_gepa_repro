"""Spawn-safe replacement of process transport, never of a scoring rule.

The author's nested multiprocessing target cannot be pickled on Windows. Load
the same trusted AMPS source in the child and call the same named function.
Drain IPC while the child runs to avoid the original join-before-read deadlock.
"""
from __future__ import annotations

import importlib.util
import multiprocessing
from multiprocessing.connection import wait
from pathlib import Path
import sys
import time
import types

from .control import OperationalHalt


def load_livebench_sources(artifact: Path):
    """Load only original scorer files, avoiding dataset/program import effects."""
    base = artifact / "gepa_artifact/benchmarks/livebench_math/livebenchmath_utils"
    prefix = "_gepa_paper_livebench"
    for suffix, path in [("", base), (".AMPS_Hard", base / "AMPS_Hard"),
                         (".math_competitions", base / "math_competitions"),
                         (".olympiad", base / "olympiad")]:
        name = prefix + suffix
        old = sys.modules.get(name)
        if old and list(old.__path__) != [str(path)]:
            raise ValueError("LIVEBENCH_MODULE_SOURCE_CONFLICT")
        if not old:
            package = types.ModuleType(name)
            package.__path__ = [str(path)]
            sys.modules[name] = package
    modules = {}
    for name, rel in [("util", "util.py"), ("AMPS_Hard.utils", "AMPS_Hard/utils.py"),
                      ("math_competitions.utils", "math_competitions/utils.py"),
                      ("olympiad.utils", "olympiad/utils.py"), ("metric", "metric.py")]:
        full = prefix + "." + name
        if full in sys.modules:
            modules[name] = sys.modules[full]
            continue
        spec = importlib.util.spec_from_file_location(full, base / rel)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


def _child(connection, artifact: str, function: str, args: tuple) -> None:
    try:
        module = load_livebench_sources(Path(artifact))["AMPS_Hard.utils"]
        connection.send(("ok", getattr(module, function)(*args)))
    except BaseException as exc:
        try:
            connection.send(("error", exc))
        except Exception:
            connection.send(("error", RuntimeError(type(exc).__name__)))
    finally:
        connection.close()


def run_with_timeout(artifact: Path, function: str, args=(), timeout=8):
    if function != "is_equiv":
        raise ValueError("ONLY_AUTHOR_AMPS_EQUIVALENCE_IS_ALLOWED")
    ctx = multiprocessing.get_context("spawn")
    read, write = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(write, str(artifact.resolve()), function, args))
    process.start()
    write.close()
    deadline = time.monotonic() + timeout
    try:
        ready = wait([read, process.sentinel], timeout=max(0, deadline - time.monotonic()))
        if read in ready:
            try:
                kind, value = read.recv()
            except EOFError as exc:
                raise OperationalHalt("AUTHOR_SCORER_WORKER_EOF") from exc
            if kind == "error":
                raise value
            return value
        if process.sentinel in ready:
            raise OperationalHalt("AUTHOR_SCORER_WORKER_EXITED_WITHOUT_RESULT")
        raise TimeoutError("Operation timed out")
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
        read.close()
        process.close()


def install(artifact: Path, author_module=None):
    modules = load_livebench_sources(artifact) if author_module is None else None
    module = modules["AMPS_Hard.utils"] if modules is not None else author_module
    expected = artifact / "gepa_artifact/benchmarks/livebench_math/livebenchmath_utils/AMPS_Hard/utils.py"
    if Path(module.__file__).resolve() != expected.resolve():
        raise ValueError("AUTHOR_AMPS_MODULE_SOURCE_MISMATCH")
    def transport(func, args=(), timeout=8):
        if func is not module.is_equiv:
            raise ValueError("AUTHOR_FUNCTION_IDENTITY_MISMATCH")
        return run_with_timeout(artifact, "is_equiv", args, timeout)
    module.run_with_timeout = transport
    return modules if modules is not None else module
