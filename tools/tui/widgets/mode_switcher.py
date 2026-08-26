"""Persona & Inference Mode Switcher for Intel Arc AI Studio.

Inspired by Toad's ModeSwitcher, this provides a popup to switch between
different AI persona modes that adjust the system prompt, generation parameters,
and prompt placeholder dynamically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


@dataclass
class PersonaMode:
    """Defines a persona mode with its system prompt and UI metadata."""

    id: str
    name: str
    description: str
    system_prompt: str
    placeholder: str = "What would you like to do?"
    icon: str = "●"
    generation_params: dict = field(default_factory=dict)


# Built-in persona modes for Intel Arc AI Studio
BUILTIN_MODES: list[PersonaMode] = [
    PersonaMode(
        id="default",
        name="Default",
        description="Balanced general intelligence assistant",
        system_prompt=(
            "You are a helpful AI assistant running locally on Intel Arc hardware "
            "via OpenVINO Model Server. Be concise, accurate, and helpful."
        ),
        placeholder="What would you like to do? (Type / for commands, ⏎ to send)",
        icon="✦",
    ),
    PersonaMode(
        id="code",
        name="Code Assistant",
        description="Programming & code generation specialist",
        system_prompt=(
            "You are an expert programming assistant. Write clean, well-documented code. "
            "Use proper formatting with markdown code fences. Minimize conversational filler. "
            "When asked to fix or modify code, show only the relevant changes."
        ),
        placeholder="Describe what you'd like to code...",
        icon="⌨",
        generation_params={"temperature": 0.3},
    ),
    PersonaMode(
        id="openvino",
        name="OpenVINO Expert",
        description="Intel Arc optimization & quantization expert",
        system_prompt=(
            "You are an expert in Intel OpenVINO toolkit, Intel Arc GPU architecture, NPU offload, "
            "INT4/INT8 precision quantization, ONNX model conversion, and inference latency tuning. "
            "Provide specific, actionable advice for optimizing AI models on Intel hardware."
        ),
        placeholder="Ask about OpenVINO optimization...",
        icon="⚡",
        generation_params={"temperature": 0.4},
    ),
    PersonaMode(
        id="shell",
        name="Shell Assistant",
        description="PowerShell & command-line specialist",
        system_prompt=(
            "You are a command-line expert. Format output as direct executable PowerShell or Bash commands. "
            "Use code fences with the appropriate shell language. Minimize explanation unless asked. "
            "Prefer one-liners and pipelines where possible."
        ),
        placeholder="What command do you need?",
        icon="❯",
        generation_params={"temperature": 0.2},
    ),
]


class ModeSwitcher(Vertical):
    """Floating popup for switching between AI persona modes.

    Displays as a modern overlay card anchored in the studio interface.
    """

    BINDING_GROUP_TITLE = "Mode switcher"
    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss mode switcher"),
    ]

    class ModeSelected(Message):
        """Emitted when a persona mode is selected."""

        def __init__(self, mode_id: str) -> None:
            self.mode_id = mode_id
            super().__init__()

    def __init__(
        self,
        modes: list[PersonaMode] | None = None,
        *,
        id: str | None = "mode-switcher",
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        self._modes = modes or BUILTIN_MODES
        self._current_mode_id = "default"

    def compose(self) -> ComposeResult:
        with Horizontal(classes="mode-switcher-header"):
            yield Static("✦ INFERENCE MODES & PERSONAS", classes="mode-switcher-title")
            yield Static("[dim]Esc close[/]", classes="mode-switcher-esc-hint")
        yield Static("Select a persona to tailor system instructions and generation style:", classes="mode-switcher-desc")

        options = []
        for m in self._modes:
            active_badge = " [bold green]● ACTIVE[/]" if m.id == self._current_mode_id else ""
            options.append(
                Option(
                    f"{m.icon} [bold cyan]{m.name}[/]{active_badge}\n  [dim]{m.description}[/]",
                    id=m.id,
                )
            )
        yield OptionList(*options, id="mode-option-list")

        with Horizontal(classes="mode-switcher-footer"):
            yield Static("[dim]↑/↓ Navigate  •  Enter Select  •  Esc Dismiss[/]", classes="mode-switcher-hints")

    def set_active_mode(self, mode_id: str) -> None:
        self._current_mode_id = mode_id
        try:
            opt_list = self.query_one("#mode-option-list", OptionList)
            opt_list.clear_options()
            for m in self._modes:
                active_badge = " [bold green]● ACTIVE[/]" if m.id == mode_id else ""
                opt_list.add_option(
                    Option(
                        f"{m.icon} [bold cyan]{m.name}[/]{active_badge}\n  [dim]{m.description}[/]",
                        id=m.id,
                    )
                )
        except Exception:
            pass

    def focus_options(self) -> None:
        try:
            self.query_one("#mode-option-list", OptionList).focus()
        except Exception:
            pass

    def get_mode(self, mode_id: str) -> PersonaMode | None:
        """Returns the PersonaMode for the given ID."""
        for m in self._modes:
            if m.id == mode_id:
                return m
        return None

    @property
    def modes(self) -> list[PersonaMode]:
        return self._modes

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id:
            self.set_active_mode(event.option_id)
            self.post_message(self.ModeSelected(event.option_id))
        self.display = False

    def action_dismiss(self) -> None:
        self.display = False
