"""Application configuration loaded from the root config.json file."""
import json
import os
from typing import Any, Dict

# Root of the repository: backend/app/core/config.py -> parents[3]
BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Values used when a key is missing from config.json.
DEFAULTS: Dict[str, Any] = {
    "default_db_path": "",
}


def load_config() -> Dict[str, Any]:
    """Read config.json, falling back to defaults for missing keys."""
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            config.update(data)
    except FileNotFoundError:
        pass
    except (ValueError, OSError):
        # A malformed or unreadable config file should not prevent startup.
        pass
    return config


def get_config() -> Dict[str, Any]:
    """Return the current application configuration."""
    return load_config()
