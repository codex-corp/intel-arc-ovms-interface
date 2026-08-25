from __future__ import annotations

import unittest
from tools.tui.theme import pill, pill_markup, CURATED_THEMES
from tools.tui.widgets.chat_widgets import (
    PlanCard,
    TerminalToolCard,
    ThoughtCard,
    ToolCallHeader,
    UserMessageCard,
)


class TuiWidgetsAndThemeTests(unittest.TestCase):
    """Unit tests for Toad-style TUI widgets and theme helpers."""

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
        self.assertIn("Hello Arc", user_card.render().plain)
        self.assertIn("12:00:00", user_card.border_subtitle)


if __name__ == "__main__":
    unittest.main()
