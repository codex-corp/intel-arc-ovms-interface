from __future__ import annotations

from typing import List
from rich.text import Text
from textual.theme import Theme

try:
    from textual.content import Content
except ImportError:
    Content = None


def pill(text: str, background: str = "rgb(40,42,54)", foreground: str = "rgb(189,147,249)") -> Text:
    """Formats text with half-block ends (▌text▐) matching the Toad design aesthetic.

    Args:
        text: Badge label string.
        background: Terminal background color or style.
        foreground: Foreground text color.

    Returns:
        Rich Text instance with styled pill edges.
    """
    badge = Text()
    badge.append("▌", style=f"{background}")
    badge.append(f" {text} ", style=f"{foreground} on {background} bold")
    badge.append("▐", style=f"{background}")
    return badge


def pill_markup(text: str, background: str = "#334155", foreground: str = "#f1f5f9") -> str:
    """Returns Rich markup string for inline pill badges."""
    return f"[{background}]▌[/][bold {foreground} on {background}] {text} [/][{background}]▐[/]"


# Curated Themes with Toad/Tokyo-Night/Dracula/Arc aesthetics
CURATED_THEMES: List[Theme] = [
    Theme(
        name="toad-dark",
        primary="#50fa7b",      # Green accent (tools & success)
        secondary="#bd93f9",    # Purple accent (model pill & prompts)
        accent="#8be9fd",       # Cyan accent
        foreground="#f8f8f2",
        background="#1e1f29",   # Deep slate background
        surface="#282a36",
        panel="#21222c",
        boost="#343746",
        success="#50fa7b",
        warning="#f1fa8c",
        error="#ff5555",
        dark=True,
    ),
    Theme(
        name="arc-cyberpunk",
        primary="#00c7fd",
        secondary="#38bdf8",
        accent="#a855f7",
        foreground="#f1f5f9",
        background="#080c14",
        surface="#0b1120",
        panel="#111c33",
        boost="#0f1d3a",
        success="#10b981",
        warning="#f59e0b",
        error="#ef4444",
        dark=True,
    ),
    Theme(
        name="arc-titan",
        primary="#38bdf8",
        secondary="#0284c7",
        accent="#a855f7",
        foreground="#e2e8f0",
        background="#0f172a",
        surface="#1e293b",
        panel="#334155",
        boost="#1e3a5f",
        success="#22c55e",
        warning="#eab308",
        error="#f43f5e",
        dark=True,
    ),
]
