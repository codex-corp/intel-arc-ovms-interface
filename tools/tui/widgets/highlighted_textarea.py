from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from pygments.token import Token
from rich.text import Text
from textual import on
from textual.content import Content
from textual.highlight import HighlightTheme, TokenType, highlight
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import TextArea
from textual.widgets.text_area import Selection

RE_MATCH_FILE_PROMPT = re.compile(r"(@\S+)|@\"(.*)\"")
RE_SLASH_COMMAND = re.compile(r"(\/\S*)(\W.*)?$")


class TextualHighlightTheme(HighlightTheme):
    """Style definition mapping Pygments tokens to Textual design tokens."""

    STYLES: dict[TokenType, str] = {
        Token.Comment: "$text-muted",
        Token.Error: "$text-error on $error 20%",
        Token.Generic.Strong: "bold",
        Token.Generic.Emph: "italic",
        Token.Generic.Error: "$text-error",
        Token.Generic.Heading: "$primary bold underline",
        Token.Generic.Subheading: "$primary bold",
        Token.Keyword: "$accent bold",
        Token.Keyword.Constant: "$success bold",
        Token.Keyword.Namespace: "$secondary",
        Token.Keyword.Type: "$accent",
        Token.Literal.Number: "$warning",
        Token.Literal.String.Backtick: "$text-muted",
        Token.Literal.String: "$success",
        Token.Literal.String.Doc: "$success italic",
        Token.Literal.String.Double: "$success",
        Token.Name: "$text",
        Token.Name.Attribute: "$warning",
        Token.Name.Builtin: "$accent",
        Token.Name.Builtin.Pseudo: "italic",
        Token.Name.Class: "$warning bold",
        Token.Name.Constant: "$error",
        Token.Name.Decorator: "$primary bold",
        Token.Name.Entity: "$text",
        Token.Name.Function: "$warning underline",
        Token.Name.Function.Magic: "$warning underline",
        Token.Name.Tag: "$primary bold",
        Token.Name.Variable: "$secondary",
        Token.Number: "$warning",
        Token.Operator: "bold",
        Token.Operator.Word: "bold $error",
        Token.String: "$success",
        Token.Whitespace: "",
    }


class HighlightedTextArea(TextArea):
    """Textarea with live syntax highlighting for Markdown, code fences, and tokens."""

    highlight_language = reactive("markdown")

    @dataclass
    class CursorMove(Message):
        selection: Selection

    def __init__(
        self,
        text: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
        placeholder: str | Content = "",
    ):
        self._text_cache: dict[int, Text] = {}
        self._highlight_lines: list[Content] | None = None
        super().__init__(
            text,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
            highlight_cursor_line=False,
            placeholder=placeholder,
        )
        self.compact = True

    def _clear_caches(self) -> None:
        self._highlight_lines = None
        self._text_cache.clear()

    def notify_style_update(self) -> None:
        self._clear_caches()
        return super().notify_style_update()

    def _watch_selection(self, previous_selection: Selection, selection: Selection) -> None:
        self.post_message(self.CursorMove(selection))
        super()._watch_selection(previous_selection, selection)

    @property
    def highlight_lines(self) -> Sequence[Content]:
        if self._highlight_lines is None:
            text = self.text
            if text.startswith("/") and "\n" not in text:
                content = self.highlight_slash_command(text)
                self._highlight_lines = [content]
                return self._highlight_lines

            language = self.highlight_language
            if language == "markdown":
                content = self.highlight_markdown(text)
                content_lines = content.split("\n", allow_blank=True)[:-1]
                self._highlight_lines = content_lines
            elif language == "shell":
                content = self.highlight_shell(text)
                content_lines = content.split("\n", allow_blank=True)
                self._highlight_lines = content_lines
            else:
                content = Content(text)
                self._highlight_lines = content.split("\n", allow_blank=True)
        return self._highlight_lines

    def highlight_slash_command(self, text: str) -> Content:
        return Content.styled(text, "$text-success")

    def highlight_markdown(self, text: str) -> Content:
        """Highlights markdown content with code fences and @path references."""
        content = highlight(
            text + "\n```",
            language="markdown",
            theme=TextualHighlightTheme,
        )
        content = content.highlight_regex(RE_MATCH_FILE_PROMPT, style="$primary")
        return content

    def highlight_shell(self, text: str) -> Content:
        """Highlights bash/powershell command text."""
        return highlight(text, language="sh")

    @on(TextArea.Changed)
    def _on_changed(self) -> None:
        self._highlight_lines = None
        self._text_cache.clear()

    def get_line(self, line_index: int) -> Text:
        if (cached_line := self._text_cache.get(line_index)) is not None:
            return cached_line.copy()
        try:
            line = self.highlight_lines[line_index]
        except (IndexError, TypeError):
            return Text("", end="", no_wrap=True)
        rendered_line = list(line.render_segments(self.visual_style))
        text = Text.assemble(
            *[(seg_text, style) for seg_text, style, _ in rendered_line],
            end="",
            no_wrap=True,
        )
        self._text_cache[line_index] = text.copy()
        return text
