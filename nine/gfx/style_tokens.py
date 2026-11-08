"""Naval-RTS Style Bible 1.0 — frozen design targets, NOT the live palette.

The existing pygame artwork continues to use gfx.palette / gfx.ui.
These tokens are a migration specification for the next art passes.
"""

from dataclasses import dataclass
from types import MappingProxyType


STYLE_VERSION = "1.0"

# Single source of truth for target HEX colors. These are non-emissive
# *design values*: scene exposure and weather may modulate the final pixel.
COLOR_HEX = MappingProxyType({
    "water_deep": "#081923",
    "water_mid": "#102B39",
    "water_ridge": "#295464",
    "water_foam": "#B3D1D4",
    "steel_shadow": "#1D2830",
    "steel_hull": "#465A65",
    "steel_deck": "#6D7C82",
    "steel_edge": "#A0ADB1",
    "steel_armor": "#627681",
    "steel_roof": "#899A9F",
    "steel_seam": "#263843",
    "steel_rust": "#7C604D",
    "signal_window": "#DCC68E",
    "signal_cyan": "#7DDAD5",
    "signal_cyan_low": "#438F92",
    "signal_amber": "#EAB96D",
    "signal_pirate": "#D8876E",
    "signal_friendly": "#85DED5",
    "veil_depth": "#1F4458",
    "veil_mist": "#467F91",
    "veil_glow": "#8AD3D7",
    "veil_fringe": "#9E92C6",
    "ui_bg": "#0B1922",
    "ui_panel": "#102430",
    "ui_raised": "#183340",
    "ui_line": "#3C5D69",
    "ui_text": "#E8F1EF",
    "ui_muted": "#B5CAD0",
    "ui_focus": "#85DED5",
    "ui_warning": "#F0C583",
    "ui_error": "#FF9B8F",
    "ui_good": "#A9D9BD",
})


@dataclass(frozen=True)
class MaterialToken:
    base: str
    shadow: str
    edge: str
    wear_coverage: float

    def __post_init__(self):
        if any(key not in COLOR_HEX for key in (self.base, self.shadow, self.edge)):
            raise ValueError("Material refers to an unknown color")
        if not 0 <= self.wear_coverage <= 0.30:
            raise ValueError("Wear must be restrained and explicitly bounded")


MATERIALS = MappingProxyType({
    "hull_matte": MaterialToken("steel_hull", "steel_shadow", "steel_edge", 0.14),
    "deck_painted": MaterialToken("steel_deck", "steel_seam", "steel_roof", 0.1),
    "armor_segment": MaterialToken("steel_armor", "steel_shadow", "steel_edge", 0.18),
    "service_metal": MaterialToken("steel_roof", "steel_seam", "steel_edge", 0.08),
    "salt_worn_trim": MaterialToken("steel_rust", "steel_shadow", "steel_deck", 0.24),
})


@dataclass(frozen=True)
class LodTier:
    name: str
    min_pixels: int
    max_pixels: int | None
    features: tuple[str, ...]


LOD_TIERS = (
    LodTier("far", 0, 24, ("silhouette", "bow", "faction_signal")),
    LodTier("tactical", 24, 84, ("silhouette", "superstructure", "primary_turrets", "shadows")),
    LodTier("inspection", 84, None,
            ("silhouette", "modules", "seams", "hatches", "markings", "wear")),
)


def rgb(token):
    """Convert a palette token to an RGB tuple without pygame dependency."""
    hexcode = COLOR_HEX[token]
    return tuple(int(hexcode[i:i + 2], 16) for i in (1, 3, 5))


def lod_for_length(pixel_length):
    """Choose the target detail level by on-screen silhouette length."""
    if pixel_length < 0:
        raise ValueError("On-screen length cannot be negative")
    for tier in LOD_TIERS:
        if tier.max_pixels is None or pixel_length < tier.max_pixels:
            return tier.name
    raise AssertionError("Unreachable LOD length")


def _linear(channel):
    channel = channel / 255.0
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(token):
    r, g, b = rgb(token)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(foreground, background):
    """WCAG relative-luminance contrast for opaque token colors."""
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)
