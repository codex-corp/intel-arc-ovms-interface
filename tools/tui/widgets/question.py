from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional
from textual import events, on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import HorizontalGroup, VerticalGroup
from textual.message import Message
from textual.widgets import Label, Static


@dataclass
class Ask:
    """Prompt payload for asking a question with selectable options."""

    question: str
    options: List[str]
    callback: Optional[Callable[[int, str], Any]] = None
    details: Optional[str] = None


class QuestionOption(HorizontalGroup):
    """Single selectable option row with number badge and hover styling."""

    DEFAULT_CSS = """
    QuestionOption {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        margin: 0 0;
    }

    QuestionOption:hover {
        background: $boost;
        color: $text;
    }

    QuestionOption.-highlighted {
        background: $primary 25%;
        color: $text-accent;
        text-style: bold;
    }
    """

    def __init__(self, index: int, label: str, *, is_highlighted: bool = False, classes: str | None = None):
        super().__init__(classes=f"{classes or ''} {'-highlighted' if is_highlighted else ''}".strip())
        self.index = index
        self.label_text = label

    def compose(self) -> ComposeResult:
        key_num = f"[{self.index + 1}]"
        yield Label(f"[bold cyan]{key_num}[/] {self.label_text}", id=f"opt-label-{self.index}")


class Question(VerticalGroup, can_focus=True):
    """Interactive multi-choice & confirmation widget for prompt swapping."""

    DEFAULT_CSS = """
    Question {
        height: auto;
        background: black 25%;
        border: round $primary;
        padding: 1;
        margin: 0 0 1 0;
        display: none;
    }

    #question-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }

    #question-details {
        color: $text-muted;
        background: $surface 50%;
        border-left: outer $secondary;
        padding: 0 1;
        margin-bottom: 1;
    }

    #question-options-container {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("1", "select_1", "Option 1", show=False, priority=True),
        Binding("2", "select_2", "Option 2", show=False, priority=True),
        Binding("3", "select_3", "Option 3", show=False, priority=True),
        Binding("4", "select_4", "Option 4", show=False, priority=True),
        Binding("5", "select_5", "Option 5", show=False, priority=True),
        Binding("6", "select_6", "Option 6", show=False, priority=True),
        Binding("7", "select_7", "Option 7", show=False, priority=True),
        Binding("8", "select_8", "Option 8", show=False, priority=True),
        Binding("9", "select_9", "Option 9", show=False, priority=True),
        Binding("up", "cursor_up", "Up", priority=True, show=False),
        Binding("down", "cursor_down", "Down", priority=True, show=False),
        Binding("enter", "submit", "Select", priority=True),
        Binding("escape", "dismiss", "Dismiss", priority=True),
    ]

    @dataclass
    class Answer(Message):
        """Emitted when an option is selected."""

        index: int
        label: str

    @dataclass
    class Dismissed(Message):
        """Emitted when question is dismissed/cancelled."""

    def __init__(self, id: str | None = "chat-question", classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self.current_ask: Optional[Ask] = None
        self._highlighted_index: int = 0
        self.title_widget = Static("", id="question-title")
        self.details_widget = Static("", id="question-details")
        self.options_container = VerticalGroup(id="question-options-container")

    def compose(self) -> ComposeResult:
        yield self.title_widget
        yield self.details_widget
        yield self.options_container

    def present(self, ask: Ask) -> None:
        """Presents a question and its options to the user."""
        self.current_ask = ask
        self._highlighted_index = 0

        self.title_widget.update(f"[bold cyan]❯[/] [bold]{ask.question}[/]")

        if ask.details:
            self.details_widget.update(ask.details)
            self.details_widget.display = True
        else:
            self.details_widget.display = False

        self._render_options()
        self.display = True
        try:
            self.focus()
        except Exception:
            pass

    def _render_options(self) -> None:
        if not self.current_ask:
            return
        try:
            self.options_container.remove_children()
            for idx, opt_label in enumerate(self.current_ask.options):
                is_hl = idx == self._highlighted_index
                self.options_container.mount(QuestionOption(idx, opt_label, is_highlighted=is_hl))
        except Exception:
            # Fallback when running outside active app message loop
            pass

    def _select_index(self, index: int) -> None:
        if not self.current_ask or index < 0 or index >= len(self.current_ask.options):
            return
        label = self.current_ask.options[index]
        callback = self.current_ask.callback
        self.display = False

        if callback:
            callback(index, label)

        try:
            self.post_message(self.Answer(index, label))
        except Exception:
            pass
        self.current_ask = None

    def action_cursor_up(self) -> None:
        if not self.current_ask:
            return
        self._highlighted_index = max(0, self._highlighted_index - 1)
        self._render_options()

    def action_cursor_down(self) -> None:
        if not self.current_ask:
            return
        self._highlighted_index = min(len(self.current_ask.options) - 1, self._highlighted_index + 1)
        self._render_options()

    def action_submit(self) -> None:
        self._select_index(self._highlighted_index)

    def action_dismiss(self) -> None:
        self.display = False
        self.current_ask = None
        try:
            self.post_message(self.Dismissed())
        except Exception:
            pass

    def action_select_1(self) -> None: self._select_index(0)
    def action_select_2(self) -> None: self._select_index(1)
    def action_select_3(self) -> None: self._select_index(2)
    def action_select_4(self) -> None: self._select_index(3)
    def action_select_5(self) -> None: self._select_index(4)
    def action_select_6(self) -> None: self._select_index(5)
    def action_select_7(self) -> None: self._select_index(6)
    def action_select_8(self) -> None: self._select_index(7)
    def action_select_9(self) -> None: self._select_index(8)

    @on(events.Click, "QuestionOption")
    def on_option_clicked(self, event: events.Click) -> None:
        for child in self.query(QuestionOption):
            if child == event.widget or child in event.widget.ancestors:
                self._select_index(child.index)
                break
