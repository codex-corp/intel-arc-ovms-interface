from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalGroup
from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option


@dataclass
class SlashCommand:
    """Definition of a slash command available in Chat Studio."""

    command: str
    help: str
    hint: str | None = None
    action: Optional[str] = None


DEFAULT_SLASH_COMMANDS: List[SlashCommand] = [
    SlashCommand("/list", "List all discovered models and their readiness status"),
    SlashCommand("/status", "Display inference engine & API gateway health"),
    SlashCommand("/switch", "Switch active OpenVINO model in OVMS", "<name>"),
    SlashCommand("/model", "Alias for /switch to change active model", "<name>"),
    SlashCommand("/enable", "Enable a model in OVMS dynamic config", "<name>"),
    SlashCommand("/disable", "Disable a model in OVMS dynamic config", "<name>"),
    SlashCommand("/pull", "Download model weights from OpenVINO catalog", "<name>"),
    SlashCommand("/reload", "Trigger dynamic reload of OVMS configuration"),
    SlashCommand("/rollback", "Restore configuration from previous backup snapshot"),
    SlashCommand("/theme", "Switch UI theme palette", "<name>"),
    SlashCommand("/clear", "Clear chat canvas and message history"),
    SlashCommand("/help", "Display keyboard shortcuts and available commands"),
]


class SlashComplete(VerticalGroup):
    """Floating autocomplete popup for slash commands and dynamic argument completion."""

    DEFAULT_CSS = """
    SlashComplete {
        height: auto;
        max-height: 8;
        background: $surface;
        border: round $secondary;
        padding: 0;
        margin: 0 0 1 0;
        display: none;
    }

    SlashComplete OptionList {
        background: transparent;
        border: none;
        height: auto;
        max-height: 7;
        padding: 0;
    }

    SlashComplete OptionList:focus > .option-list--option-highlighted {
        background: $primary 30%;
        color: $text;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("up", "cursor_up", "Up", priority=True, show=False),
        Binding("down", "cursor_down", "Down", priority=True, show=False),
        Binding("tab", "submit", "Complete", priority=True),
        Binding("enter", "submit", "Select", priority=True),
        Binding("escape", "dismiss", "Dismiss", priority=True),
    ]

    @dataclass
    class Selected(Message):
        """Emitted when a command or dynamic argument is selected from the list."""

        completion: str

    @dataclass
    class Dismissed(Message):
        """Emitted when the slash complete popup is dismissed."""

    def __init__(
        self,
        commands: Iterable[SlashCommand] | None = None,
        *,
        dynamic_completer: Optional[Callable[[str, str], List[Tuple[str, str]]]] = None,
        id: str | None = "slash-complete",
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self.commands: List[SlashCommand] = list(commands) if commands else DEFAULT_SLASH_COMMANDS
        self._filtered: List[Tuple[str, str, str]] = []  # (completion_text, label, description)
        self.dynamic_completer = dynamic_completer
        self.option_list = OptionList(id="slash-option-list")
        self.display = False

    def compose(self) -> ComposeResult:
        yield self.option_list

    def on_mount(self) -> None:
        self.display = False

    def filter_commands(self, query: str) -> None:
        """Filters available commands or dynamically autocompletes arguments (e.g. /model <name>, /enable <name>)."""
        raw_text = query.lstrip()

        # If not starting with '/', always hide the menu
        if not raw_text.startswith("/"):
            self._filtered = []
            self.display = False
            return

        parts = raw_text.split(maxsplit=1)
        cmd_part = parts[0].lower()
        has_space = " " in raw_text
        arg_part = parts[1] if len(parts) > 1 else ""

        self._filtered = []

        # Case 1: Typing command arguments (e.g. "/model ", "/model qwen", "/enable ", "/disable ")
        if has_space and self.dynamic_completer:
            dynamic_options = self.dynamic_completer(cmd_part, arg_part)
            for val, desc in dynamic_options:
                completion = f"{cmd_part} {val}"
                label = f"[bold green]{cmd_part}[/] [bold cyan]{val}[/] [dim]— {desc}[/]"
                self._filtered.append((completion, label, desc))

        # Case 2: Typing command name (e.g. "/mod", "/", "/sw")
        if not self._filtered and not has_space:
            clean_cmd = cmd_part[1:]  # strip leading '/'
            if not clean_cmd:
                matches = self.commands
            else:
                prefix_matches = [c for c in self.commands if c.command.lower().startswith(f"/{clean_cmd}")]
                desc_matches = [c for c in self.commands if clean_cmd in c.help.lower() and c not in prefix_matches]
                matches = prefix_matches if prefix_matches else desc_matches

            for cmd in matches:
                hint_str = f" [cyan]{cmd.hint}[/]" if cmd.hint else ""
                label = f"[bold green]{cmd.command}[/]{hint_str} [dim]— {cmd.help}[/]"
                completion = f"{cmd.command} " if cmd.hint else cmd.command
                self._filtered.append((completion, label, cmd.help))

        try:
            self.option_list.clear_options()
            for idx, (comp, lbl, _) in enumerate(self._filtered):
                self.option_list.add_option(Option(lbl, id=str(idx)))

            if self._filtered:
                self.option_list.highlighted = 0
                self.display = True
            else:
                self.display = False
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        self.option_list.action_cursor_up()

    def action_cursor_down(self) -> None:
        self.option_list.action_cursor_down()

    def action_submit(self) -> None:
        if self.option_list.highlighted is not None and 0 <= self.option_list.highlighted < len(self._filtered):
            selected_completion = self._filtered[self.option_list.highlighted][0]
            self.post_message(self.Selected(selected_completion))
            self.display = False

    def action_dismiss(self) -> None:
        self.display = False
        self.post_message(self.Dismissed())

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            try:
                idx = int(str(event.option_id))
                if 0 <= idx < len(self._filtered):
                    self.post_message(self.Selected(self._filtered[idx][0]))
                    self.display = False
            except (ValueError, IndexError):
                pass
