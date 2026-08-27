import csv
import io
import json
import os
import re
import threading
import time


HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS_FILE = os.path.join(HERE, "prompts.json")
EDITOR_FILE = os.path.join(HERE, "prompt_editor.html")
PRESET_DIR = os.path.join(os.path.dirname(HERE), "Preset")
_lock = threading.Lock()


def _clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


DEFAULT_STEP_TEMPERATURE = 0.3
DEFAULT_WRITER_TEMPERATURE = 0.85
DEFAULT_SUMMARY_TEMPERATURE = 0.25
DEFAULT_FREQUENCY_PENALTY = 0.0
DEFAULT_PRESENCE_PENALTY = 0.0
DEFAULT_REPETITION_PENALTY = 1.0
DEFAULT_REPETITION_PENALTY_RANGE = 0


def _defaults(default_steps, default_writer, default_summary):
    clean = validate_config(default_steps, default_writer, default_summary, "")
    return _apply_legacy_sampling_defaults(clean)


def _apply_legacy_sampling_defaults(clean):
    """Preserve the hard-coded sampler values used before config version 6."""
    if clean["steps"]:
        clean["steps"][-1]["presence_penalty"] = 0.4
    clean["writer"]["frequency_penalty"] = 0.3
    clean["writer"]["presence_penalty"] = 0.3
    clean["summary"]["frequency_penalty"] = 0.1
    return clean


def _migrate_v1(data, default_writer):
    old_slots = data.get("slots") if isinstance(data, dict) else None
    if not isinstance(old_slots, list):
        return None
    steps = []
    writer = _clone(default_writer)
    for raw in old_slots:
        if not isinstance(raw, dict):
            continue
        if raw.get("kind") == "writer":
            writer = {
                "id": "writer", "name": str(raw.get("name") or "Writer"),
                "prompt": str(raw.get("prompt") or default_writer["prompt"])
            }
            continue
        steps.append({
            "id": str(raw.get("id") or f"step_{len(steps) + 1}"),
            "name": str(raw.get("name") or f"Step {len(steps) + 1}"),
            "step": len(steps) + 1,
            "prompt": str(raw.get("prompt") or "Analyze the current scene."),
        })
    return {"steps": steps, "writer": writer}


