from __future__ import annotations

import asyncio
from typing import Dict, List

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Input, Markdown, Select, Static, TabbedContent, TabPane

from tools.tui.backend import (
    RuntimeConfig,
    format_management_result,
    get_runtime_status,
    load_runtime_config,
    run_management_command,
    start_runtime_component,
)
from tools.tui.chat_client import ChatClient


class ArcAiApp(App):
    TITLE = "Intel Arc AI"
    SUB_TITLE = "Local OVMS Chat + Management"

    CSS = """
    Screen { layout: vertical; }
    #top-status { height: 3; padding: 0 1; content-align: left middle; }
    #chat-scroll { height: 1fr; border: solid $panel; padding: 1; }
    .chat-user { margin: 1 0; padding: 1; background: $boost; }
    .chat-assistant { margin: 1 0; padding: 1; border-left: tall $accent; }
    .chat-reasoning { margin: 0 0 1 2; color: $text-muted; }
    #chat-controls { height: auto; margin-top: 1; }
    #chat-input { width: 1fr; }
    #chat-model { width: 32; }
    #models-table { height: 1fr; }
    #model-actions, #runtime-actions { height: auto; margin-top: 1; }
    #model-action-select { width: 36; }
    #system-info, #action-output { padding: 1; border: solid $panel; margin-bottom: 1; }
    Button { margin-right: 1; }
    """

    BINDINGS = [
        ("ctrl+r", "refresh", "Refresh"),
        ("ctrl+l", "clear_chat", "Clear Chat"),
        ("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config: RuntimeConfig = load_runtime_config()
        self.chat_client = ChatClient(self.config)
        self.messages: List[Dict[str, str]] = []
        self._models: List[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Checking runtime...", id="top-status")

        with TabbedContent(initial="chat"):
            with TabPane("Chat", id="chat"):
                yield VerticalScroll(id="chat-scroll")
                with Horizontal(id="chat-controls"):
                    yield Select([], prompt="Model", id="chat-model", allow_blank=False)
                    yield Input(placeholder="Message your local model...", id="chat-input")
                    yield Button("Send", id="send", variant="primary")

            with TabPane("Models", id="models"):
                yield DataTable(id="models-table", cursor_type="row")
                with Horizontal(id="model-actions"):
                    yield Select([], prompt="Select model", id="model-action-select", allow_blank=False)
                    yield Button("Refresh", id="refresh-models")
                    yield Button("Enable", id="enable-model", variant="success")
                    yield Button("Disable", id="disable-model", variant="warning")
                    yield Button("Reload", id="reload-models")
                yield Static("Ready.", id="action-output")

            with TabPane("System", id="system"):
                yield Static("Loading...", id="system-info")
                with Horizontal(id="runtime-actions"):
                    yield Button("Start OVMS", id="start-ovms", variant="success")
                    yield Button("Start Gateway", id="start-gateway", variant="success")
                    yield Button("Refresh Status", id="refresh-status")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#models-table", DataTable)
        table.add_columns("Model", "State", "Path")
        self.action_refresh()

    def action_refresh(self) -> None:
        self.run_worker(self._refresh_runtime(), group="status", exclusive=True)

    def action_clear_chat(self) -> None:
        self.messages.clear()
        container = self.query_one("#chat-scroll", VerticalScroll)
        container.remove_children()

    async def _refresh_runtime(self) -> None:
        status = await asyncio.to_thread(get_runtime_status, self.config)
        loaded = set(status.loaded_models)
        registered = status.registry_models
        model_names = sorted(set(registered) | loaded | ({status.configured_model} if status.configured_model else set()))
        self._models = model_names

        ovms_text = "UP" if status.ovms_reachable else "DOWN"
        gateway_text = "UP" if status.gateway_reachable else "DOWN"
        loaded_text = ", ".join(status.loaded_models) if status.loaded_models else "none"
        self.query_one("#top-status", Static).update(
            f"OVMS {ovms_text} :{self.config.ovms_port}   |   "
            f"Gateway {gateway_text} :{self.config.proxy_port}   |   Loaded: {loaded_text}"
        )
        self.query_one("#system-info", Static).update(
            f"Project: {self.config.root}\n"
            f"OVMS: {ovms_text} on {self.config.ovms_port}\n"
            f"Gateway: {gateway_text} at {self.config.gateway_base_url}\n"
            f"Configured model: {status.configured_model or '-'}\n"
            f"Registered models: {len(registered)}\n"
            f"Loaded models: {loaded_text}"
        )

        options = [(name, name) for name in model_names]
        chat_select = self.query_one("#chat-model", Select)
        action_select = self.query_one("#model-action-select", Select)
        chat_select.set_options(options)
        action_select.set_options(options)
        preferred = status.loaded_models[0] if status.loaded_models else status.configured_model
        if preferred and preferred in model_names:
            chat_select.value = preferred
            action_select.value = preferred

        table = self.query_one("#models-table", DataTable)
        table.clear()
        for name in model_names:
            if name in loaded:
                state = "LOADED"
            elif name in registered:
                state = "REGISTERED"
            else:
                state = "CONFIGURED"
            table.add_row(name, state, registered.get(name, ""))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat-input":
            await self._submit_chat()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "send":
            await self._submit_chat()
        elif button_id in {"refresh-models", "refresh-status"}:
            self.action_refresh()
        elif button_id == "enable-model":
            self._run_model_action("enable")
        elif button_id == "disable-model":
            self._run_model_action("disable")
        elif button_id == "reload-models":
            self._run_model_action("reload", requires_model=False)
        elif button_id == "start-ovms":
            self._start_component("ovms")
        elif button_id == "start-gateway":
            self._start_component("gateway")

    async def _submit_chat(self) -> None:
        input_widget = self.query_one("#chat-input", Input)
        text = input_widget.value.strip()
        if not text:
            return

        model_select = self.query_one("#chat-model", Select)
        model = str(model_select.value) if model_select.value is not Select.BLANK else ""
        if not model:
            self.notify("No model selected.", severity="warning")
            return

        input_widget.value = ""
        input_widget.disabled = True
        send_button = self.query_one("#send", Button)
        send_button.disabled = True

        container = self.query_one("#chat-scroll", VerticalScroll)
        await container.mount(Static(f"You\n{text}", classes="chat-user"))
        assistant_widget = Markdown("_Generating..._", classes="chat-assistant")
        reasoning_widget = Static("", classes="chat-reasoning")
        await container.mount(reasoning_widget, assistant_widget)
        container.scroll_end(animate=False)

        self.messages.append({"role": "user", "content": text})
        answer = ""
        reasoning = ""
        try:
            async for delta in self.chat_client.stream_chat(model, self.messages):
                if delta.reasoning:
                    reasoning += delta.reasoning
                    preview = reasoning[-1200:]
                    reasoning_widget.update(f"Thinking: {preview}")
                if delta.content:
                    answer += delta.content
                    await assistant_widget.update(answer)
                    container.scroll_end(animate=False)
            if not answer:
                await assistant_widget.update("_No content returned._")
            else:
                self.messages.append({"role": "assistant", "content": answer})
        except Exception as exc:
            await assistant_widget.update(f"**Request failed:** `{exc}`")
            self.notify("Chat request failed.", severity="error")
        finally:
            input_widget.disabled = False
            send_button.disabled = False
            input_widget.focus()

    def _selected_management_model(self) -> str:
        selector = self.query_one("#model-action-select", Select)
        return "" if selector.value is Select.BLANK else str(selector.value)

    def _run_model_action(self, command: str, *, requires_model: bool = True) -> None:
        model = self._selected_management_model() if requires_model else None
        if requires_model and not model:
            self.notify("Select a model first.", severity="warning")
            return
        self.run_worker(self._management_worker(command, model), group="management", exclusive=True)

    async def _management_worker(self, command: str, model: str | None) -> None:
        output = self.query_one("#action-output", Static)
        output.update(f"Running {command}...")
        try:
            result = await asyncio.to_thread(run_management_command, self.config, command, model)
            output.update(format_management_result(result))
            if result.returncode == 0:
                self.notify(f"{command} completed.")
            else:
                self.notify(f"{command} failed ({result.returncode}).", severity="error")
        except Exception as exc:
            output.update(str(exc))
            self.notify(f"{command} failed.", severity="error")
        self.action_refresh()

    def _start_component(self, component: str) -> None:
        try:
            start_runtime_component(self.config, component)
            self.notify(f"Starting {component}...")
            self.set_timer(2.0, self.action_refresh)
        except Exception as exc:
            self.notify(f"Could not start {component}: {exc}", severity="error")


def main() -> None:
    ArcAiApp().run()


if __name__ == "__main__":
    main()
