from __future__ import annotations

from typing import List, Tuple
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, Markdown


class ToolCallHeader(Static):
    """Header line representing a tool invocation (e.g. '▶ 🔧 Find HTML, CSS, and JS files ✓')."""

    def __init__(self, title: str, *, status: str = "done", id: str | None = None, classes: str | None = None):
        check_icon = "✓" if status == "done" else "…"
        content = f"[bold cyan]▶[/] [bold yellow]🔧 {title}[/] [green]{check_icon}[/]"
        super().__init__(content, id=id, classes=f"tool-call-header {classes or ''}".strip())


class TerminalToolCard(Static):
    """Terminal command execution box styled with green panel border and title banner, matching Toad's TerminalTool."""

    DEFAULT_CLASSES = "terminal-tool-card"

    def __init__(
        self,
        command: str,
        output: str,
        *,
        status: str = "success",
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(output.strip(), id=id, classes=f"terminal-tool-card -{status} {classes or ''}".strip())
        self.command = command
        self.status = status
        self.border_title = f" {command} "


class PlanCard(Static):
    """Structured plan tracking card showing active/pending steps with step glyphs (➡, ⊙, ✔)."""

    DEFAULT_CLASSES = "plan-card"

    def __init__(
        self,
        steps: List[Tuple[str, str]],  # (status, text) where status is 'active', 'pending', 'done'
        *,
        title: str = "Plan",
        id: str | None = None,
        classes: str | None = None,
    ):
        self.steps = steps
        content = self._render_steps(steps)
        super().__init__(content, id=id, classes=f"plan-card {classes or ''}".strip())
        self.border_title = f" {title} "

    def _render_steps(self, steps: List[Tuple[str, str]]) -> str:
        lines = []
        for status, text in steps:
            if status in {"active", "in_progress"}:
                lines.append(f"[bold cyan]➡ {text}[/]")
            elif status in {"done", "completed"}:
                lines.append(f"[bold green]✔[/] [strike dim]{text}[/]")
            else:  # pending
                lines.append(f"[dim]⊙ {text}[/]")
        return "\n".join(lines)

    def update_steps(self, steps: List[Tuple[str, str]]) -> None:
        self.steps = steps
        self.update(self._render_steps(steps))


class ThoughtCard(Static):
    """Collapsible reasoning/thought stream card."""

    DEFAULT_CLASSES = "thought-card"

    def __init__(self, content: str = "", *, id: str | None = None, classes: str | None = None):
        super().__init__(content, id=id, classes=f"thought-card {classes or ''}".strip())
        self.border_title = " 🧠 THOUGHT PROCESS "


class UserMessageCard(Static):
    """User message card with Toad-style prefix and styling."""

    DEFAULT_CLASSES = "user-msg-card"

    def __init__(self, content: str, *, timestamp: str = "", id: str | None = None, classes: str | None = None):
        super().__init__(f"[bold cyan]❯[/] {content}", id=id, classes=f"user-msg-card {classes or ''}".strip())
        if timestamp:
            self.border_subtitle = f" {timestamp} "
