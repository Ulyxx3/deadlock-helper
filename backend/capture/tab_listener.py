"""Event-driven OS keyboard listener that triggers OCR only when TAB is held."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from pynput import keyboard


class TabScoreboardListener:
    """Listens globally for Key.tab without interacting with the game process.

    Triggers `on_scoreboard_visible` after `settle_delay_ms` so the scoreboard UI
    has finished fading in, and enforces a cooldown so CPU stays near 0% during combat.
    """

    def __init__(
        self,
        on_scoreboard_visible: Callable[[], None],
        settle_delay_ms: int = 120,
        min_interval_s: float = 0.35,
        hold_poll_interval_s: float = 1.0,
    ) -> None:
        self.on_scoreboard_visible = on_scoreboard_visible
        self.settle_delay_s = max(0.0, settle_delay_ms / 1000.0)
        self.min_interval_s = min_interval_s
        self.hold_poll_interval_s = hold_poll_interval_s

        self._tab_held = False
        self._last_trigger_ts = 0.0
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._listener: keyboard.Listener | None = None
        self._poll_thread: threading.Thread | None = None

    def _safe_trigger(self) -> None:
        now = time.monotonic()
        with self._lock:
            if not self._tab_held:
                return
            if now - self._last_trigger_ts < self.min_interval_s:
                return
            self._last_trigger_ts = now
        self.on_scoreboard_visible()

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key != keyboard.Key.tab:
            return
        with self._lock:
            already_held = self._tab_held
            self._tab_held = True
        if already_held:
            return
        timer = threading.Timer(self.settle_delay_s, self._safe_trigger)
        timer.daemon = True
        timer.start()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key == keyboard.Key.tab:
            with self._lock:
                self._tab_held = False

    def _hold_loop(self) -> None:
        while not self._stop_event.wait(self.hold_poll_interval_s):
            if self._tab_held:
                self._safe_trigger()

    def start(self) -> None:
        """Start background keyboard listener and optional hold-poll loop."""
        self._stop_event.clear()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        if self.hold_poll_interval_s > 0:
            self._poll_thread = threading.Thread(target=self._hold_loop, daemon=True)
            self._poll_thread.start()

    def stop(self) -> None:
        """Stop listener cleanly."""
        self._stop_event.set()
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def run_forever(self) -> None:
        """Block until KeyboardInterrupt."""
        self.start()
        try:
            while not self._stop_event.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
