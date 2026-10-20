"""TEST ONLY composition-boundary prompt; no live sender or runtime integration."""
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
A5 = OUT.parent / 'real-llm-draft-phase7a5'
spec = importlib.util.spec_from_file_location('phase7a5_frozen_prompt', A5 / 'prompt.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
previous = base.previous

COMPOSITION = '''

EVIDENCE COMPOSITION RULE:

Do not calculate, count, aggregate, summarize or infer quantities from evidence items.

Do not introduce:
- numbers
- spelled-out quantities
- totals
- counts
- collection claims

unless the exact quantity is explicitly supported by an admitted claim.

Multiple evidence records do not imply:
- multiple products
- multiple configurations
- all products
- complete coverage
- every case

Describe each supported item individually when needed.
'''
SYSTEM = base.SYSTEM + COMPOSITION


def messages():
    """Preserve the saved A.5 user message; append only the requested rule."""
    frozen = previous.phase2.strict((A5 / 'prompt.json').read_bytes())
    if frozen[0] != dict(role='system', content=base.SYSTEM):
        raise ValueError('P7A6_A5_PROMPT_DRIFT')
    return [dict(role='system', content=SYSTEM), frozen[1]]
