import copy
import json
import os
import random
import re
import threading
import uuid


HERE = os.path.dirname(os.path.abspath(__file__))
LOREBOOKS_FILE = os.path.join(HERE, "lorebooks.json")
_lock = threading.Lock()
_cache = None
_cache_mtime = None

DEFAULT_SETTINGS = {
    "scan_depth": 2,
    "case_sensitive": False,
    "match_whole_words": False,
    "recursive": False,
    "max_recursion_steps": 0,
    "token_budget": 2048,
}


def _clone(value):
    return copy.deepcopy(value)


def _identifier(value, prefix):
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return (text[:80] or f"{prefix}_{uuid.uuid4().hex[:12]}")


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
        "id": _identifier(raw.get("id") or raw.get("uid"), "entry"),
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


def validate_config(raw, valid_agent_ids=None):
    raw = raw if isinstance(raw, dict) else {}
    settings_raw = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
    settings = {
        "scan_depth": int(settings_raw.get("scan_depth", 2)),
        "case_sensitive": bool(settings_raw.get("case_sensitive", False)),
        "match_whole_words": bool(settings_raw.get("match_whole_words", False)),
        "recursive": bool(settings_raw.get("recursive", False)),
        "max_recursion_steps": max(0, min(100, int(settings_raw.get("max_recursion_steps", 0)))),
        "token_budget": max(0, min(131072, int(settings_raw.get("token_budget", 2048)))),
    }
    if not 1 <= settings["scan_depth"] <= 1000:
        raise ValueError("default scan depth must be between 1 and 1000")
    books, seen = [], set()
    for book_index, raw_book in enumerate(raw.get("books") or []):
        if not isinstance(raw_book, dict):
            raise ValueError("each lorebook must be an object")
        book_id = _identifier(raw_book.get("id"), "book")
        if book_id in seen:
            raise ValueError("lorebook ids must be unique")
        seen.add(book_id)
        name = str(raw_book.get("name") or f"Lorebook {book_index + 1}").strip()[:100]
        entries = [validate_entry(entry, i) for i, entry in enumerate(raw_book.get("entries") or [])]
        entry_ids = [item["id"] for item in entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError(f"entry ids in {name} must be unique")
        books.append({"id": book_id, "name": name, "entries": entries})
    known_books = {book["id"] for book in books}
    allowed_agents = set(valid_agent_ids or []) if valid_agent_ids is not None else None
    assignments = {}
    for agent_id, book_ids in (raw.get("assignments") or {}).items():
        agent_id = str(agent_id)
        if agent_id == "summary" or (allowed_agents is not None and agent_id not in allowed_agents):
            continue
        ordered = []
        for book_id in book_ids if isinstance(book_ids, list) else []:
            book_id = str(book_id)
            if book_id in known_books and book_id not in ordered:
                ordered.append(book_id)
        if ordered:
            assignments[agent_id] = ordered
    return {"version": 1, "settings": settings, "books": books, "assignments": assignments}


def load_config(valid_agent_ids=None):
    global _cache, _cache_mtime
    with _lock:
        mtime = os.path.getmtime(LOREBOOKS_FILE) if os.path.exists(LOREBOOKS_FILE) else None
        if _cache is None or mtime != _cache_mtime:
            try:
                with open(LOREBOOKS_FILE, "r", encoding="utf-8") as handle:
                    _cache = validate_config(json.load(handle))
            except FileNotFoundError:
                _cache = validate_config({})
            except Exception as exc:
                print(f"⚠️ Could not load lorebooks.json ({exc}); using empty lorebooks.")
                _cache = validate_config({})
            _cache_mtime = mtime
        return validate_config(_clone(_cache), valid_agent_ids)


def save_config(raw, valid_agent_ids=None):
    global _cache, _cache_mtime
    clean = validate_config(raw, valid_agent_ids)
    temp_path = LOREBOOKS_FILE + ".tmp"
    with _lock:
        with open(temp_path, "w", encoding="utf-8") as handle:
            json.dump(clean, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, LOREBOOKS_FILE)
        _cache = _clone(clean)
        _cache_mtime = os.path.getmtime(LOREBOOKS_FILE)
    return _clone(clean)


def import_sillytavern(data, fallback_name="Imported Lorebook"):
    """Convert SillyTavern World Info or Character Book JSON to our model."""
    if not isinstance(data, dict):
        raise ValueError("World Info JSON must be an object")
    source_entries = data.get("entries")
    if isinstance(source_entries, dict):
        source_entries = list(source_entries.values())
    if not isinstance(source_entries, list):
        raise ValueError("World Info JSON has no entries")
    book_name = str(data.get("name") or data.get("title") or fallback_name).strip()[:100]
    converted = []
    for index, source in enumerate(source_entries):
        source = source if isinstance(source, dict) else {}
        ext = source.get("extensions") if isinstance(source.get("extensions"), dict) else {}
        converted.append(validate_entry({
            "id": source.get("uid", source.get("id")),
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
            "use_probability": source.get("useProbability", ext.get("useProbability", True)),
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
    return {"id": _identifier(None, "book"), "name": book_name, "entries": converted}


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
    # Group entries compete; group_override entries win, otherwise weighted choice.
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