def load_config(default_steps, default_writer, default_summary):
    with _lock:
        if not os.path.exists(PROMPTS_FILE):
            return _defaults(default_steps, default_writer, default_summary)
        try:
            with open(PROMPTS_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and data.get("version") in (2, 3, 4, 5, 6, 7):
                clean = validate_config(
                    data.get("steps"), data.get("writer"), data.get("summary") or default_summary,
                    data.get("group_prompt") or "")
                return clean if data.get("version") in (6, 7) else _apply_legacy_sampling_defaults(clean)
            migrated = _migrate_v1(data, default_writer)
            return _apply_legacy_sampling_defaults(validate_config(
                migrated["steps"], migrated["writer"], default_summary)) if migrated else _defaults(
                    default_steps, default_writer, default_summary)
        except Exception as exc:
            print(f"⚠️ Could not load prompts.json ({exc}); using built-in prompts.")
            return _defaults(default_steps, default_writer, default_summary)


def _temperature(raw, fallback, label):
    try:
        value = float(raw if raw is not None else fallback)
    except (TypeError, ValueError):
        raise ValueError(f"{label} has an invalid temperature")
    if value < 0 or value > 1.5:
        raise ValueError(f"{label} temperature must be between 0.00 and 1.50")
    return round(value, 2)


def _penalty(raw, fallback, label):
    try:
        value = float(raw if raw is not None else fallback)
    except (TypeError, ValueError):
        raise ValueError(f"{label} has an invalid value")
    if value < -2.0 or value > 2.0:
        raise ValueError(f"{label} must be between -2.00 and 2.00")
    return round(value, 2)


def _repetition_penalty(raw, label):
    try:
        value = float(raw if raw is not None else DEFAULT_REPETITION_PENALTY)
    except (TypeError, ValueError):
        raise ValueError(f"{label} has an invalid repetition penalty")
    if value < 0.0 or value > 2.0:
        raise ValueError(f"{label} repetition penalty must be between 0.00 and 2.00")
    return round(value, 2)


def _repetition_range(raw, label):
    try:
        value = int(raw if raw is not None else DEFAULT_REPETITION_PENALTY_RANGE)
    except (TypeError, ValueError):
        raise ValueError(f"{label} has an invalid repetition range")
    if value < 0 or value > 32768:
        raise ValueError(f"{label} repetition range must be between 0 and 32768 tokens")
    return value


def _sampling(raw, temperature_fallback, label):
    return {
        "temperature": _temperature(raw.get("temperature"), temperature_fallback, label),
        "frequency_penalty": _penalty(
            raw.get("frequency_penalty"), DEFAULT_FREQUENCY_PENALTY,
            f"{label} frequency penalty"),
        "presence_penalty": _penalty(
            raw.get("presence_penalty"), DEFAULT_PRESENCE_PENALTY,
            f"{label} presence penalty"),
        "repetition_penalty": _repetition_penalty(raw.get("repetition_penalty"), label),
        "repetition_penalty_range": _repetition_range(
            raw.get("repetition_penalty_range"), label),
    }


def validate_config(steps, writer, summary, group_prompt=""):
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    if len(steps) > 23:
        raise ValueError("A maximum of 23 reasoning steps is supported")
    clean_steps = []
    seen_ids, seen_steps = set(), set()
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise ValueError(f"step {index + 1} must be an object")
        slot_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        prompt = str(raw.get("prompt") or "").strip()
        try:
            step = int(raw.get("step"))
        except (TypeError, ValueError):
            raise ValueError(f"{name or f'step {index + 1}'} has an invalid step number")
        if not slot_id or len(slot_id) > 80 or slot_id in seen_ids:
            raise ValueError(f"step {index + 1} has an invalid or duplicate id")
        if not name or len(name) > 100:
            raise ValueError(f"step {index + 1} has an invalid name")
        if not prompt or len(prompt) > 30000:
            raise ValueError(f"step {index + 1} has an invalid prompt")
        if step < 1 or step > 23 or step in seen_steps:
            raise ValueError(f"step number {step} is invalid or already occupied")
        seen_ids.add(slot_id)
        seen_steps.add(step)
        clean_steps.append({
            "id": slot_id, "name": name, "step": step, "prompt": prompt,
            **_sampling(raw, DEFAULT_STEP_TEMPERATURE, name),
        })
    clean_steps.sort(key=lambda item: item["step"])

    if not isinstance(writer, dict):
        raise ValueError("writer must be an object")
    writer_name = str(writer.get("name") or "Writer").strip()
    writer_prompt = str(writer.get("prompt") or "").strip()
    if not writer_name or len(writer_name) > 100 or not writer_prompt or len(writer_prompt) > 30000:
        raise ValueError("writer settings are invalid")
    clean_writer = {
        "id": "writer", "name": writer_name, "prompt": writer_prompt,
        **_sampling(writer, DEFAULT_WRITER_TEMPERATURE, "Writer"),
    }

    if not isinstance(summary, dict):
        raise ValueError("summary must be an object")
    summary_prompt = str(summary.get("prompt") or "").strip()
    if not summary_prompt or len(summary_prompt) > 30000:
        raise ValueError("summary prompt is invalid")
    clean_summary = {
        "id": "summary", "name": "Summarize", "prompt": summary_prompt,
        **_sampling(summary, DEFAULT_SUMMARY_TEMPERATURE, "Summarize"),
    }
    clean_group_prompt = str(group_prompt or "").strip()
    if len(clean_group_prompt) > 30000:
        raise ValueError("group prompt is too long")
    return {"steps": clean_steps, "writer": clean_writer, "summary": clean_summary,
            "group_prompt": clean_group_prompt}


def save_config(steps, writer, summary, group_prompt=""):
    clean = validate_config(steps, writer, summary, group_prompt)
    payload = {"version": 7, **clean}
    temp_file = PROMPTS_FILE + ".tmp"
    with _lock:
        with open(temp_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(temp_file, PROMPTS_FILE)
    return _clone(clean)


def _safe_preset_name(name):
    name = re.sub(r"[^\w\- ]", "", str(name or "").strip(), flags=re.UNICODE)
    name = re.sub(r"\s+", "_", name).strip("_-")
    return name[:80] or time.strftime("prompt_preset_%Y%m%d_%H%M%S")


def config_to_csv(steps, writer, summary, group_prompt=""):
    clean = validate_config(steps, writer, summary, group_prompt)
    headers = [f"step{number}" for number in range(1, 24)] + ["writer"]
    headers += [f"step{number}_title" for number in range(1, 24)]
    headers += ["writer_title", "summarize_title"]
    headers += [f"step{number}_temperature" for number in range(1, 24)]
    headers += ["writer_temperature", "summarize", "summarize_temperature", "group_prompt"]
    sampling_fields = ["frequency_penalty", "presence_penalty", "repetition_penalty",
                       "repetition_penalty_range"]
    for field in sampling_fields:
        headers += [f"step{number}_{field}" for number in range(1, 24)]
        headers += [f"writer_{field}", f"summarize_{field}"]
    by_step = {item["step"]: item["prompt"] for item in clean["steps"]}
    by_title = {item["step"]: item["name"] for item in clean["steps"]}
    by_temp = {item["step"]: item["temperature"] for item in clean["steps"]}
    row = [by_step.get(number, "") for number in range(1, 24)] + [clean["writer"]["prompt"]]
    row += [by_title.get(number, "") for number in range(1, 24)]
    row += [clean["writer"]["name"], clean["summary"]["name"]]
    row += [by_temp.get(number, "") for number in range(1, 24)]
    row += [clean["writer"]["temperature"], clean["summary"]["prompt"],
            clean["summary"]["temperature"], clean["group_prompt"]]
    by_number = {item["step"]: item for item in clean["steps"]}
    for field in sampling_fields:
        row += [by_number.get(number, {}).get(field, "") for number in range(1, 24)]
        row += [clean["writer"][field], clean["summary"][field]]
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows([headers, row])
    return buffer.getvalue()


def save_preset(name, steps, writer, summary, group_prompt=""):
    csv_text = config_to_csv(steps, writer, summary, group_prompt)
    filename = _safe_preset_name(name) + ".csv"
    os.makedirs(PRESET_DIR, exist_ok=True)
    path = os.path.abspath(os.path.join(PRESET_DIR, filename))
    if os.path.dirname(path) != os.path.abspath(PRESET_DIR):
        raise ValueError("invalid preset filename")
    with _lock:
        temp_file = path + ".tmp"
        with open(temp_file, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(csv_text)
        os.replace(temp_file, path)
    return {"filename": filename, "csv": csv_text}


def export_preset(name, steps, writer, summary, group_prompt=""):
    """Build a downloadable preset without writing it to the Preset folder."""
    return {
        "filename": _safe_preset_name(name) + ".csv",
        "csv": config_to_csv(steps, writer, summary, group_prompt),
    }


def list_presets():
    if not os.path.isdir(PRESET_DIR):
        return []
    presets = []
    for filename in os.listdir(PRESET_DIR):
        if not filename.lower().endswith(".csv"):
            continue
        path = os.path.abspath(os.path.join(PRESET_DIR, filename))
        if os.path.dirname(path) != os.path.abspath(PRESET_DIR) or not os.path.isfile(path):
            continue
        presets.append({"filename": filename, "name": os.path.splitext(filename)[0]})
    return sorted(presets, key=lambda item: item["name"].casefold())


def load_preset_file(filename, default_writer, default_summary):
    safe_name = os.path.basename(str(filename or ""))
    if safe_name != str(filename or "") or not safe_name.lower().endswith(".csv"):
        raise ValueError("invalid preset filename")
    path = os.path.abspath(os.path.join(PRESET_DIR, safe_name))
    if os.path.dirname(path) != os.path.abspath(PRESET_DIR) or not os.path.isfile(path):
        raise ValueError("preset file was not found")
    if os.path.getsize(path) > 1_000_000:
        raise ValueError("CSV file is too large")
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        config = csv_to_config(handle.read(), default_writer, default_summary)
    return save_config(config["steps"], config["writer"], config["summary"],
                       config.get("group_prompt", ""))


def csv_to_config(csv_text, default_writer, default_summary):
    if not isinstance(csv_text, str) or not csv_text.strip() or len(csv_text) > 1_000_000:
        raise ValueError("CSV file is empty or too large")
    try:
        rows = list(csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff"))))
    except csv.Error as exc:
        raise ValueError(f"invalid CSV: {exc}") from exc
    if not rows:
        raise ValueError("CSV does not contain a preset row")
    row = rows[0]
    expected = {f"step{number}" for number in range(1, 24)} | {"writer"}
    if not row.keys() or not any(key in expected for key in row.keys()):
        raise ValueError("CSV must contain step1, step2, ... or writer columns")
    steps = []
    for number in range(1, 24):
        prompt = str(row.get(f"step{number}") or "").strip()
        if prompt:
            title = str(row.get(f"step{number}_title") or "").strip()
            steps.append({
                "id": f"preset_step_{number}", "name": title or f"Step {number}",
                "step": number, "prompt": prompt,
                "temperature": row.get(f"step{number}_temperature") or DEFAULT_STEP_TEMPERATURE,
                "frequency_penalty": row.get(f"step{number}_frequency_penalty") or DEFAULT_FREQUENCY_PENALTY,
                "presence_penalty": row.get(f"step{number}_presence_penalty") or DEFAULT_PRESENCE_PENALTY,
                "repetition_penalty": row.get(f"step{number}_repetition_penalty") or DEFAULT_REPETITION_PENALTY,
                "repetition_penalty_range": row.get(f"step{number}_repetition_penalty_range") or DEFAULT_REPETITION_PENALTY_RANGE,
            })
    writer_prompt = str(row.get("writer") or "").strip() or default_writer["prompt"]
    writer_title = str(row.get("writer_title") or "").strip()
    writer = {
        "id": "writer", "name": writer_title or default_writer.get("name") or "Writer",
        "prompt": writer_prompt,
        "temperature": row.get("writer_temperature") or DEFAULT_WRITER_TEMPERATURE,
        "frequency_penalty": row.get("writer_frequency_penalty") or DEFAULT_FREQUENCY_PENALTY,
        "presence_penalty": row.get("writer_presence_penalty") or DEFAULT_PRESENCE_PENALTY,
        "repetition_penalty": row.get("writer_repetition_penalty") or DEFAULT_REPETITION_PENALTY,
        "repetition_penalty_range": row.get("writer_repetition_penalty_range") or DEFAULT_REPETITION_PENALTY_RANGE,
    }
    summary = {
        "id": "summary",
        "name": str(row.get("summarize_title") or "").strip() or "Summarize",
        "prompt": str(row.get("summarize") or "").strip() or default_summary["prompt"],
        "temperature": row.get("summarize_temperature") or DEFAULT_SUMMARY_TEMPERATURE,
        "frequency_penalty": row.get("summarize_frequency_penalty") or DEFAULT_FREQUENCY_PENALTY,
        "presence_penalty": row.get("summarize_presence_penalty") or DEFAULT_PRESENCE_PENALTY,
        "repetition_penalty": row.get("summarize_repetition_penalty") or DEFAULT_REPETITION_PENALTY,
        "repetition_penalty_range": row.get("summarize_repetition_penalty_range") or DEFAULT_REPETITION_PENALTY_RANGE,
    }
    return validate_config(steps, writer, summary, row.get("group_prompt") or "")


def import_preset(csv_text, default_writer, default_summary):
    config = csv_to_config(csv_text, default_writer, default_summary)
    return save_config(config["steps"], config["writer"], config["summary"],
                       config.get("group_prompt", ""))


def read_editor():
    with open(EDITOR_FILE, "r", encoding="utf-8") as handle:
        return handle.read()
