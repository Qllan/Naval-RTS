"""Contract tests for approved Style Bible 1.0 target tokens.

These do not pretend to visually validate live pygame art.
"""

import re
from pathlib import Path

import pytest

from nine.gfx.style_tokens import (
    COLOR_HEX, LOD_TIERS, MATERIALS, STYLE_VERSION, contrast_ratio,
    lod_for_length, rgb,
)


DOCUMENT = Path(__file__).resolve().parents[1] / "docs" / "design" / "style-bible-v1.md"


def test_style_tokens_have_valid_hex_channels_and_version():
    assert STYLE_VERSION == "1.0"
    assert len(COLOR_HEX) >= 25
    for token, code in COLOR_HEX.items():
        assert re.fullmatch(r"#[0-9A-F]{6}", code), token
        channels = rgb(token)
        assert len(channels) == 3 and all(0 <= c <= 255 for c in channels)


@pytest.mark.parametrize("label", (
    "ui_text", "ui_muted", "ui_focus", "ui_warning", "ui_error", "ui_good",
))
@pytest.mark.parametrize("background", ("ui_bg", "ui_panel", "ui_raised"))
def test_all_text_and_status_tokens_have_aa_contrast(label, background):
    assert contrast_ratio(label, background) >= 4.5


def test_materials_reference_known_tokens_and_have_bounded_wear():
    for material in MATERIALS.values():
        assert material.base in COLOR_HEX
        assert material.shadow in COLOR_HEX
        assert material.edge in COLOR_HEX
        assert material.wear_coverage <= 0.30


def test_lod_is_total_nonoverlapping_and_based_on_screen_size():
    assert [(t.name, t.min_pixels, t.max_pixels) for t in LOD_TIERS] == [
        ("far", 0, 24), ("tactical", 24, 84), ("inspection", 84, None)]
    assert [lod_for_length(size) for size in (0, 23.99, 24, 83.99, 84, 256)] == [
        "far", "far", "tactical", "tactical", "inspection", "inspection"]
    with pytest.raises(ValueError):
        lod_for_length(-1)


def test_documented_palette_matches_code_exactly():
    doc = DOCUMENT.read_text(encoding="utf-8")
    for name, code in COLOR_HEX.items():
        assert f"| `{name}` | `{code}` |" in doc
    assert "N-17" in doc and "M-08" in doc and "B-31" in doc
    assert "Slot.diagram_pos" in doc and "Slot.pos" in doc


def test_style_tokens_do_not_mutate_live_game_palette():
    from nine.gfx import palette as old

    assert old.OCEAN_DEEP == (8, 18, 30)
    assert old.VEIL_TINT == (84, 44, 128)
    # The new target is intentionally distinct until R1.3.
    assert rgb("water_deep") != old.OCEAN_DEEP
