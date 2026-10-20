"""Build isolated TEST-only packages without resealing historical experiments."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
from unittest.mock import patch

from scripts import prepare_minimal_writer_flash_preflight as pf


@contextmanager
def isolated_flash_package():
    sources = pf.read_sources()
    codes = pf.code_bindings()
    criteria = (pf.DEST / 'success-criteria.md').read_bytes()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        frozen = root / 'preflight'
        frozen.mkdir()
        with (patch.object(pf, 'DEST', frozen),
              patch.object(pf, 'RESULTS', str(root / 'results'))):
            files = pf.build_bundle(sources, codes, criteria)
            for name, body in files.items():
                (frozen / name).write_bytes(body)
            (frozen / 'report.md').write_text('Isolated offline unit-test package.', encoding='utf-8')
            yield pf.sha(files['manifest.json'])
