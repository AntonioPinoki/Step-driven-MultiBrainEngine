import copy
import json
import os
import random
import re
import threading
import uuid


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
LOREBOOK_DIR = os.path.join(PROJECT_ROOT, "Lorebooks")
BOOKS_DIR = os.path.join(LOREBOOK_DIR, "books")
SETTINGS_FILE = os.path.join(LOREBOOK_DIR, "settings.json")
MAX_BOOK_BYTES = 8 * 1024 * 1024
_lock = threading.Lock()

DEFAULT_SETTINGS = {
    "scan_depth": 2,
    "case_sensitive": False,
    "match_whole_words": False,
    "recursive": False,
    "max_recursion_steps": 0,
    "token_budget": 2048,
}


class SettingsDocumentError(ValueError):
    """Raised when an existing settings.json cannot be safely read."""


def _clone(value):
    return copy.deepcopy(value)


def _identifier(value, prefix):
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return text[:80] or f"{prefix}_{uuid.uuid4().hex[:12]}"


def safe_tag_name(value):
    """Return a stable XML-ish tag name while preserving Japanese names."""
    text = re.sub(r"[\x00-\x20<>/&\\\"']+", "_", str(value or "").strip())
    text = re.sub(r"_+", "_", text).strip("_")[:100]
    if not text:
        return "entry"
    if text[0].isdigit() or text.lower() == "lorebook":
        text = "entry_" + text
    return text


def _nullable_bool(value):
    return value if isinstance(value, bool) else None


def _nullable_int(value, minimum, maximum):
    if value in (None, ""):
        return None
    value = int(value)
    if value < minimum or value > maximum:
        raise ValueError(f"value must be between {minimum} and {maximum}")
    return value


def _strings(value):
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:500] for item in value if str(item).strip()]


def validate_entry(raw, index=0):
    if not isinstance(raw, dict):
        raise ValueError("each lorebook entry must be an object")
    name = str(raw.get("name") or raw.get("comment") or f"Entry {index + 1}").strip()[:100]
    content = str(raw.get("content") or "").strip()
    if len(content) > 100000:
        raise ValueError(f"{name} content must be 100000 characters or fewer")
    probability = raw.get("probability", 100)
    probability = max(0, min(100, int(probability if probability is not None else 100)))
    return {
        "id": _identifier(raw.get("id") or raw.get("uid") or f"entry_{index + 1}", "entry"),
        "name": name or f"Entry {index + 1}",
        "content": content,
        "keys": _strings(raw.get("keys", raw.get("key", []))),
        "secondary_keys": _strings(raw.get("secondary_keys", raw.get("keysecondary", []))),
        "constant": bool(raw.get("constant", False)),
        "selective": bool(raw.get("selective", False)),
        "selective_logic": int(raw.get("selective_logic", raw.get("selectiveLogic", 0)) or 0),
        "enabled": bool(raw.get("enabled", not raw.get("disable", False))),
        "order": int(raw.get("order", raw.get("insertion_order", 0)) or 0),
        "scan_depth": _nullable_int(raw.get("scan_depth", raw.get("scanDepth")), 1, 1000),
        "case_sensitive": _nullable_bool(raw.get("case_sensitive", raw.get("caseSensitive"))),
        "match_whole_words": _nullable_bool(raw.get("match_whole_words", raw.get("matchWholeWords"))),
        "use_probability": bool(raw.get("use_probability", raw.get("useProbability", False))),
        "probability": probability,
        "exclude_recursion": bool(raw.get("exclude_recursion", raw.get("excludeRecursion", False))),
        "prevent_recursion": bool(raw.get("prevent_recursion", raw.get("preventRecursion", False))),
        "sticky": _nullable_int(raw.get("sticky"), 0, 1000),
        "cooldown": _nullable_int(raw.get("cooldown"), 0, 1000),
        "delay": _nullable_int(raw.get("delay"), 0, 1000),
        "group": str(raw.get("group") or "")[:100],
        "group_override": bool(raw.get("group_override", raw.get("groupOverride", False))),
        "group_weight": int(raw.get("group_weight", raw.get("groupWeight", 100)) or 100),
        "extensions": _clone(raw.get("extensions") or {}),
    }


