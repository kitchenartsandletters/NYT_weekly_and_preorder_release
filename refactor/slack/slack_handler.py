"""Minimal Slack command handler for preorder operations."""
from typing import Dict

from ..src.readiness import analyze_readiness


def handle_slash(command: str, text: str = "") -> str:
    """Handle incoming slash commands.

    Currently supports only `/preorders list` returning a simple string of ISBNs.
    """
    if command == "/preorders" and text.strip() == "list":
        isbns = analyze_readiness()
        if not isbns:
            return "No preorders ready for release."
        return "\n".join(isbns)
    return "Command not recognized."
