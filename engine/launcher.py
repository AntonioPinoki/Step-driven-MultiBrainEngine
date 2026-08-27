# --- START OF FILE launcher.py ---
# Step-driven MultiBrainEngine — launcher.
# Opens the setup window. Press Continue and your settings are saved to
# engine/config.json, then the server starts in this same console window.
# Press Cancel (or close the window) and nothing starts.

import json
import os
import queue
import re
import ssl
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = HERE  # the launcher lives inside engine/ alongside the server
CONFIG_FILE = os.path.join(ENGINE, "config.json")
PORT = 8001
SERVER_URL = f"http://127.0.0.1:{PORT}/v1"


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            pass
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def test_provider(base_url, api_key):
    """Ask the provider for its model list. True = it answered."""
    url = base_url.rstrip("/")
    if not url.endswith("/models"):
        url += "/models"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8001",
        "X-Title": "BrainEngine2",
    })
    with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
        return r.status == 200


# =========================================================
# SETUP WINDOW
# =========================================================
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BG     = "#101613"
CARD   = "#18211c"
BORDER = "#2a3830"
INK    = "#e6e2d6"
MUTED  = "#8a9a8f"
AMBER  = "#e8c47a"
SAGE   = "#9db4a6"
ROSE   = "#d99a8f"
FONT   = ("Meiryo UI", 10)
FONT_B = ("Meiryo UI", 10, "bold")
FONT_S = ("Meiryo UI", 8, "bold")
FONT_T = ("Meiryo UI", 16, "bold")
FONT_D = ("Georgia", 15, "bold")     # guide display headings
FONT_H = ("Georgia", 12, "bold")
FONT_N = ("Georgia", 19, "bold")     # step numbers
FONT_M = ("Consolas", 10)            # the address, in code style
FONT_LOG = ("Meiryo UI", 9)           # standard Windows font with native Japanese glyphs
FONT_PROMPT_TITLE = ("Meiryo UI", 10) # Prompt Studio names may contain Japanese
WARN_BG = "#251d13"
WARN_BD = "#5c4522"


class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Step-driven MultiBrainEngine — Setup")
        self.geometry("600x720")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.result = None

        cfg = load_config()
        main = cfg.get("main") or {}
        logic = cfg.get("logic") or {}

        tk.Label(self, text="Step-driven MultiBrainEngine", bg=BG, fg=AMBER,
                 font=FONT_T, anchor="w").pack(fill="x", padx=24, pady=(20, 2))
        tk.Label(self, text="Check your API settings, then press Continue to start the server.",
                 bg=BG, fg=MUTED, font=FONT, anchor="w").pack(fill="x", padx=24, pady=(0, 14))

        main_card = self._card("MAIN PROVIDER  ·  used for the Director and the Writer  ·  required")
        self.main_key   = self._field(main_card, "API key", main.get("api_key", ""), secret=True)
        self.main_model = self._field(main_card, "Model name", main.get("model", ""))
        self.main_url   = self._field(main_card, "Base URL", main.get("base_url", ""))
        self.main_status = self._test_row(main_card, lambda: self._run_test(
            self.main_url.get(), self.main_key.get(), self.main_status))

        opt_card = self._card("BACKGROUND PROVIDER  ·  cheaper model for the hidden thinking  ·  optional")
        self.logic_on = tk.BooleanVar(
            value=bool(logic.get("api_key") or logic.get("model") or logic.get("base_url")))
        tk.Checkbutton(opt_card, text="Use a separate (cheaper) model for the background agents",
                       variable=self.logic_on, bg=CARD, fg=INK, selectcolor=BG,
                       activebackground=CARD, activeforeground=INK, font=FONT,
                       command=self._toggle_logic).pack(anchor="w", padx=14, pady=(4, 6))
        self.logic_key   = self._field(opt_card, "API key", logic.get("api_key", ""), secret=True)
        self.logic_model = self._field(opt_card, "Model name", logic.get("model", ""))
        self.logic_url   = self._field(opt_card, "Base URL", logic.get("base_url", ""))
        self.logic_status = self._test_row(opt_card, lambda: self._run_test(
            self.logic_url.get(), self.logic_key.get(), self.logic_status))
        self._toggle_logic()

        tk.Label(self, text="Settings are saved on this computer only, in engine\\config.json.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=26, pady=(10, 0))

        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", padx=24, pady=(14, 20))
        tk.Button(footer, text="Cancel", bg=CARD, fg=MUTED, activebackground=BORDER,
                  activeforeground=INK, relief="flat", font=FONT_B, padx=20, pady=8,
                  cursor="hand2", command=self._cancel).pack(side="right")
        tk.Button(footer, text="Continue  →", bg=AMBER, fg="#20241c", activebackground="#f2d492",
                  relief="flat", font=FONT_B, padx=26, pady=8, cursor="hand2",
                  command=self._continue).pack(side="right", padx=(0, 12))
        tk.Button(footer, text="SillyTavern setup guide", bg=BG, fg=SAGE, activebackground=BG,
                  activeforeground=AMBER, relief="flat", font=("Segoe UI", 9, "underline"),
                  cursor="hand2", command=self.open_guide).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # first run ever: open the guide on top of the settings automatically
        if not os.path.exists(CONFIG_FILE):
            self.after(350, self.open_guide)

    # ---------- widget helpers ----------
    def _card(self, title):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="x", padx=24, pady=7)
        tk.Label(wrap, text=title, bg=BG, fg=SAGE, font=FONT_S, anchor="w").pack(fill="x", pady=(0, 3))
        card = tk.Frame(wrap, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        return card

    def _field(self, parent, label, value, secret=False):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=14, pady=5)
        tk.Label(row, text=label, bg=CARD, fg=MUTED, font=FONT, width=11,
                 anchor="w").pack(side="left")
        entry = tk.Entry(row, bg=BG, fg=INK, insertbackground=INK, relief="flat",
                         font=FONT, show="●" if secret else "")
        entry.insert(0, value)
        entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(6, 0))
        if secret:
            def toggle(v=[False]):
                v[0] = not v[0]
                entry.config(show="" if v[0] else "●")
                btn.config(text="hide" if v[0] else "show")
            btn = tk.Button(row, text="show", bg=CARD, fg=SAGE, activebackground=CARD,
                            relief="flat", font=("Segoe UI", 8), cursor="hand2", command=toggle)
            btn.pack(side="left", padx=(6, 0))
        return entry

    def _test_row(self, parent, command):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=14, pady=(2, 10))
        tk.Button(row, text="Test connection", bg=CARD, fg=SAGE, activebackground=CARD,
                  relief="flat", font=FONT_S, cursor="hand2", command=command).pack(side="left", padx=(88, 8))
        status = tk.Label(row, text="", bg=CARD, font=("Segoe UI", 9))
        status.pack(side="left")
        return status

    def _toggle_logic(self):
        state = "normal" if self.logic_on.get() else "disabled"
        for entry in (self.logic_key, self.logic_model, self.logic_url):
            entry.config(state=state)

    def _run_test(self, url, key, status_label):
        url, key = url.strip(), key.strip()
        if not url or not key:
            status_label.config(text="enter the URL and key first", fg=ROSE)
            return
        status_label.config(text="testing…", fg=MUTED)
        def work():
            try:
                ok = test_provider(url, key)
                msg, col = ("connection OK ✓", SAGE) if ok else ("unexpected answer from provider", ROSE)
            except Exception as e:
                msg, col = (f"failed: {str(e)[:70]}", ROSE)
            self.after(0, lambda: status_label.config(text=msg, fg=col))
        threading.Thread(target=work, daemon=True).start()

    # ---------- buttons ----------
    def _continue(self):
        key   = self.main_key.get().strip()
        model = self.main_model.get().strip()
        url   = self.main_url.get().strip()
        if not (key and model and url):
            messagebox.showwarning("Missing settings",
                "The main provider needs all three fields:\nAPI key, model name and base URL.")
            return
        cfg = {"main": {"api_key": key, "model": model, "base_url": url}}
        if self.logic_on.get():
            lkey   = self.logic_key.get().strip()
            lmodel = self.logic_model.get().strip()
            lurl   = self.logic_url.get().strip()
            if not (lkey and lmodel and lurl):
                messagebox.showwarning("Missing settings",
                    "The background provider is enabled but incomplete.\n\n"
                    "Fill its three fields — or untick the box to use the\nmain provider for everything.")
                return
            cfg["logic"] = {"api_key": lkey, "model": lmodel, "base_url": lurl}
        save_config(cfg)
        self.result = "continue"
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()

    def open_guide(self):
        if getattr(self, "_guide", None) and self._guide.winfo_exists():
            self._guide.focus_set()
            return
        self._guide = GuideWindow(self)


# =========================================================
# SILLYTAVERN SETUP GUIDE
# =========================================================
class GuideWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Connecting SillyTavern — Guide")
        self.geometry("660x720")
        self.configure(bg=BG)
        self.transient(parent)

        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        bar = tk.Scrollbar(self, orient="vertical", command=canvas.yview,
                           bg=CARD, troughcolor=BG, width=10)
        self.page = tk.Frame(canvas, bg=BG)
        self.page.bind("<Configure>",
                       lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.page, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._build()

    # ---------- content ----------
    def _build(self):
        p = self.page

        tk.Label(p, text="Connecting SillyTavern", bg=BG, fg=AMBER,
                 font=FONT_D, anchor="w").pack(fill="x", padx=28, pady=(24, 4))
        tk.Label(p, text="Two quick steps, about a minute. You only do this once.",
                 bg=BG, fg=MUTED, font=FONT, anchor="w").pack(fill="x", padx=28, pady=(0, 18))

        # ---- step 1 ----
        self._step(p, "1", "Point SillyTavern at the server")
        self._bullet(p, "Open SillyTavern.")
        self._bullet(p, "Click the API Connections tab — the plug icon at the top.")
        self._bullet(p, "Select  Chat Completion  →  Custom (OpenAI-compatible).")
        self._bullet(p, "Paste this into the Base URL field:")
        self._url_row(p)
        self._bullet(p, "Hit Connect.")

        # ---- step 2 (critical) ----
        self._step(p, "2", "Turn on reasoning", required=True)
        warn = tk.Frame(p, bg=WARN_BG, highlightbackground=WARN_BD, highlightthickness=1)
        warn.pack(fill="x", padx=28, pady=(0, 10))
        self._bullet(warn, "Click the Advanced Formatting tab — the “A” icon on the top menu bar.", bg=WARN_BG)
        self._bullet(warn, "Find the Reasoning section.", bg=WARN_BG)
        self._bullet(warn, "Turn on  “Add to prompt”.", bg=WARN_BG)
        self._bullet(warn, "Set  “Max number of thinking blocks to add”  to a high number (e.g. 100).", bg=WARN_BG)
        why = tk.Frame(warn, bg=WARN_BG)
        why.pack(fill="x", padx=16, pady=(4, 14))
        tk.Label(why, text="Why this matters", bg=WARN_BG, fg=AMBER,
                 font=FONT_S, anchor="w").pack(fill="x")
        tk.Label(why, bg=WARN_BG, fg=INK, font=("Segoe UI", 9), anchor="w", justify="left",
                 text="After every reply, SillyTavern tucks the character's hidden thoughts away.\n"
                      "This setting hands them back to the engine on the next turn — that's how\n"
                      "the character keeps the thread of its inner voice from message to message.\n"
                      "Without it the engine still runs, but that short-term emotional continuity\n"
                      "is lost.").pack(fill="x", pady=(3, 0))

        # ---- closing note ----
        note = tk.Frame(p, bg=BG)
        note.pack(fill="x", padx=28, pady=(14, 26))
        tk.Label(note, text="That's it — streaming can stay on or off, both work.\n"
                            "Close this guide whenever you're ready.",
                 bg=BG, fg=SAGE, font=("Segoe UI", 9), anchor="w",
                 justify="left").pack(fill="x")

    # ---------- pieces ----------
    def _step(self, parent, number, title, required=False):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=28, pady=(10, 6))
        tk.Label(row, text=number, bg=BG, fg=AMBER, font=FONT_N).pack(side="left")
        tk.Label(row, text=title, bg=BG, fg=INK, font=FONT_H,
                 anchor="w").pack(side="left", padx=(14, 0), pady=(6, 0))
        if required:
            tk.Label(row, text="REQUIRED", bg=AMBER, fg="#20241c", font=("Segoe UI", 7, "bold"),
                     padx=7, pady=2).pack(side="left", padx=(12, 0), pady=(8, 0))

    def _bullet(self, parent, text, bg=BG):
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x", padx=16 if bg != BG else 28, pady=2)
        tk.Label(row, text="·", bg=bg, fg=SAGE, font=FONT_B).pack(side="left", padx=(26, 8))
        tk.Label(row, text=text, bg=bg, fg=INK, font=FONT, anchor="w").pack(side="left")

    def _url_row(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=28, pady=(6, 4))
        box = tk.Frame(row, bg="#0b100d", highlightbackground=BORDER, highlightthickness=1)
        box.pack(side="left", padx=(34, 10))
        tk.Label(box, text=SERVER_URL, bg="#0b100d", fg=AMBER, font=FONT_M,
                 padx=12, pady=6).pack()
        btn = tk.Button(row, text="copy", bg=CARD, fg=SAGE, activebackground=BORDER,
                        activeforeground=INK, relief="flat", font=FONT_S, padx=14, pady=5,
                        cursor="hand2")
        btn.config(command=lambda: self._copy(btn))
        btn.pack(side="left")

    def _copy(self, btn):
        self.clipboard_clear()
        self.clipboard_append(SERVER_URL)
        btn.config(text="copied ✓", fg=AMBER)
        self.after(1800, lambda: btn.config(text="copy", fg=SAGE) if btn.winfo_exists() else None)