def _source_entry_location(data):
    candidates = [(data, "entries")]
    character_book = data.get("character_book")
    if isinstance(character_book, dict):
        candidates.append((character_book, "entries"))
    nested = data.get("data")
    if isinstance(nested, dict):
        candidates.append((nested, "entries"))
        character_book = nested.get("character_book")
        if isinstance(character_book, dict):
            candidates.append((character_book, "entries"))
    for owner, key in candidates:
        entries = owner.get(key)
        if isinstance(entries, dict):
            return owner, key, entries
        if isinstance(entries, list):
            return owner, key, entries
    raise ValueError("World Info JSON has no entries")


def _source_entries(data):
    _, _, entries = _source_entry_location(data)
    return list(entries.values()) if isinstance(entries, dict) else entries


def import_sillytavern(data, fallback_name="Imported Lorebook", book_id=None):
    """Convert SillyTavern World Info, Character Book, or our JSON to the internal model."""
    if not isinstance(data, dict):
        raise ValueError("World Info JSON must be an object")
    source_entries = _source_entries(data)
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    direct_character_book = data.get("character_book")
    direct_character_book = (
        direct_character_book
        if isinstance(direct_character_book, dict) else {}
    )
    character_book = nested.get("character_book")
    character_book = character_book if isinstance(character_book, dict) else {}
    book_name = str(
        data.get("name") or data.get("title")
        or direct_character_book.get("name")
        or nested.get("name") or nested.get("title")
        or character_book.get("name")
        or fallback_name
    ).strip()[:100]
    converted = []
    for index, source in enumerate(source_entries):
        source = source if isinstance(source, dict) else {}
        ext = source.get("extensions") if isinstance(source.get("extensions"), dict) else {}
        converted.append(validate_entry({
            "id": source.get("uid", source.get("id", f"entry_{index + 1}")),
            "name": source.get("comment") or source.get("name") or f"Entry {index + 1}",
            "content": source.get("content"),
            "keys": source.get("key", source.get("keys", [])),
            "secondary_keys": source.get("keysecondary", source.get("secondary_keys", [])),
            "constant": source.get("constant", False),
            "selective": source.get("selective", False),
            "selective_logic": source.get("selectiveLogic", ext.get("selectiveLogic", 0)),
            "enabled": source.get("enabled", not source.get("disable", False)),
            "order": source.get("order", source.get("insertion_order", 0)),
            "scan_depth": source.get("scanDepth", ext.get("scan_depth")),
            "case_sensitive": source.get("caseSensitive", ext.get("case_sensitive")),
            "match_whole_words": source.get("matchWholeWords", ext.get("match_whole_words")),
            "use_probability": source.get("useProbability", ext.get("useProbability", False)),
            "probability": source.get("probability", ext.get("probability", 100)),
            "exclude_recursion": source.get("excludeRecursion", ext.get("exclude_recursion", False)),
            "prevent_recursion": source.get("preventRecursion", ext.get("prevent_recursion", False)),
            "sticky": source.get("sticky", ext.get("sticky")),
            "cooldown": source.get("cooldown", ext.get("cooldown")),
            "delay": source.get("delay", ext.get("delay")),
            "group": source.get("group", ext.get("group", "")),
            "group_override": source.get("groupOverride", ext.get("group_override", False)),
            "group_weight": source.get("groupWeight", ext.get("group_weight", 100)),
            "extensions": ext,
        }, index))
    entry_ids = [item["id"] for item in converted]
    if len(entry_ids) != len(set(entry_ids)):
        raise ValueError(f"entry ids in {book_name} must be unique")
    return {
        "id": str(book_id or _identifier(None, "book")),
        "name": book_name or fallback_name,
        "entries": converted,
    }


def _safe_book_filename(value):
    stem = os.path.splitext(os.path.basename(str(value or "")))[0]
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._")[:100] or "Lorebook"
    if stem.upper() in {
        "CON", "PRN", "AUX", "NUL",
        *{f"COM{number}" for number in range(1, 10)},
        *{f"LPT{number}" for number in range(1, 10)},
    }:
        stem = "_" + stem
    return stem + ".json"


def _valid_book_ref(value):
    value = str(value or "").strip()
    if not value or value != os.path.basename(value) or not value.lower().endswith(".json"):
        return None
    if len(value) > 160 or any(char in value for char in '<>:"/\\|?*'):
        return None
    return value


