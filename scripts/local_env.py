"""Load selected API keys from the project-local ``.env`` file."""

import os
from pathlib import Path

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_api_keys(
    *names: str,
    project_root: Path | None = None,
) -> None:
    """Load only ``names`` without replacing existing environment values."""

    root = PROJECT_ROOT if project_root is None else project_root
    env_path = root / ".env"
    if not env_path.is_file():
        return

    values = dotenv_values(env_path)
    for name in names:
        value = values.get(name)
        if value is not None:
            os.environ.setdefault(name, value)
