"""Integrated Gradio control surface for BrainEngine."""

from __future__ import annotations

import os
from typing import Any

import lorebook_store
import provider_config
import ui_text
import ui_theme
from web_lorebooks import build_lorebooks
from web_prompt_assistant import build_prompt_assistant
from web_prompt_studio import build_prompt_studio


def create_ui(server: Any, language: str = "ja"):
    import gradio as gr

    language = ui_text.normalize_language(language)
    tr = lambda key: ui_text.t(key, language)

    def dashboard_values():
        settings = provider_config.runtime_settings()
        not_configured = ui_text.t("not_configured", language)
        main_url = settings.get("BASE_URL") or not_configured
        main_model = settings.get("MODEL_NAME") or not_configured
        logic_url = settings.get("LOGIC_BASE_URL") or ""
        logic_model = settings.get("LOGIC_MODEL") or ""
        return (
            f"● {ui_text.t('running', language)}",
            f"**{ui_text.t('multibrain_api', language)}:** `http://127.0.0.1:8001/v1`",
            f"**{ui_text.t('main_provider_api', language)}:** `{main_url}`  \n"
            f"**{ui_text.t('model', language)}:** `{main_model}`",
            gr.Markdown(
                value=(f"**{ui_text.t('background_provider_api', language)}:** "
                       f"`{logic_url}`  \n**{ui_text.t('model', language)}:** "
                       f"`{logic_model or not_configured}`"),
                visible=bool(logic_url),
            ),
        )

    def load_providers():
        config = provider_config.load_config()
        main = config.get("main") or {}
        logic = config.get("logic") or {}
        return (
            main.get("base_url", ""), main.get("model", ""), main.get("api_key", ""),
            bool(logic), logic.get("base_url", ""), logic.get("model", ""),
            logic.get("api_key", ""),
            *dashboard_values(),
        )

    def test_connection(base_url, api_key):
        result = provider_config.test_provider(base_url, api_key)
        if result["ok"]:
            return tr("connection_ok")
        return str(tr("connection_failed")).format(error=result.get("error") or result.get("status"))

    def save_providers(main_url, main_model, main_key, logic_on, logic_url, logic_model, logic_key):
        payload = {"main": {"base_url": main_url, "model": main_model, "api_key": main_key}}
        if logic_on:
            payload["logic"] = {
                "base_url": logic_url, "model": logic_model, "api_key": logic_key,
            }
        try:
            clean = provider_config.save_config(payload)
            server.reload_provider_runtime(provider_config.runtime_settings(clean))
        except provider_config.ProviderConfigError as exc:
            raise gr.Error(str(exc)) from exc
        return tr("saved")

    def lore_config():
        prompts = server.active_prompt_setup()
        agent_ids = [str(item["id"]) for item in prompts["steps"]] + ["writer"]
        body = lorebook_store.load_config(agent_ids)
        body["agents"] = [
            {"id": item["id"], "name": item["name"], "step": item.get("step")}
            for item in prompts["steps"]
        ] + [{"id": "writer", "name": prompts["writer"]["name"], "step": "writer"}]
        return body

    def save_lore_config(payload):
        prompts = server.active_prompt_setup()
        agent_ids = [str(item["id"]) for item in prompts["steps"]] + ["writer"]
        return lorebook_store.save_config(payload, agent_ids)

    def assistant_context():
        config = server.active_prompt_setup()
        agents = list(config["steps"]) + [config["writer"], config["summary"]]
        return {"agents": [{
            "id": item["id"], "name": item["name"], "step": item.get("step"),
            "recent_output_count": len(server.RECENT_AGENT_OUTPUTS.get(item["id"], ())),
            "order": server.PROMPT_ORDERS.get(item["id"], ""),
        } for item in agents]}

    def save_orders(orders):
        valid = {str(item["id"]) for item in assistant_context()["agents"]}
        clean = {}
        for agent_id, value in (orders or {}).items():
            value = str(value or "").strip()
            if str(agent_id) in valid and value:
                if len(value) > 12000:
                    raise ValueError("Each temporary order must be 12000 characters or fewer")
                clean[str(agent_id)] = value
        server.PROMPT_ORDERS.clear()
        server.PROMPT_ORDERS.update(clean)
        return dict(clean)

    async def stream_assistant(messages, temperature, max_tokens):
        reference = server.prompt_assistant_reference()
        api_messages = [{
            "role": "system",
            "content": server.PROMPT_ASSISTANT_SYSTEM +
                       "\n\nCURRENT BRAINENGINE REFERENCE:\n" + reference,
        }, *messages[-20:]]
        stream = await server.writer_client.chat.completions.create(
            model=server.MODEL_NAME, messages=api_messages, temperature=temperature,
            max_tokens=max_tokens, stream=True,
            extra_headers={"HTTP-Referer": "http://localhost:8001", "X-Title": "BrainEngine2 PromptAssistant"},
        )
        try:
            async for part in server._stream_with_timeout(stream, server.STREAM_STALL_TIMEOUT):
                if part.choices:
                    delta = part.choices[0].delta.content or ""
                    if delta:
                        yield delta
        finally:
            await stream.close()

    with gr.Blocks(title="Step-driven MultiBrainEngine") as demo:
        gr.Markdown(f"# {tr('app_title')}", elem_classes="brain-header")
        with gr.Tabs():
            with gr.Tab(tr("dashboard")):
                with gr.Row():
                    language_selector = gr.Dropdown(
                        choices=ui_text.LANGUAGE_CHOICES, value=language,
                        label=tr("language"), scale=1, allow_custom_value=False,
                    )
                    language_apply = gr.Button(tr("common.apply"), variant="primary", scale=1)
                server_status = gr.Markdown(elem_classes="brain-status-ok")
                multibrain_api = gr.Markdown(elem_classes="brain-dashboard-card")
                main_provider_api = gr.Markdown(elem_classes="brain-dashboard-card")
                logic_provider_api = gr.Markdown(elem_classes="brain-dashboard-card")
                gr.Markdown(tr("dashboard_note"), elem_classes="brain-dashboard-note")

            with gr.Tab(tr("providers")):
                provider_status = gr.Markdown()
                with gr.Accordion(tr("main_provider"), open=True):
                    main_url = gr.Textbox(label=tr("base_url"))
                    main_model = gr.Textbox(label=tr("model"))
                    main_key = gr.Textbox(label=tr("api_key"), type="password")
                    main_test = gr.Button(tr("test_connection"))
                    main_test_status = gr.Markdown()
                logic_on = gr.Checkbox(label=tr("background_provider"))
                with gr.Accordion(tr("background_provider"), open=False):
                    logic_url = gr.Textbox(label=tr("base_url"))
                    logic_model = gr.Textbox(label=tr("model"))
                    logic_key = gr.Textbox(label=tr("api_key"), type="password")
                    logic_test = gr.Button(tr("test_connection"))
                    logic_test_status = gr.Markdown()
                provider_save = gr.Button(tr("save"), variant="primary")

            with gr.Tab(tr("prompt_studio")) as prompt_tab:
                prompt_ui = build_prompt_studio(
                    server.DEFAULT_REASONING_STEPS, server.DEFAULT_WRITER, server.DEFAULT_SUMMARY,
                    get_debug=lambda: server.DEBUG_MODE,
                    set_debug=lambda enabled: setattr(server, "DEBUG_MODE", bool(enabled)),
                    i18n=tr,
                )

            with gr.Tab(tr("lorebooks")) as lore_tab:
                lore_ui = build_lorebooks(
                    gr, load_config=lore_config, save_config=save_lore_config,
                    import_book=lorebook_store.import_sillytavern, i18n=tr,
                )

            with gr.Tab(tr("prompt_assistant")):
                assistant_ui = build_prompt_assistant(
                    gr, text=ui_text.t, language=language, get_context=assistant_context,
                    save_orders=save_orders, stream_reply=stream_assistant, i18n=tr,
                )

        demo.load(
            load_providers, None,
            [main_url, main_model, main_key, logic_on, logic_url, logic_model,
             logic_key, server_status, multibrain_api, main_provider_api,
             logic_provider_api],
        )
        prompt_load_event = demo.load(
            prompt_ui.callbacks.load, None, prompt_ui.form_outputs,
        )
        prompt_load_event.then(
            prompt_ui.refresh_step_ui,
            prompt_ui.step_state_inputs,
            prompt_ui.step_ui_outputs,
            show_progress="hidden",
        )
        prompt_tab.select(
            prompt_ui.refresh_step_ui,
            prompt_ui.step_state_inputs,
            prompt_ui.step_ui_outputs,
            show_progress="hidden",
        )
        demo.load(lore_ui["load"], None, lore_ui["load_outputs"])
        lore_tab.select(
            lore_ui["refresh"], lore_ui["refresh_inputs"],
            lore_ui["assignment_outputs"], show_progress="hidden",
        )
        demo.load(assistant_ui["load"], None, assistant_ui["load_outputs"])
        prompt_ui.save_event.then(
            assistant_ui["refresh"], assistant_ui["refresh_inputs"],
            assistant_ui["load_outputs"], show_progress="hidden",
        )
        prompt_ui.save_event.then(
            prompt_ui.refresh_step_ui,
            prompt_ui.step_state_inputs,
            prompt_ui.step_ui_outputs,
            show_progress="hidden",
        )
        main_test.click(test_connection, [main_url, main_key], main_test_status)
        logic_test.click(test_connection, [logic_url, logic_key], logic_test_status)
        provider_save.click(
            save_providers,
            [main_url, main_model, main_key, logic_on, logic_url, logic_model, logic_key],
            provider_status,
        ).then(
            dashboard_values, None,
            [server_status, multibrain_api, main_provider_api, logic_provider_api],
        )
        language_apply.click(
            fn=None, inputs=language_selector, outputs=None,
            js="""(language) => {
                window.localStorage.setItem('brainengine-language', language);
                window.location.assign(`/ui/${language}/`);
            }""",
        )

    return demo


def mount(fastapi_app, server):
    import gradio as gr
    from fastapi.responses import RedirectResponse

    @fastapi_app.get("/", include_in_schema=False)
    async def web_root():
        return RedirectResponse("/ui/ja/")

    @fastapi_app.get("/ui", include_in_schema=False)
    @fastapi_app.get("/ui/", include_in_schema=False)
    async def legacy_web_root():
        return RedirectResponse("/ui/ja/")

    mounted = fastapi_app
    allowed = [os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Preset"))]
    for code in ui_text.SUPPORTED_LANGUAGES:
        mounted = gr.mount_gradio_app(
            mounted, create_ui(server, code), path=f"/ui/{code}",
            allowed_paths=allowed, theme=ui_theme.create_theme(), css=ui_theme.CUSTOM_CSS,
            footer_links=[], show_error=True,
        )
    return mounted