def _book_path(filename):
    filename = _valid_book_ref(filename)
    if not filename:
        raise ValueError("invalid lorebook filename")
    path = os.path.abspath(os.path.join(BOOKS_DIR, filename))
    if os.path.dirname(path) != os.path.abspath(BOOKS_DIR):
        raise ValueError("invalid lorebook filename")
    return path


def _ensure_directories():
    os.makedirs(BOOKS_DIR, exist_ok=True)


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def _unique_book_filename(preferred, existing=None):
    existing = {name.casefold() for name in (existing or [])}
    candidate = _safe_book_filename(preferred)
    if candidate.casefold() not in existing:
        return candidate
    stem, extension = os.path.splitext(candidate)
    number = 2
    while f"{stem} ({number}){extension}".casefold() in existing:
        number += 1
    return f"{stem} ({number}){extension}"


def _load_book_file(filename):
    path = _book_path(filename)
    if os.path.getsize(path) > MAX_BOOK_BYTES:
        raise ValueError("file is larger than 8 MB")
    with open(path, "r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    book = import_sillytavern(
        data, os.path.splitext(filename)[0], book_id=filename)
    book["file"] = filename
    return book


def discover_books():
    if not os.path.isdir(BOOKS_DIR):
        return [], []
    books, errors = [], []
    seen = set()
    for filename in sorted(os.listdir(BOOKS_DIR), key=str.casefold):
        if not filename.lower().endswith(".json"):
            continue
        folded = filename.casefold()
        if folded in seen:
            errors.append({"file": filename, "error": "duplicate filename"})
            continue
        seen.add(folded)
        try:
            books.append(_load_book_file(filename))
        except Exception as exc:
            errors.append({"file": filename, "error": str(exc)})
    return books, errors


def _validate_global_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    settings = {
        "scan_depth": int(raw.get("scan_depth", 2)),
        "case_sensitive": bool(raw.get("case_sensitive", False)),
        "match_whole_words": bool(raw.get("match_whole_words", False)),
        "recursive": bool(raw.get("recursive", False)),
        "max_recursion_steps": max(0, min(100, int(raw.get("max_recursion_steps", 0)))),
        "token_budget": max(0, min(131072, int(raw.get("token_budget", 2048)))),
    }
    if not 1 <= settings["scan_depth"] <= 1000:
        raise ValueError("default scan depth must be between 1 and 1000")
    return settings


def _book_refs(raw):
    if not isinstance(raw, list):
        return []
    result = []
    for value in raw:
        filename = _valid_book_ref(value)
        if filename and filename.casefold() not in {item.casefold() for item in result}:
            result.append(filename)
    return result


def _target_record(agent_id, raw):
    raw = raw if isinstance(raw, dict) else {"books": raw}
    step = raw.get("target_position")
    try:
        step = int(step) if step not in (None, "", "writer") else None
    except (TypeError, ValueError):
        step = None
    return {
        "target_name": str(raw.get("target_name") or agent_id).strip()[:100] or str(agent_id),
        "target_position": step,
        "books": _book_refs(raw.get("books")),
    }


def validate_settings_document(raw):
    raw = raw if isinstance(raw, dict) else {}
    profiles = {}
    for preset_id, source in (raw.get("profiles") or {}).items():
        preset_id = str(preset_id or "").strip()
        if not preset_id or len(preset_id) > 80 or not isinstance(source, dict):
            continue
        assignments = {}
        for agent_id, target in (source.get("assignments") or {}).items():
            agent_id = str(agent_id or "").strip()
            if not agent_id or agent_id == "summary":
                continue
            record = _target_record(agent_id, target)
            if record["books"]:
                assignments[agent_id] = record
        profiles[preset_id] = {
            "last_known_name": str(
                source.get("last_known_name") or preset_id).strip()[:100] or preset_id,
            "assignments": assignments,
        }
    return {
        "version": 2,
        "settings": _validate_global_settings(raw.get("settings")),
        "profiles": profiles,
    }


def _load_settings_document():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            return validate_settings_document(json.load(handle))
    except FileNotFoundError:
        return validate_settings_document({})
    except Exception as exc:
        raise SettingsDocumentError(
            f"Could not read Lorebooks/settings.json: {exc}") from exc


