"""TEST ONLY prompt candidate; no live execution entry point."""
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
A3 = OUT.parent / 'real-llm-draft-phase7a3'
spec = importlib.util.spec_from_file_location('phase7a3_frozen_prompt', A3 / 'prompt.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
previous = base.previous
PREVIOUS = base.PREVIOUS  # Compatibility for the unchanged A.3 regression suite.

JSON_ESCAPING = r'''

JSON STRING ESCAPING REQUIREMENT:

The output must be valid JSON.

The article field value is a JSON string.

Escape all newline characters inside the article string as \n.

Do not output literal line breaks inside JSON string values.

Do not use markdown code fences.

Do not prepend explanations.

Return exactly:

{
  "article": "..."
}
'''
BOUNDARY = base.BOUNDARY + JSON_ESCAPING
SYSTEM = base.SYSTEM + JSON_ESCAPING


def messages():
    """Append only the escaping instruction to the saved A.3 system message."""
    frozen = previous.phase2.strict((A3 / 'prompt.json').read_bytes())
    if frozen[0] != dict(role='system', content=base.SYSTEM):
        raise ValueError('P7A5_A3_PROMPT_DRIFT')
    return [dict(role='system', content=SYSTEM), frozen[1]]