# =========================================================
# CONTROL WINDOW
# =========================================================
class QueueWriter:
    """Mirror console output while forwarding it to the Tk log window."""

    def __init__(self, original, output_queue):
        self.original = original
        self.output_queue = output_queue

    def write(self, text):
        if not text:
            return 0
        self.original.write(text)
        self.original.flush()
        self.output_queue.put(text)
        return len(text)

    def flush(self):
        self.original.flush()

    def isatty(self):
        return self.original.isatty()

    def fileno(self):
        return self.original.fileno()

    @property
    def encoding(self):
        return getattr(self.original, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self.original, "errors", "replace")


class PromptStudio(tk.Frame):
    """Native Prompt Studio tab backed by the existing HTTP API."""

    API_ROOT = f"http://127.0.0.1:{PORT}"

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.steps = []
        self.group_prompt = ""
        self.writer = {"id": "writer", "name": "Writer", "prompt": "", "temperature": .85,
                       "frequency_penalty": .3, "presence_penalty": .3,
                       "repetition_penalty": 1.0, "repetition_penalty_range": 0}
        self.summary = {"id": "summary", "name": "Summarize", "prompt": "", "temperature": .25,
                        "frequency_penalty": .1, "presence_penalty": 0.0,
                        "repetition_penalty": 1.0, "repetition_penalty_range": 0}
        self.step_widgets = []
        self.loaded = False
        self.debug_enabled = False
        self._build_shell()

    def _build_shell(self):
        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(fill="x", padx=24, pady=(18, 12))
        heading = tk.Frame(toolbar, bg=BG)
        heading.pack(fill="x")
        tk.Label(heading, text="Prompt Studio", bg=BG, fg=AMBER,
                 font=FONT_T, anchor="w").pack(fill="x")
        self.status = tk.Label(heading, text="Edit the reasoning chain used for the next request.",
                               bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.status.pack(fill="x", pady=(2, 0))

        actions = tk.Frame(toolbar, bg=BG)
        actions.pack(fill="x", pady=(10, 0))
        self.preset_box = ttk.Combobox(actions, state="readonly", width=20)
        self.preset_box.bind("<<ComboboxSelected>>", self._load_selected_preset)
        self.preset_name = tk.Entry(actions, bg="#0b100d", fg=INK,
                                    insertbackground=INK, relief="flat", width=17,
                                    font=FONT)
        self.preset_name.insert(0, "Preset name")
        self.debug_button = self._button(actions, "Debug: Off", self.toggle_debug)
        self.prompt_action_widgets = [
            self.preset_box,
            self.preset_name,
            self._button(actions, "Save preset", self.save_preset),
            self._button(actions, "Import", self.import_preset),
            self._button(actions, "＋ Add step", self.add_step),
            self.debug_button,
            self._button(actions, "Apply", self.save, primary=True),
        ]
        self._prompt_action_layout = None
        actions.bind("<Configure>", self._layout_prompt_actions)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        self.canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        bar = tk.Scrollbar(body, orient="vertical", command=self.canvas.yview,
                           bg=CARD, troughcolor=BG, width=12)
        self.page = tk.Frame(self.canvas, bg=BG)
        self.page_window = self.canvas.create_window((0, 0), window=self.page, anchor="nw")
        self.page.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(
            self.page_window, width=e.width))
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda _e: self.canvas.bind_all(
            "<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda _e: self.canvas.unbind_all("<MouseWheel>"))

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command,
                         bg=AMBER if primary else CARD,
                         fg="#20241c" if primary else SAGE,
                         activebackground="#f2d492" if primary else BORDER,
                         activeforeground="#20241c" if primary else INK,
                         relief="flat", font=FONT_B, padx=12, pady=6,
                         cursor="hand2")

    def _layout_prompt_actions(self, event):
        """Keep Apply visible by wrapping the toolbar on narrower windows."""
        mode = "wide" if event.width >= 860 else "compact"
        if mode == self._prompt_action_layout:
            return
        self._prompt_action_layout = mode
        for widget in self.prompt_action_widgets:
            widget.grid_forget()
        for column in range(len(self.prompt_action_widgets) + 1):
            event.widget.grid_columnconfigure(column, weight=0)
        event.widget.grid_columnconfigure(0, weight=1)
        if mode == "wide":
            for index, widget in enumerate(self.prompt_action_widgets, start=1):
                widget.grid(row=0, column=index,
                            padx=(0, 8) if index < len(self.prompt_action_widgets) else 0,
                            ipady=3 if index == 1 else 0, sticky="e")
        else:
            for index, widget in enumerate(self.prompt_action_widgets[:3], start=1):
                widget.grid(row=0, column=index, padx=(0, 8) if index < 3 else 0,
                            pady=(0, 7), ipady=3 if index == 1 else 0, sticky="e")
            for index, widget in enumerate(self.prompt_action_widgets[3:], start=1):
                widget.grid(row=1, column=index, padx=(0, 8) if index < 3 else 0,
                            sticky="e")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def show(self):
        if not self.loaded:
            self.load()

    def _request(self, path, payload=None):
        data = None
        headers = {}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        request = urllib.request.Request(self.API_ROOT + path, data=data,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            detail = str(exc)
            if hasattr(exc, "read"):
                try:
                    body = json.loads(exc.read().decode("utf-8"))
                    detail = body.get("detail") or detail
                except Exception:
                    pass
            raise RuntimeError(detail) from exc

    def load(self):
        self.status.config(text="Loading…", fg=AMBER)
        try:
            body = self._request("/api/prompts")
            self.steps = body["steps"]
            self.writer = body["writer"]
            self.summary = body["summary"]
            self.group_prompt = body.get("group_prompt", "")
            self.debug_enabled = bool(self._request("/api/debug").get("enabled"))
            self._update_debug_button()
            self._refresh_presets()
            self._render()
            self.loaded = True
            self._notice("Prompt settings loaded.", True)
        except Exception as exc:
            self._notice(f"Could not load Prompt Studio: {exc}", False)

    def _update_debug_button(self):
        enabled = self.debug_enabled
        self.debug_button.config(
            text="Debug: On" if enabled else "Debug: Off",
            bg="#765ca5" if enabled else CARD,
            fg=INK if enabled else SAGE,
            activebackground="#8b70b8" if enabled else BORDER,
            activeforeground=INK,
        )

    def toggle_debug(self):
        try:
            body = self._request("/api/debug", {"enabled": not self.debug_enabled})
            self.debug_enabled = bool(body.get("enabled"))
            self._update_debug_button()
            state = "enabled" if self.debug_enabled else "disabled"
            self._notice(
                f"Debug mode {state}. Text traces are saved in the debug folder.", True)
        except Exception as exc:
            self._notice(f"Could not change debug mode: {exc}", False)

    def _refresh_presets(self, selected=""):
        items = self._request("/api/presets").get("presets", [])
        self.preset_files = [item["filename"] for item in items]
        self.preset_box["values"] = ["Saved presets…"] + [item["name"] for item in items]
        index = self.preset_files.index(selected) + 1 if selected in self.preset_files else 0
        self.preset_box.current(index)

    def _render(self):
        for child in self.page.winfo_children():
            child.destroy()
        self.step_widgets = []
        self.steps.sort(key=lambda item: item["step"])
        for number, item in enumerate(self.steps, start=1):
            item["step"] = number
        tk.Label(self.page, text=f"{len(self.steps)} reasoning steps  ·  Maximum 23",
                 bg=BG, fg=AMBER, font=FONT_B, anchor="w").pack(
                     fill="x", pady=(0, 10))
        for item in self.steps:
            self._step_card(item)
        if not self.steps:
            tk.Label(self.page, text="No reasoning steps. Writer will respond directly.",
                     bg=CARD, fg=MUTED, font=FONT, pady=24).pack(fill="x")
        self.writer_widgets = self._fixed_card(
            "Final output", "Writer", self.writer, editable_name=True)
        self.summary_widgets = self._fixed_card(
            "Summarization", "[[SUMMARIZE]]", self.summary, editable_name=False)
        self.group_prompt_widget = self._group_prompt_card()

    def _group_prompt_card(self):
        tk.Label(self.page, text="Group chat prompt", bg=BG, fg=INK, font=FONT_H,
                 anchor="w").pack(fill="x", pady=(24, 7))
        card = tk.Frame(self.page, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 18))
        tk.Label(
            card,
            text=("Applied above every reasoning-step and Final output prompt in group chats.  "
                  "Wildcards: {{user}}, {{char}}, {{groupchar}}, {{allchar}}"),
            bg=CARD, fg=MUTED, font=("Meiryo UI", 8), anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))
        prompt = tk.Text(card, height=7, bg="#0b100d", fg=INK,
                         insertbackground=INK, selectbackground="#405347",
                         relief="flat", wrap="word", font=FONT_LOG, padx=10, pady=8)
        prompt.insert("1.0", self.group_prompt)
        prompt.pack(fill="x", padx=12, pady=(0, 12))
        return prompt

    def _step_card(self, item):
        card = tk.Frame(self.page, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=12, pady=10)
        tk.Label(head, text=f"{item['step']:02d}", bg=CARD, fg=AMBER,
                 font=FONT_B, width=4).pack(side="left")
        name = tk.Entry(head, bg="#0b100d", fg=INK, insertbackground=INK,
                        relief="flat", font=FONT_PROMPT_TITLE)
        name.insert(0, item["name"])
        name.pack(side="left", fill="x", expand=True, ipady=5, padx=(4, 10))
        tk.Label(head, text="Step", bg=CARD, fg=MUTED, font=FONT).pack(side="left")
        available = list(range(1, len(self.steps) + 1))
        number = ttk.Combobox(head, state="readonly", width=3,
                              values=available, font=FONT, justify="center")
        number.set(item["step"])
        number.pack(side="left", ipady=4, padx=(6, 10))
        number.bind("<<ComboboxSelected>>",
                    lambda _e, target=item: self._change_step_number(target))
        self._button(head, "Remove", lambda target=item: self.remove_step(target)).pack(side="right")

        prompt = tk.Text(card, height=8, bg="#0b100d", fg=INK,
                         insertbackground=INK, selectbackground="#405347",
                         relief="flat", wrap="word", font=FONT_LOG, padx=10, pady=8)
        prompt.insert("1.0", item["prompt"])
        prompt.pack(fill="x", padx=12)
        sampling = self._sampling_panel(card, item)
        self.step_widgets.append({"item": item, "name": name, "step": number,
                                  "prompt": prompt, "sampling": sampling})

    def _change_step_number(self, target):
        try:
            target_widgets = next(
                widgets for widgets in self.step_widgets
                if widgets["item"]["id"] == target["id"])
            old_number = int(target["step"])
            new_number = int(target_widgets["step"].get())
            if new_number != old_number:
                displaced = next(
                    (widgets for widgets in self.step_widgets
                     if widgets["item"]["id"] != target["id"]
                     and int(widgets["step"].get()) == new_number), None)
                if displaced is not None:
                    displaced["step"].set(old_number)
            self.steps, self.writer, self.summary, self.group_prompt = self._collect()
            self._render()
            self._notice(f"{target['name']} moved. Apply to activate the new order.", True)
        except Exception as exc:
            self._notice(f"Could not change step order: {exc}", False)
            self._render()

    def _fixed_card(self, title, badge, item, editable_name):
        tk.Label(self.page, text=title, bg=BG, fg=INK, font=FONT_H,
                 anchor="w").pack(fill="x", pady=(24, 7))
        card = tk.Frame(self.page, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=12, pady=10)
        tk.Label(head, text=badge, bg=CARD, fg=AMBER, font=FONT_B,
                 width=14, anchor="w").pack(side="left")
        name = tk.Entry(head, bg="#0b100d", fg=INK, insertbackground=INK,
                        disabledbackground="#101713", disabledforeground=MUTED,
                        relief="flat", font=FONT_PROMPT_TITLE)
        name.insert(0, item.get("name", badge))
        name.pack(side="left", fill="x", expand=True, ipady=5)
        if not editable_name:
            name.config(state="disabled")
        prompt = tk.Text(card, height=11, bg="#0b100d", fg=INK,
                         insertbackground=INK, selectbackground="#405347",
                         relief="flat", wrap="word", font=FONT_LOG, padx=10, pady=8)
        prompt.insert("1.0", item.get("prompt", ""))
        prompt.pack(fill="x", padx=12)
        return {"name": name, "prompt": prompt, "sampling": self._sampling_panel(card, item)}

    def _sampling_panel(self, parent, item):
        panel = tk.Frame(parent, bg=CARD)
        panel.pack(fill="x", padx=12, pady=10)
        specs = (
            ("temperature", "Temperature", 0.0, 1.5, .05, .3, False),
            ("frequency_penalty", "Frequency penalty", -2.0, 2.0, .05, 0.0, False),
            ("repetition_penalty", "Repetition penalty", 0.0, 2.0, .01, 1.0, False),
            ("repetition_penalty_range", "Repeat range (tokens)", 0, 32768, 1, 0, True),
            ("presence_penalty", "Presence penalty", -2.0, 2.0, .05, 0.0, False),
        )
        widgets = {}
        for key, label, minimum, maximum, resolution, fallback, integer in specs:
            row = tk.Frame(panel, bg=CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=label, bg=CARD, fg=MUTED, font=FONT_S,
                     width=23, anchor="w").pack(side="left")
            value = item.get(key, fallback)
            display = str(int(value)) if integer else f"{float(value):.2f}"
            value_var = tk.StringVar(value=display)
            value_entry = tk.Entry(
                row, textvariable=value_var, bg="#0b100d", fg=AMBER,
                insertbackground=INK, selectbackground="#405347",
                relief="flat", font=FONT_B, width=8, justify="right")
            value_entry.pack(side="right", ipady=3)
            def update(raw, target=value_var, as_integer=integer):
                target.set(str(int(float(raw))) if as_integer else f"{float(raw):.2f}")
            scale = tk.Scale(row, from_=minimum, to=maximum, resolution=resolution,
                             orient="horizontal", showvalue=False, bg=CARD, fg=INK,
                             troughcolor="#0b100d", activebackground=AMBER,
                             highlightthickness=0, bd=0, command=update)
            scale.set(value)
            scale.pack(side="right", fill="x", expand=True, padx=(14, 6))
            control = {
                "label": label, "scale": scale, "entry": value_entry,
                "variable": value_var, "minimum": minimum, "maximum": maximum,
                "resolution": resolution, "integer": integer,
            }
            value_entry.bind("<Return>", lambda _e, item=control: self._try_sampling_entry(item))
            value_entry.bind("<FocusOut>", lambda _e, item=control: self._try_sampling_entry(item))
            widgets[key] = control
        tk.Label(panel,
                 text="Repeat penalty 1.00 = off  ·  Repeat range 0 = provider default",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w").pack(
                     fill="x", pady=(5, 0))
        return widgets

    @staticmethod
    def _commit_sampling_entry(control):
        try:
            value = float(control["entry"].get().strip())
        except ValueError as exc:
            raise ValueError(f"{control['label']} must be a number") from exc
        if value < control["minimum"] or value > control["maximum"]:
            raise ValueError(
                f"{control['label']} must be between {control['minimum']} and {control['maximum']}")
        if control["integer"]:
            value = int(round(value))
        else:
            resolution = float(control["resolution"])
            value = round(round(value / resolution) * resolution, 2)
        control["scale"].set(value)
        control["variable"].set(str(int(value)) if control["integer"] else f"{value:.2f}")
        return value

    def _try_sampling_entry(self, control):
        try:
            self._commit_sampling_entry(control)
        except ValueError as exc:
            self._notice(str(exc), False)
        return "break"

    @classmethod
    def _sampling_values(cls, widgets):
        values = {key: cls._commit_sampling_entry(control)
                  for key, control in widgets.items()}
        return {
            "temperature": round(float(values["temperature"]), 2),
            "frequency_penalty": round(float(values["frequency_penalty"]), 2),
            "presence_penalty": round(float(values["presence_penalty"]), 2),
            "repetition_penalty": round(float(values["repetition_penalty"]), 2),
            "repetition_penalty_range": int(values["repetition_penalty_range"]),
        }

    def _collect(self):
        steps = []
        for widgets in self.step_widgets:
            item = widgets["item"]
            steps.append({
                "id": item["id"], "name": widgets["name"].get().strip(),
                "step": int(widgets["step"].get()),
                "prompt": widgets["prompt"].get("1.0", "end-1c").strip(),
                **self._sampling_values(widgets["sampling"]),
            })
        if len({item["step"] for item in steps}) != len(steps):
            raise ValueError("Each reasoning step must have a unique step number")
        writer = {
            "id": "writer", "name": self.writer_widgets["name"].get().strip(),
            "prompt": self.writer_widgets["prompt"].get("1.0", "end-1c").strip(),
            **self._sampling_values(self.writer_widgets["sampling"]),
        }
        summary = {
            "id": "summary", "name": "Summarize",
            "prompt": self.summary_widgets["prompt"].get("1.0", "end-1c").strip(),
            **self._sampling_values(self.summary_widgets["sampling"]),
        }
        group_prompt = self.group_prompt_widget.get("1.0", "end-1c").strip()
        return steps, writer, summary, group_prompt

    def save(self):
        try:
            steps, writer, summary, group_prompt = self._collect()
            body = self._request("/api/prompts", {
                "steps": steps, "writer": writer, "summary": summary,
                "group_prompt": group_prompt})
            self.steps, self.writer, self.summary = body["steps"], body["writer"], body["summary"]
            self.group_prompt = body.get("group_prompt", "")
            self._render()
            self._notice("Saved. These prompts are active for the next request.", True)
        except Exception as exc:
            self._notice(f"Could not save: {exc}", False)

    def add_step(self):
        try:
            self.steps, self.writer, self.summary, self.group_prompt = self._collect()
        except Exception as exc:
            self._notice(f"Fix the current step numbers first: {exc}", False)
            return
        if len(self.steps) >= 23:
            self._notice("The 23-step limit has been reached.", False)
            return
        occupied = {item["step"] for item in self.steps}
        number = next(value for value in range(1, 24) if value not in occupied)
        self.steps.append({"id": f"step_{int(time.time() * 1000)}", "name": f"Step {number}",
                           "step": number, "prompt": "Analyze the current scene and pass a concise, useful result to the next step.",
                           "temperature": .3, "frequency_penalty": 0.0,
                           "presence_penalty": 0.0, "repetition_penalty": 1.0,
                           "repetition_penalty_range": 0})
        self._render()

    def remove_step(self, target):
        try:
            steps, self.writer, self.summary, self.group_prompt = self._collect()
            self.steps = [item for item in steps if item["id"] != target["id"]]
            self._render()
        except Exception as exc:
            self._notice(f"Could not remove step: {exc}", False)

    def save_preset(self):
        try:
            steps, writer, summary, group_prompt = self._collect()
            name = self.preset_name.get().strip()
            if name == "Preset name":
                name = ""
            body = self._request("/api/presets/save", {
                "name": name, "steps": steps, "writer": writer, "summary": summary,
                "group_prompt": group_prompt})
            self._refresh_presets(body["filename"])
            self._notice(f"{body['filename']} saved in the Preset folder.", True)
        except Exception as exc:
            self._notice(f"Could not save preset: {exc}", False)

    def _load_selected_preset(self, _event=None):
        index = self.preset_box.current()
        if index <= 0:
            return
        filename = self.preset_files[index - 1]
        try:
            body = self._request("/api/presets/load", {"filename": filename})
            self.steps, self.writer, self.summary = body["steps"], body["writer"], body["summary"]
            self.group_prompt = body.get("group_prompt", "")
            self._render()
            self._notice(f"{filename} is now active.", True)
        except Exception as exc:
            self._notice(f"Could not load preset: {exc}", False)

    def import_preset(self):
        path = filedialog.askopenfilename(parent=self, title="Import prompt preset",
                                          filetypes=[("CSV preset", "*.csv")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                csv_text = handle.read()
            filename = os.path.basename(path)
            body = self._request("/api/presets/import", {
                "filename": filename, "csv": csv_text})
            self.steps, self.writer, self.summary = body["steps"], body["writer"], body["summary"]
            self.group_prompt = body.get("group_prompt", "")
            self._refresh_presets(filename)
            self._render()
            self._notice(f"{filename} imported and activated.", True)
        except Exception as exc:
            self._notice(f"Could not import preset: {exc}", False)

    def _notice(self, text, ok):
        self.status.config(text=text, fg=SAGE if ok else ROSE)


class LorebookStudio(tk.Frame):
    """Editor for agent-bound SillyTavern-compatible lorebooks."""

    API_ROOT = f"http://127.0.0.1:{PORT}"

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.loaded = False
        self.books, self.assignments, self.agents = [], {}, []
        self.settings = {}
        self.current_book = None
        self.current_entry = None
        self.open_assignment_bands = set()
        self.wheel_target = "page"
        self.assignment_height = 205
        self._build()

    def _build(self):
        outer_scrollbar = tk.Scrollbar(self, orient="vertical", bg=CARD,
                                       troughcolor=BG, width=12)
        outer_scrollbar.pack(side="right", fill="y")
        self.page_canvas = tk.Canvas(self, bg=BG, highlightthickness=0,
                                     yscrollcommand=outer_scrollbar.set)
        self.page_canvas.pack(side="left", fill="both", expand=True)
        outer_scrollbar.config(command=self.page_canvas.yview)
        self.page = tk.Frame(self.page_canvas, bg=BG)
        self.page_window = self.page_canvas.create_window((0, 0), window=self.page, anchor="nw")
        self.page.bind("<Configure>", lambda _event: self.page_canvas.configure(
            scrollregion=self.page_canvas.bbox("all")))
        self.page_canvas.bind("<Configure>", lambda event: self.page_canvas.itemconfigure(
            self.page_window, width=event.width))
        self.bind_all("<Button-1>", self._choose_wheel_target, add="+")
        self.bind_all("<MouseWheel>", self._on_lore_mousewheel, add="+")

        top = tk.Frame(self.page, bg=BG)
        top.pack(fill="x", padx=20, pady=(16, 10))
        tk.Label(top, text="Lorebooks", bg=BG, fg=AMBER, font=FONT_T).pack(side="left")
        self.status = tk.Label(top, text="Agent-bound World Info", bg=BG, fg=MUTED, font=FONT)
        self.status.pack(side="left", padx=14)
        self._button(top, "Apply", self.save, True).pack(side="right")
        self._button(top, "Import ST JSON", self.import_json).pack(side="right", padx=6)

        settings = tk.Frame(self.page, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        settings.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(settings, text="Default scan depth", bg=CARD, fg=MUTED, font=FONT).pack(side="left", padx=(12, 5), pady=8)
        self.scan_depth = tk.Entry(settings, width=6, bg="#0b100d", fg=INK, insertbackground=INK, relief="flat")
        self.scan_depth.pack(side="left", ipady=4)
        tk.Label(settings, text="Token budget / agent", bg=CARD, fg=MUTED, font=FONT).pack(side="left", padx=(18, 5))
        self.token_budget = tk.Entry(settings, width=8, bg="#0b100d", fg=INK, insertbackground=INK, relief="flat")
        self.token_budget.pack(side="left", ipady=4)
        self.case_var = tk.BooleanVar()
        self.whole_var = tk.BooleanVar()
        self.recursive_var = tk.BooleanVar()
        tk.Checkbutton(settings, text="Case sensitive", variable=self.case_var, bg=CARD, fg=SAGE,
                       selectcolor=BG, activebackground=CARD).pack(side="left", padx=14)
        tk.Checkbutton(settings, text="Whole words", variable=self.whole_var, bg=CARD, fg=SAGE,
                       selectcolor=BG, activebackground=CARD).pack(side="left")
        tk.Checkbutton(settings, text="Recursive", variable=self.recursive_var, bg=CARD, fg=SAGE,
                       selectcolor=BG, activebackground=CARD).pack(side="left", padx=10)

        assignment_header = tk.Frame(self.page, bg=BG)
        assignment_header.pack(fill="x", padx=20, pady=(0, 5))
        tk.Label(assignment_header, text="AGENT LOREBOOK ASSIGNMENTS", bg=BG, fg=AMBER,
                 font=FONT_S, anchor="w").pack(side="left")
        tk.Label(assignment_header,
                 text="Open an agent, then move lorebooks between Assigned and Available. Apply to save.",
                 bg=BG, fg=MUTED, font=("Meiryo UI", 8), anchor="w").pack(side="left", padx=12)
        assignment_wrap = tk.Frame(self.page, bg=BG, highlightbackground=BORDER,
                                   highlightthickness=1)
        assignment_wrap.pack(fill="x", padx=20, pady=(0, 10))
        assignment_scroll = tk.Scrollbar(assignment_wrap, orient="vertical", bg=CARD,
                                         troughcolor=BG, width=11)
        assignment_scroll.pack(side="right", fill="y")
        self.assignment_wrap = assignment_wrap
        self.assignment_canvas = tk.Canvas(
            assignment_wrap, bg=BG, height=self.assignment_height, highlightthickness=0,
            yscrollcommand=assignment_scroll.set)
        self.assignment_canvas.pack(side="left", fill="x", expand=True)
        assignment_scroll.config(command=self.assignment_canvas.yview)
        self.assignment_bands = tk.Frame(self.assignment_canvas, bg=BG)
        self.assignment_window = self.assignment_canvas.create_window(
            (0, 0), window=self.assignment_bands, anchor="nw")
        self.assignment_bands.bind(
            "<Configure>", lambda _event: self.assignment_canvas.configure(
                scrollregion=self.assignment_canvas.bbox("all")))
        self.assignment_canvas.bind(
            "<Configure>", lambda event: self.assignment_canvas.itemconfigure(
                self.assignment_window, width=event.width))

        self.assignment_grip = tk.Label(
            assignment_wrap, text="◢", bg=BG, fg=AMBER, font=("Meiryo UI", 10),
            cursor="sizing", padx=2, pady=0)
        self.assignment_grip.place(relx=1.0, rely=1.0, anchor="se")
        self.assignment_grip.bind("<Button-1>", self._start_assignment_resize)
        self.assignment_grip.bind("<B1-Motion>", self._resize_assignment)

        panes = tk.PanedWindow(self.page, orient="horizontal", bg=BG, sashwidth=5,
                               relief="flat", height=650)
        panes.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        left, middle, right = (tk.Frame(panes, bg=CARD, highlightbackground=BORDER, highlightthickness=1) for _ in range(3))
        panes.add(left, minsize=180, width=210); panes.add(middle, minsize=210, width=245); panes.add(right, minsize=330)

        self._section_title(left, "LOREBOOKS")
        self.book_list = tk.Listbox(left, bg="#0b100d", fg=INK, selectbackground="#405347", relief="flat", exportselection=False)
        self.book_list.pack(fill="both", expand=True, padx=8, pady=6)
        self.book_list.bind("<<ListboxSelect>>", self._select_book)
        row = tk.Frame(left, bg=CARD); row.pack(fill="x", padx=8, pady=(0, 8))
        self._button(row, "+ Book", self.add_book).pack(side="left")
        self._button(row, "Delete", self.delete_book).pack(side="right")

        self._section_title(middle, "ENTRIES")
        self.book_name = tk.Entry(middle, bg="#0b100d", fg=INK, insertbackground=INK, relief="flat", font=FONT_B)
        self.book_name.pack(fill="x", padx=8, pady=(2, 6), ipady=5)
        self.book_name.bind("<FocusOut>", self._commit_book_name)
        self.book_name.bind("<Return>", self._commit_book_name)
        self.entry_list = tk.Listbox(middle, bg="#0b100d", fg=INK, selectbackground="#405347", relief="flat", exportselection=False)
        self.entry_list.pack(fill="both", expand=True, padx=8, pady=6)
        self.entry_list.bind("<<ListboxSelect>>", self._select_entry)
        row = tk.Frame(middle, bg=CARD); row.pack(fill="x", padx=8, pady=(0, 8))
        self._button(row, "+ Entry", self.add_entry).pack(side="left")
        self._button(row, "Delete", self.delete_entry).pack(side="right")

        self._section_title(right, "ENTRY EDITOR")
        form = tk.Frame(right, bg=CARD); form.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.entry_name = self._field(form, "Entry name")
        self.keys = self._field(form, "Primary keys (comma-separated)")
        self.secondary = self._field(form, "Secondary keys")
        opts = tk.Frame(form, bg=CARD); opts.pack(fill="x", pady=4)
        self.constant_var = tk.BooleanVar(); self.enabled_var = tk.BooleanVar(value=True); self.selective_var = tk.BooleanVar()
        for label, var in (("Constant", self.constant_var), ("Enabled", self.enabled_var), ("Secondary condition", self.selective_var)):
            tk.Checkbutton(opts, text=label, variable=var, bg=CARD, fg=SAGE, selectcolor=BG,
                           activebackground=CARD).pack(side="left", padx=(0, 10))
        modes = tk.Frame(form, bg=CARD); modes.pack(fill="x", pady=3)
        tk.Label(modes, text="Secondary logic", bg=CARD, fg=MUTED, font=FONT_S).pack(side="left")
        self.logic_box = ttk.Combobox(modes, state="readonly", width=9,
                                      values=("AND ANY", "NOT ALL", "NOT ANY", "AND ALL"))
        self.logic_box.current(0); self.logic_box.pack(side="left", padx=(5, 12))
        tk.Label(modes, text="Case", bg=CARD, fg=MUTED, font=FONT_S).pack(side="left")
        self.entry_case = ttk.Combobox(modes, state="readonly", width=7, values=("Default", "Yes", "No"))
        self.entry_case.current(0); self.entry_case.pack(side="left", padx=(5, 12))
        tk.Label(modes, text="Whole word", bg=CARD, fg=MUTED, font=FONT_S).pack(side="left")
        self.entry_whole = ttk.Combobox(modes, state="readonly", width=7, values=("Default", "Yes", "No"))
        self.entry_whole.current(0); self.entry_whole.pack(side="left", padx=5)
        nums = tk.Frame(form, bg=CARD); nums.pack(fill="x", pady=3)
        self.order = self._small_field(nums, "Order", "0")
        self.entry_depth = self._small_field(nums, "Scan depth", "")
        self.probability = self._small_field(nums, "Probability %", "100")
        tk.Label(form, text="Content · macros: {{user}}, {{char}}, {{groupchar}}, {{allchar}}",
                 bg=CARD, fg=MUTED, font=FONT_S, anchor="w").pack(fill="x", pady=(6, 3))
        self.content = tk.Text(form, bg="#0b100d", fg=INK, insertbackground=INK, selectbackground="#405347",
                               relief="flat", wrap="word", font=FONT_LOG, height=10, padx=8, pady=7)
        self.content.pack(fill="both", expand=True)
        self._button(form, "Update entry", self.commit_entry).pack(anchor="e", pady=(7, 4))

    @staticmethod
    def _is_descendant(widget, ancestor):
        current = widget
        while current is not None:
            if current == ancestor:
                return True
            current = getattr(current, "master", None)
        return False

    def _choose_wheel_target(self, event):
        if not self.winfo_ismapped() or not self._is_descendant(event.widget, self):
            return
        self.wheel_target = (
            "assignments" if self._is_descendant(event.widget, self.assignment_wrap)
            else "page")

    def _on_lore_mousewheel(self, event):
        if not self.winfo_ismapped():
            return
        units = int(-event.delta / 120) if event.delta else 0
        if not units:
            units = -1 if event.delta > 0 else 1
        if self.wheel_target == "assignments":
            self.assignment_canvas.yview_scroll(units, "units")
        else:
            self.page_canvas.yview_scroll(units, "units")
        return "break"

    def _start_assignment_resize(self, event):
        self.wheel_target = "assignments"
        self._resize_start_y = event.y_root
        self._resize_start_height = self.assignment_canvas.winfo_height()
        return "break"

    def _resize_assignment(self, event):
        delta = event.y_root - self._resize_start_y
        self.assignment_height = max(120, min(600, self._resize_start_height + delta))
        self.assignment_canvas.configure(height=self.assignment_height)
        self.page.update_idletasks()
        self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all"))
        return "break"

    @staticmethod
    def _section_title(parent, text):
        tk.Label(parent, text=text, bg=CARD, fg=AMBER, font=FONT_S, anchor="w").pack(fill="x", padx=9, pady=(9, 3))

    @staticmethod
    def _field(parent, label):
        tk.Label(parent, text=label, bg=CARD, fg=MUTED, font=FONT_S, anchor="w").pack(fill="x", pady=(3, 2))
        widget = tk.Entry(parent, bg="#0b100d", fg=INK, insertbackground=INK, relief="flat")
        widget.pack(fill="x", ipady=4)
        return widget

    @staticmethod
    def _small_field(parent, label, default):
        box = tk.Frame(parent, bg=CARD); box.pack(side="left", fill="x", expand=True, padx=(0, 7))
        tk.Label(box, text=label, bg=CARD, fg=MUTED, font=FONT_S).pack(anchor="w")
        widget = tk.Entry(box, bg="#0b100d", fg=INK, insertbackground=INK, relief="flat", width=8)
        widget.insert(0, default); widget.pack(fill="x", ipady=3)
        return widget

    @staticmethod
    def _button(parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=AMBER if primary else CARD,
                         fg="#20241c" if primary else SAGE, activebackground=BORDER,
                         relief="flat", font=FONT_B, padx=11, pady=6, cursor="hand2")

    def _request(self, path, payload=None):
        data, headers, method = None, {}, "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"; method = "POST"
        request = urllib.request.Request(self.API_ROOT + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            detail = str(exc)
            if hasattr(exc, "read"):
                try: detail = json.loads(exc.read().decode("utf-8")).get("detail") or detail
                except Exception: pass
            raise RuntimeError(detail) from exc

    def show(self):
        if not self.loaded: self.load()

    def load(self):
        try:
            body = self._request("/api/lorebooks")
            self.books = body.get("books", []); self.assignments = body.get("assignments", {})
            self.settings = body.get("settings", {}); self.agents = body.get("agents", [])
            self.scan_depth.delete(0, "end"); self.scan_depth.insert(0, self.settings.get("scan_depth", 2))
            self.token_budget.delete(0, "end"); self.token_budget.insert(0, self.settings.get("token_budget", 2048))
            self.case_var.set(self.settings.get("case_sensitive", False)); self.whole_var.set(self.settings.get("match_whole_words", False))
            self.recursive_var.set(self.settings.get("recursive", False))
            self.loaded = True; self._render_assignment_bands(); self._render_books(); self.status.config(text="Lorebooks loaded", fg=SAGE)
        except Exception as exc: self.status.config(text=f"Could not load: {exc}", fg=ROSE)

    def _render_books(self, select=0):
        self.book_list.delete(0, "end")
        for book in self.books: self.book_list.insert("end", book["name"])
        if self.books:
            select = min(select, len(self.books)-1); self.book_list.selection_set(select); self._select_book()
        else:
            self.current_book = None; self.entry_list.delete(0, "end"); self.book_name.delete(0, "end")

    def _select_book(self, _event=None):
        selection = self.book_list.curselection()
        if not selection: return
        self.current_book = self.books[selection[0]]; self.current_entry = None
        self.book_name.delete(0, "end"); self.book_name.insert(0, self.current_book["name"])
        self.entry_list.delete(0, "end")
        for entry in self.current_book["entries"]: self.entry_list.insert("end", entry["name"])
        if self.current_book["entries"]:
            self.entry_list.selection_set(0); self._select_entry()

    def _select_entry(self, _event=None):
        selection = self.entry_list.curselection()
        if not selection or not self.current_book: return
        self.current_entry = self.current_book["entries"][selection[0]]
        values = ((self.entry_name, self.current_entry["name"]), (self.keys, ", ".join(self.current_entry["keys"])),
                  (self.secondary, ", ".join(self.current_entry["secondary_keys"])), (self.order, self.current_entry["order"]),
                  (self.entry_depth, self.current_entry.get("scan_depth") or ""), (self.probability, self.current_entry.get("probability", 100)))
        for widget, value in values: widget.delete(0, "end"); widget.insert(0, value)
        self.constant_var.set(self.current_entry.get("constant", False)); self.enabled_var.set(self.current_entry.get("enabled", True))
        self.selective_var.set(self.current_entry.get("selective", False)); self.content.delete("1.0", "end"); self.content.insert("1.0", self.current_entry["content"])
        self.logic_box.current(max(0, min(3, int(self.current_entry.get("selective_logic", 0)))))
        self.entry_case.current(0 if self.current_entry.get("case_sensitive") is None else (1 if self.current_entry["case_sensitive"] else 2))
        self.entry_whole.current(0 if self.current_entry.get("match_whole_words") is None else (1 if self.current_entry["match_whole_words"] else 2))

    def _commit_book_name(self, _event=None):
        if self.current_book:
            name = self.book_name.get().strip()
            if name:
                self.current_book["name"] = name
                selection = self.book_list.curselection()
                if selection:
                    index = selection[0]; self.book_list.delete(index); self.book_list.insert(index, name); self.book_list.selection_set(index)
                self._render_assignment_bands()
        return "break" if _event and getattr(_event, "keysym", "") == "Return" else None

    def _agent_band_title(self, agent):
        step = agent.get("step")
        return f"Step {step} · {agent['name']}" if isinstance(step, int) else f"Writer · {agent['name']}"

    def _render_assignment_bands(self):
        for child in self.assignment_bands.winfo_children():
            child.destroy()
        books_by_id = {book["id"]: book for book in self.books}
        for agent in self.agents:
            agent_id = str(agent["id"])
            card = tk.Frame(self.assignment_bands, bg=CARD, highlightbackground=BORDER,
                            highlightthickness=1)
            card.pack(fill="x", pady=(0, 5))
            expanded = agent_id in self.open_assignment_bands
            header = tk.Button(
                card, text=("▾  " if expanded else "▸  ") + self._agent_band_title(agent),
                bg=CARD, fg=INK, activebackground="#213027", activeforeground=AMBER,
                relief="flat", font=FONT_B, anchor="w", padx=12, pady=7,
                command=lambda target=agent_id: self._toggle_assignment_band(target))
            header.pack(fill="x")
            if not expanded:
                continue
            body = tk.Frame(card, bg="#101713")
            body.pack(fill="x", padx=8, pady=(0, 8))
            assigned_ids = [book_id for book_id in self.assignments.get(agent_id, [])
                            if book_id in books_by_id]
            self._assignment_window(
                body, "ASSIGNED · applied from left to right", assigned_ids, books_by_id,
                lambda book_id, target=agent_id: self._unassign_book(target, book_id), True)
            available_ids = [book["id"] for book in self.books if book["id"] not in assigned_ids]
            self._assignment_window(
                body, "AVAILABLE LOREBOOKS", available_ids, books_by_id,
                lambda book_id, target=agent_id: self._assign_book(target, book_id), False)

    def _assignment_window(self, parent, label, book_ids, books_by_id, command, removable):
        tk.Label(parent, text=label, bg="#101713", fg=AMBER if removable else MUTED,
                 font=FONT_S, anchor="w").pack(fill="x", padx=7, pady=(7, 3))
        window = tk.Frame(parent, bg="#090d0b", highlightbackground=BORDER,
                          highlightthickness=1)
        window.pack(fill="x", padx=7, pady=(0, 3))
        if not book_ids:
            tk.Label(window, text="None", bg="#090d0b", fg=MUTED,
                     font=("Meiryo UI", 8), anchor="w").grid(
                         row=0, column=0, sticky="w", padx=8, pady=7)
            return
        for index, book_id in enumerate(book_ids):
            book = books_by_id[book_id]
            chip = tk.Frame(window, bg="#1b2921", highlightbackground="#385142",
                            highlightthickness=1)
            chip.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
            window.grid_columnconfigure(index % 3, weight=1)
            tk.Button(chip, text=book["name"], bg="#1b2921", fg=INK,
                      activebackground="#2a4033", activeforeground=AMBER,
                      relief="flat", anchor="w", font=FONT, padx=8, pady=4,
                      command=(None if removable else lambda value=book_id: command(value))).pack(
                          side="left", fill="x", expand=True)
            if removable:
                tk.Button(chip, text="×", bg="#1b2921", fg=ROSE,
                          activebackground="#462923", activeforeground=INK,
                          relief="flat", font=FONT_B, padx=7, pady=4,
                          command=lambda value=book_id: command(value)).pack(side="right")

    def _toggle_assignment_band(self, agent_id):
        if agent_id in self.open_assignment_bands:
            self.open_assignment_bands.remove(agent_id)
        else:
            self.open_assignment_bands.add(agent_id)
        self._render_assignment_bands()

    def _assign_book(self, agent_id, book_id):
        current = self.assignments.setdefault(agent_id, [])
        if book_id not in current:
            current.append(book_id)
        self.status.config(text="Assignment updated locally · Apply to save", fg=AMBER)
        self._render_assignment_bands()

    def _unassign_book(self, agent_id, book_id):
        current = self.assignments.setdefault(agent_id, [])
        if book_id in current:
            current.remove(book_id)
        self.status.config(text="Assignment removed locally · Apply to save", fg=AMBER)
        self._render_assignment_bands()

    def commit_entry(self):
        if not self.current_entry: return
        try:
            depth = self.entry_depth.get().strip()
            self.current_entry.update({"name": self.entry_name.get().strip(), "content": self.content.get("1.0", "end-1c").strip(),
                "keys": [x.strip() for x in self.keys.get().split(",") if x.strip()],
                "secondary_keys": [x.strip() for x in self.secondary.get().split(",") if x.strip()],
                "constant": self.constant_var.get(), "enabled": self.enabled_var.get(), "selective": self.selective_var.get(),
                "selective_logic": self.logic_box.current(),
                "case_sensitive": None if self.entry_case.current() == 0 else self.entry_case.current() == 1,
                "match_whole_words": None if self.entry_whole.current() == 0 else self.entry_whole.current() == 1,
                "order": int(self.order.get() or 0), "scan_depth": int(depth) if depth else None,
                "probability": int(self.probability.get() or 100), "use_probability": int(self.probability.get() or 100) < 100})
            index = self.current_book["entries"].index(self.current_entry); self.entry_list.delete(index); self.entry_list.insert(index, self.current_entry["name"]); self.entry_list.selection_set(index)
            self.status.config(text="Entry updated locally · Apply to save", fg=AMBER)
        except Exception as exc: self.status.config(text=f"Invalid entry: {exc}", fg=ROSE)

    def add_book(self):
        book = {"id": f"book_{int(time.time()*1000)}", "name": "New Lorebook", "entries": []}
        self.books.append(book); self._render_assignment_bands(); self._render_books(len(self.books)-1)

    def delete_book(self):
        if not self.current_book or not messagebox.askyesno("Delete lorebook", f"Delete {self.current_book['name']}?", parent=self): return
        book_id = self.current_book["id"]; self.books.remove(self.current_book)
        for agent_id in list(self.assignments): self.assignments[agent_id] = [x for x in self.assignments[agent_id] if x != book_id]
        self._render_assignment_bands(); self._render_books()

    def add_entry(self):
        if not self.current_book: return
        entry = {"id": f"entry_{int(time.time()*1000)}", "name": "New Entry", "content": "Enter lore here.", "keys": [], "secondary_keys": [],
                 "constant": True, "selective": False, "selective_logic": 0, "enabled": True, "order": 0, "scan_depth": None,
                 "case_sensitive": None, "match_whole_words": None, "use_probability": False, "probability": 100, "extensions": {}}
        self.current_book["entries"].append(entry); self._select_book(); self.entry_list.selection_clear(0, "end"); self.entry_list.selection_set(len(self.current_book["entries"])-1); self._select_entry()

    def delete_entry(self):
        if self.current_book and self.current_entry and messagebox.askyesno("Delete entry", f"Delete {self.current_entry['name']}?", parent=self):
            self.current_book["entries"].remove(self.current_entry); self._select_book()

    def _collect_assignments(self):
        if self.current_book:
            self.current_book["name"] = self.book_name.get().strip()
        return {key: value for key, value in self.assignments.items() if value}

    def save(self):
        try:
            self.commit_entry(); assignments = self._collect_assignments()
            settings = {**self.settings, "scan_depth": int(self.scan_depth.get()), "token_budget": int(self.token_budget.get()),
                        "case_sensitive": self.case_var.get(), "match_whole_words": self.whole_var.get(),
                        "recursive": self.recursive_var.get()}
            body = self._request("/api/lorebooks", {"version": 1, "settings": settings, "books": self.books, "assignments": assignments})
            self.books, self.assignments, self.settings = body["books"], body["assignments"], body["settings"]
            self._render_assignment_bands(); self._render_books(); self.status.config(text="Saved · active for the next request", fg=SAGE)
        except Exception as exc: self.status.config(text=f"Could not save: {exc}", fg=ROSE)

    def import_json(self):
        path = filedialog.askopenfilename(parent=self, title="Import SillyTavern World Info", filetypes=[("JSON", "*.json")])
        if not path: return
        try:
            with open(path, "r", encoding="utf-8-sig") as handle: data = json.load(handle)
            body = self._request("/api/lorebooks/import", {"name": os.path.splitext(os.path.basename(path))[0], "data": data})
            book = body["book"]
            existing = next((item for item in self.books if item["name"] == book["name"]), None)
            if existing and messagebox.askyesno("Replace lorebook", f"Replace existing {book['name']}?", parent=self):
                book["id"] = existing["id"]; self.books[self.books.index(existing)] = book
            elif existing:
                book["name"] += " (imported)"; self.books.append(book)
            else: self.books.append(book)
            self._render_assignment_bands(); self._render_books(self.books.index(book)); self.status.config(text="Imported locally · Apply to save", fg=AMBER)
        except Exception as exc: self.status.config(text=f"Import failed: {exc}", fg=ROSE)


class PromptAssistant(tk.Frame):
    """Chat UI for discussing active prompts with the connected main LLM."""

    API_ROOT = f"http://127.0.0.1:{PORT}"

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.messages = []
        self.busy = False
        self.context_loaded = False
        self.context_loading = False
        self.stream_queue = queue.Queue()
        self.current_reply = ""
        self.agent_list = []
        self.order_widgets = {}
        self._build()

    def _build(self):
        page_scrollbar = tk.Scrollbar(
            self, orient="vertical", bg=CARD, troughcolor=BG, width=12)
        page_scrollbar.pack(side="right", fill="y")
        self.page_canvas = tk.Canvas(
            self, bg=BG, highlightthickness=0, bd=0,
            yscrollcommand=page_scrollbar.set)
        self.page_canvas.pack(side="left", fill="both", expand=True)
        page_scrollbar.config(command=self.page_canvas.yview)
        page = tk.Frame(self.page_canvas, bg=BG)
        self.page_window = self.page_canvas.create_window(
            (0, 0), window=page, anchor="nw")
        page.bind(
            "<Configure>",
            lambda _event: self.page_canvas.configure(
                scrollregion=self.page_canvas.bbox("all")))
        self.page_canvas.bind(
            "<Configure>",
            lambda event: self.page_canvas.itemconfigure(
                self.page_window, width=event.width))

        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(header, text="PromptAssistant", bg=BG, fg=AMBER,
                 font=FONT_T, anchor="w").pack(fill="x")
        tk.Label(
            header,
            text="Discuss prompt changes using the active Prompt Studio settings and each agent's latest three outputs.",
            bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(3, 0))
        self.context_status = tk.Label(header, text="Context has not been checked yet.",
                                       bg=BG, fg=MUTED, font=FONT_S, anchor="w")
        self.context_status.pack(fill="x", pady=(8, 0))

        settings = tk.Frame(header, bg=BG)
        settings.pack(fill="x", pady=(10, 0))
        self.max_tokens_control = self._assistant_setting(
            settings, "Output range (tokens)", 512, 8192, 1, 2200, True)
        self.temperature_control = self._assistant_setting(
            settings, "Temperature", 0.0, 1.5, .05, .4, False)

        order_section = tk.Frame(header, bg=BG)
        order_section.pack(fill="x", pady=(10, 0))
        order_toolbar = tk.Frame(order_section, bg=BG)
        order_toolbar.pack(fill="x", pady=(0, 5))
        tk.Label(order_toolbar, text="TEMPORARY ORDERS", bg=BG, fg=SAGE,
                 font=FONT_S, anchor="w").pack(side="left")
        self.order_status = tk.Label(
            order_toolbar, text="入力した内容は次の各リクエストでだけプロンプト末尾に追加されます。",
            bg=BG, fg=MUTED, font=("Meiryo UI", 8), anchor="w")
        self.order_status.pack(side="left", fill="x", expand=True, padx=(10, 8))
        self.order_save_button = tk.Button(
            order_toolbar, text="一時オーダーを反映", bg=CARD, fg=AMBER,
            activebackground=BORDER, activeforeground=INK, relief="flat",
            font=("Meiryo UI", 8, "bold"), cursor="hand2",
            command=self._save_orders)
        self.order_save_button.pack(side="right")
        self.orders_frame = tk.Frame(order_section, bg=BG)
        self.orders_frame.pack(fill="x")

        chat_wrap = tk.Frame(page, bg="#090d0b", highlightbackground=BORDER,
                             highlightthickness=1)
        chat_wrap.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        bar = tk.Scrollbar(chat_wrap, orient="vertical", bg=CARD, troughcolor=BG, width=12)
        bar.pack(side="right", fill="y")
        self.chat = tk.Text(chat_wrap, bg="#090d0b", fg=INK, relief="flat",
                            wrap="word", font=FONT_LOG, padx=16, pady=14,
                            selectbackground="#405347", selectforeground=INK,
                            yscrollcommand=bar.set, state="disabled")
        self.chat.pack(side="left", fill="both", expand=True)
        bar.config(command=self.chat.yview)
        self.chat.tag_configure("user_label", foreground=AMBER, font=FONT_B,
                                spacing1=10, spacing3=3)
        self.chat.tag_configure("assistant_label", foreground=SAGE, font=FONT_B,
                                spacing1=14, spacing3=3)
        self.chat.tag_configure("message", foreground=INK, lmargin1=8, lmargin2=8,
                                spacing3=8)
        # Keep Markdown fonts Japanese-capable. Segoe UI can render Latin text but
        # shows replacement boxes for Japanese glyphs on some Windows installs.
        self.chat.tag_configure("md_h1", foreground=AMBER,
                                font=("Meiryo UI", 16, "bold"), spacing1=14, spacing3=7)
        self.chat.tag_configure("md_h2", foreground=AMBER,
                                font=("Meiryo UI", 13, "bold"), spacing1=12, spacing3=5)
        self.chat.tag_configure("md_h3", foreground=SAGE,
                                font=("Meiryo UI", 11, "bold"), spacing1=10, spacing3=4)
        self.chat.tag_configure("md_bold", foreground=INK, font=("Meiryo UI", 9, "bold"))
        self.chat.tag_configure("md_italic", foreground=INK, font=("Meiryo UI", 9, "italic"))
        self.chat.tag_configure("md_code", foreground="#d8c898", background="#131b17",
                                font=FONT_LOG)
        self.chat.tag_configure("md_code_block", foreground="#d8c898", background="#131b17",
                                font=FONT_LOG, lmargin1=18, lmargin2=18, spacing1=6, spacing3=6)
        self.chat.tag_configure("md_quote", foreground=SAGE, lmargin1=22, lmargin2=22,
                                spacing1=4, spacing3=4)
        self.chat.tag_configure("md_list", foreground=INK, lmargin1=22, lmargin2=38,
                                spacing1=2, spacing3=2)
        self.chat.tag_configure("md_link", foreground="#8fb8d8", underline=True)
        self.chat.tag_configure("md_table", foreground=INK, background="#101713",
                                font=("MS Gothic", 9), lmargin1=12, lmargin2=12)
        self.chat.tag_configure("md_table_head", foreground=AMBER, background="#18211c",
                                font=("MS Gothic", 9, "bold"), lmargin1=12, lmargin2=12)
        self.chat.tag_configure("md_rule", foreground=BORDER, spacing1=5, spacing3=5)

        compose = tk.Frame(page, bg=BG)
        compose.pack(fill="x", padx=24, pady=(0, 20))
        input_wrap = tk.Frame(compose, bg="#0b100d", highlightbackground=BORDER,
                              highlightthickness=1)
        input_wrap.pack(side="left", fill="both", expand=True)
        self.input = tk.Text(input_wrap, height=4, bg="#0b100d", fg=INK,
                             insertbackground=INK, selectbackground="#405347",
                             relief="flat", wrap="word", font=FONT_LOG, padx=10, pady=8)
        self.input.pack(fill="both", expand=True)
        self.input.bind("<Return>", self._handle_input_return)

        buttons = tk.Frame(compose, bg=BG)
        buttons.pack(side="right", fill="y", padx=(10, 0))
        self.send_button = tk.Button(
            buttons, text="Send", bg=AMBER, fg="#20241c",
            activebackground="#f2d492", relief="flat", font=FONT_B,
            width=12, pady=8, cursor="hand2", command=self.send)
        self.send_button.pack(fill="x")
        tk.Button(buttons, text="Clear chat", bg=CARD, fg=MUTED,
                  activebackground=BORDER, activeforeground=INK, relief="flat",
                  font=FONT_B, width=12, pady=7, cursor="hand2",
                  command=self.clear).pack(fill="x", pady=(8, 0))
        tk.Label(buttons, text="Enter: send\nShift+Enter: new line", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8), justify="center").pack(pady=(8, 0))

        self._reset_chat_with_greeting()
        self._bind_page_mousewheel_tree(page)

    def _bind_page_mousewheel_tree(self, widget):
        # The chat transcript keeps Text's native wheel behavior. Everywhere
        # else in PromptAssistant scrolls the surrounding page.
        if widget is self.chat:
            return
        widget.bind("<MouseWheel>", self._on_page_mousewheel)
        for child in widget.winfo_children():
            self._bind_page_mousewheel_tree(child)

    def _on_page_mousewheel(self, event):
        self.page_canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def _greeting(self):
        introduction = (
            "現在のプロンプトと各エージェントの直近3出力を参照しながら、"
            "変更方針を一緒に検討できます。\n\n"
            "上部の「TEMPORARY ORDERS」では、対象プロンプトの帯を開いて文面を入力し、"
            "「一時オーダーを反映」を押すことで、保存済みのプロンプト構成を維持したまま、"
            "そのブレインに一時的な指示や変化を加えられます。元のプロンプトやプリセットは"
            "書き換わりません。実現したい変化を教えていただければ、どのオーダー欄へ何を"
            "入力するか、コピーできる文面まで一緒に考えます。\n\n")
        if not self.agent_list:
            listing = "現在のプロンプト一覧を読み込んでいます…"
        else:
            labels = []
            for agent in self.agent_list:
                if agent.get("step") is not None:
                    kind = f"Step {agent['step']}"
                elif agent.get("id") == "writer":
                    kind = "Writer"
                elif agent.get("id") == "summary":
                    kind = "Summarize"
                else:
                    kind = "Fixed"
                labels.append(f"・{kind}: {agent['name']}")
            listing = "現在Prompt Studioに設定されているプロンプト:\n" + "\n".join(labels)
        return (
            introduction + listing
            + "\n\n現在の構成で気になっている点、または一時オーダーで試したい変化があれば教えてください。")

    def _render_order_bands(self):
        for child in self.orders_frame.winfo_children():
            child.destroy()
        self.order_widgets = {}
        for agent in self.agent_list:
            agent_id = str(agent["id"])
            if agent.get("step") is not None:
                prefix = f"Step {agent['step']}"
            elif agent_id == "writer":
                prefix = "Writer"
            elif agent_id == "summary":
                prefix = "Summarize"
            else:
                prefix = "Prompt"
            card = tk.Frame(self.orders_frame, bg=CARD, highlightbackground=BORDER,
                            highlightthickness=1)
            card.pack(fill="x", pady=2)
            body = tk.Frame(card, bg="#0b100d")
            text = tk.Text(body, height=4, bg="#0b100d", fg=INK,
                           insertbackground=INK, selectbackground="#405347",
                           relief="flat", wrap="word", font=FONT_LOG, padx=10, pady=8)
            text.pack(fill="x")
            text.insert("1.0", agent.get("order", ""))
            title = f"{prefix} · {agent['name']}"
            button = tk.Button(
                card, text=f"▸  {title}", bg=CARD, fg=INK,
                activebackground=BORDER, activeforeground=INK, relief="flat",
                anchor="w", font=("Meiryo UI", 9, "bold"), padx=10, pady=5,
                cursor="hand2")
            button.pack(fill="x")
            button.config(command=lambda b=button, p=body, label=title:
                          self._toggle_order_band(b, p, label))
            self.order_widgets[agent_id] = text
        self._bind_page_mousewheel_tree(self.orders_frame)

    @staticmethod
    def _toggle_order_band(button, body, title):
        if body.winfo_manager():
            body.pack_forget()
            button.config(text=f"▸  {title}")
        else:
            body.pack(fill="x")
            button.config(text=f"▾  {title}")
            body.winfo_children()[0].focus_set()

    def _save_orders(self):
        if not self.order_widgets:
            return
        orders = {
            agent_id: widget.get("1.0", "end-1c").strip()
            for agent_id, widget in self.order_widgets.items()
        }
        self.order_save_button.config(state="disabled", text="反映中…")
        self.order_status.config(text="一時オーダーを反映しています…", fg=AMBER)

        def work():
            try:
                body = self._request("/api/prompt-assistant/orders", {"orders": orders})
                self.after(0, lambda: self._finish_order_save(body.get("orders", {}), None))
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda message=error: self._finish_order_save(None, message))
        threading.Thread(target=work, daemon=True).start()

    def _finish_order_save(self, orders, error):
        self.order_save_button.config(state="normal", text="一時オーダーを反映")
        if error:
            self.order_status.config(text=f"反映できませんでした: {error}", fg=ROSE)
            return
        active_count = len(orders or {})
        self.order_status.config(
            text=(f"{active_count}件の一時オーダーを反映中。"
                  if active_count else "一時オーダーはすべて解除されています。"),
            fg=SAGE)

    def _assistant_setting(self, parent, label, minimum, maximum, resolution,
                           value, integer):
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(side="left", fill="x", expand=True, padx=(0, 8) if integer else (8, 0))
        row = tk.Frame(card, bg=CARD)
        row.pack(fill="x", padx=10, pady=(7, 2))
        tk.Label(row, text=label, bg=CARD, fg=MUTED, font=FONT_S,
                 width=21, anchor="w").pack(side="left")
        variable = tk.StringVar(value=str(int(value)) if integer else f"{float(value):.2f}")
        entry = tk.Entry(row, textvariable=variable, bg="#0b100d", fg=AMBER,
                         insertbackground=INK, selectbackground="#405347",
                         relief="flat", font=FONT_B, width=8, justify="right")
        entry.pack(side="right", ipady=3)
        error = tk.Label(card, text="", bg=CARD, fg=ROSE, font=("Segoe UI", 8),
                         anchor="w")
        error.pack(fill="x", padx=10, pady=(0, 5))

        def update(raw):
            variable.set(str(int(float(raw))) if integer else f"{float(raw):.2f}")
            error.config(text="")
        scale = tk.Scale(row, from_=minimum, to=maximum, resolution=resolution,
                         orient="horizontal", showvalue=False, bg=CARD,
                         troughcolor="#0b100d", activebackground=AMBER,
                         highlightthickness=0, bd=0, command=update)
        scale.set(value)
        scale.pack(side="right", fill="x", expand=True, padx=(10, 6))
        control = {
            "label": label, "minimum": minimum, "maximum": maximum,
            "resolution": resolution, "integer": integer, "variable": variable,
            "entry": entry, "scale": scale, "error": error,
        }
        entry.bind("<Return>", lambda _e: self._commit_assistant_setting(control))
        return control

    def _commit_assistant_setting(self, control):
        try:
            value = float(control["entry"].get().strip())
        except ValueError:
            control["error"].config(text=f"{control['label']} must be a number.")
            return None
        if value < control["minimum"] or value > control["maximum"]:
            control["error"].config(
                text=f"Enter a value from {control['minimum']} to {control['maximum']}.")
            return None
        if control["integer"]:
            value = int(round(value))
        else:
            resolution = float(control["resolution"])
            value = round(round(value / resolution) * resolution, 2)
        control["scale"].set(value)
        control["variable"].set(
            str(int(value)) if control["integer"] else f"{float(value):.2f}")
        control["error"].config(text="")
        return value

    def _handle_input_return(self, event):
        if event.state & 0x0001:
            return None
        return self.send()

    def _request(self, path, payload=None):
        data = None
        headers = {}
        method = "GET"
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            method = "POST"
        request = urllib.request.Request(self.API_ROOT + path, data=data,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            detail = str(exc)
            if hasattr(exc, "read"):
                try:
                    detail = json.loads(exc.read().decode("utf-8")).get("detail") or detail
                except Exception:
                    pass
            raise RuntimeError(detail) from exc

    def _stream_request(self, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.API_ROOT + "/api/prompt-assistant/stream", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        terminal_received = False
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if event.get("delta"):
                        self.stream_queue.put(("delta", event["delta"]))
                    elif event.get("error"):
                        terminal_received = True
                        self.stream_queue.put(("error", event["error"]))
                    elif event.get("done"):
                        terminal_received = True
                        self.stream_queue.put(("done", None))
            if not terminal_received:
                self.stream_queue.put(("done", None))
        except Exception as exc:
            detail = str(exc)
            if hasattr(exc, "read"):
                try:
                    detail = json.loads(exc.read().decode("utf-8")).get("detail") or detail
                except Exception:
                    pass
            self.stream_queue.put(("error", detail))

    def show(self, force=False):
        if self.context_loading or (self.context_loaded and not force):
            return
        self.context_loading = True
        def work():
            try:
                body = self._request("/api/prompt-assistant/context")
                agents = body.get("agents", [])
                outputs = sum(item.get("recent_output_count", 0) for item in agents)
                message = f"Context ready: {len(agents)} agents · {outputs} recent outputs in memory"
                self.after(0, lambda: self._finish_context_load(message, None, agents))
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda message=error: self._finish_context_load(None, message, None))
        threading.Thread(target=work, daemon=True).start()

    def _finish_context_load(self, message, error, agents):
        self.context_loading = False
        self.context_loaded = error is None
        self.context_status.config(
            text=message if error is None else f"Could not read context: {error}",
            fg=SAGE if error is None else ROSE)
        if error is None:
            self.agent_list = list(agents or [])
            self._render_order_bands()
            if not self.messages:
                self._reset_chat_with_greeting()

    def _append_message(self, role, content):
        self.chat.config(state="normal")
        label = "YOU" if role == "user" else "PROMPTASSISTANT"
        tag = "user_label" if role == "user" else "assistant_label"
        self.chat.insert("end", label + "\n", tag)
        self.chat.insert("end", str(content).strip() + "\n", "message")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _insert_inline_markdown(self, text, base_tag="message"):
        pattern = re.compile(
            r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|(?<!\*)\*[^*]+\*(?!\*))")
        position = 0
        for match in pattern.finditer(text):
            if match.start() > position:
                self.chat.insert("end", text[position:match.start()], base_tag)
            token = match.group(0)
            if token.startswith("**"):
                tags = (base_tag,) if base_tag.startswith("md_h") else (base_tag, "md_bold")
                self.chat.insert("end", token[2:-2], tags)
            elif token.startswith("`"):
                self.chat.insert("end", token[1:-1], (base_tag, "md_code"))
            elif token.startswith("["):
                label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", token).groups()
                self.chat.insert("end", f"{label} ({url})", (base_tag, "md_link"))
            else:
                tags = (base_tag,) if base_tag.startswith("md_h") else (base_tag, "md_italic")
                self.chat.insert("end", token[1:-1], tags)
            position = match.end()
        if position < len(text):
            self.chat.insert("end", text[position:], base_tag)

    @staticmethod
    def _table_cells(line):
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    def _insert_markdown_table(self, rows):
        cells = [self._table_cells(row) for row in rows]
        column_count = max(len(row) for row in cells)
        for row in cells:
            row.extend([""] * (column_count - len(row)))
        widths = [max(len(row[index]) for row in cells) for index in range(column_count)]
        separator = "├" + "┼".join("─" * (width + 2) for width in widths) + "┤\n"
        for index, row in enumerate(cells):
            formatted = "│ " + " │ ".join(
                cell.ljust(widths[column]) for column, cell in enumerate(row)) + " │\n"
            self.chat.insert("end", formatted, "md_table_head" if index == 0 else "md_table")
            if index == 0:
                self.chat.insert("end", separator, "md_table")

    def _insert_markdown(self, content):
        lines = str(content).strip().splitlines()
        index = 0
        in_code = False
        code_lines = []
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code:
                    self.chat.insert("end", "\n".join(code_lines) + "\n", "md_code_block")
                    code_lines = []
                    in_code = False
                else:
                    in_code = True
                index += 1
                continue
            if in_code:
                code_lines.append(line)
                index += 1
                continue
            if ("|" in line and index + 1 < len(lines)
                    and re.match(r"^\s*\|?\s*:?-{3,}", lines[index + 1])):
                table_rows = [line]
                index += 2  # skip Markdown's alignment row
                while index < len(lines) and "|" in lines[index] and lines[index].strip():
                    table_rows.append(lines[index])
                    index += 1
                self._insert_markdown_table(table_rows)
                self.chat.insert("end", "\n", "message")
                continue
            heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
            if heading:
                tag = {1: "md_h1", 2: "md_h2", 3: "md_h3"}[len(heading.group(1))]
                self._insert_inline_markdown(heading.group(2), tag)
                self.chat.insert("end", "\n", tag)
            elif re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
                self.chat.insert("end", "────────────────────────────────────────\n", "md_rule")
            elif re.match(r"^\s*[-*+]\s+", line):
                body = re.sub(r"^\s*[-*+]\s+", "", line)
                self.chat.insert("end", "• ", "md_list")
                self._insert_inline_markdown(body, "md_list")
                self.chat.insert("end", "\n", "md_list")
            elif re.match(r"^\s*\d+[.)]\s+", line):
                marker = re.match(r"^\s*(\d+[.)])\s+", line)
                body = line[marker.end():]
                self.chat.insert("end", marker.group(1) + " ", "md_list")
                self._insert_inline_markdown(body, "md_list")
                self.chat.insert("end", "\n", "md_list")
            elif stripped.startswith(">"):
                self.chat.insert("end", "▎ ", "md_quote")
                self._insert_inline_markdown(stripped[1:].strip(), "md_quote")
                self.chat.insert("end", "\n", "md_quote")
            elif not stripped:
                self.chat.insert("end", "\n", "message")
            else:
                self._insert_inline_markdown(line, "message")
                self.chat.insert("end", "\n", "message")
            index += 1
        if in_code and code_lines:
            self.chat.insert("end", "\n".join(code_lines) + "\n", "md_code_block")

    def _render_chat(self):
        self.chat.config(state="normal")
        self.chat.delete("1.0", "end")
        display_messages = [{"role": "assistant", "content": self._greeting()}, *self.messages]
        for message in display_messages:
            role = message["role"]
            label = "YOU" if role == "user" else "PROMPTASSISTANT"
            tag = "user_label" if role == "user" else "assistant_label"
            self.chat.insert("end", label + "\n", tag)
            self._insert_markdown(message["content"])
            self.chat.insert("end", "\n", "message")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def send(self):
        if self.busy:
            return "break"
        content = self.input.get("1.0", "end-1c").strip()
        if not content:
            return "break"
        if len(content) > 12000:
            self.context_status.config(text="Message must be 12000 characters or fewer.", fg=ROSE)
            return "break"
        max_tokens = self._commit_assistant_setting(self.max_tokens_control)
        temperature = self._commit_assistant_setting(self.temperature_control)
        if max_tokens is None or temperature is None:
            self.context_status.config(text="Fix the highlighted generation setting.", fg=ROSE)
            return "break"
        self.input.delete("1.0", "end")
        self.messages.append({"role": "user", "content": content})
        self.messages = self.messages[-20:]
        self._append_message("user", content)
        self.busy = True
        self.send_button.config(state="disabled", text="Thinking…")
        self.context_status.config(text="PromptAssistant is thinking with the connected LLM…", fg=AMBER)

        payload = {
            "messages": list(self.messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        self.current_reply = ""
        self.chat.config(state="normal")
        self.chat.insert("end", "PROMPTASSISTANT\n", "assistant_label")
        self.chat.config(state="disabled")
        threading.Thread(target=self._stream_request, args=(payload,), daemon=True).start()
        self.after(5, self._drain_stream_queue)
        return "break"

    def _drain_stream_queue(self):
        deltas = []
        terminal = None
        while True:
            try:
                event, value = self.stream_queue.get_nowait()
            except queue.Empty:
                break
            if event == "delta":
                deltas.append(value)
            else:
                terminal = (event, value)
                break
        if deltas:
            text = "".join(deltas)
            self.current_reply += text
            self.chat.config(state="normal")
            self.chat.insert("end", text, "message")
            self.chat.config(state="disabled")
            self.chat.see("end")
        if terminal is not None:
            event, value = terminal
            if event == "error":
                self._finish_reply(None, value)
            elif event == "done":
                self._finish_reply(self.current_reply, None)
            return
        if self.busy:
            self.after(5, self._drain_stream_queue)

    def _finish_reply(self, reply, error):
        self.busy = False
        self.send_button.config(state="normal", text="Send")
        if error:
            self.chat.config(state="normal")
            self.chat.insert("end", "\n", "message")
            self.chat.config(state="disabled")
            self.context_status.config(text=f"PromptAssistant failed: {error}", fg=ROSE)
            return
        self.messages.append({"role": "assistant", "content": reply})
        self.messages = self.messages[-20:]
        self._render_chat()
        self.context_status.config(text="Answer received from the connected Main Provider.", fg=SAGE)

    def clear(self):
        if self.busy:
            return
        self.messages = []
        self._reset_chat_with_greeting()

    def _reset_chat_with_greeting(self):
        self._render_chat()


class ControlWindow(tk.Tk):
    """Keep BrainEngine running and display its live console output."""

    POLL_MS = 60

    def __init__(self):
        super().__init__()
        self.title("Step-driven MultiBrainEngine — Control")
        self.geometry("920x700")
        self.minsize(700, 480)
        self.configure(bg=BG)

        self.log_queue = queue.Queue()
        self.server = None
        self.server_thread = None
        self.closing = False
        self.closed = False
        self.current_tab = "log"
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        sys.stdout = QueueWriter(self.original_stdout, self.log_queue)
        sys.stderr = QueueWriter(self.original_stderr, self.log_queue)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.stop_server)
        self.after(self.POLL_MS, self._drain_log_queue)
        self.after(50, self._start_server)

    def _build(self):
        tab_bar = tk.Frame(self, bg="#090d0b")
        tab_bar.pack(fill="x")
        self.tab_buttons = {}
        self.tab_buttons["log"] = tk.Button(
            tab_bar, text="  Main log  ", bg=BG, fg=AMBER, relief="flat",
            font=FONT_B, padx=16, pady=10, cursor="hand2",
            command=lambda: self._show_tab("log"))
        self.tab_buttons["log"].pack(side="left", padx=(14, 2), pady=(7, 0))
        self.tab_buttons["prompts"] = tk.Button(
            tab_bar, text="  Prompt Studio  ", bg=CARD, fg=MUTED, relief="flat",
            font=FONT_B, padx=16, pady=10, cursor="hand2",
            command=lambda: self._show_tab("prompts"))
        self.tab_buttons["prompts"].pack(side="left", padx=2, pady=(7, 0))
        self.tab_buttons["lorebooks"] = tk.Button(
            tab_bar, text="  Lorebooks  ", bg=CARD, fg=MUTED, relief="flat",
            font=FONT_B, padx=16, pady=10, cursor="hand2",
            command=lambda: self._show_tab("lorebooks"))
        self.tab_buttons["lorebooks"].pack(side="left", padx=2, pady=(7, 0))
        self.tab_buttons["assistant"] = tk.Button(
            tab_bar, text="  PromptAssistant  ", bg=CARD, fg=MUTED, relief="flat",
            font=FONT_B, padx=16, pady=10, cursor="hand2",
            command=lambda: self._show_tab("assistant"))
        self.tab_buttons["assistant"].pack(side="left", padx=2, pady=(7, 0))

        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True)
        self.log_page = tk.Frame(self.content, bg=BG)
        self.prompt_page = PromptStudio(self.content)
        self.lorebook_page = LorebookStudio(self.content)
        self.assistant_page = PromptAssistant(self.content)
        self.pages = {
            "log": self.log_page,
            "prompts": self.prompt_page,
            "lorebooks": self.lorebook_page,
            "assistant": self.assistant_page,
        }
        self.log_page.pack(fill="both", expand=True)

        header = tk.Frame(self.log_page, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 12))

        title_row = tk.Frame(header, bg=BG)
        title_row.pack(fill="x")
        tk.Label(title_row, text="Step-driven MultiBrainEngine", bg=BG, fg=AMBER,
                 font=FONT_T, anchor="w").pack(side="left")
        self.status = tk.Label(title_row, text="● STARTING", bg=BG, fg=AMBER,
                               font=FONT_S, anchor="e")
        self.status.pack(side="right", pady=(5, 0))

        info = tk.Frame(header, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        info.pack(fill="x", pady=(12, 0))
        self._address_row(info, "SillyTavern address", SERVER_URL, self._copy_server_url)
        self._address_row(info, "Prompt Studio", "Available in the tab above",
                          lambda: self._show_tab("prompts"), action_text="open")
        tk.Label(info, text="Stop the server with the button below or by closing this window.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w").pack(
                     fill="x", padx=14, pady=(2, 10))

        log_wrap = tk.Frame(self.log_page, bg="#090d0b", highlightbackground=BORDER,
                            highlightthickness=1)
        log_wrap.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        scrollbar = tk.Scrollbar(log_wrap, orient="vertical", bg=CARD,
                                 troughcolor=BG, width=12)
        scrollbar.pack(side="right", fill="y")
        self.log = tk.Text(log_wrap, bg="#090d0b", fg=INK, insertbackground=INK,
                           selectbackground="#405347", selectforeground=INK,
                           relief="flat", wrap="word", font=FONT_LOG,
                           padx=12, pady=10, undo=False,
                           yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log.yview)
        self.log.config(state="disabled")

        footer = tk.Frame(self.log_page, bg=BG)
        footer.pack(fill="x", padx=24, pady=(0, 20))
        tk.Button(footer, text="Clear log", bg=CARD, fg=MUTED,
                  activebackground=BORDER, activeforeground=INK, relief="flat",
                  font=FONT_B, padx=16, pady=7, cursor="hand2",
                  command=self.clear_log).pack(side="left")
        tk.Button(footer, text="Copy log", bg=CARD, fg=SAGE,
                  activebackground=BORDER, activeforeground=INK, relief="flat",
                  font=FONT_B, padx=16, pady=7, cursor="hand2",
                  command=self.copy_log).pack(side="left", padx=(10, 0))
        self.stop_button = tk.Button(
            footer, text="Stop server", bg=ROSE, fg="#201715",
            activebackground="#e8aaa0", relief="flat", font=FONT_B,
            padx=20, pady=7, cursor="hand2", command=self.stop_server)
        self.stop_button.pack(side="right")

    def _show_tab(self, name):
        self.current_tab = name
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        for key, button in self.tab_buttons.items():
            selected = key == name
            button.config(bg=BG if selected else CARD,
                          fg=AMBER if selected else MUTED)
        if name == "prompts":
            if self.server is not None and self.server.started:
                self.prompt_page.show()
            else:
                self.prompt_page._notice("The server is still starting. Try this tab again shortly.", False)
        elif name == "lorebooks":
            if self.server is not None and self.server.started:
                self.lorebook_page.show()
            else:
                self.lorebook_page.status.config(text="The server is still starting.", fg=ROSE)
        elif name == "assistant":
            if self.server is not None and self.server.started:
                self.assistant_page.show(force=True)
            else:
                self.assistant_page.context_status.config(
                    text="The server is still starting. Try this tab again shortly.", fg=ROSE)

    def _address_row(self, parent, label, value, command, action_text="copy"):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(row, text=label, bg=CARD, fg=MUTED, font=FONT,
                 width=18, anchor="w").pack(side="left")
        tk.Label(row, text=value, bg=CARD, fg=AMBER, font=FONT_M,
                 anchor="w").pack(side="left", fill="x", expand=True)
        tk.Button(row, text=action_text, bg=CARD, fg=SAGE,
                  activebackground=BORDER, activeforeground=INK, relief="flat",
                  font=FONT_S, padx=10, cursor="hand2", command=command).pack(side="right")

    def _copy_server_url(self):
        self.clipboard_clear()
        self.clipboard_append(SERVER_URL)

    def _start_server(self):
        def run():
            try:
                import uvicorn
                config = uvicorn.Config(
                    "server:app", host="127.0.0.1", port=PORT, use_colors=False
                )
                self.server = uvicorn.Server(config)
                if self.closing:
                    self.server.should_exit = True
                self.server.run()
            except Exception as exc:
                print(f"\n❌ Server failed to start: {exc}")
            finally:
                self.log_queue.put(None)

        print()
        print("=" * 62)
        print("  Step-driven MultiBrainEngine")
        print(f"  SillyTavern address : {SERVER_URL}")
        print(f"  Prompt Studio       : http://127.0.0.1:{PORT}/prompts")
        print("  Stop the server from the control window")
        print("=" * 62)
        self.server_thread = threading.Thread(target=run, name="BrainEngineServer", daemon=True)
        self.server_thread.start()

    def _drain_log_queue(self):
        chunks = []
        server_stopped = False
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                server_stopped = True
            else:
                chunks.append(item)

        if chunks:
            text = "".join(chunks)
            self.log.config(state="normal")
            self.log.insert("end", text)
            self.log.see("end")
            self.log.config(state="disabled")

        if self.server is not None and self.server.started and not self.closing:
            self.status.config(text="● RUNNING", fg=SAGE)
            if self.current_tab == "prompts" and not self.prompt_page.loaded:
                self.prompt_page.show()
            elif self.current_tab == "assistant":
                self.assistant_page.show()

        if server_stopped:
            self.status.config(text="● STOPPED", fg=ROSE)
            if self.closing:
                self._finish_close()
                return

        self.after(self.POLL_MS, self._drain_log_queue)

    def clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def copy_log(self):
        text = self.log.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)

    def stop_server(self):
        if self.closing:
            return
        self.closing = True
        self.status.config(text="● STOPPING", fg=AMBER)
        self.stop_button.config(state="disabled", text="Stopping…")
        if self.server is not None:
            self.server.should_exit = True
        elif not self.server_thread or not self.server_thread.is_alive():
            self._finish_close()
            return
        self.after(100, self._wait_for_server)

    def _wait_for_server(self):
        if self.server_thread and self.server_thread.is_alive():
            self.after(100, self._wait_for_server)
        else:
            self._finish_close()

    def _finish_close(self):
        if self.closed:
            return
        self.closed = True
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self.destroy()


# =========================================================
# START
# =========================================================
def main():
    app = Launcher()
    app.mainloop()
    if app.result != "continue":
        return

    os.chdir(ENGINE)
    sys.path.insert(0, ENGINE)
    try:
        control = ControlWindow()
        control.mainloop()
    except KeyboardInterrupt:
        if 'control' in locals() and control.winfo_exists():
            control.stop_server()
    except Exception as e:
        print(f"\n❌ Server failed to start: {e}")


if __name__ == "__main__":
    main()
