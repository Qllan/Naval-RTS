import os
import sys
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
# Настройки игрока в тестах — во временном каталоге, а не в ~/.nine
os.environ.setdefault("NINE_HOME", tempfile.mkdtemp(prefix="nine-test-"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
