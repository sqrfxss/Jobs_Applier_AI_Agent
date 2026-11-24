"""Human-readable preview and explicit manual handoff for academic portals.

This module does not fill or submit university websites. The preview contains
no executable JavaScript or live form and cannot transmit personal data.
"""

from __future__ import annotations

import html
import sys
import webbrowser
from pathlib import Path

from aihawk.academic_approval import ApplicationPreview
from aihawk.academic_sources import _host


def render_preview(
    preview: ApplicationPreview,
    *,
    title: str,
    official_hosts: tuple[str, ...],
    sources: tuple[str, ...] = (),
    binding_summary: tuple[tuple[str, str, str], ...] = (),
    binding_fingerprint: str | None = None,
) -> str:
    """Render an escaped, standalone, non-submitting HTML review document."""
    host = _host(preview.opportunity_url)
    allowed = tuple(x.lower().rstrip(".") for x in official_hosts)
    if not allowed or not any(host == h or host.endswith("." + h) for h in allowed):
        raise ValueError("Application link is not on an allowed institutional domain.")
    if any(key.startswith("__") for key, _ in preview.fields):
        raise ValueError("Reserved review field names are not permitted.")
    t = html.escape(title, quote=True)
    link = html.escape(preview.opportunity_url, quote=True)
    rows = "\n".join(f"<tr><th scope='row'>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in preview.fields)
    cites = "\n".join(f"<li>{html.escape(src)}</li>" for src in sources) or "<li>No reviewed requirements supplied</li>"
    attachments = "\n".join(f"<li>{html.escape(item)}</li>" for item in preview.attachment_hashes) or "<li>None</li>"
    mapping_rows = "".join(
        "<tr><td>" + html.escape(field) + "</td><td>" + html.escape(selector) + "</td><td>" + html.escape(kind) + "</td></tr>"
        for field, selector, kind in binding_summary
    )
    mapping_html = (
        (
            "<h2>Exact browser field mapping (review before preparation)</h2><table><thead>"
            "<tr><th>Reviewed field</th><th>CSS selector</th><th>Action</th></tr></thead>"
            f"<tbody>{mapping_rows}</tbody></table>"
            f"<p>Preparation fingerprint: <code>{html.escape(binding_fingerprint or '')}</code></p>"
        )
        if binding_summary
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Application review: {t}</title>
<style>
body{{font:16px/1.55 system-ui,sans-serif;max-width:850px;margin:2rem auto;padding:0 1rem;color:#172331}}
h1{{font-size:1.65rem}}.notice{{border-left:4px solid #754d00;padding:1rem;background:#faf4e8}}
table{{border-collapse:collapse;width:100%;overflow-wrap:anywhere}}
th,td{{border:1px solid #bcc4cd;padding:.65rem;text-align:left;vertical-align:top}}
th{{width:33%}}code{{overflow-wrap:anywhere}}a{{color:#144e8e}}
</style></head><body>
<h1>University application review: {t}</h1>
<p class="notice"><strong>Review only — nothing has been submitted.</strong>
Check all statements, personal details, attachments, costs and the current official deadline
before opening the university portal. This file cannot submit an application.</p>
<p><strong>Official portal:</strong>
<a href="{link}" rel="noopener noreferrer" target="_blank">{link}</a></p>
<p><strong>SHA-256 application fingerprint:</strong> <code>{preview.fingerprint()}</code></p>
<h2>Form values</h2><table><tbody>{rows}</tbody></table>
{mapping_html}
<h2>Attachment hashes</h2><ul>{attachments}</ul>
<h2>Source records (review independently)</h2><ul>{cites}</ul>
<p>Any change in the form values or attachment digests requires a new review.</p>
<p>Proceed to the university website manually. No automatic submission is authorized.</p>
</body></html>"""


def save_preview(path: Path, contents: str) -> Path:
    """Write a private preview; caller controls path and file permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def open_manual_portal(
    preview: ApplicationPreview,
    *,
    official_hosts: tuple[str, ...],
    prompt=input,
    is_interactive: bool | None = None,
    browser_open=webbrowser.open_new_tab,
) -> bool:
    """Open the institution's site ONLY after typing an explicit challenge.

    This is a handoff, not browser automation. The user must fill and submit
    the real application in the university portal.
    """
    host = _host(preview.opportunity_url)
    if not official_hosts or not any(host == h.lower().rstrip(".") or host.endswith("." + h.lower().rstrip(".")) for h in official_hosts):
        raise ValueError("Application host is not on the official allowlist.")
    if is_interactive is None:
        is_interactive = sys.stdin.isatty()
    if not is_interactive:
        raise PermissionError("Opening an academic portal requires an interactive human terminal.")
    challenge = "OPEN " + preview.fingerprint()[-12:]
    answer = prompt(f"Type '{challenge}' to open {host} for MANUAL application: ")
    if answer != challenge:
        return False
    return bool(browser_open(preview.opportunity_url))