def _prompt_context(prompt_config):
    if isinstance(prompt_config, dict):
        preset_id = str(prompt_config.get("preset_id") or "preset_builtin_default")
        preset_name = str(prompt_config.get("preset_name") or "Default")
        agents = [
            {"id": str(item["id"]), "name": str(item.get("name") or item["id"]),
             "step": item.get("step")}
            for item in prompt_config.get("steps", [])
        ]
        writer = prompt_config.get("writer") or {}
        if writer:
            agents.append({
                "id": "writer", "name": str(writer.get("name") or "Writer"),
                "step": "writer",
            })
        return preset_id, preset_name, agents
    agent_ids = [str(value) for value in (prompt_config or []) if str(value) != "summary"]
    agents = [
        {"id": agent_id, "name": agent_id, "step": "writer" if agent_id == "writer" else None}
        for agent_id in agent_ids
    ]
    return "preset_builtin_default", "Default", agents


def load_config(prompt_config=None):
    books, book_errors = discover_books()
    settings_error = None
    try:
        document = _load_settings_document()
    except SettingsDocumentError as exc:
        settings_error = str(exc)
        document = validate_settings_document({})
    preset_id, preset_name, agents = _prompt_context(prompt_config)
    profile = document["profiles"].get(preset_id, {
        "last_known_name": preset_name, "assignments": {},
    })
    current_ids = {agent["id"] for agent in agents}
    assignments = {}
    missing_targets = []
    all_references = []
    for agent_id, target in profile.get("assignments", {}).items():
        refs = list(target.get("books", []))
        all_references.extend(refs)
        if agent_id in current_ids:
            if refs:
                assignments[agent_id] = refs
        else:
            missing_targets.append({
                "target_id": agent_id,
                "target_name": target.get("target_name") or agent_id,
                "target_position": target.get("target_position"),
                "books": refs,
            })
    known = {book["id"].casefold() for book in books}
    missing_files = [
        filename for filename in dict.fromkeys(all_references)
        if filename.casefold() not in known
    ]
    return {
        "version": 2,
        "preset_id": preset_id,
        "preset_name": preset_name,
        "settings": _clone(document["settings"]),
        "books": books,
        "assignments": assignments,
        "missing_files": missing_files,
        "missing_targets": missing_targets,
        "book_errors": book_errors,
        "settings_error": settings_error,
    }


def profile_exists(preset_id):
    document = _load_settings_document()
    return str(preset_id or "") in document["profiles"]


def ensure_profile(preset_id, preset_name, copy_from=None):
    preset_id = str(preset_id or "").strip()
    if not preset_id:
        raise ValueError("preset id is required")
    with _lock:
        document = _load_settings_document()
        if preset_id not in document["profiles"]:
            source = document["profiles"].get(str(copy_from or ""))
            document["profiles"][preset_id] = (
                _clone(source) if source else {
                    "last_known_name": str(preset_name or preset_id),
                    "assignments": {},
                }
            )
        document["profiles"][preset_id]["last_known_name"] = str(
            preset_name or preset_id).strip()[:100] or preset_id
        _write_json(SETTINGS_FILE, validate_settings_document(document))


def rename_profile(preset_id, preset_name):
    ensure_profile(preset_id, preset_name)


def move_assignment_target(preset_id, source_id, destination, prompt_config):
    preset_id = str(preset_id or "").strip()
    source_id = str(source_id or "").strip()
    destination = str(destination or "").strip()
    _, preset_name, agents = _prompt_context(prompt_config)
    agent = next((item for item in agents if item["id"] == destination), None)
    if not preset_id or not source_id or agent is None:
        raise ValueError("select a valid missing target and destination")
    with _lock:
        document = _load_settings_document()
        profile = document["profiles"].get(preset_id)
        if not profile or source_id not in profile["assignments"]:
            raise ValueError("missing assignment target was not found")
        source = profile["assignments"].pop(source_id)
        target = profile["assignments"].setdefault(destination, {
            "target_name": agent["name"],
            "target_position": agent["step"] if isinstance(agent.get("step"), int) else None,
            "books": [],
        })
        for filename in source["books"]:
            if filename.casefold() not in {item.casefold() for item in target["books"]}:
                target["books"].append(filename)
        target["target_name"] = agent["name"]
        target["target_position"] = (
            agent["step"] if isinstance(agent.get("step"), int) else None)
        profile["last_known_name"] = preset_name
        _write_json(SETTINGS_FILE, validate_settings_document(document))


