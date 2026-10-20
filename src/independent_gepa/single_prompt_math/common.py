"""Small durable identity helpers for the separate single-Prompt experiment."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from ..protocol import ProtocolViolation


class Abort(BaseException):
    """Operational failures must escape GEPA's ordinary proposer handlers."""


@dataclass(frozen=True)
class ParsedOutput:
    answer: str
    valid: bool


def progress(message: str) -> None:
    """Console progress is optional; durable scientific evidence is not."""
    try:print(message,flush=True)
    except OSError:pass
    except ValueError:
        import sys
        if not getattr(sys.stdout,'closed',False):raise


def canonical(value: Any) -> bytes:
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())


def write(path: Path,value: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.pending')
    with temporary.open('wb') as stream:
        stream.write(canonical(value)+b'\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def git(root: Path,*args: str) -> str:
    return subprocess.check_output(['git',*args],cwd=root,text=True,encoding='utf-8').strip()


def source_inventory(root: Path) -> dict[str,str]:
    paths=[*root.joinpath('src').rglob('*.py'),*root.joinpath('scripts').glob('*.py'),
           *root.joinpath('tests').rglob('*.py'),root/'AGENTS.md',root/'pyproject.toml',
           root/'configs/gepa_single_prompt_math_seed42_repeat3.yaml',
           root/'configs/gepa_single_prompt_math_v6.yaml',root/'configs/gepa_single_prompt_posthoc_v6.yaml',
           root/'configs/gepa_single_prompt_scoring_continuation_v7.yaml',root/'docs/gepa_single_prompt_scoring_continuation_v7.md',
           root/'docs/gepa_single_prompt_math_v6.md',root/'docs/gepa_single_prompt_compute_v6.md',
           root/'docs/gepa_single_prompt_analysis_v6.md',
           root/'docs/gepa_single_prompt_math_v1.md',
           root/'docs/gepa_single_prompt_semantic_review_v2.md',
           root/'docs/gepa_single_prompt_recovery_v3.md',
           root/'docs/gepa_single_prompt_native_guard_v4.md',
           root/'docs/gepa_single_prompt_scoring_continuation_v5.md',
           root/'configs/gepa_single_prompt_scoring_continuation_v5.yaml',
           root/'experiments/protocols/gepa_single_prompt_math_seed42_repeat3_v4/copied_scoring_sources.json']
    return {p.relative_to(root).as_posix():file_hash(p) for p in sorted(paths)}


def require_private(root: Path,path: Path,parent: str='runs') -> Path:
    path=path.resolve()
    if not path.is_relative_to((root/parent).resolve()):
        raise ProtocolViolation('PRIVATE_EXPERIMENT_PATH_REQUIRED')
    return path
