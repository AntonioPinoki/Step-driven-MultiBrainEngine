"""Provider configuration persistence, validation, and connection checks.

The on-disk format intentionally matches the original launcher config.json:
``main`` is required and ``logic`` is optional.  Environment overrides are
applied only when constructing the runtime settings, never written to disk.
"""

from __future__ import annotations

import json
import os
import ssl
import tempfile
import urllib.request
from pathlib import Path
from typing import Mapping


CONFIG_FILE = Path(__file__).with_name("config.json")
_FIELDS = ("api_key", "model", "base_url")


class ProviderConfigError(ValueError):
    """Raised when provider settings are incomplete or malformed."""


def _clean_provider(value, label, *, required):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ProviderConfigError(f"{label} provider must be an object.")
    clean = {field: str(value.get(field) or "").strip() for field in _FIELDS}
    populated = [field for field in _FIELDS if clean[field]]
    if required and len(populated) != len(_FIELDS):
        missing = ", ".join(field for field in _FIELDS if not clean[field])
        raise ProviderConfigError(f"{label} provider is missing: {missing}.")
    if not required and populated and len(populated) != len(_FIELDS):
        missing = ", ".join(field for field in _FIELDS if not clean[field])
        raise ProviderConfigError(
            f"{label} provider is enabled but missing: {missing}."
        )
    if clean["base_url"] and not clean["base_url"].lower().startswith(("http://", "https://")):
        raise ProviderConfigError(f"{label} provider base_url must use http:// or https://.")
    return clean


def validate_config(raw, *, require_main=True):
    """Return a normalized config while preserving the legacy JSON shape."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ProviderConfigError("Provider configuration must be an object.")
    clean = {"main": _clean_provider(raw.get("main"), "Main", required=require_main)}
    logic = _clean_provider(raw.get("logic"), "Background", required=False)
    if any(logic.values()):
        clean["logic"] = logic
    return clean


def load_config(path=CONFIG_FILE, *, validate=False):
    """Load provider settings. Missing files return an empty legacy config."""
    path = Path(path)
    if not path.exists():
        return validate_config({}, require_main=True) if validate else {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle) or {}
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderConfigError(f"Could not read {path.name}: {exc}") from exc
    return validate_config(raw, require_main=validate) if validate else raw


def save_config(raw, path=CONFIG_FILE):
    """Validate and atomically save provider settings."""
    clean = validate_config(raw)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(clean, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return clean


def runtime_settings(raw=None, environ: Mapping[str, str] | None = None):
    """Resolve file settings plus the environment overrides used historically."""
    raw = load_config() if raw is None else raw
    if not isinstance(raw, dict):
        raise ProviderConfigError("Provider configuration must be an object.")
    environ = os.environ if environ is None else environ
    main = raw.get("main") or {}
    logic = raw.get("logic") or {}
    resolved = {
        "API_KEY": environ.get("BRAIN_API_KEY") or main.get("api_key") or "",
        "MODEL_NAME": environ.get("BRAIN_MODEL") or main.get("model") or "",
        "BASE_URL": environ.get("BRAIN_BASE_URL") or main.get("base_url") or "",
        "LOGIC_API_KEY": environ.get("BRAIN_LOGIC_API_KEY") or logic.get("api_key") or "",
        "LOGIC_MODEL": environ.get("BRAIN_LOGIC_MODEL") or logic.get("model") or "",
        "LOGIC_BASE_URL": environ.get("BRAIN_LOGIC_BASE_URL") or logic.get("base_url") or "",
    }
    return {key: str(value).strip() for key, value in resolved.items()}


def test_provider(base_url, api_key, *, timeout=15):
    """Call the OpenAI-compatible models endpoint and return a useful result."""
    base_url = str(base_url or "").strip()
    api_key = str(api_key or "").strip()
    if not base_url or not api_key:
        return {"ok": False, "status": None, "error": "Base URL and API key are required."}
    if not base_url.lower().startswith(("http://", "https://")):
        return {"ok": False, "status": None, "error": "Base URL must use http:// or https://."}
    url = base_url.rstrip("/")
    if not url.endswith("/models"):
        url += "/models"
    request = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8001",
        "X-Title": "BrainEngine2",
    })
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=ssl.create_default_context()
        ) as response:
            status = response.status
            return {"ok": status == 200, "status": status, "error": None}
    except Exception as exc:
        return {"ok": False, "status": getattr(exc, "code", None), "error": str(exc)}
