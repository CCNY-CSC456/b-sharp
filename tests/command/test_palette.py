"""REQ-OPS-003: the dashboard uses the Airfield color palette on charcoal."""

import re

import pytest

from src.command.dashboard import dashboard

# The agreed palette. If a color changes, change it here and in dashboard.html.
PALETTE = {
    "--bg": "#1c1d1f",             # charcoal page background
    "--available": "#6fd08c",      # runway status: Available
    "--not-available": "#b18cff",  # runway status: Not Available
    "--danger": "#ff6b6b",         # warnings and errors
    "--accent": "#d6d6d2",         # Send button, logo mark, focus ring
}

# Reserved for arriving and departing planes in a later requirement.
RESERVED_FOR_PLANES = ["#5ab4ff", "#ffb02e"]

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


# --- helpers -------------------------------------------------------------

def page_css():
    """The CSS inside the page's <style> tag, as the server sends it."""
    return re.search(r"<style>(.*?)</style>", dashboard(), re.S).group(1)


def root_block(css):
    """The first :root { ... } block, where every color token is defined."""
    return re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)


def tokens(css):
    """{"--bg": "#1c1d1f", ...} for every token in :root."""
    return {name: value.strip().lower() for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root_block(css))}


def rule(css, selector):
    """The body of the style rule for exactly this selector."""
    match = re.search(r"(?:^|[}\s])" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"no style rule for {selector}"
    return match.group(1)


def contrast(foreground, background):
    """WCAG contrast ratio between two hex colors, from 1 (none) to 21 (black on white)."""
    def luminance(hex_color):
        channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    lighter, darker = sorted([luminance(foreground), luminance(background)], reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


# --- tests ---------------------------------------------------------------

def test_palette_tokens_have_the_agreed_values():
    defined = tokens(page_css())
    for name, value in PALETTE.items():
        assert defined.get(name) == value, f"{name} should be {value}"


def test_colors_only_come_from_tokens():
    css = page_css()
    outside_root = css.replace(root_block(css), "")
    assert HEX.findall(outside_root) == []


def test_reserved_plane_colors_are_not_used_yet():
    css = page_css().lower()
    for color in RESERVED_FOR_PLANES:
        assert color not in css


def test_page_background_is_flat_charcoal():
    css = page_css()
    body = rule(css, "body")
    assert "var(--bg)" in body
    assert "gradient" not in body


def test_runway_status_colors():
    css = page_css()
    assert "var(--available)" in rule(css, ".runway-status")
    assert "var(--not-available)" in rule(css, ".runway-status.unavailable")
    assert "var(--not-available)" in rule(css, ".map-runway.unavailable")


def test_warnings_and_errors_are_red():
    css = page_css()
    for selector in [".status-pill.degraded", ".degraded-message", ".feedback.error"]:
        assert "var(--danger)" in rule(css, selector), selector


def test_accent_is_light_gray():
    css = page_css()
    assert "var(--accent)" in rule(css, ".send-button")
    assert "var(--accent)" in rule(css, ".brand-mark")
    assert "var(--accent)" in rule(css, ".message-input:focus")


@pytest.mark.parametrize("text_token", ["--text", "--muted", "--available", "--not-available", "--danger"])
@pytest.mark.parametrize("surface_token", ["--bg", "--panel", "--panel-raised"])
def test_text_is_readable_on_every_panel(text_token, surface_token):
    defined = tokens(page_css())
    assert contrast(defined[text_token], defined[surface_token]) >= 4.5


def test_send_button_text_is_readable():
    defined = tokens(page_css())
    assert contrast(defined["--on-accent"], defined["--accent"]) >= 4.5
    