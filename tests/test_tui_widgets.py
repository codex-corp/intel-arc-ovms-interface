from __future__ import annotations

import unittest
from tools.tui.theme import pill, pill_markup, CURATED_THEMES
from tools.tui.widgets.chat_widgets import (
    AgentResponse,
    AgentThought,
    PlanCard,
    PromptTextArea,
    TerminalToolCard,
    ThoughtCard,
    ToolCallHeader,
    UserMessageCard,
)
from tools.tui.widgets.highlighted_textarea import HighlightedTextArea
from tools.tui.widgets.question import Ask, Question
from tools.tui.widgets.slash_command import DEFAULT_SLASH_COMMANDS, SlashCommand, SlashComplete


class TuiWidgetsAndThemeTests(unittest.TestCase):
    """Unit tests for Toad-style TUI widgets, Markdown stream, and prompt editor."""

    def test_pill_helpers(self):
        text_badge = pill("Qwen2.5", "#bd93f9", "#1e1f29")
        self.assertIn("Qwen2.5", text_badge.plain)
        self.assertTrue(text_badge.plain.startswith("▌"))
        self.assertTrue(text_badge.plain.endswith("▐"))

        markup = pill_markup("shell", "#21222c", "#8be9fd")
        self.assertIn("▌", markup)
        self.assertIn("shell", markup)
        self.assertIn("▐", markup)

    def test_curated_themes_structure(self):
        self.assertTrue(len(CURATED_THEMES) >= 3)
        theme_names = [t.name for t in CURATED_THEMES]
        self.assertIn("toad-dark", theme_names)
        self.assertIn("arc-cyberpunk", theme_names)

    def test_terminal_tool_card_creation(self):
        cmd = "find . -type f -name '*.xml'"
        output = "./models/Qwen/openvino_model.xml\n"
        card = TerminalToolCard(command=cmd, output=output, status="success")
        self.assertEqual(card.command, cmd)
        self.assertEqual(card.status, "success")
        self.assertIn(cmd, card.border_title)
        self.assertEqual(card.render().plain.strip(), output.strip())

    def test_plan_card_step_rendering(self):
        steps = [
            ("done", "Step 1: Check memory"),
            ("active", "Step 2: Load model"),
            ("pending", "Step 3: Benchmark"),
        ]
        card = PlanCard(steps=steps, title="Execution Plan")
        self.assertEqual(card.border_title, " Execution Plan ")
        rendered = card.render().plain
        self.assertIn("Step 1: Check memory", rendered)
        self.assertIn("Step 2: Load model", rendered)
        self.assertIn("Step 3: Benchmark", rendered)

    def test_thought_and_user_cards(self):
        thought = ThoughtCard("Analyzing layers...")
        self.assertIn("THOUGHT", thought.border_title)

        user_card = UserMessageCard("Hello Arc", timestamp="12:00:00")
        self.assertEqual(user_card.content, "Hello Arc")
        self.assertEqual(user_card.timestamp, "12:00:00")

    def test_highlighted_prompt_textarea(self):
        prompt_editor = PromptTextArea("```python\nprint('hello')\n```")
        self.assertEqual(prompt_editor.highlight_language, "markdown")
        lines = prompt_editor.highlight_lines
        self.assertTrue(len(lines) >= 3)
        first_line = prompt_editor.get_line(0)
        self.assertTrue(bool(first_line.plain))

        # Test action_submit and action_newline
        prompt_editor.action_submit()
        prompt_editor.action_newline()
        self.assertIn("\n", prompt_editor.text)

    def test_agent_response_and_thought_markdown(self):
        resp = AgentResponse("# Heading\n```python\nval = 42\n```\n| col1 | col2 |\n|---|---|\n| a | b |")
        self.assertIsNotNone(resp)
        thought = AgentThought("Thinking about the algorithm...")
        self.assertIsNotNone(thought)

    def test_slash_complete_widget(self):
        def sample_completer(cmd: str, arg: str):
            if cmd == "/model":
                return [("Qwen2.5-Coder", "Downloaded"), ("Llama-3.2", "Ready")]
            return []

        sc = SlashComplete(dynamic_completer=sample_completer)
        self.assertTrue(len(sc.commands) >= 5)
        sc.filter_commands("/mod")
        self.assertEqual(len(sc._filtered), 1)
        self.assertEqual(sc._filtered[0][0], "/model ")

        # Dynamic argument completion for /model <arg>
        sc.filter_commands("/model ")
        self.assertEqual(len(sc._filtered), 2)
        self.assertEqual(sc._filtered[0][0], "/model Qwen2.5-Coder")

        sc.filter_commands("/")
        self.assertEqual(len(sc._filtered), len(DEFAULT_SLASH_COMMANDS))

        sc.filter_commands("")
        self.assertEqual(len(sc._filtered), 0)
        self.assertFalse(sc.display)

    def test_question_widget(self):
        callback_result = []

        def on_answer(idx: int, label: str):
            callback_result.append((idx, label))

        ask_payload = Ask(
            question="Proceed with download?",
            options=["Yes, download", "Cancel"],
            callback=on_answer,
            details="Estimated size: 4.2 GB",
        )
        q = Question()
        q.present(ask_payload)
        self.assertEqual(q.current_ask.question, "Proceed with download?")
        self.assertEqual(len(q.current_ask.options), 2)

        # Simulate choosing option 0
        q._select_index(0)
        self.assertEqual(callback_result, [(0, "Yes, download")])
        self.assertFalse(q.display)

    def test_arabic_shaping_and_rtl(self):
        from tools.tui.arabic_utils import is_arabic_or_rtl

        arabic_sample = "مرحبا بالعالم"
        english_sample = "Hello World"

        self.assertTrue(is_arabic_or_rtl(arabic_sample))
        self.assertFalse(is_arabic_or_rtl(english_sample))
        self.assertFalse(is_arabic_or_rtl(""))

        # Test UserMessageCard gets RTL CSS class for Arabic content
        arabic_card = UserMessageCard(arabic_sample)
        self.assertIn("-rtl", arabic_card.classes)

        # English card should NOT get RTL class
        english_card = UserMessageCard(english_sample)
        self.assertNotIn("-rtl", english_card.classes)

    def test_mode_switcher_personas(self):
        from tools.tui.widgets.mode_switcher import BUILTIN_MODES, ModeSwitcher, PersonaMode

        # Verify built-in modes structure
        self.assertTrue(len(BUILTIN_MODES) >= 4)
        mode_ids = [m.id for m in BUILTIN_MODES]
        self.assertIn("default", mode_ids)
        self.assertIn("code", mode_ids)
        self.assertIn("openvino", mode_ids)
        self.assertIn("shell", mode_ids)

        # Verify each mode has required fields
        for mode in BUILTIN_MODES:
            self.assertIsInstance(mode, PersonaMode)
            self.assertTrue(mode.id)
            self.assertTrue(mode.name)
            self.assertTrue(mode.description)
            self.assertTrue(mode.system_prompt)
            self.assertTrue(mode.placeholder)
            self.assertTrue(mode.icon)

        # Verify ModeSwitcher widget creation and mode lookup
        switcher = ModeSwitcher(id="test-switcher")
        self.assertEqual(len(switcher.modes), len(BUILTIN_MODES))
        default_mode = switcher.get_mode("default")
        self.assertIsNotNone(default_mode)
        self.assertEqual(default_mode.name, "Default")
        self.assertIsNone(switcher.get_mode("nonexistent"))

    def test_code_copied_message(self):
        # Verify CodeCopied message can be created
        event = AgentResponse.CodeCopied("python", 42)
        self.assertEqual(event.language, "python")
        self.assertEqual(event.length, 42)

        # Verify ResponseCopied message
        resp_event = AgentResponse.ResponseCopied(128)
        self.assertEqual(resp_event.length, 128)

        # Verify AgentResponse creation and children
        resp_card = AgentResponse("# Header\n```python\nprint('hello')\n```", model_name="Qwen")
        self.assertIn("Qwen", resp_card.model_name)


if __name__ == "__main__":
    unittest.main()