def remove_assignment_target(preset_id, target_id):
    with _lock:
        document = _load_settings_document()
        profile = document["profiles"].get(str(preset_id or ""))
        if profile:
            profile["assignments"].pop(str(target_id or ""), None)
            _write_json(SETTINGS_FILE, validate_settings_document(document))


def remove_missing_file_reference(preset_id, filename):
    filename = _valid_book_ref(filename)
    if not filename:
        raise ValueError("select a valid missing lorebook file")
    with _lock:
        document = _load_settings_document()
        profile = document["profiles"].get(str(preset_id or ""))
        if profile:
            for target_id, target in list(profile["assignments"].items()):
                target["books"] = [
                    item for item in target["books"]
                    if item.casefold() != filename.casefold()
                ]
                if not target["books"]:
                    profile["assignments"].pop(target_id, None)
            _write_json(SETTINGS_FILE, validate_settings_document(document))


def _serialize_book(book, filename):
    normalized = import_sillytavern(
        book, os.path.splitext(filename)[0], book_id=filename)
    return {
        "name": normalized["name"],
        "entries": normalized["entries"],
    }


def _set_native(entry, internal_key, st_key, value, st_style):
    if internal_key in entry:
        entry[internal_key] = _clone(value)
    elif st_key in entry:
        entry[st_key] = _clone(value)
    else:
        entry[st_key if st_style else internal_key] = _clone(value)


def _merge_native_entry(source, desired, st_style):
    merged = _clone(source) if isinstance(source, dict) else {}
    _set_native(merged, "name", "comment", desired["name"], st_style)
    _set_native(merged, "content", "content", desired["content"], st_style)
    _set_native(merged, "keys", "key", desired["keys"], st_style)
    _set_native(
        merged, "secondary_keys", "keysecondary",
        desired["secondary_keys"], st_style)
    for internal_key, st_key in (
        ("constant", "constant"),
        ("selective", "selective"),
        ("selective_logic", "selectiveLogic"),
        ("order", "order"),
        ("scan_depth", "scanDepth"),
        ("case_sensitive", "caseSensitive"),
        ("match_whole_words", "matchWholeWords"),
        ("use_probability", "useProbability"),
        ("probability", "probability"),
        ("exclude_recursion", "excludeRecursion"),
        ("prevent_recursion", "preventRecursion"),
        ("sticky", "sticky"),
        ("cooldown", "cooldown"),
        ("delay", "delay"),
        ("group", "group"),
        ("group_override", "groupOverride"),
        ("group_weight", "groupWeight"),
    ):
        _set_native(
            merged, internal_key, st_key, desired[internal_key], st_style)
    if "disable" in merged:
        merged["disable"] = not desired["enabled"]
    else:
        _set_native(merged, "enabled", "enabled", desired["enabled"], st_style)
    if "uid" not in merged and "id" not in merged:
        merged["uid" if st_style else "id"] = desired["id"]
    return merged


def _set_book_name(source, name):
    if "name" in source:
        source["name"] = name
        return
    if "title" in source:
        source["title"] = name
        return
    direct = source.get("character_book")
    if isinstance(direct, dict):
        direct["name"] = name
        return
    nested = source.get("data")
    nested = nested if isinstance(nested, dict) else None
    character_book = nested.get("character_book") if nested else None
    if isinstance(character_book, dict):
        character_book["name"] = name
        return
    source["name"] = name


def _merge_book_source(source, book, filename):
    """Apply editable fields while preserving unknown source JSON fields."""
    merged = _clone(source)
    owner, key, container = _source_entry_location(merged)
    raw_entries = (
        list(container.values()) if isinstance(container, dict) else list(container)
    )
    source_normalized = import_sillytavern(
        source, os.path.splitext(filename)[0], book_id=filename)
    desired = import_sillytavern(
        book, os.path.splitext(filename)[0], book_id=filename)
    raw_by_id = {
        normalized["id"]: raw
        for normalized, raw in zip(source_normalized["entries"], raw_entries)
    }
    key_by_id = {}
    if isinstance(container, dict):
        key_by_id = {
            normalized["id"]: raw_key
            for normalized, raw_key in zip(
                source_normalized["entries"], container.keys())
        }
    st_style = any(
        isinstance(raw, dict)
        and any(field in raw for field in (
            "uid", "key", "keysecondary", "selectiveLogic", "disable"))
        for raw in raw_entries
    )
    rebuilt = []
    rebuilt_keys = []
    used_keys = set()
    for entry in desired["entries"]:
        source_entry = raw_by_id.get(entry["id"])
        rebuilt.append(_merge_native_entry(source_entry, entry, st_style))
        raw_key = str(key_by_id.get(entry["id"], entry["id"]))
        candidate = raw_key
        suffix = 2
        while candidate in used_keys:
            candidate = f"{raw_key}_{suffix}"
            suffix += 1
        used_keys.add(candidate)
        rebuilt_keys.append(candidate)
    if isinstance(container, dict):
        owner[key] = dict(zip(rebuilt_keys, rebuilt))
    else:
        owner[key] = rebuilt
    _set_book_name(merged, desired["name"])
    return merged


