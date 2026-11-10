"""Mouse control via CH9329 HID emulator."""

import atexit
import logging
import time

from .hid_protocol import CH9329, build_mouse_abs_packet, build_mouse_rel_packet

logger = logging.getLogger(__name__)

BUTTON_MAP = {
    "left": 0x01,
    "right": 0x02,
    "middle": 0x04,
}

BUTTON_MODES = ("absolute", "relative")


class Mouse:
    """Mouse controller using CH9329."""

    def __init__(self, ch9329: CH9329, screen_width: int = 1920, screen_height: int = 1080,
                 button_mode: str = "absolute"):
        self._dev = ch9329
        self._button_mode = self._check_mode(button_mode)
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._buttons: int = 0x00  # Currently pressed button bitmask
        atexit.register(self._release_all)

    def _release_all(self):
        try:
            if self._dev.is_open:
                self._dev.release_all()
        except Exception:
            pass

    def _screen_to_abs(self, x: int, y: int) -> tuple[int, int]:
        """Convert screen coordinates to CH9329 absolute coordinates (0-4095)."""
        abs_x = int(x * 4096 / self._screen_width)
        abs_y = int(y * 4096 / self._screen_height)
        return abs_x, abs_y

    @staticmethod
    def _check_mode(button_mode: str) -> str:
        if button_mode not in BUTTON_MODES:
            raise ValueError(f"Invalid button_mode: {button_mode!r}")
        return button_mode

    def _relative(self, button_mode: str | None) -> bool:
        return self._check_mode(button_mode or self._button_mode) == "relative"

    def _send_buttons(self, buttons: int, x: int | None, y: int | None, relative: bool):
        """Report *buttons*, moving to (x, y) first when both are given.

        Relative mode sends button-free absolute moves plus relative button
        reports, for targets that ignore buttons in absolute reports.
        """
        if x is not None and y is not None:
            abs_x, abs_y = self._screen_to_abs(x, y)
            self._dev.send(build_mouse_abs_packet(0 if relative else buttons, abs_x, abs_y))
            if not relative:
                return
        self._dev.send(build_mouse_rel_packet(buttons, 0, 0))

    def move_absolute(self, x: int, y: int, button_mode: str | None = None):
        """Move mouse to absolute screen position (preserves button state).

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
            button_mode: "absolute" or "relative"; None uses the default
        """
        buttons = 0 if self._relative(button_mode) else self._buttons
        abs_x, abs_y = self._screen_to_abs(x, y)
        packet = build_mouse_abs_packet(buttons, abs_x, abs_y)
        self._dev.send(packet)

    def move_relative(self, dx: int, dy: int):
        """Move mouse relative to current position (preserves button state).

        Args:
            dx: Horizontal movement (-127 to 127)
            dy: Vertical movement (-127 to 127)
        """
        packet = build_mouse_rel_packet(self._buttons, dx, dy)
        self._dev.send(packet)

    def click(self, button: str = "left", x: int | None = None, y: int | None = None,
              button_mode: str | None = None):
        """Click a mouse button, optionally at a position.

        Args:
            button: Button name (left, right, middle)
            x: Optional screen X coordinate (moves to position first)
            y: Optional screen Y coordinate (moves to position first)
            button_mode: "absolute" or "relative"; None uses the default
        """
        relative = self._relative(button_mode)
        btn_bit = BUTTON_MAP.get(button, 0x01)
        self._send_buttons(btn_bit, x, y, relative)
        time.sleep(0.01)
        self._send_buttons(0x00, x, y, relative)

    def mouse_down(self, button: str = "left", x: int | None = None, y: int | None = None,
                   button_mode: str | None = None):
        """Press and hold a mouse button.

        Args:
            button: Button name (left, right, middle)
            x: Optional screen X coordinate
            y: Optional screen Y coordinate
            button_mode: "absolute" or "relative"; None uses the default
        """
        relative = self._relative(button_mode)
        btn_bit = BUTTON_MAP.get(button, 0x01)
        self._buttons |= btn_bit
        self._send_buttons(self._buttons, x, y, relative)

    def mouse_up(self, button: str = "left", x: int | None = None, y: int | None = None,
                 button_mode: str | None = None):
        """Release a mouse button.

        Args:
            button: Button name (left, right, middle)
            x: Optional screen X coordinate
            y: Optional screen Y coordinate
            button_mode: "absolute" or "relative"; None uses the default
        """
        relative = self._relative(button_mode)
        btn_bit = BUTTON_MAP.get(button, 0x01)
        self._buttons &= ~btn_bit
        self._send_buttons(self._buttons, x, y, relative)

    def scroll(self, amount: int):
        """Scroll the mouse wheel.

        Args:
            amount: Scroll amount (positive=up, negative=down, -127 to 127)
        """
        amount = max(-127, min(127, amount))
        packet = build_mouse_rel_packet(self._buttons, 0, 0, scroll=amount)
        self._dev.send(packet)
