"""Three native editable text components with canonical request rendering."""
from dataclasses import dataclass,replace
from hashlib import sha256
import json
from ..protocol import ProtocolViolation as SearchContractError
BLOCKS=("role","strategy","answer")

@dataclass(frozen=True)
class SystemPrompt:
    role: str
    strategy: str
    answer: str

    def __post_init__(self):
        if any(not isinstance(getattr(self,key),str) for key in BLOCKS):
            raise SearchContractError('SYSTEM_PROMPT_BLOCK_TYPE_INVALID')

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != set(BLOCKS):
            raise SearchContractError('SYSTEM_PROMPT_SCHEMA_INVALID')
        return cls(**value)

    def to_dict(self):
        return {key: getattr(self, key) for key in BLOCKS}

    def serialize(self):
        return json.dumps(self.to_dict(), ensure_ascii=True, separators=(',', ':'))

    def encode(self, encoding='utf-8'):
        """Existing hash ports consume canonical structured bytes, never rendered text."""
        return self.serialize().encode(encoding)

    def render(self):
        return '\n\n'.join(getattr(self, key) for key in BLOCKS)

    @property
    def prompt_hash(self):
        return sha256(self.encode()).hexdigest()

    @property
    def system_hash(self):
        return sha256(self.render().encode()).hexdigest()

    def block_hash(self, block):
        if block not in BLOCKS:
            raise SearchContractError('SYSTEM_PROMPT_TARGET_BLOCK_INVALID')
        return sha256(getattr(self, block).encode()).hexdigest()

    def edit(self, block, content):
        if block not in BLOCKS:
            raise SearchContractError('SYSTEM_PROMPT_TARGET_BLOCK_INVALID')
        return replace(self, **{block: content})


def require_prompt(value):
    if not isinstance(value, SystemPrompt):
        raise SearchContractError('STRUCTURED_SYSTEM_PROMPT_REQUIRED')
    return value


def solver_messages(prompt, problem):
    require_prompt(prompt)
    if not isinstance(problem, str):
        raise SearchContractError('SOLVER_PROBLEM_TEXT_REQUIRED')
    return [dict(role='system', content=prompt.render()), dict(role='user', content=problem)]
