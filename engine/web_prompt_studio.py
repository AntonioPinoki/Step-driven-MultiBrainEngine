"""Gradio Prompt Studio built on top of :mod:`prompt_store`.

The module deliberately imports Gradio only inside ``build_prompt_studio`` so
the server and the prompt persistence layer remain usable without the optional
web UI dependency.  Callback helpers are public to keep the fairly large form
easy to test without launching a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import tempfile
import uuid
from typing import Any, Callable, Iterable

try:
    from . import prompt_store
except ImportError:  # Support ``engine`` being placed directly on sys.path.
    import prompt_store


MAX_STEPS = 23
SAMPLING_FIELDS = (
    "temperature",
    "frequency_penalty",
    "presence_penalty",
    "repetition_penalty",
    "repetition_penalty_range",
)
STEP_WIDTH = 5 + len(SAMPLING_FIELDS)  # enabled, id, name, number, sampling, prompt
FIXED_WIDTH = 2 + len(SAMPLING_FIELDS)  # name, sampling, prompt


def _sampling(item: dict[str, Any]) -> list[Any]:
    return [item.get(field) for field in SAMPLING_FIELDS]


def config_to_form(config: dict[str, Any]) -> tuple[Any, ...]:
    """Convert a prompt config into the fixed 23-slot Gradio form values."""
    by_number = {int(item["step"]): item for item in config.get("steps", [])}
    values: list[Any] = []
    for number in range(1, MAX_STEPS + 1):
        item = by_number.get(number)
        if item:
            values.extend([True, item["id"], item["name"], number, *_sampling(item), item["prompt"]])
        else:
            values.extend([
                False, f"step_{number}", f"Step {number}", number,
                prompt_store.DEFAULT_STEP_TEMPERATURE,
                prompt_store.DEFAULT_FREQUENCY_PENALTY,
                prompt_store.DEFAULT_PRESENCE_PENALTY,
                prompt_store.DEFAULT_REPETITION_PENALTY,
                prompt_store.DEFAULT_REPETITION_PENALTY_RANGE, "",
            ])
    writer = config["writer"]
    summary = config["summary"]
    values.extend([writer.get("name", "Writer"), *_sampling(writer), writer["prompt"]])
    values.extend([summary.get("name", "Summarize"), *_sampling(summary), summary["prompt"]])
    values.append(config.get("group_prompt", ""))
    return tuple(values)


def form_to_config(values: Iterable[Any]) -> dict[str, Any]:
    """Convert fixed form values to a config and validate it via prompt_store."""
    values = list(values)
    expected = MAX_STEPS * STEP_WIDTH + FIXED_WIDTH * 2 + 1
    if len(values) != expected:
        raise ValueError(f"Prompt Studio expected {expected} values, received {len(values)}")
    cursor = 0
    steps = []
    for _ in range(MAX_STEPS):
        enabled, slot_id, name, number = values[cursor:cursor + 4]
        cursor += 4
        sampling = dict(zip(SAMPLING_FIELDS, values[cursor:cursor + len(SAMPLING_FIELDS)]))
        cursor += len(SAMPLING_FIELDS)
        prompt = values[cursor]
        cursor += 1
        if enabled:
            steps.append({
                "id": slot_id, "name": name, "step": number, "prompt": prompt,
                **sampling,
            })

    def fixed(slot_id: str) -> dict[str, Any]:
        nonlocal cursor
        name = values[cursor]
        cursor += 1
        sampling = dict(zip(SAMPLING_FIELDS, values[cursor:cursor + len(SAMPLING_FIELDS)]))
        cursor += len(SAMPLING_FIELDS)
        prompt = values[cursor]
        cursor += 1
        return {"id": slot_id, "name": name, "prompt": prompt, **sampling}

    writer = fixed("writer")
    summary = fixed("summary")
    return prompt_store.validate_config(steps, writer, summary, values[cursor])


def step_number_choices(enabled_values: Iterable[Any], number_values: Iterable[Any]):
    """Return per-slot choices containing only unused numbers plus its current one."""
    enabled = [bool(value) for value in enabled_values]
    numbers = [int(value) if value not in (None, "") else index + 1
               for index, value in enumerate(number_values)]
    used = {number for active, number in zip(enabled, numbers) if active}
    return [
        [number for number in range(1, MAX_STEPS + 1)
         if number not in used or (active and number == current)]
        for active, current in zip(enabled, numbers)
    ]


@dataclass(frozen=True)
class PresetDropdownState:
    """Gradio-neutral description of a saved-preset dropdown update."""

    choices: list[tuple[str, str]]
    value: str


class PromptStudioCallbacks:
    """Persistence callbacks shared by Gradio and unit tests."""

    def __init__(
        self,
        default_steps: list[dict[str, Any]],
        default_writer: dict[str, Any],
        default_summary: dict[str, Any],
        get_debug: Callable[[], bool] | None = None,
        set_debug: Callable[[bool], Any] | None = None,
    ) -> None:
        self.default_steps = default_steps
        self.default_writer = default_writer
        self.default_summary = default_summary
        self.get_debug = get_debug or (lambda: False)
        self.set_debug = set_debug or (lambda enabled: enabled)

    def load(self) -> tuple[Any, ...]:
        return config_to_form(prompt_store.load_config(
            self.default_steps, self.default_writer, self.default_summary))

    def save(self, *values: Any) -> tuple[Any, ...]:
        config = form_to_config(values)
        saved = prompt_store.save_config(**config)
        return ("Saved Prompt Studio settings.", *config_to_form(saved))

    def presets(self) -> list[tuple[str, str]]:
        return [(item["name"], item["filename"]) for item in prompt_store.list_presets()]

    def save_preset(self, name: str, *values: Any) -> tuple[str, PresetDropdownState]:
        config = form_to_config(values)
        result = prompt_store.save_preset(name, **config)
        return (
            f"Saved preset: {result['filename']}",
            PresetDropdownState(self.presets(), result["filename"]),
        )

    def load_preset(self, filename: str) -> tuple[Any, ...]:
        config = prompt_store.load_preset_file(
            filename, self.default_writer, self.default_summary)
        return (f"Loaded preset: {filename}", *config_to_form(config))

    def import_preset(self, file_value: Any) -> tuple[Any, ...]:
        path = getattr(file_value, "name", file_value)
        if not path:
            raise ValueError("Choose a CSV preset to import")
        if os.path.getsize(path) > 1_000_000:
            raise ValueError("CSV file is too large")
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            csv_text = handle.read()
        config = prompt_store.import_preset(
            csv_text, self.default_writer, self.default_summary)
        name = os.path.splitext(os.path.basename(path))[0]
        result = prompt_store.save_preset(name, **config)
        return (
            f"Imported preset: {result['filename']}",
            PresetDropdownState(self.presets(), result["filename"]),
            *config_to_form(config),
        )

    def export_preset(self, name: str, *values: Any) -> tuple[str, str]:
        config = form_to_config(values)
        result = prompt_store.export_preset(name, **config)
        export_dir = os.path.join(tempfile.gettempdir(), "brainengine_exports")
        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, result["filename"])
        with open(path, "w", encoding="utf-8-sig", newline="") as handle:
            handle.write(result["csv"])
        return f"Export ready: {result['filename']}", path

    def debug_state(self) -> bool:
        return bool(self.get_debug())

    def toggle_debug(self, enabled: bool) -> tuple[bool, str]:
        result = self.set_debug(bool(enabled))
        if isinstance(result, dict):
            enabled = bool(result.get("enabled", enabled))
        elif isinstance(result, bool):
            enabled = result
        return enabled, f"Debug mode {'enabled' if enabled else 'disabled'}."


@dataclass
class PromptStudioUI:
    callbacks: PromptStudioCallbacks
    form_inputs: list[Any]
    form_outputs: list[Any]
    status: Any
    preset: Any
    debug: Any
    save_event: Any


def _sampling_controls(gr: Any, prefix: str, values: Iterable[Any], tr=lambda key: key) -> list[Any]:
    temperature, frequency, presence, repetition, repetition_range = values
    with gr.Row():
        return [
            gr.Slider(0, 1.5, value=temperature, step=.01, label=tr("temperature")),
            gr.Slider(-2, 2, value=frequency, step=.01, label=tr("frequency_penalty")),
            gr.Slider(-2, 2, value=presence, step=.01, label=tr("presence_penalty")),
            gr.Slider(0, 2, value=repetition, step=.01, label=tr("repetition_penalty")),
            gr.Number(value=repetition_range, precision=0, minimum=0, maximum=32768,
                      label=tr("repetition_range")),
        ]


def build_prompt_studio(
    default_steps: list[dict[str, Any]],
    default_writer: dict[str, Any],
    default_summary: dict[str, Any],
    *,
    get_debug: Callable[[], bool] | None = None,
    set_debug: Callable[[bool], Any] | None = None,
    i18n: Any | None = None,
) -> PromptStudioUI:
    """Build Prompt Studio inside the caller's active ``gr.Blocks``/``gr.Tab``.

    The returned handle can be retained by ``web_ui`` for future integration.
    """
    import gradio as gr
    tr = i18n or (lambda key: key)

    callbacks = PromptStudioCallbacks(
        default_steps, default_writer, default_summary, get_debug, set_debug)
    initial = prompt_store.load_config(default_steps, default_writer, default_summary)
    initial_values = iter(config_to_form(initial))
    form: list[Any] = []

    gr.Markdown(tr("prompt_studio_help"))
    with gr.Row():
        debug = gr.Checkbox(value=callbacks.debug_state(), label=tr("debug_traces"))
        save_button = gr.Button(tr("save_settings"), variant="primary")
    with gr.Row():
        preset = gr.Dropdown(callbacks.presets(), label=tr("saved_presets"))
        preset_name = gr.Textbox(label=tr("preset_name"), placeholder="My preset")
        save_preset_button = gr.Button(tr("save_preset"))
        export_button = gr.Button(tr("export_csv"))
        import_file = gr.File(label=tr("import_csv"), file_types=[".csv"], type="filepath")
    status = gr.Markdown()
    export_file = gr.File(
        label=tr("exported_preset"), interactive=False,
        elem_classes="brain-export-file",
    )

    with gr.Tabs():
        with gr.Tab(tr("reasoning_steps")):
            add_step_button = gr.Button(tr("add_step"), variant="secondary")
            step_containers: list[Any] = []
            enabled_controls: list[Any] = []
            id_controls: list[Any] = []
            number_controls: list[Any] = []
            remove_buttons: list[Any] = []
            initial_enabled = []
            initial_numbers = []
            initial_step_values = []
            for _ in range(MAX_STEPS):
                values = [next(initial_values) for _ in range(STEP_WIDTH)]
                initial_step_values.append(values)
                initial_enabled.append(bool(values[0]))
                initial_numbers.append(int(values[3]))
            initial_choices = step_number_choices(initial_enabled, initial_numbers)
            for number in range(1, MAX_STEPS + 1):
                values = initial_step_values[number - 1]
                with gr.Column(visible=bool(values[0])) as step_container:
                    with gr.Accordion(f"Step {values[3]}", open=bool(values[0])):
                        with gr.Row():
                            enabled = gr.Checkbox(value=values[0], visible=False)
                            slot_id = gr.Textbox(value=values[1], visible=False)
                            name = gr.Textbox(value=values[2], label=tr("title_label"), scale=3)
                            step_number = gr.Dropdown(
                                choices=initial_choices[number - 1], value=values[3],
                                label=tr("step"), allow_custom_value=False, scale=1,
                            )
                            remove_button = gr.Button(tr("delete_step"), variant="stop", scale=1)
                        sampling_values = values[4:4 + len(SAMPLING_FIELDS)]
                        sampling = _sampling_controls(gr, f"Step {number}", sampling_values, tr)
                        prompt = gr.Textbox(
                            value=values[-1], label=tr("prompt_label"), lines=10,
                            elem_classes="brain-editor",
                        )
                    form.extend([enabled, slot_id, name, step_number, *sampling, prompt])
                    step_containers.append(step_container)
                    enabled_controls.append(enabled)
                    id_controls.append(slot_id)
                    number_controls.append(step_number)
                    remove_buttons.append(remove_button)
        with gr.Tab(tr("writer")):
            writer_name = gr.Textbox(value=next(initial_values), label=tr("title_label"))
            writer_sampling_values = [next(initial_values) for _ in SAMPLING_FIELDS]
            writer_sampling = _sampling_controls(gr, "Writer", writer_sampling_values, tr)
            writer_prompt = gr.Textbox(value=next(initial_values), label=tr("prompt_label"), lines=16)
            form.extend([writer_name, *writer_sampling, writer_prompt])
        with gr.Tab(tr("summarization")):
            summary_name = gr.Textbox(value=next(initial_values), label=tr("title_label"), interactive=False)
            summary_sampling_values = [next(initial_values) for _ in SAMPLING_FIELDS]
            summary_sampling = _sampling_controls(gr, "Summarization", summary_sampling_values, tr)
            summary_prompt = gr.Textbox(value=next(initial_values), label=tr("prompt_label"), lines=16)
            form.extend([summary_name, *summary_sampling, summary_prompt])
        with gr.Tab(tr("group_chat")):
            group_prompt = gr.Textbox(value=next(initial_values), label=tr("group_prompt"), lines=16)
            form.append(group_prompt)

    form_outputs = list(form)

    def preset_dropdown_update(state: PresetDropdownState):
        return gr.update(choices=state.choices, value=state.value)

    def save_preset(*values):
        message, state = callbacks.save_preset(*values)
        return message, preset_dropdown_update(state)

    def import_preset(file_value):
        message, state, *form_values = callbacks.import_preset(file_value)
        return message, preset_dropdown_update(state), *form_values

    def refresh_step_ui(*step_values):
        enabled_values = step_values[:MAX_STEPS]
        number_values = step_values[MAX_STEPS:]
        choices = step_number_choices(enabled_values, number_values)
        containers = [gr.update(visible=bool(active)) for active in enabled_values]
        dropdowns = [
            gr.update(choices=slot_choices, value=int(current))
            for slot_choices, current in zip(choices, number_values)
        ]
        return [*containers, *dropdowns]

    def add_step(*step_values):
        enabled_values = [bool(value) for value in step_values[:MAX_STEPS]]
        number_values = [int(value) for value in step_values[MAX_STEPS:MAX_STEPS * 2]]
        ids = list(step_values[MAX_STEPS * 2:])
        try:
            slot = enabled_values.index(False)
        except ValueError as exc:
            raise gr.Error("A maximum of 23 reasoning steps is supported") from exc
        used = {number for active, number in zip(enabled_values, number_values) if active}
        new_number = next(number for number in range(1, MAX_STEPS + 1) if number not in used)
        enabled_values[slot] = True
        number_values[slot] = new_number
        ids[slot] = f"step_{uuid.uuid4().hex[:12]}"
        choices = step_number_choices(enabled_values, number_values)
        return [
            *enabled_values, *ids,
            *[gr.update(visible=active) for active in enabled_values],
            *[gr.update(choices=choices[index], value=number_values[index])
              for index in range(MAX_STEPS)],
        ]

    def remove_step(slot):
        def remove(*values):
            enabled_values = [bool(value) for value in values[:MAX_STEPS]]
            number_values = [int(value) for value in values[MAX_STEPS:]]
            enabled_values[slot] = False
            choices = step_number_choices(enabled_values, number_values)
            return [
                *enabled_values,
                *[gr.update(visible=active) for active in enabled_values],
                *[gr.update(choices=choices[index], value=number_values[index])
                  for index in range(MAX_STEPS)],
            ]
        return remove

    step_state_inputs = [*enabled_controls, *number_controls]
    step_ui_outputs = [*step_containers, *number_controls]
    add_step_button.click(
        add_step, [*enabled_controls, *number_controls, *id_controls],
        [*enabled_controls, *id_controls, *step_containers, *number_controls],
    )
    for index, button in enumerate(remove_buttons):
        button.click(
            remove_step(index), step_state_inputs,
            [*enabled_controls, *step_containers, *number_controls],
        )
    for dropdown in number_controls:
        dropdown.input(refresh_step_ui, step_state_inputs, step_ui_outputs,
                       show_progress="hidden")

    save_event = save_button.click(
        callbacks.save, inputs=form, outputs=[status, *form_outputs])
    save_preset_button.click(
        save_preset, inputs=[preset_name, *form], outputs=[status, preset])
    preset_event = preset.change(
        callbacks.load_preset, inputs=preset, outputs=[status, *form_outputs])
    preset_event.then(refresh_step_ui, step_state_inputs, step_ui_outputs,
                      show_progress="hidden")
    import_event = import_file.change(
        import_preset, inputs=import_file,
        outputs=[status, preset, *form_outputs],
    )
    import_event.then(refresh_step_ui, step_state_inputs, step_ui_outputs,
                      show_progress="hidden")
    export_button.click(
        callbacks.export_preset, inputs=[preset_name, *form], outputs=[status, export_file])
    debug.change(callbacks.toggle_debug, inputs=debug, outputs=[debug, status])
    return PromptStudioUI(
        callbacks, form, form_outputs, status, preset, debug, save_event)