def _book_semantics(data, filename):
    normalized = import_sillytavern(
        data, os.path.splitext(filename)[0], book_id=filename)
    return {"name": normalized["name"], "entries": normalized["entries"]}


def save_config(raw, prompt_config=None):
    raw = raw if isinstance(raw, dict) else {}
    preset_id, preset_name, agents = _prompt_context(prompt_config)
    draft_preset_id = str(raw.get("preset_id") or "").strip()
    if draft_preset_id and draft_preset_id != preset_id:
        raise ValueError(
            "The active prompt preset changed. Reload Lorebooks before saving.")
    with _lock:
        _ensure_directories()
        document = _load_settings_document()
        document["settings"] = _validate_global_settings(raw.get("settings"))
        existing = [name for name in os.listdir(BOOKS_DIR) if name.lower().endswith(".json")]
        remapped = {}
        for raw_book in raw.get("books") or []:
            if not isinstance(raw_book, dict):
                raise ValueError("each lorebook must be an object")
            original_id = str(raw_book.get("id") or "")
            supplied = _valid_book_ref(raw_book.get("file") or original_id)
            filename = supplied or _unique_book_filename(raw_book.get("name"), existing)
            path = _book_path(filename)
            if supplied and os.path.isfile(path):
                if os.path.getsize(path) > MAX_BOOK_BYTES:
                    raise ValueError(f"{filename} is larger than 8 MB")
                with open(path, "r", encoding="utf-8-sig") as handle:
                    source = json.load(handle)
                desired = _book_semantics(raw_book, filename)
                if _book_semantics(source, filename) != desired:
                    _write_json(
                        path, _merge_book_source(source, raw_book, filename))
            else:
                _write_json(path, _serialize_book(raw_book, filename))
            existing.append(filename)
            if original_id:
                remapped[original_id] = filename

        profile = document["profiles"].setdefault(preset_id, {
            "last_known_name": preset_name, "assignments": {},
        })
        profile["last_known_name"] = preset_name
        targets = profile.setdefault("assignments", {})
        selections = raw.get("assignments") if isinstance(raw.get("assignments"), dict) else {}
        for agent in agents:
            agent_id = agent["id"]
            refs = []
            for value in selections.get(agent_id, []) or []:
                filename = remapped.get(str(value)) or _valid_book_ref(value)
                if filename and filename.casefold() not in {item.casefold() for item in refs}:
                    refs.append(filename)
            if refs:
                targets[agent_id] = {
                    "target_name": agent["name"],
                    "target_position": (
                        agent["step"] if isinstance(agent.get("step"), int) else None),
                    "books": refs,
                }
            else:
                targets.pop(agent_id, None)
        _write_json(SETTINGS_FILE, validate_settings_document(document))
    return load_config(prompt_config)


def import_book_file(data, filename_hint="Imported Lorebook"):
    """Store one imported JSON file immediately and return its normalized view."""
    import_sillytavern(data, filename_hint)
    with _lock:
        _ensure_directories()
        existing = [name for name in os.listdir(BOOKS_DIR) if name.lower().endswith(".json")]
        filename = _unique_book_filename(filename_hint, existing)
        _write_json(_book_path(filename), data)
    return _load_book_file(filename)


def delete_book_file(filename):
    """Delete one book file. Assignment references intentionally remain as Missing."""
    path = _book_path(filename)
    with _lock:
        if os.path.isfile(path):
            os.remove(path)


def _regex_key(key):
    match = re.fullmatch(r"/(.*)/([a-zA-Z]*)", key, flags=re.DOTALL)
    if not match:
        return None
    flags = re.IGNORECASE if "i" in match.group(2) else 0
    try:
        return re.compile(match.group(1), flags)
    except re.error:
        return None


