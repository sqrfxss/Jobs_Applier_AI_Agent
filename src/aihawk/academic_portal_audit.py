"""Read-only portal accessibility and DOM inventory; not end-to-end submission."""

import argparse
import json
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from aihawk.official_fetch import validate_network_host
from aihawk.academic_inspect import inspect_controls

PORTALS = [
    ("Maastricht / Studielink", "https://www.studielink.nl/", "studielink.nl"),
    ("Aalto / Studyinfo", "https://opintopolku.fi/konfo/en/", "opintopolku.fi"),
    ("Masaryk", "https://www.fi.muni.cz/admission/doctoral/application.html.en", "muni.cz"),
    ("DTU", "https://efzu.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_2001/job/8538", "efzu.fa.em2.oraclecloud.com"),
    ("UAM", "https://secretaria-virtual.uam.es/Navegacion/InicioAdmision.Posgrado.html", "uam.es"),
    ("Charles", "https://is.cuni.cz/studium/eng/prijimacky/index.php?do=obory", "cuni.cz"),
    ("Tartu / DreamApply", "https://estonia.dreamapply.com/", "estonia.dreamapply.com"),
    ("Comenius", "https://e-prihlaska.uniba.sk/ais/eprihlas/#!/vyhladavanie", "uniba.sk"),
    ("Deusto", "https://www.deusto.es/en/home/study/admissions/phd/online-or-in-person-admission-process/tramite", "deusto.es"),
    ("KU Leuven", "https://www.kuleuven.be/personeel/jobsite/jobs/60788924?lang=en", "kuleuven.be"),
]


def safe(url, host):
    try:
        p = urlsplit(url)
        h = p.hostname or ""
        return p.scheme == "https" and not p.username and not p.password and p.port in (None, 443) and (h == host or h.endswith("." + host))
    except ValueError:
        return False


def audit(item):
    name, url, host = item
    out = {"institution": name, "url": url, "read_only": True, "end_to_end_verified": False}
    try:
        validate_network_host(url, (host,))
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            b = p.chromium.launch(channel="chrome", headless=True)
            try:
                c = b.new_context(accept_downloads=False, service_workers="block")

                def route(r):
                    if r.request.method not in ("GET", "HEAD", "OPTIONS") or not safe(r.request.url, host):
                        return r.abort()
                    return r.continue_()

                c.route("**/*", route)
                page = c.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=12000)
                page.wait_for_timeout(1200)
                if not safe(page.url, host):
                    raise ValueError("off-domain redirect")
                inventory = inspect_controls(page, official_hosts=(host,))
                controls = inventory["controls"]
                counts = {k: sum(x["kind"] == k for x in controls) for k in ("text", "select", "upload")}
                flags = page.evaluate(
                    """() => ({password:!!document.querySelector('input[type=password]'),comboboxes:document.querySelectorAll('[role=combobox]').length,frames:document.querySelectorAll('iframe').length,bodyLength:document.body?.innerText.length||0})"""
                )
                out.update(
                    status="public_page_loaded",
                    http_status=response.status if response else None,
                    final_host=urlsplit(page.url).hostname,
                    page_title=page.title()[:120],
                    controls=counts,
                    flags=flags,
                )
                if out["http_status"] and out["http_status"] >= 400:
                    out["status"] = "http_error"
                elif flags["bodyLength"] < 100:
                    out["status"] = "insufficient_content"
            finally:
                b.close()
    except Exception as e:
        out.update(status="blocked_or_unavailable", error=str(e)[:300])
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(audit, PORTALS))
    out = {"schema": "aihawk.portal.public-audit.v1", "at": datetime.now(timezone.utc).isoformat(), "results": results, "e2e_passes": 0, "submitted": 0}
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf8")
    print(
        json.dumps(
            {
                "attempts": len(results),
                "loaded": sum(x["status"] == "public_page_loaded" for x in results),
                "results": [{"institution": x["institution"], "status": x["status"], "controls": x.get("controls"), "flags": x.get("flags")} for x in results],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
