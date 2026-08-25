from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Select, Static, TabbedContent, TabPane, TextArea

from tools.tui.backend import (
    RuntimeConfig,
    download_model_files,
    format_management_result,
    get_runtime_status,
    is_model_downloaded,
    load_runtime_config,
    run_management_command,
    start_runtime_component,
)
from tools.tui.chat_client import ChatClient
from tools.tui.theme import CURATED_THEMES, pill, pill_markup
from tools.tui.widgets.chat_widgets import (
    PlanCard,
    TerminalToolCard,
    ThoughtCard,
    ToolCallHeader,
    UserMessageCard,
)


class ArcAiApp(App):
    TITLE = "Toad - Intel Arc AI Studio"
    SUB_TITLE = "Local OpenVINO Model Server"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        ("ctrl+f", "focus_input", "Focus"),
        ("ctrl+t", "toggle_theme", "Theme"),
        ("ctrl+l", "clear_chat", "Clear"),
        ("ctrl+r", "refresh", "Refresh"),
        ("ctrl+q", "quit", "Quit"),
    ]

    THEME_NAMES = [
        "toad-dark",
        "arc-cyberpunk",
        "catppuccin-mocha",
        "tokyo-night",
        "dracula",
        "nord",
        "gruvbox",
        "monokai",
        "rose-pine",
        "arc-titan",
        "textual-dark",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config: RuntimeConfig = load_runtime_config()
        self.chat_client = ChatClient(self.config)
        self.messages: List[Dict[str, str]] = []
        self._models: List[str] = []
        self._downloaded_models: Set[str] = set()
        self._loaded_models: Set[str] = set()
        self._active_model: str = ""
        self._theme_index = 0

    def on_mount(self) -> None:
        for custom_theme in CURATED_THEMES:
            self.register_theme(custom_theme)
        self.theme = "toad-dark"
        self._theme_index = 0

        table = self.query_one("#models-table", DataTable)
        table.add_columns("Status", "Model Identifier", "Local Model Path", "State Hint")
        self.action_refresh()

    def compose(self) -> ComposeResult:
        yield Header()

        # Top Live Telemetry Bar
        with Horizontal(id="top-bar"):
            yield Static("⚡ OVMS : Loading...", id="pill-ovms", classes="status-pill")
            yield Static("🌐 GATEWAY : Loading...", id="pill-gateway", classes="status-pill")
            yield Static("🧠 MODEL : Loading...", id="pill-model", classes="status-pill accent")

        with TabbedContent(initial="chat"):
            with TabPane("💬 Chat Studio", id="chat"):
                yield VerticalScroll(id="chat-scroll")

                # Toad-style Prompt Container
                with Vertical(id="chat-compose-container"):
                    with Horizontal(id="chat-input-row"):
                        yield Static("❯", id="chat-prompt-glyph")
                        yield TextArea(
                            placeholder="What would you like to do? (Press Enter / Ctrl+Enter to send)",
                            id="chat-input",
                            show_line_numbers=False,
                        )
                    with Horizontal(id="prompt-shortcuts-row"):
                        yield Static(
                            f"{pill_markup('! shell', '#21222c', '#8be9fd')}  {pill_markup('/ commands', '#21222c', '#bd93f9')}  {pill_markup('@ files', '#21222c', '#50fa7b')}",
                            id="prompt-shortcuts-text",
                        )

                # Info Bar matching Toad's #info-container
                with Horizontal(id="info-container"):
                    yield Static(pill_markup("Intel Arc LLM", "#bd93f9", "#1e1f29"), id="info-agent-pill")
                    yield Static(f" {self.config.root}", id="info-path-text")
                    yield Static(pill_markup("Default", "#21222c", "#8be9fd"), id="info-mode-pill")

                # Model Selector & Control Toolbar
                with Horizontal(id="chat-model-toolbar"):
                    yield Select([], prompt="Select Model", id="chat-model", allow_blank=True)
                    yield Button("🧹 Clear", id="clear-chat-btn")
                    yield Button("➤ Send", id="send", variant="primary")

            with TabPane("📦 Model Manager", id="models"):
                with Vertical(id="models-container"):
                    yield DataTable(id="models-table", cursor_type="row")
                    with Horizontal(id="model-actions"):
                        yield Select([], prompt="Select model", id="model-action-select", allow_blank=True)
                        yield Button("⚡ Load Model", id="switch-model", variant="success")
                        yield Button("⬇️ Download", id="download-model", variant="primary")
                        yield Button("🔄 Reload Config", id="reload-models")
                        yield Button("✨ Refresh", id="refresh-models")
                    yield Static("Ready. Select a model from the list or table to manage.", id="action-output")

            with TabPane("⚙️ System Health", id="system"):
                with Grid(id="system-grid"):
                    yield Static("Inference Engine\nLoading...", id="card-ovms", classes="system-card highlight")
                    yield Static("Gateway Proxy\nLoading...", id="card-gateway", classes="system-card")
                    yield Static("Hardware & Model\nLoading...", id="card-hw", classes="system-card")

                with Horizontal(id="runtime-actions"):
                    yield Button("▶ Start OVMS", id="start-ovms", variant="success")
                    yield Button("▶ Start Gateway", id="start-gateway", variant="primary")
                    yield Button("🔄 Refresh All", id="refresh-status")

        yield Footer()

    def action_focus_input(self) -> None:
        try:
            self.query_one("#chat-input", TextArea).focus()
        except Exception:
            pass

    def action_refresh(self) -> None:
        self._refresh_runtime(preserve_action_output=False)

    def action_clear_chat(self) -> None:
        self.messages.clear()
        self.query_one("#chat-scroll", VerticalScroll).remove_children()
        self.notify("Chat conversation cleared.", title="Clean Canvas")

    def action_toggle_theme(self) -> None:
        self._theme_index = (self._theme_index + 1) % len(self.THEME_NAMES)
        new_theme = self.THEME_NAMES[self._theme_index]
        self.theme = new_theme
        self.notify(f"Theme switched to: {new_theme}", title="Theme Changed")

    def _refresh_runtime(self, preserve_action_output: bool = False) -> None:
        status = get_runtime_status(self.config)
        self._status = status
        registered = status.registry_models
        loaded = set(status.loaded_models)
        downloaded = set(status.downloaded_models)
        active_model = status.configured_model or (status.loaded_models[0] if status.loaded_models else "")

        self._active_model = active_model
        self._loaded_models = loaded
        self._downloaded_models = list(status.downloaded_models)
        self._enabled_models = status.enabled_models

        all_models = sorted(set(registered) | loaded | downloaded | ({active_model} if active_model else set()))
        self._models = all_models

        # Telemetry pills
        pill_ovms = self.query_one("#pill-ovms", Static)
        pill_gateway = self.query_one("#pill-gateway", Static)
        pill_model = self.query_one("#pill-model", Static)

        if status.ovms_reachable:
            pill_ovms.update(f"⚡ OVMS: :{self.config.ovms_port} ● ONLINE")
            pill_ovms.remove_class("offline")
            pill_ovms.add_class("online")
        else:
            pill_ovms.update(f"⚡ OVMS: :{self.config.ovms_port} ● OFFLINE")
            pill_ovms.remove_class("online")
            pill_ovms.add_class("offline")

        if status.gateway_reachable:
            pill_gateway.update(f"🌐 GATEWAY: :{self.config.proxy_port} ● ACTIVE")
            pill_gateway.remove_class("offline")
            pill_gateway.add_class("online")
        else:
            pill_gateway.update(f"🌐 GATEWAY: :{self.config.proxy_port} ● STANDBY")
            pill_gateway.remove_class("online")
            pill_gateway.add_class("offline")

        pill_model.update(f"🧠 MODEL: {active_model or 'None'}")

        # Update Info Bar pill
        try:
            info_pill = self.query_one("#info-agent-pill", Static)
            model_label = active_model or "Intel Arc LLM"
            info_pill.update(pill_markup(model_label, "#bd93f9", "#1e1f29"))
        except Exception:
            pass

        # System Dashboard Cards
        card_ovms = self.query_one("#card-ovms", Static)
        card_gateway = self.query_one("#card-gateway", Static)
        card_hw = self.query_one("#card-hw", Static)

        card_ovms.border_title = "⚡ OVMS INFERENCE ENGINE"
        card_ovms.update(
            f"• State: {'🟢 READY' if status.ovms_reachable else '🔴 STOPPED'}\n"
            f"• REST Port: {self.config.ovms_port}\n"
            f"• Target Device: GPU (Intel Arc)\n"
            f"• Active Model: {active_model or 'None'}"
        )

        card_gateway.border_title = "🌐 API GATEWAY & IDE PROXY"
        card_gateway.update(
            f"• State: {'🟢 STREAMING' if status.gateway_reachable else '⚪ STANDBY'}\n"
            f"• Base URL: {self.config.gateway_base_url}\n"
            f"• Protocol: OpenAI v1/v3 SSE\n"
            f"• Compatibility: Strict / JetBrains / VS Code"
        )

        card_hw.border_title = "🖥️ HARDWARE & REPOSITORY"
        card_hw.update(
            f"• Active Model: {active_model or '-'}\n"
            f"• Installed Local Models: {len(downloaded)} ready\n"
            f"• Total Registered: {len(registered)} known\n"
            f"• Active Theme: {self.theme}"
        )

        # 1. Chat Studio Model Selector
        model_select = self.query_one("#chat-model", Select)
        installed_options = [
            (f"{m} ★ [ACTIVE]" if m == self._active_model else f"{m} [READY]", m)
            for m in self._downloaded_models
        ]
        if not installed_options:
            installed_options = [("No Models Downloaded", Select.BLANK)]

        current_val = model_select.value
        model_select.set_options(installed_options)

        if current_val in self._downloaded_models:
            model_select.value = current_val
        elif self._active_model in self._downloaded_models:
            model_select.value = self._active_model
        elif self._downloaded_models:
            model_select.value = self._downloaded_models[0]
        else:
            model_select.value = Select.BLANK

        # 2. Model Manager Action Dropdown
        action_select = self.query_one("#model-action-select", Select)
        current_action_model = str(action_select.value) if action_select.value is not Select.BLANK else ""

        action_options = [
            (f"{name} {'★ [ACTIVE]' if name == self._active_model else ('[READY]' if name in self._downloaded_models else '[DOWNLOAD REQ]')}", name)
            for name in all_models
        ]
        action_select.set_options(action_options)

        if current_action_model and current_action_model in all_models:
            action_select.value = current_action_model
        elif self._active_model and self._active_model in all_models:
            action_select.value = self._active_model
        elif all_models:
            action_select.value = all_models[0]

        # 3. Models DataTable
        table = self.query_one("#models-table", DataTable)
        table.clear()
        for name in all_models:
            path_val = status.registry_models.get(name, self.config.model_path if name == status.configured_model else "-")
            if name == self._active_model and status.loaded_models:
                state_badge = "[bold green]● LOADED[/]"
                state_hint = "[green]Active (In Memory)[/]"
            elif name == self._active_model:
                state_badge = "[green]● ACTIVE[/]"
                state_hint = "[green]Active (Configured)[/]"
            elif name in self._downloaded_models:
                state_badge = "[cyan]● READY[/]"
                state_hint = "[cyan]Installed (Standby)[/]"
            else:
                state_badge = "[dim red]○ NOT DOWNLOADED[/]"
                state_hint = "[dim yellow]Download Required[/]"

            table.add_row(state_badge, name, path_val, state_hint, key=name)

        self._update_model_action_buttons(preserve_output=preserve_action_output)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "model-action-select":
            self._update_model_action_buttons(preserve_output=False)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value:
            model_name = str(event.row_key.value)
            action_select = self.query_one("#model-action-select", Select)
            if model_name in self._models:
                action_select.value = model_name
                self._update_model_action_buttons(preserve_output=False)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.row_key and event.row_key.value:
            model_name = str(event.row_key.value)
            action_select = self.query_one("#model-action-select", Select)
            if model_name in self._models:
                action_select.value = model_name
                self._update_model_action_buttons(preserve_output=False)

    def _selected_management_model(self) -> str:
        selector = self.query_one("#model-action-select", Select)
        return "" if selector.value is Select.BLANK else str(selector.value)

    def _update_model_action_buttons(self, preserve_output: bool = False) -> None:
        model = self._selected_management_model()
        switch_btn = self.query_one("#switch-model", Button)
        download_btn = self.query_one("#download-model", Button)
        reload_btn = self.query_one("#reload-models", Button)
        output = self.query_one("#action-output", Static)

        if not model:
            switch_btn.disabled = True
            download_btn.disabled = True
            reload_btn.disabled = False
            return

        is_downloaded = model in self._downloaded_models
        is_active = model == self._active_model

        if is_active:
            switch_btn.disabled = True
            switch_btn.label = "✓ Active Model"
            download_btn.disabled = True
            reload_btn.disabled = False
            if not preserve_output:
                mem_desc = "Loaded in memory & serving inference" if self._loaded_models else "Configured in OVMS config"
                output.update(f"⭐ [bold green]{model}[/]: Currently active ({mem_desc}).")
        elif is_downloaded:
            switch_btn.disabled = False
            switch_btn.label = "⚡ Load Model"
            download_btn.disabled = True
            reload_btn.disabled = False
            if not preserve_output:
                output.update(
                    f"● [cyan]{model}[/] is downloaded and ready in local storage.\n"
                    f"Click [bold green]⚡ Load Model[/] to switch the active OVMS model."
                )
        else:
            switch_btn.disabled = True
            switch_btn.label = "⚡ Load Model"
            download_btn.disabled = False
            reload_btn.disabled = False
            if not preserve_output:
                output.update(
                    f"⚠️ [bold yellow]{model}[/] is registered but not downloaded on local disk.\n"
                    f"Click [bold cyan]⬇️ Download[/] to download weights from OpenVINO Hub."
                )

    async def on_key(self, event) -> None:
        if event.key in {"enter", "ctrl+enter", "ctrl+j"}:
            try:
                chat_input = self.query_one("#chat-input", TextArea)
                if self.focused == chat_input:
                    # If shift is held or multiline intended, allow default
                    if event.key == "shift+enter":
                        return
                    event.prevent_default()
                    event.stop()
                    await self._submit_chat()
            except Exception:
                pass

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "send":
            await self._submit_chat()
        elif button_id == "clear-chat-btn":
            self.action_clear_chat()
        elif button_id in {"refresh-models", "refresh-status"}:
            self.action_refresh()
        elif button_id == "download-model":
            self._run_download_action()
        elif button_id == "switch-model":
            self._run_model_action("switch")
        elif button_id == "reload-models":
            self._run_model_action("reload", requires_model=False)
        elif button_id == "start-ovms":
            self._start_component("ovms")
        elif button_id == "start-gateway":
            self._start_component("gateway")

    async def _submit_chat(self) -> None:
        input_widget = self.query_one("#chat-input", TextArea)
        text = input_widget.text.strip()
        if not text:
            return

        model_select = self.query_one("#chat-model", Select)
        model = str(model_select.value) if model_select.value is not Select.BLANK else ""
        if not model:
            self.notify("Please select an installed model first.", severity="warning", title="No Model")
            return

        input_widget.text = ""
        input_widget.disabled = True
        send_button = self.query_one("#send", Button)
        send_button.disabled = True

        streaming_active = True

        # Animating Send Button
        async def run_spinner() -> None:
            symbols = ["✦", "✧", "✶", "✷", "✸", "✹", "✺"]
            idx = 0
            while streaming_active:
                send_button.label = f"{symbols[idx % len(symbols)]} Generating"
                idx += 1
                await asyncio.sleep(0.12)

        spinner_task = asyncio.create_task(run_spinner())
        container = self.query_one("#chat-scroll", VerticalScroll)
        now_str = datetime.now().strftime("%H:%M:%S")

        # Mount User Message using Toad-styled UserMessageCard
        user_card = UserMessageCard(text, timestamp=now_str)
        await container.mount(user_card)

        # Thought Process (collapsible / distinct thought card)
        thought_widget = ThoughtCard("")
        thought_widget.display = False

        # Assistant response widget
        assistant_card = Static("✦ Generating response...", classes="chat-assistant-card")
        await container.mount(thought_widget, assistant_card)
        container.scroll_end(animate=False)

        self.messages.append({"role": "user", "content": text})
        answer = ""
        reasoning = ""

        try:
            async for delta in self.chat_client.stream_chat(model, self.messages):
                if delta.reasoning:
                    reasoning += delta.reasoning
                    if not thought_widget.display:
                        thought_widget.display = True
                    thought_widget.update(reasoning)
                    container.scroll_end(animate=False)

                if delta.content:
                    answer += delta.content
                    assistant_card.update(answer)
                    container.scroll_end(animate=False)

            if not answer:
                assistant_card.update("[italic red]No text content returned by model.[/]")
            else:
                self.messages.append({"role": "assistant", "content": answer})

        except Exception as exc:
            assistant_card.update(f"[bold red]❌ Request failed:[/] {exc}")
            self.notify(f"Generation error: {exc}", severity="error", title="Chat Error")
        finally:
            streaming_active = False
            await spinner_task
            send_button.label = "➤ Send"
            send_button.disabled = False
            input_widget.disabled = False
            input_widget.focus()
            container.scroll_end(animate=True)

    def _run_download_action(self) -> None:
        model = self._selected_management_model()
        if not model:
            self.notify("Please select a target model to download.", severity="warning")
            return
        asyncio.create_task(self._download_worker(model))

    async def _download_worker(self, model: str) -> None:
        output = self.query_one("#action-output", Static)
        download_btn = self.query_one("#download-model", Button)
        download_btn.disabled = True
        output.update(f"⏳ Connecting to repository to download [bold cyan]{model}[/]...")
        self.notify(f"Downloading {model}...", title="Download Started")

        def on_prog(msg: str) -> None:
            self.call_from_thread(output.update, f"⏳ {msg}")

        try:
            dest_dir = await asyncio.to_thread(download_model_files, self.config, model, on_prog)
            output.update(
                f"🎉 [bold green]SUCCESS:[/] Model [bold cyan]{model}[/] downloaded & verified!\n"
                f"📁 Location: [cyan]{dest_dir}[/]\n"
                f"👉 Click [bold green]⚡ Load Model[/] to activate it in OVMS."
            )
            self.notify(f"Model {model} downloaded and ready.", title="Download Complete")
        except Exception as exc:
            output.update(f"❌ [bold red]Download failed for {model}:[/] {exc}")
            self.notify(f"Download failed: {exc}", severity="error", title="Download Failed")
        finally:
            self._refresh_runtime(preserve_action_output=True)

    def _run_model_action(self, command: str, *, requires_model: bool = True) -> None:
        model = self._selected_management_model() if requires_model else None
        if requires_model and not model:
            self.notify("Please select a target model from the dropdown first.", severity="warning")
            return
        asyncio.create_task(self._management_worker(command, model))

    async def _management_worker(self, command: str, model: str | None) -> None:
        output = self.query_one("#action-output", Static)
        output.update(f"⏳ Switching active model to [bold cyan]{model or 'config'}[/] (updating OVMS)...")
        try:
            result = await asyncio.to_thread(run_management_command, self.config, command, model)
            output.update(format_management_result(result))
            if result.returncode == 0:
                self.notify(f"Switched active model to {model or 'current'}.", title="Model Loaded")
            else:
                self.notify(f"Action '{command}' failed with exit code {result.returncode}.", severity="error", title="Action Failed")
        except Exception as exc:
            output.update(f"[red]Error:[/] {exc}")
            self.notify(f"Execution error: {exc}", severity="error")
        self._refresh_runtime(preserve_action_output=True)

    def _start_component(self, component: str) -> None:
        try:
            start_runtime_component(self.config, component)
            self.notify(f"Triggered background launch for {component.upper()}.", title="Service Starting")
            self.set_timer(2.5, self.action_refresh)
        except Exception as exc:
            self.notify(f"Could not start {component}: {exc}", severity="error", title="Launch Error")


def main() -> None:
    ArcAiApp().run()


if __name__ == "__main__":
    main()
