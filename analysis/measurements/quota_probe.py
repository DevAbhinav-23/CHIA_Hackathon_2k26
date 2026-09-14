"""One tiny express-mode call, to ask whether the quota answers at all (D-8)."""
import os
import time
from datetime import datetime, timezone

MODEL = "gemini-3.8-flash"
PROMPT = "Reply with the single word OK."


def main() -> int:
    """Send one `generate_content` and print OK or ERR, never the key."""
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key or key.startswith("${"):
        print("ERR NoKey GEMINI_API_KEY is unset, empty or unexpanded",
              datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return 2

    from google import genai
    from google.genai import types

    started = time.monotonic()
    client = genai.Client(vertexai=True, api_key=key)    # a temporary closes itself
    try:
        answer = client.models.generate_content(
            model=MODEL, contents=PROMPT,
            config=types.GenerateContentConfig(max_output_tokens=64))
    except Exception as error:              # noqa: BLE001 - the error IS the answer
        print("ERR", type(error).__name__, str(error).replace(key, "<key>")[:200],
              f"{time.monotonic() - started:.1f}",
              datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return 1
    print("OK", getattr(getattr(answer, "usage_metadata", None),
                        "total_token_count", None),
          f"{time.monotonic() - started:.1f}",
          datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
