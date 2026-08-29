"""Gradio Lorebook editor with lossless draft updates."""

from __future__ import annotations

import copy
import html
import json
import os
import uuid
from typing import Any


MAX_ASSIGNMENT_AGENTS = 24


def _copy(value):
    return copy.deepcopy(value)


def book_choices(draft):
    return [(book.get("name") or book["id"], book["id"]) for book in (draft or {}).get("books", [])]


def assignment_book_choices(draft):
    choices = book_choices(draft)
    known = {value for _, value in choices}
    choices.extend(
        (f"⚠ {filename} (Missing)", filename)
        for filename in (draft or {}).get("missing_files", [])
        if filename not in known
    )
    return choices


def entry_choices(draft, book_id):
    book = find_book(draft, book_id)
    return [(entry.get("name") or entry["id"], entry["id"]) for entry in (book or {}).get("entries", [])]


def find_book(draft, book_id):
    return next((book for book in (draft or {}).get("books", []) if book.get("id") == book_id), None)


def find_entry(draft, book_id, entry_id):
    book = find_book(draft, book_id)
    return next((entry for entry in (book or {}).get("entries", []) if entry.get("id") == entry_id), None)


def update_entry(draft, book_id, entry_id, **changes):
    """Return a new draft while preserving fields not exposed by the web UI."""
    updated = _copy(draft or {})
    entry = find_entry(updated, book_id, entry_id)
    if entry is None:
        raise ValueError("Select a lorebook entry first")
    for key, value in changes.items():
        if key in ("keys", "secondary_keys"):
            value = [part.strip() for part in str(value or "").split(",") if part.strip()]
        entry[key] = value
    return updated


def add_book(draft, name="New Lorebook"):
    updated = _copy(draft or {})
    updated.setdefault("books", [])
    book = {"id": f"book_{uuid.uuid4().hex[:12]}", "name": name, "entries": []}
    updated["books"].append(book)
    return updated, book["id"]


def add_entry(draft, book_id):
    updated = _copy(draft or {})
    book = find_book(updated, book_id)
    if book is None:
        raise ValueError("Select a lorebook first")
    entry = {
        "id": f"entry_{uuid.uuid4().hex[:12]}", "name": "New Entry", "content": "",
        "keys": [], "secondary_keys": [], "constant": False, "selective": False,
        "selective_logic": 0, "enabled": True, "order": 100, "scan_depth": None,
        "case_sensitive": None, "match_whole_words": None, "use_probability": False,
        "probability": 100, "exclude_recursion": False, "prevent_recursion": False,
        "sticky": None, "cooldown": None, "delay": None, "group": "",
        "group_override": False, "group_weight": 100, "extensions": {},
    }
    book.setdefault("entries", []).append(entry)
    return updated, entry["id"]


def delete_entry(draft, book_id, entry_id):
    updated = _copy(draft or {})
    book = find_book(updated, book_id)
    if book:
        book["entries"] = [item for item in book.get("entries", []) if item.get("id") != entry_id]
    return updated


def delete_book(draft, book_id):
    updated = _copy(draft or {})
    updated["books"] = [book for book in updated.get("books", []) if book.get("id") != book_id]
    for agent_id, assigned in list(updated.get("assignments", {}).items()):
        remaining = [item for item in assigned if item != book_id]
        if remaining:
            updated["assignments"][agent_id] = remaining
        else:
            updated["assignments"].pop(agent_id, None)
    return updated


def update_assignments(draft, agent_ids, selections):
    """Return a draft containing the complete set of visible agent assignments."""
    updated = _copy(draft or {})
    known_books = (
        {book["id"] for book in updated.get("books", [])}
        | {str(item) for item in updated.get("missing_files", [])}
    )
    assignments = {}
    for agent_id, selected in zip(agent_ids, selections):
        agent_id = str(agent_id or "")
        if not agent_id or agent_id == "summary":
            continue
        ordered = []
        for book_id in selected or []:
            book_id = str(book_id)
            if book_id in known_books and book_id not in ordered:
                ordered.append(book_id)
        if ordered:
            assignments[agent_id] = ordered
    updated["assignments"] = assignments
    return updated


def assigned_book_names(draft, book_ids):
    names = {
        str(book["id"]): str(book.get("name") or book["id"])
        for book in (draft or {}).get("books", [])
    }
    return [
        names.get(str(book_id), f"⚠ {book_id} (Missing)")
        for book_id in book_ids or []
    ]