def _matches(text, key, case_sensitive, whole_words):
    regex = _regex_key(key)
    if regex is not None:
        return bool(regex.search(text))
    haystack, needle = (text, key) if case_sensitive else (text.casefold(), key.casefold())
    if not whole_words:
        return needle in haystack
    if any(char.isspace() for char in needle):
        return needle in haystack
    return bool(re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack))


def _entry_matches(entry, text, settings):
    if entry["constant"]:
        return True
    keys = entry["keys"]
    if not keys:
        return False
    case_sensitive = entry["case_sensitive"] if entry["case_sensitive"] is not None else settings["case_sensitive"]
    whole_words = entry["match_whole_words"] if entry["match_whole_words"] is not None else settings["match_whole_words"]
    primary = any(_matches(text, key, case_sensitive, whole_words) for key in keys)
    if not primary:
        return False
    if not entry["selective"] or not entry["secondary_keys"]:
        return True
    secondary = [_matches(text, key, case_sensitive, whole_words) for key in entry["secondary_keys"]]
    logic = entry["selective_logic"]
    return {0: any(secondary), 1: not all(secondary), 2: not any(secondary), 3: all(secondary)}.get(logic, any(secondary))


def _chat_text(messages, depth):
    visible = []
    for message in reversed(messages if isinstance(messages, list) else []):
        if message.get("role") not in ("user", "assistant"):
            continue
        content = message.get("content")
        if isinstance(content, str):
            visible.append(content)
        if len(visible) >= depth:
            break
    return "\n".join(reversed(visible))


def activate_book(book, messages, settings, rng=None, fixed_context=""):
    """Return activated entries in SillyTavern insertion-order precedence."""
    rng = rng or random
    fixed_context = str(fixed_context or "")
    ordered = sorted(book["entries"], key=lambda item: item["order"], reverse=True)
    active, active_ids, recursion_text = [], set(), ""
    max_steps = settings.get("max_recursion_steps", 0) or len(ordered)
    passes = 1 + (max_steps if settings.get("recursive") else 0)
    for pass_index in range(passes):
        newly_active = []
        for entry in ordered:
            if not entry["enabled"] or entry["id"] in active_ids:
                continue
            if pass_index and entry["exclude_recursion"]:
                continue
            depth = entry["scan_depth"] or settings["scan_depth"]
            scan_text = _chat_text(messages, depth)
            if fixed_context:
                scan_text = f"{fixed_context}\n{scan_text}"
            if recursion_text:
                scan_text += "\n" + recursion_text
            if not _entry_matches(entry, scan_text, settings):
                continue
            if entry["use_probability"] and rng.random() * 100 >= entry["probability"]:
                continue
            newly_active.append(entry)
            active_ids.add(entry["id"])
        if not newly_active:
            break
        active.extend(newly_active)
        recursion_text += "\n" + "\n".join(
            item["content"] for item in newly_active if not item["prevent_recursion"])
        if any(item["prevent_recursion"] for item in newly_active):
            break
    grouped, result = {}, []
    for entry in active:
        (grouped.setdefault(entry["group"], []).append(entry) if entry["group"] else result.append(entry))
    for candidates in grouped.values():
        overrides = [item for item in candidates if item["group_override"]]
        pool = overrides or candidates
        weights = [max(0, item["group_weight"]) for item in pool]
        result.append(rng.choices(pool, weights=weights if any(weights) else None, k=1)[0])
    return sorted(result, key=lambda item: item["order"], reverse=True)


def render_lore(entries, expand=None, token_budget=0):
    parts, used = [], 0
    character_budget = token_budget * 4 if token_budget else 0
    for entry in entries:
        content = expand(entry["content"]) if expand else entry["content"]
        if not str(content or "").strip():
            continue
        tag = safe_tag_name(entry["name"])
        block = f"<{tag}>\n{content}\n</{tag}>"
        if character_budget and parts and used + len(block) > character_budget:
            break
        if character_budget and not parts and len(block) > character_budget:
            block = block[:max(0, character_budget - len(tag) * 2 - 8)] + f"\n</{tag}>"
        parts.append(block)
        used += len(block)
    joined = "\n".join(parts)
    return f"<lorebook>\n{joined}\n</lorebook>" if parts else ""
