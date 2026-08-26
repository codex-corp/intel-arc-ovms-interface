from __future__ import annotations

from typing import List, Tuple
from rich.text import Text
from textual import events, on
from textual.binding import Binding
from textual.content import Content
from textual.message import Message
from textual.reactive import var
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Markdown, Static
from textual.widgets._markdown import MarkdownBlock, MarkdownFence
from textual.widgets.markdown import MarkdownStream

from tools.tui.arabic_utils import is_arabic_or_rtl
from tools.tui.theme import pill_markup
from tools.tui.widgets.highlighted_textarea import HighlightedTextArea


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


class AgentThought(Markdown, can_focus=True):
    """Streaming thought / internal reasoning process with collapsible Markdown support."""

    DEFAULT_CLASSES = "thought-card"
    _stream: var[MarkdownStream | None] = var(None)

    def __init__(self, initial_text: str = "", *, id: str | None = None, classes: str | None = None):
        super().__init__(initial_text, id=id, classes=f"thought-card {classes or ''}".strip())
        self.border_title = " 🧠 THOUGHT PROCESS "

    @property
    def stream(self) -> MarkdownStream:
        if self._stream is None:
            self._stream = self.get_stream(self)
        return self._stream

    async def append_fragment(self, fragment: str) -> None:
        self.loading = False
        await self.stream.write(fragment)
        self.scroll_end(animate=False)


# Alias for backward compatibility
ThoughtCard = AgentThought


class ConversationCodeFence(MarkdownFence):
    """Custom code fence block featuring a header bar with language badge and a clickable Copy button."""

    DEFAULT_CSS = """
    ConversationCodeFence {
        margin: 1 0;
        padding: 0;
        background: #151720;
        border: solid #2c3140;
        width: 1fr;
        height: auto;
    }
    ConversationCodeFence:focus-within {
        border: solid $accent;
    }
    .code-fence-header {
        height: 1;
        background: #1e2230;
        padding: 0 1;
        align: left middle;
        border-bottom: solid #2c3140;
    }
    .code-fence-lang {
        color: $accent;
        text-style: bold;
        width: 1fr;
    }
    .code-fence-copy-btn {
        min-width: 12;
        height: 1;
        background: #2b3042;
        color: $text;
        border: none;
        padding: 0 1;
        text-style: bold;
    }
    .code-fence-copy-btn:hover {
        background: $primary;
        color: #ffffff;
    }
    .code-fence-body {
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        lang_display = (self.lexer or "code").upper()
        icon = "🐍" if "py" in self.lexer.lower() else "⚡" if any(k in self.lexer.lower() for k in ["sh", "bash", "ps", "cmd"]) else "📄"
        with Horizontal(classes="code-fence-header"):
            yield Static(f"{icon} {lang_display}", classes="code-fence-lang")
            yield Button("📋 Copy Code", id="copy-fence-btn", classes="code-fence-copy-btn")
        yield Label(self._highlighted_code, id="code-content", classes="code-fence-body", expand=True)

    @on(Button.Pressed, "#copy-fence-btn")
    def on_copy_fence_button(self, event: Button.Pressed) -> None:
        event.stop()
        text_to_copy = self.code
        try:
            import pyperclip
            pyperclip.copy(text_to_copy)
        except Exception:
            pass
        try:
            self.app.copy_to_clipboard(text_to_copy)
        except Exception:
            pass
        lang = self.lexer or "code"
        self.post_message(AgentResponse.CodeCopied(lang, len(text_to_copy)))


class AgentResponseMarkdown(Markdown):
    """Markdown renderer using custom ConversationCodeFence blocks."""

    def get_block_class(self, block_name: str) -> type[MarkdownBlock]:
        if block_name == "fence":
            return ConversationCodeFence
        return super().get_block_class(block_name)


class AgentResponse(Vertical):
    """Streaming Markdown response container featuring an assistant header, copy response button, and code fence copy buttons."""

    DEFAULT_CLASSES = "chat-assistant-card"

    class CodeCopied(Message):
        """Emitted when code is copied to clipboard."""

        def __init__(self, language: str, length: int) -> None:
            self.language = language
            self.length = length
            super().__init__()

    class ResponseCopied(Message):
        """Emitted when full response is copied."""

        def __init__(self, length: int) -> None:
            self.length = length
            super().__init__()

    def __init__(self, initial_markdown: str = "", *, model_name: str = "", id: str | None = None, classes: str | None = None):
        super().__init__(id=id, classes=f"chat-assistant-card {classes or ''}".strip())
        self.raw_text = initial_markdown
        self.model_name = model_name
        self._markdown_widget = AgentResponseMarkdown(initial_markdown, id="assistant-markdown")
        self._stream: MarkdownStream | None = None

    def compose(self) -> ComposeResult:
        yield self._markdown_widget
        with Horizontal(classes="assistant-card-footer"):
            model_tag = f"✦ {self.model_name}" if self.model_name else "✦ Assistant"
            yield Static(model_tag, classes="assistant-footer-model")
            yield Button("📋 Copy", id="copy-response-btn", classes="copy-response-btn")

    @property
    def stream(self) -> MarkdownStream:
        if self._stream is None:
            self._stream = self._markdown_widget.get_stream(self._markdown_widget)
        return self._stream

    async def append_fragment(self, fragment: str) -> None:
        self.raw_text += fragment
        await self.stream.write(fragment)
        self.scroll_end(animate=False)

    @on(Button.Pressed, "#copy-response-btn")
    def on_copy_response(self, event: Button.Pressed) -> None:
        event.stop()
        text_to_copy = self.raw_text
        try:
            import pyperclip
            pyperclip.copy(text_to_copy)
        except Exception:
            pass
        try:
            self.app.copy_to_clipboard(text_to_copy)
        except Exception:
            pass
        self.post_message(self.ResponseCopied(len(text_to_copy)))


class UserInput(Horizontal):
    """User input prompt block matching Toad's UserInput component."""

    DEFAULT_CLASSES = "user-input-block"

    def __init__(self, content: str, *, timestamp: str = "", id: str | None = None, classes: str | None = None):
        is_rtl = is_arabic_or_rtl(content)
        rtl_class = "-rtl" if is_rtl else ""
        super().__init__(id=id, classes=f"user-input-block {rtl_class} {classes or ''}".strip())
        self.content = content
        self.timestamp = timestamp

    def compose(self) -> ComposeResult:
        yield Static("❯", id="prompt")
        yield Markdown(self.content, id="content")


