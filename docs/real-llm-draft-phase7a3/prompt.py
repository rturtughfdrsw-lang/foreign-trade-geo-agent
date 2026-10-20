"""TEST ONLY prompt candidate. No transport, credentials or execution entry point."""
import importlib.util
import json
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
PREVIOUS = OUT.parent / 'real-llm-draft-phase7a2'
sys.dont_write_bytecode = True
sys.path.insert(0, str(PREVIOUS))
spec = importlib.util.spec_from_file_location('phase7a2_experiment', PREVIOUS / 'experiment.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)

BOUNDARY = '''

INTERNAL METADATA / READER-FACING ARTICLE BOUNDARY:
Internal metadata is only for controlling generation behavior.
Internal metadata MUST NEVER appear in the article.
This applies wherever metadata occurs: source headers, evidence context/locators, record policy_constraints, origin, review_status, experiment labels and authorization fields. Use these only as generation constraints; never quote, paraphrase, translate or explain their workflow meaning to readers. A requirement to preserve evidence meaning does not authorize copying its control metadata.
Forbidden reader-facing terms include: test-only; production authorization; admission; evidence gate; gate status; approval status; internal validation; experiment status; authorization state. Also do not emit their underscore/space variants, status values such as READY from admission_status=READY, production authorization=false, or internal validation metadata. Do not restate them as disclaimers, scenario notices, headings, introductions or conclusions.
The output article must be suitable for publication on a real customer website in its language, structure and editorial quality. It must contain only evidence-supported claims, allowed scope information and normal SEO content. This quality requirement grants no factual, semantic, production or publication authorization. With the supplied synthetic evidence, retain the explicit fictional scenario notice and all factual applicability limits; never portray this scenario as a real customer or manufacturer endorsement. Express that notice in ordinary reader language without internal metadata.
The article must not discuss system workflow, model execution, validation process or experiment environment. Keep unresolved buyer questions and prospective documentation requests: they describe the buyer's technical decision, not the system's internal validation. Do not remove evidence-supported manufacturing details merely because they contain ordinary words such as internal handover. Return only the existing article JSON contract; do not add a metadata section or fields.
'''
SYSTEM = previous.SYSTEM + BOUNDARY


def messages():
    """Keep the frozen user message byte-for-byte; change only system instructions."""
    original = json.loads((PREVIOUS / 'prompt.json').read_text(encoding='utf-8'))
    return [dict(role='system', content=SYSTEM), original[1]]
