"""Minimal Slack command handler for preorder operations."""
from typing import Dict

from ..src.analyze_readiness import analyze_readiness


def handle_slash(command: str, text: str = "") -> str:
    """Handle incoming slash commands.

    Currently supports only `/preorders list` returning a simple string of ISBNs.
    """
    if command == "/preorders" and text.strip() == "list":
        rows = analyze_readiness()
        if not rows:
            return "No preorders ready for release."
        lines = [f"{r['isbn']} - {r['title']}" for r in rows]
        return "\n".join(lines)
    return "Command not recognized."
