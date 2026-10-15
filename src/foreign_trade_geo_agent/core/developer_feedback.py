"""Non-authorizing local developer feedback, separate from trusted reviews."""
from dataclasses import dataclass
import re

from .history import validate_uuid

FEEDBACK_KIND = 'LOCAL_DEVELOPER_FEEDBACK'


@dataclass(frozen=True, slots=True)
class FeedbackBinding:
    database: str
    run_id: str
    object_id: str
    version: int
    digest: str

    def __post_init__(self):
        if self.database not in {'candidate', 'live'}:
            raise ValueError('Unknown history source')
        validate_uuid(self.run_id, 'run_id')
        if self.object_id != 'run':
            validate_uuid(self.object_id, 'object_id')
        if type(self.version) is not int or not 1 <= self.version <= 1000:
            raise ValueError('Invalid version')
        if not re.fullmatch(r'[0-9a-f]{64}', self.digest):
            raise ValueError('Invalid digest')


def validate_feedback(note, marked_text, disposition):
    if disposition not in {'observation', 'needs_revision'}:
        raise ValueError('Feedback cannot approve or authorize')
    for text in (note, marked_text):
        if type(text) is not str or len(text) > 2000 or any(ord(c) < 32 and c not in '\n\r\t' for c in text):
            raise ValueError('Invalid feedback text')
    if not note.strip():
        raise ValueError('Opinion is required')
