"""Shared UI theme tokens and style helpers."""

import customtkinter as ctk

APP_BG_COLOR = ("#f8fafc", "#0f172a")
CARD_FG_COLOR = ("#ffffff", "#1e293b")
DROP_ZONE_FG_COLOR = ("#f1f5f9", "#172033")
BORDER_COLOR = ("#cbd5e1", "#475569")
HOVER_COLOR = ("#e2e8f0", "#334155")
INPUT_FG_COLOR = ("#ffffff", "#111827")
INPUT_BORDER_COLOR = ("#cbd5e1", "#334155")
PRIMARY_TEXT_COLOR = ("#111827", "#f9fafb")
SECONDARY_TEXT_COLOR = ("#374151", "#d1d5db")
MUTED_TEXT_COLOR = ("#4b5563", "#9ca3af")
PROCESSING_TEXT_COLOR = ("#1d4ed8", "#60a5fa")
SUCCESS_TEXT_COLOR = ("#166534", "#4ade80")
ERROR_TEXT_COLOR = ("#b91c1c", "#f87171")
PRIMARY_BUTTON_FG_COLOR = ("#3B8ED0", "#1F6AA5")
PRIMARY_BUTTON_HOVER_COLOR = ("#36719F", "#144870")
SECONDARY_BUTTON_FG_COLOR = ("#e2e8f0", "#334155")
SECONDARY_BUTTON_HOVER_COLOR = ("#cbd5e1", "#475569")
SECONDARY_BUTTON_TEXT_COLOR = ("#111827", "#f9fafb")
DANGER_BUTTON_FG_COLOR = ("#b91c1c", "#dc2626")
DANGER_BUTTON_HOVER_COLOR = ("#991b1b", "#b91c1c")
SUCCESS_BUTTON_FG_COLOR = ("#16a34a", "#22c55e")
SUCCESS_BUTTON_HOVER_COLOR = ("#15803d", "#16a34a")
ACTION_BUTTON_TEXT_COLOR = ("#f8fafc", "#f8fafc")
CARD_CORNER_RADIUS = 12
CONTROL_HEIGHT = 34
PRIMARY_ACTION_HEIGHT = 40
SECTION_HEADING_SIZE = 15
SUBSECTION_HEADING_SIZE = 14
HELPER_TEXT_SIZE = 11
SELECTOR_FG_COLOR = ("#e6edf6", "#243247")
SELECTOR_BUTTON_COLOR = ("#c8d7ea", "#36506e")
SELECTOR_BUTTON_HOVER_COLOR = ("#b8cae0", "#456486")
SELECTOR_DROPDOWN_FG_COLOR = ("#ffffff", "#1b2636")


def neutral_option_menu_style() -> dict:
    """Shared neutral styling for option menus."""
    return {
        "height": CONTROL_HEIGHT,
        "corner_radius": 8,
        "fg_color": SELECTOR_FG_COLOR,
        "button_color": SELECTOR_BUTTON_COLOR,
        "button_hover_color": SELECTOR_BUTTON_HOVER_COLOR,
        "text_color": PRIMARY_TEXT_COLOR,
        "dropdown_fg_color": SELECTOR_DROPDOWN_FG_COLOR,
        "dropdown_hover_color": HOVER_COLOR,
        "dropdown_text_color": PRIMARY_TEXT_COLOR,
    }


def secondary_button_style() -> dict:
    """Shared secondary button styling."""
    return {
        "height": CONTROL_HEIGHT,
        "corner_radius": 8,
        "font": ctk.CTkFont(size=13),
        "fg_color": SECONDARY_BUTTON_FG_COLOR,
        "hover_color": SECONDARY_BUTTON_HOVER_COLOR,
        "text_color": SECONDARY_BUTTON_TEXT_COLOR,
    }

