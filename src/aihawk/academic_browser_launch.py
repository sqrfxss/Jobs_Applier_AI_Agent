"""Launch a local trusted Chromium browser for human-operated academic tasks.

Use Playwright's bundled Chromium where available. If only that executable
is absent, use an installed stable Chrome or Edge browser. Never accept an
untrusted manifest-supplied executable path or remote debugging endpoint.
"""

from __future__ import annotations


def launch_operator_browser(playwright, *, headless: bool = False):
    """Open a locally installed Chromium-family browser with safe fallback."""
    errors = []
    for channel in (None, "chrome", "msedge"):
        options = {"headless": headless}
        if channel is not None:
            options["channel"] = channel
        try:
            return playwright.chromium.launch(**options)
        except Exception as error:
            detail = str(error)
            # Only fall back after Playwright explicitly reports that the
            # selected browser installation is unavailable. Other errors
            # (security, launch crash, policy, permissions) remain fatal.
            missing = "Executable doesn't exist" in detail or "executable doesn't exist" in detail
            if not missing:
                raise
            errors.append(channel or "playwright-chromium")
    raise RuntimeError(
        "No supported local Chromium/Chrome/Edge browser was found. "
        "Install a browser using 'python -m playwright install chromium'. "
        f"Attempted channels: {', '.join(errors)}."
    )