def build_lorebooks(
    gr: Any, *, load_config, save_config, import_book, delete_book_file,
    move_assignment_target, remove_assignment_target,
    remove_missing_file_reference, i18n=None,
):
    draft = gr.State({})
    tr = i18n or (lambda key: key)
    gr.Markdown("### Lorebooks")
    with gr.Row():
        active_preset = gr.Markdown("")
        refresh_button = gr.Button(tr("lorebook.refresh_books"), scale=1)
    status = gr.Markdown("")
    with gr.Accordion(tr("global_settings"), open=False):
        with gr.Row():
            scan_depth = gr.Number(value=2, precision=0, minimum=1, maximum=1000, label=tr("scan_depth"))
            token_budget = gr.Number(value=2048, precision=0, minimum=0, maximum=131072, label=tr("token_budget"))
        with gr.Row():
            case_sensitive = gr.Checkbox(label=tr("case_sensitive"))
            whole_words = gr.Checkbox(label=tr("whole_words"))
            recursive = gr.Checkbox(label=tr("recursive"))

    with gr.Accordion(tr("agent_assignments"), open=False):
        gr.Markdown(tr("lorebook.assignment_help"))
        assignment_agent_ids = []
        assignment_rows = []
        assignment_labels = []
        assignment_dropdowns = []
        assignment_summaries = []
        with gr.Column(elem_classes="brain-lorebook-assignment-scroll"):
            for _ in range(MAX_ASSIGNMENT_AGENTS):
                assignment_agent_ids.append(gr.State(None))
                with gr.Group(
                    visible=False, elem_classes="brain-lorebook-agent-card",
                ) as assignment_row:
                    with gr.Row():
                        with gr.Column(
                            scale=2, min_width=240,
                            elem_classes="brain-lorebook-agent-info",
                        ):
                            agent_label = gr.Markdown(
                                "", elem_classes="brain-lorebook-agent-label",
                            )
                            summary = gr.Markdown(
                                "", elem_classes="brain-lorebook-active-books",
                            )
                        assigned = gr.Dropdown(
                            choices=[], multiselect=True, filterable=True,
                            label=tr("lorebook.available_books"), scale=3,
                            elem_classes="brain-lorebook-assignment-dropdown",
                        )
                assignment_rows.append(assignment_row)
                assignment_labels.append(agent_label)
                assignment_dropdowns.append(assigned)
                assignment_summaries.append(summary)

    apply_button = gr.Button(tr("apply_lorebooks"), variant="primary")

    with gr.Accordion(tr("lorebook.missing_and_errors"), open=False):
        missing_files_text = gr.Markdown("")
        with gr.Row():
            missing_file = gr.Dropdown(label=tr("lorebook.missing_files"))
            remove_missing_file_button = gr.Button(tr("lorebook.remove_missing_reference"))
        missing_targets_text = gr.Markdown("")
        with gr.Row():
            missing_target = gr.Dropdown(label=tr("lorebook.missing_targets"))
            destination = gr.Dropdown(label=tr("lorebook.destination"))
            move_target_button = gr.Button(tr("lorebook.move_assignment"))
            remove_target_button = gr.Button(tr("lorebook.remove_assignment"))
        book_errors_text = gr.Markdown("")

    with gr.Row():
        book = gr.Dropdown(label=tr("lorebook"), choices=[], scale=2)
        add_book_button = gr.Button(tr("add_book"))
        delete_book_button = gr.Button(tr("delete_book"))
        import_file = gr.File(label=tr("import_st_json"), file_types=[".json"], type="filepath")
    book_name = gr.Textbox(label=tr("lorebook_title"))
    with gr.Row():
        entry = gr.Dropdown(label=tr("entry"), choices=[], scale=2)
        add_entry_button = gr.Button(tr("add_entry"))
        delete_entry_button = gr.Button(tr("delete_entry"))

    save_entry_button = gr.Button(tr("update_draft"), variant="primary")
    entry_name = gr.Textbox(label=tr("entry_title"))
    content = gr.Textbox(label=tr("content"), lines=10, max_lines=24)
    with gr.Row():
        keys = gr.Textbox(label=tr("primary_keys"), info=tr("comma_separated"))
        secondary_keys = gr.Textbox(label=tr("secondary_keys"), info=tr("comma_separated"))
    with gr.Row():
        enabled = gr.Checkbox(value=True, label=tr("enabled"))
        constant = gr.Checkbox(label=tr("always_active"))
        selective = gr.Checkbox(label=tr("use_secondary_keys"))
        use_probability = gr.Checkbox(label=tr("use_probability"))
    with gr.Row():
        order = gr.Number(value=100, precision=0, label=tr("order"))
        probability = gr.Slider(0, 100, value=100, step=1, label=tr("probability"))
        entry_scan_depth = gr.Number(value=None, precision=0, minimum=1, maximum=1000, label=tr("entry_scan_depth"))
    def assignment_label(agent):
        name = agent.get("name") or agent["id"]
        step = agent.get("step")
        if isinstance(step, int):
            return f"{tr('step')} {step} · {name}"
        return f"{tr('writer')} · {name}"

    def assignment_summary(body, book_ids):
        selected = [html.escape(name) for name in assigned_book_names(body, book_ids)]
        listing = " / ".join(selected) if selected else tr("lorebook.none_assigned")
        return f"**{tr('lorebook.active_books')}:** {listing}"

    def assignment_control_values(body):
        books = assignment_book_choices(body)
        agents = list((body or {}).get("agents", []))[:MAX_ASSIGNMENT_AGENTS]
        agent_ids = []
        rows = []
        labels = []
        dropdowns = []
        summaries = []
        for index in range(MAX_ASSIGNMENT_AGENTS):
            if index < len(agents):
                agent = agents[index]
                agent_id = str(agent["id"])
                selected = body.get("assignments", {}).get(agent_id, [])
                agent_ids.append(agent_id)
                rows.append(gr.Group(visible=True))
                labels.append(f"#### {html.escape(assignment_label(agent))}")
                dropdowns.append(gr.Dropdown(
                    choices=books, value=selected, multiselect=True, filterable=True,
                ))
                summaries.append(assignment_summary(body, selected))
            else:
                agent_ids.append(None)
                rows.append(gr.Group(visible=False))
                labels.append("")
                dropdowns.append(gr.Dropdown(choices=books, value=[], multiselect=True))
                summaries.append("")
        return [*agent_ids, *rows, *labels, *dropdowns, *summaries]

    def issue_values(body):
        preset_name = html.escape(str(body.get("preset_name") or "Default"))
        preset = f"**{tr('lorebook.current_preset')}:** {preset_name}"
        missing = list(body.get("missing_files", []))
        missing_lines = (
            "\n".join(f"- <code>{html.escape(str(item))}</code>" for item in missing)
            if missing else tr("lorebook.no_missing_files")
        )
        targets = list(body.get("missing_targets", []))
        target_choices = []
        for item in targets:
            position = item.get("target_position")
            suffix = f" (Step {position})" if position not in (None, "") else ""
            label = f"{item.get('target_name') or item['target_id']}{suffix}"
            target_choices.append((label, item["target_id"]))
        target_lines = (
            "\n".join(
                f"- **{html.escape(str(item.get('target_name') or item['target_id']))}** "
                f"(<code>{html.escape(str(item['target_id']))}</code>)"
                for item in targets
            )
            if targets else tr("lorebook.no_missing_targets")
        )
        destinations = [
            (assignment_label(agent), str(agent["id"]))
            for agent in body.get("agents", [])
        ]
        errors = list(body.get("book_errors", []))
        settings_error = str(body.get("settings_error") or "").strip()
        error_lines = (
            "\n".join(
                f"- <code>{html.escape(str(item.get('file', '')))}</code>: "
                f"{html.escape(str(item.get('error', '')))}"
                for item in errors
            )
            if errors else tr("lorebook.no_invalid_files")
        )
        if settings_error:
            error_lines = (
                f"- **settings.json:** {html.escape(settings_error)}\n"
                + error_lines
            )
        return (
            preset,
            f"**{tr('lorebook.missing_files')}**\n\n{missing_lines}",
            gr.Dropdown(choices=[(item, item) for item in missing],
                        value=missing[0] if missing else None),
            f"**{tr('lorebook.missing_targets')}**\n\n{target_lines}",
            gr.Dropdown(choices=target_choices,
                        value=target_choices[0][1] if target_choices else None),
            gr.Dropdown(choices=destinations,
                        value=destinations[0][1] if destinations else None),
            f"**{tr('lorebook.invalid_files')}**\n\n{error_lines}",
        )

    def load_all():
        body = load_config()
        books = book_choices(body)
        book_id = books[0][1] if books else None
        entries = entry_choices(body, book_id)
        entry_id = entries[0][1] if entries else None
        settings = body.get("settings", {})
        return (
            body, *issue_values(body),
            gr.Dropdown(choices=books, value=book_id),
            gr.Dropdown(choices=entries, value=entry_id),
            *entry_values(body, book_id, entry_id),
            *assignment_control_values(body),
            settings.get("scan_depth", 2), settings.get("token_budget", 2048),
            settings.get("case_sensitive", False), settings.get("match_whole_words", False),
            settings.get("recursive", False), tr("lorebook.loaded_status"),
        )

    def refresh_assignments(body):
        fresh = load_config()
        if body and body.get("preset_id") == fresh.get("preset_id"):
            updated = _copy(body)
        else:
            updated = _copy(fresh)
        updated["preset_id"] = fresh.get("preset_id")
        updated["preset_name"] = fresh.get("preset_name")
        updated["agents"] = fresh.get("agents", [])
        valid_agents = {str(agent["id"]) for agent in updated["agents"]}
        updated["assignments"] = {
            str(agent_id): list(book_ids)
            for agent_id, book_ids in updated.get("assignments", {}).items()
            if str(agent_id) in valid_agents
        }
        return updated, *assignment_control_values(updated)

    def entry_values(body, book_id, entry_id):
        selected_book = find_book(body, book_id) or {}
        selected = find_entry(body, book_id, entry_id) or {}
        return (
            selected_book.get("name", ""), selected.get("name", ""),
            selected.get("content", ""), ", ".join(selected.get("keys", [])),
            ", ".join(selected.get("secondary_keys", [])), selected.get("enabled", True),
            selected.get("constant", False), selected.get("selective", False),
            selected.get("use_probability", False), selected.get("order", 100),
            selected.get("probability", 100), selected.get("scan_depth"),
        )

    editor_outputs = [book_name, entry_name, content, keys, secondary_keys, enabled,
                      constant, selective, use_probability, order, probability, entry_scan_depth]

    def select_book(body, book_id):
        entries = entry_choices(body, book_id)
        entry_id = entries[0][1] if entries else None
        return gr.Dropdown(choices=entries, value=entry_id), *entry_values(body, book_id, entry_id)

    def select_entry(body, book_id, entry_id):
        return entry_values(body, book_id, entry_id)

    def commit(body, book_id, entry_id, bname, *values):
        updated = _copy(body)
        selected_book = find_book(updated, book_id)
        if selected_book is None:
            raise gr.Error("Select a lorebook first")
        selected_book["name"] = str(bname or "").strip() or "Lorebook"
        names = ("name", "content", "keys", "secondary_keys", "enabled", "constant",
                 "selective", "use_probability", "order", "probability", "scan_depth")
        try:
            updated = update_entry(updated, book_id, entry_id, **dict(zip(names, values)))
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
        return updated, "Draft updated"

    def create_book(body):
        updated, book_id = add_book(body)
        return updated, gr.Dropdown(choices=book_choices(updated), value=book_id), gr.Dropdown(choices=[], value=None), *entry_values(updated, book_id, None)

    def remove_book_file(book_id):
        if not book_id:
            raise gr.Error("Select a lorebook first")
        delete_book_file(book_id)
        return load_all()

    def create_entry(body, book_id):
        try:
            updated, entry_id = add_entry(body, book_id)
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
        return updated, gr.Dropdown(choices=entry_choices(updated, book_id), value=entry_id), *entry_values(updated, book_id, entry_id)

    def remove_entry(body, book_id, entry_id):
        updated = delete_entry(body, book_id, entry_id)
        choices = entry_choices(updated, book_id)
        selected = choices[0][1] if choices else None
        return updated, gr.Dropdown(choices=choices, value=selected), *entry_values(updated, book_id, selected)

    def commit_assignment(body, agent_id, book_ids):
        updated = _copy(body)
        assignments = updated.setdefault("assignments", {})
        if agent_id and book_ids:
            assignments[str(agent_id)] = list(book_ids)
        elif agent_id:
            assignments.pop(str(agent_id), None)
        return updated, assignment_summary(updated, book_ids)

    def apply(body, depth, budget, case, whole, recurse, *assignment_values):
        agent_ids = assignment_values[:MAX_ASSIGNMENT_AGENTS]
        selections = assignment_values[MAX_ASSIGNMENT_AGENTS:]
        updated = update_assignments(body, agent_ids, selections)
        updated["settings"] = {
            **updated.get("settings", {}), "scan_depth": int(depth), "token_budget": int(budget),
            "case_sensitive": bool(case), "match_whole_words": bool(whole), "recursive": bool(recurse),
        }
        save_config(updated)
        values = list(load_all())
        values[-1] = tr("lorebook.saved_status")
        return tuple(values)

    def import_json(path):
        if not path:
            return load_all()
        if os.path.getsize(path) > 8 * 1024 * 1024:
            raise gr.Error("Lorebook file must be 8 MB or smaller")
        with open(path, "r", encoding="utf-8-sig") as handle:
            import_book(json.load(handle), os.path.basename(path))
        return load_all()

    def move_missing_target(source_id, destination_id):
        if not source_id or not destination_id:
            raise gr.Error("Select both the missing target and its destination")
        move_assignment_target(source_id, destination_id)
        return load_all()

    def remove_missing_target(target_id):
        if not target_id:
            raise gr.Error("Select a missing target first")
        remove_assignment_target(target_id)
        return load_all()

    def remove_missing_reference(filename):
        if not filename:
            raise gr.Error("Select a missing file first")
        remove_missing_file_reference(filename)
        return load_all()

    book.change(select_book, [draft, book], [entry, *editor_outputs], show_progress="hidden")
    entry.change(select_entry, [draft, book, entry], editor_outputs, show_progress="hidden")
    assignment_outputs = [
        *assignment_agent_ids, *assignment_rows, *assignment_labels,
        *assignment_dropdowns, *assignment_summaries,
    ]
    issue_outputs = [
        active_preset, missing_files_text, missing_file,
        missing_targets_text, missing_target, destination, book_errors_text,
    ]
    load_outputs = [
        draft, *issue_outputs, book, entry, *editor_outputs, *assignment_outputs,
        scan_depth, token_budget, case_sensitive, whole_words, recursive, status,
    ]

    save_entry_event = save_entry_button.click(
        commit, [draft, book, entry, *editor_outputs], [draft, status])
    add_book_event = add_book_button.click(
        create_book, draft, [draft, book, entry, *editor_outputs])
    delete_book_event = delete_book_button.click(
        remove_book_file, book, load_outputs)
    add_entry_button.click(create_entry, [draft, book], [draft, entry, *editor_outputs])
    delete_entry_button.click(remove_entry, [draft, book, entry], [draft, entry, *editor_outputs])
    for agent_id, assigned, summary in zip(
        assignment_agent_ids, assignment_dropdowns, assignment_summaries,
    ):
        assigned.input(
            commit_assignment, [draft, agent_id, assigned], [draft, summary],
            show_progress="hidden",
        )
    apply_button.click(
        apply,
        [draft, scan_depth, token_budget, case_sensitive, whole_words, recursive,
         *assignment_agent_ids, *assignment_dropdowns],
        load_outputs,
    )
    import_event = import_file.change(import_json, import_file, load_outputs)
    refresh_event = refresh_button.click(load_all, None, load_outputs)
    move_event = move_target_button.click(
        move_missing_target, [missing_target, destination], load_outputs)
    remove_target_event = remove_target_button.click(
        remove_missing_target, missing_target, load_outputs)
    remove_missing_event = remove_missing_file_button.click(
        remove_missing_reference, missing_file, load_outputs)

    for event in (save_entry_event, add_book_event):
        event.then(
            assignment_control_values, draft, assignment_outputs,
            show_progress="hidden",
        )

    return {
        "load": load_all,
        "load_outputs": load_outputs,
        "full_refresh": load_all,
        "full_refresh_outputs": load_outputs,
        "refresh": refresh_assignments,
        "refresh_inputs": [draft],
        "assignment_outputs": [draft, *assignment_outputs],
        "events": [
            refresh_event, delete_book_event, import_event, move_event,
            remove_target_event, remove_missing_event,
        ],
    }
