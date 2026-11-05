"""Run guards: loop detection. Pure and deterministic."""

import json
from collections import deque
from typing import Any

OK, WARN, ABORT = "ok", "warn", "abort"
LOOP_WARNING = ("Warning: you already did exactly this on this page. Try a different element or page, "
                "or call finish if you are stuck.")


class LoopDetector:
    """Flags the same tool + arguments repeated on the same page, within a recent window, without the
    agent getting anywhere in between.

    Moving to a different page is progress, so it clears the window: going back to a product page to try
    the next button is exploration, not a loop. The second repeat gets a warning in the observation; the
    third stops the run as 'agent_loop'. finish and take_screenshot never count.
    """

    IGNORED = {"finish", "take_screenshot"}

    def __init__(self, window: int = 8, warn_at: int = 2, abort_at: int = 3):
        self.window = window
        self.warn_at = warn_at
        self.abort_at = abort_at
        self._recent: deque[str] = deque(maxlen=window)
        self._page: str | None = None

    @staticmethod
    def _norm(url: str | None) -> str:
        return (url or "").split("#")[0]

    @staticmethod
    def signature(tool: str, args: dict[str, Any], url: str | None) -> str:
        return json.dumps([tool, args, LoopDetector._norm(url)], sort_keys=True, default=str)

    def check(self, tool: str, args: dict[str, Any], url: str | None) -> str:
        if tool in self.IGNORED:
            return OK
        if self._norm(url) != self._page:
            self._page = self._norm(url)
            self._recent.clear()
        sig = self.signature(tool, args, url)
        self._recent.append(sig)
        count = sum(1 for s in self._recent if s == sig)
        if count >= self.abort_at:
            return ABORT
        if count >= self.warn_at:
            return WARN
        return OK