# Alias for backward compatibility
UserMessageCard = UserInput


class PromptTextArea(HighlightedTextArea):
    """Markdown prompt editor with live code fence syntax highlighting, mouse selection, cut/paste, and multi-line keys."""

    BINDINGS = [
        Binding("shift+enter,shift+return,ctrl+j", "newline", "Line", key_display="⇧+⏎", priority=True),
        Binding("enter,return", "submit", "Send", key_display="⏎", priority=True),
        Binding("tab", "tab_complete", "Complete", priority=True),
    ]

    class TabCompleteRequested(Message):
        """Emitted when Tab key is pressed in the prompt editor."""

    class Submitted(Message):
        """Emitted when Enter key is pressed to submit the prompt."""

        def __init__(self, text: str) -> None:
            self.text = text
            super().__init__()

    def __init__(
        self,
        text: str = "",
        *,
        placeholder: str = "What would you like to do?",
        id: str | None = "chat-input",
        classes: str | None = None,
    ):
        super().__init__(
            text,
            id=id,
            classes=classes,
            placeholder=placeholder,
        )
        self.highlight_language = "markdown"

    def action_submit(self) -> None:
        """Submits the current prompt text."""
        self.post_message(self.Submitted(self.text))

    def action_newline(self) -> None:
        """Inserts a newline at the current cursor position."""
        self.insert("\n")

    def action_tab_complete(self) -> None:
        """Requests tab autocompletion."""
        self.post_message(self.TabCompleteRequested())
