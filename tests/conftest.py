import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# Настройки игрока в тестах — во временном каталоге, а не в ~/.nine
os.environ.setdefault("NINE_HOME", tempfile.mkdtemp(prefix="nine-test-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pygame.quit() in screenshot tests invalidates cached Font objects. Reset UI fonts
# between tests so later headless UI tests cannot reuse stale SDL resources.
import pytest
import pygame


@pytest.fixture(autouse=True)
def _fresh_ui_fonts():
    from nine.gfx.ui import Fonts
    pygame.font.init()
    Fonts.reset()
    yield
    Fonts.reset()
