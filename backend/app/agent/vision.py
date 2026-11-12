"""look_at_page: the shopper's eyes. One viewport screenshot of the store page goes to a vision model with a
question; the answer comes back as page content (untrusted: text drawn into an image can carry instructions).

Only the store's main page is ever captured. A PayPal window is a separate page and is never passed here, and a
main page that is not on the store's own host is refused, so no sign-in form can reach the vision model.
The answer never feeds the readiness score.
"""

from urllib.parse import urlparse

from .browser import PageTools, ToolError
from .llm import ChatModel

MAX_QUESTION_CHARS = 500
MAX_ANSWER_CHARS = 1500
VISION_TIMEOUT_S = 90.0


def check_store_page(tools: PageTools) -> None:
    """Refuse unless the current page is a plain web page on the store's own host."""
    parts = urlparse(tools.page.url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or parts.netloc != tools._origin:
        raise ToolError("look_at_page only works on the store's own pages.")
    if host == "paypal.com" or host.endswith(".paypal.com") or host.endswith(".paypalobjects.com"):
        raise ToolError("look_at_page never looks at PayPal pages.")


async def look_at_page(tools: PageTools, vision: ChatModel, question: str) -> str:
    question = " ".join(str(question or "").split())[:MAX_QUESTION_CHARS]
    if not question:
        raise ToolError("look_at_page needs a question, like 'What price is shown?'")
    check_store_page(tools)
    path = await tools.screenshot(f"vision-{tools._shot_n + 1:02d}")  # the viewport, not the full page
    tools._shot_n += 1
    with open(path, "rb") as fh:
        png = fh.read()
    try:
        answer = await vision.describe_image(png, question)
    except RuntimeError as exc:  # provider errors name the provider, never the key
        raise ToolError(f"The vision model failed: {str(exc).splitlines()[0][:200]}") from exc
    return answer[:MAX_ANSWER_CHARS]
