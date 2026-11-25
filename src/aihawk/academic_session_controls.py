"""Reviewed draft-only controls for an authenticated, case-isolated portal."""

import hashlib
import re
from aihawk.academic_browser import PortalPreparationError, verified_portal_host
from aihawk.academic_portal_limits import check_access
from aihawk.academic_action_budget import ActionBudget
from aihawk.academic_document_gate import is_authored_writing, require_writing_preflight
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_custom_controls import custom_select, modal_upload
from aihawk.academic_exeter_upload import upload as exeter_upload
from aihawk.academic_exeter_react_select import select as react_select
from aihawk.academic_field_journal import record as field_record, validation_labels, reconcile_summary
from aihawk.academic_submission_guard import require_open_application
from aihawk.academic_value_comparison import formatting_equivalent

SECTIONS = ("About You", "Address", "Qualifications", "Employment", "References", "Additional Information", "Declaration and Submission")
FORBIDDEN = re.compile(r"(?i)password|passcode|otp|captcha|submit|declarat|signatur|payment|consent|send invitation|send reference|confirm.*accuracy")


def _guard(page, hosts, title):
    verified_portal_host(page.url, hosts)
    check_access(hosts)
    project = page.get_by_text(title, exact=True)
    if project.count() != 1 or not project.is_visible():
        raise PortalPreparationError("Exact authenticated project identity not verified")


def _one(loc, *, visible=True):
    count = loc.count()
    if count != 1:
        raise PortalPreparationError("Reviewed control ambiguous or missing (matches=" + str(count) + ")")
    if visible and not loc.is_visible():
        raise PortalPreparationError("Reviewed control currently hidden")
    if not loc.is_enabled():
        raise PortalPreparationError("Reviewed control disabled by university; check preceding required fields")
    return loc


def inventory(page, hosts, title):
    _guard(page, hosts, title)
    return page.locator("input,select,textarea,button,[role=combobox]").evaluate_all(
        """xs=>xs.filter(x=>x.getClientRects().length && x.type!=='password' && x.type!=='hidden').map(x=>({tag:x.tagName,id:x.id,name:x.name||'',type:x.type||'',role:x.getAttribute('role'),label:[...(x.labels||[])].map(y=>y.innerText).join(' ')||x.getAttribute('aria-label')||'',text:(x.innerText||'').trim().slice(0,180),button_value:['submit','button'].includes(x.type)?x.value:null,required:x.required||x.getAttribute('aria-required')==='true',filled:['checkbox','radio'].includes(x.type)?x.checked:!!(x.value||'').trim(),selected:x.tagName==='SELECT'?x.selectedOptions[0]?.text:null,options:x.tagName==='SELECT'?[...x.options].map(o=>({label:o.text,value:o.value})):null})).slice(0,180)"""
    )


def _login_redirected(page):
    """Recognize an explicit university login URL without waiting for the DOM."""
    from urllib.parse import urlsplit

    path = urlsplit(page.url).path.casefold()
    return "/siw_ipp_lgn" in path or "/login" in path


def navigate(page, hosts, title, section, expected_heading=None, force=False):
    _guard(page, hosts, title)
    if section not in SECTIONS:
        raise PortalPreparationError("Unreviewed section")
    # Navigation only; never final submission.
    # Exeter section controls trigger a server request; do not hold the
    # browser in Playwright's implicit navigation wait on an unstable server.
    # Completed tabs may contain check glyphs. Scope to one visible button.
    # A modal must be handled first; never click through it.
    dialogs = page.get_by_role("dialog")
    if any(dialogs.nth(i).is_visible() for i in range(dialogs.count())):
        raise PortalPreparationError("Open upload dialog must be resolved before section navigation")
    # Avoid a network round-trip if already on the correct authenticated stage.
    if expected_heading and not force:
        current_heading = page.get_by_role("heading", name=expected_heading, exact=True)
        if current_heading.count() == 1 and current_heading.is_visible():
            return
    # Exeter uses different accessible names when a section is completed.
    # Read exact VISIBLE button text instead of relying on the name decoration.
    items = page.get_by_role("button")
    matches = []
    for i in range(items.count()):
        item = items.nth(i)
        if item.is_visible() and item.is_enabled() and re.sub(r"[\u2713\u2714]\s*$", "", item.inner_text()).strip() == section:
            matches.append(item)
    if len(matches) != 1:
        raise PortalPreparationError("Section navigation control not uniquely identified: " + section)
    nav = matches[0]
    if force:
        # University portals may replace a form via XHR without a full document
        # navigation. Treat only a NEW same-host document/XHR/fetch response
        # plus fresh matching stage DOM as a server readback, not an old heading.
        from urllib.parse import urlsplit
        from time import monotonic

        arrivals = []
        allowed_hosts = set(hosts)

        def seen(response):
            try:
                request = response.request
                parts = urlsplit(response.url)
                if (
                    parts.scheme == "https"
                    and parts.hostname in allowed_hosts
                    and (request.resource_type in ("document", "xhr", "fetch"))
                    and 200 <= response.status < 400
                ):
                    arrivals.append(response.url)
            except Exception:
                return

        page.on("response", seen)
        try:
            _one(nav).click(timeout=7000, no_wait_after=True)
            deadline = monotonic() + 12
            while monotonic() < deadline:
                page.wait_for_timeout(200)
                if _login_redirected(page):
                    raise PortalPreparationError("University login required after section navigation")
                if not arrivals:
                    continue
                try:
                    _guard(page, hosts, title)
                    if expected_heading:
                        heading = page.get_by_role("heading", name=expected_heading, exact=True)
                        if heading.count() != 1 or not heading.is_visible():
                            continue
                    return
                except PortalPreparationError:
                    continue
            if not arrivals:
                raise PortalPreparationError("Independent server readback: no fresh university response")
            raise PortalPreparationError("Independent server readback: response received but target stage absent")
        finally:
            page.remove_listener("response", seen)
    _one(nav).click(timeout=7000, no_wait_after=True)
    try:
        from time import monotonic

        end = monotonic() + 14
        last_error = None
        while monotonic() < end:
            page.wait_for_timeout(250)
            if _login_redirected(page):
                raise PortalPreparationError("University login required after section navigation")
            try:
                _guard(page, hosts, title)
                if expected_heading:
                    h = page.get_by_role("heading", name=expected_heading, exact=True)
                    if h.count() != 1 or not h.is_visible():
                        continue
                break
            except PortalPreparationError as exc:
                last_error = exc
        else:
            raise PortalPreparationError("Authenticated project did not reappear after section navigation") from last_error
    except Exception as error:
        # Do not replay POST navigation. Report a known login redirect
        # rather than hiding it behind a generic timeout.
        if _login_redirected(page):
            raise PortalPreparationError("University login required after section navigation") from error
        raise PortalPreparationError("Section navigation failed; browser preserved for review") from error


def _control(page, selector, expected_type):
    if not isinstance(selector, str) or not re.fullmatch(r'#[a-zA-Z0-9_-]+|\[id="[^"\r\n]{1,180}"\]|\[name="[^"\r\n]{1,180}"\]', selector):
        raise PortalPreparationError("Only reviewed exact ID/name selectors permitted")
    x = _one(page.locator(selector), visible=expected_type != "select")
    meta = x.evaluate(
        """x=>({type:x.type||'',tag:x.tagName,label:[...(x.labels||[])].map(y=>y.innerText).join(' ')+' '+(x.getAttribute('aria-label')||'')+' '+x.name+' '+x.id})"""
    )
    if FORBIDDEN.search(meta["label"]) or meta["type"] in ("password", "hidden", "submit", "button"):
        raise PortalPreparationError("Protected or final-action control")
    if expected_type == "fill" and (
        meta["tag"] not in ("INPUT", "TEXTAREA") or meta["type"] not in ("text", "email", "tel", "number", "date", "search", "textarea", "url")
    ):
        raise PortalPreparationError("Unexpected text control")
    if expected_type == "select" and meta["tag"] != "SELECT":
        raise PortalPreparationError("Expected native select")
    if expected_type == "radio" and meta["type"] != "radio":
        raise PortalPreparationError("Expected reviewed radio button")
    if expected_type == "upload" and meta["type"] != "file":
        raise PortalPreparationError("Expected file upload control")
    return x


def apply_plan(page, folder, hosts, title, plan):
    require_open_application(folder)
    _guard(page, hosts, title)
    if plan.get("schema") != "aihawk.session.draft.v1" or plan.get("project_title") != title:
        raise PortalPreparationError("Reviewed project plan required")
    if plan.get("section") not in SECTIONS[:-1]:
        raise PortalPreparationError("Final declaration excluded")
    heading = plan.get("visible_heading", "")
    if not heading or FORBIDDEN.search(heading):
        raise PortalPreparationError("Section heading not reviewed")
    marker = page.get_by_role("heading", name=heading, exact=True)
    if marker.count() != 1 or not marker.is_visible():
        marker = page.get_by_text(heading, exact=True)
    if marker.count() != 1 or not marker.is_visible():
        raise PortalPreparationError("Section identity not verified")
    # Fail fast before typing any of this stage's fields. In earlier runs,
    # the postcode was changed first, then a later address-line conflict
    # blocked the stage and left an unsaved partially edited form.
    # Invisible fields (e.g. an unexpanded MSc repeater) are intentionally
    # excluded until the institution reveals them.
    for item in plan.get("actions", []):
        if item.get("type") != "fill":
            continue
        selector = item.get("selector")
        if not isinstance(selector, str):
            continue
        loc = page.locator(selector)
        if loc.count() != 1 or not loc.is_visible() or not loc.is_enabled():
            continue
        _control(page, selector, "fill")
        expected = str(item["value"])
        existing = loc.input_value()
        if existing not in ("", expected) and existing != item.get("reviewed_previous") and not formatting_equivalent(selector, expected, existing):
            raise PortalPreparationError("Preflight existing value conflict: " + selector)
    results = []
    for index, item in enumerate(plan.get("actions", [])):
        typ = item.get("type")
        target = item.get("selector") or item.get("target_selector") or (typ + ":" + str(item.get("role", "control")) + ":" + str(item.get("index", "")))
        target = str(target)
        field_record(folder, stage=plan["section"], field=target, action=typ, status="started", attempt=index + 1, defer_summary=True)
        before = len(results)
        try:
            _guard(page, hosts, title)
            typ = item.get("type")
            if typ == "repeater_add":
                # The academic qualifications editor hides degree 2 until its
                # institution-provided Add button is pressed. Never write to
                # invisible second-degree form controls.
                if item.get("source_evidence") != "Official MSc diploma and transcript":
                    raise PortalPreparationError("Second degree insertion not source reviewed")
                button_selector = item.get("button_selector")
                target_selector = item.get("target_selector")
                if button_selector != "#q1_add" or target_selector != "#IPQ_QUAL_TYPE2":
                    raise PortalPreparationError("Unreviewed Exeter academic repeater")
                target = page.locator(target_selector)
                if target.count() != 1:
                    raise PortalPreparationError("Second degree target missing")
                if not target.is_visible():
                    trigger = _one(page.locator(button_selector))
                    if trigger.input_value().strip() != "Add another qualification":
                        raise PortalPreparationError("Exeter Add qualification button changed")
                    trigger.click(timeout=6000, no_wait_after=True)
                    target.wait_for(state="visible", timeout=9000)
                if not target.is_visible():
                    raise PortalPreparationError("Second degree panel not visible after Add")
                results.append({"type": typ, "second_degree_panel_visible": True, "local_readback": True})
                continue
            if typ == "react_select":
                results.append({"type": typ, **react_select(page, item)})
                continue
            if typ == "exeter_upload":
                result = exeter_upload(page, folder, hosts, item)
                results.append({"type": typ, **result})
                continue
            if typ in ("custom_select", "modal_upload"):
                if typ == "custom_select":
                    custom_select(page, item)
                else:
                    modal_upload(page, folder, hosts, item)
                results.append({"type": typ, "local_readback": True})
                continue
            if typ not in ("fill", "select", "upload", "radio"):
                raise PortalPreparationError("Unapproved action type")
            x = _control(page, item["selector"], typ)
            if typ == "fill":
                value = str(item["value"])
                old = x.input_value()
                if old not in ("", value) and old != item.get("reviewed_previous") and not formatting_equivalent(item["selector"], value, old):
                    raise PortalPreparationError("Existing value conflict: " + item["selector"])
                if old != value and not formatting_equivalent(item["selector"], value, old):
                    x.fill(value, timeout=5000)
                    # A number of university date widgets discard a programmatic
                    # fill after blur while accepting genuine keyboard events.
                    # Retry at most once, only for an exact reviewed date field.
                    x.blur()
                    if x.input_value() != value and (
                        re.fullmatch(r"\d{2}/[A-Za-z]{3}/\d{4}", value)
                        and re.search(r"(?:DATE|BEGD|ENDD|AWARD)", item["selector"], re.I)
                        and x.input_value() == ""
                    ):
                        x.click(timeout=4000)
                        x.press("ControlOrMeta+A")
                        x.press_sequentially(value, delay=25, timeout=6000)
                        x.press("Tab")
                if (
                    x.input_value() != value
                    and re.fullmatch(r"\d{2}/[A-Za-z]{3}/\d{4}", value)
                    and re.search(r"(?:DATE|BEGD|ENDD|AWARD)", item["selector"], re.I)
                ):
                    # Use only an installed jQuery UI datepicker instance.
                    # The original form remains responsible for validation.
                    from datetime import datetime

                    try:
                        parsed = datetime.strptime(value, "%d/%b/%Y")
                    except ValueError:
                        parsed = None
                    if parsed is not None:
                        x.evaluate(
                            """(el,date)=>{
                          const jq=window.jQuery;
                          if(!jq||!jq.fn||typeof jq.fn.datepicker!=='function')
                            return false;
                          const wrapped=jq(el);
                          const installed=!!wrapped.data('datepicker')||
                             el.classList.contains('hasDatepicker');
                          if(!installed)return false;
                          try{
                            wrapped.datepicker('setDate',new Date(
                               date.year,date.month-1,date.day));
                            wrapped.trigger('change');
                            el.dispatchEvent(new Event('input',{bubbles:true}));
                            el.blur();
                            return true;
                          }catch(e){return false;}
                        }""",
                            {"year": parsed.year, "month": parsed.month, "day": parsed.day},
                        )
                if x.input_value() != value and not formatting_equivalent(item["selector"], value, x.input_value()):
                    raise PortalPreparationError("Text readback failed at " + item["selector"] + "; portal normalized, cleared or rejected the reviewed value")
            elif typ == "select":
                options = x.locator("option").evaluate_all("xs=>xs.map(x=>({value:x.value,label:x.text}))")
                match = [o for o in options if o["label"] == item["label"]]
                values = {o["value"] for o in match}
                if len(values) != 1:
                    raise PortalPreparationError("Select label not uniquely mapped to one value")
                expected = next(iter(values))
                if x.input_value() != expected:
                    x.select_option(value=expected, force=True, timeout=6000)
                if x.input_value() != expected:
                    raise PortalPreparationError("Select readback failed")
            elif typ == "radio":
                if item.get("checked") is not True or not item.get("source_evidence"):
                    raise PortalPreparationError("Radio response requires reviewed evidence")
                x.check(timeout=6000)
                if not x.is_checked():
                    raise PortalPreparationError("Radio readback failed")
            else:
                root = folder.resolve(strict=True)
                f = (root / item["file"]).resolve(strict=True)
                if not f.is_relative_to(root) or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != item["sha256"]:
                    raise PortalPreparationError("File evidence changed or unavailable")
                if is_authored_writing(f):
                    require_writing_preflight(f)
                ActionBudget().reserve_url(page.url, "upload", hosts)
                x.set_input_files(str(f))
                names = x.evaluate("x=>[...x.files].map(f=>f.name)")
                if names != [f.name]:
                    raise PortalPreparationError("Local file selection readback failed")
            results.append({"type": typ, "selector": item["selector"], "local_readback": True})
        except Exception as exc:
            field_record(
                folder, stage=plan["section"], field=target, action=typ, status="blocked", error_type=type(exc).__name__, attempt=index + 1, defer_summary=True
            )
            reconcile_summary(folder)
            raise
        finally:
            if len(results) > before:
                field_record(
                    folder,
                    stage=plan["section"],
                    field=target,
                    action=typ,
                    status=("receipt_unverified" if typ in ("exeter_upload", "modal_upload", "upload") else "local_verified"),
                    attempt=index + 1,
                    defer_summary=True,
                )
    reconcile_summary(folder)
    atomic_json(
        folder / "Session_Draft_Result.json", {"section": plan["section"], "controls": results, "server_saved_verified": False, "final_submission": False}
    )
    return results


def save_draft(page, hosts, title, expected_next_heading=None, folder=None):
    if folder is not None:
        require_open_application(folder)
    _guard(page, hosts, title)
    button = _one(page.get_by_role("button", name="Save and continue", exact=True))
    if page.get_by_role("button", name="Submit your application", exact=True).count():
        raise PortalPreparationError("Final page excluded")
    if folder is not None:
        field_record(folder, stage=expected_next_heading or "_current", field="_save", action="save", status="save_attempt")
    ActionBudget().reserve_url(page.url, "draft_save", hosts)
    button.click(timeout=6000, no_wait_after=True)
    if expected_next_heading:
        # Wait specifically for the saved destination, not an outgoing DOM-ready event.
        page.get_by_role("heading", name=expected_next_heading, exact=True).wait_for(state="visible", timeout=14000)
        _guard(page, hosts, title)
        if folder is not None:
            field_record(
                folder, stage=expected_next_heading, field="_save", action="save", status="save_unverified", details="next_stage_visible_not_persistence"
            )
        return {"save_clicked": True, "next_heading_verified": True, "server_saved_verified": False, "final_submission": False}
    # Exeter updates its form and URL asynchronously. The first DOM-ready
    # event can refer to the outgoing page; do not mark a correct save as
    # failed or start the next stage while the document is changing.
    from time import monotonic

    deadline = monotonic() + 14
    last_error = None
    while monotonic() < deadline:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=1500)
            page.wait_for_timeout(200)
            _guard(page, hosts, title)
            if page.locator("h1,h2").count() > 0:
                break
        except Exception as exc:
            last_error = exc
            page.wait_for_timeout(200)
    else:
        raise PortalPreparationError("Draft save navigation did not settle") from last_error
    labels = validation_labels(page)
    if labels:
        if folder is not None:
            field_record(folder, stage="_current", field="_save", action="save", status="validation_rejected", validation_fields=labels)
        raise PortalPreparationError("University rejected draft: fields " + ", ".join(labels[:8]))
    errors = page.locator('[aria-invalid="true"]:visible')
    if errors.count():
        if folder is not None:
            field_record(folder, stage="_current", field="_save", action="save", status="validation_rejected", details="aria_invalid_visible")
        raise PortalPreparationError("Form validation errors after Save")
    if folder is not None:
        field_record(folder, stage="_current", field="_save", action="save", status="save_unverified", details="no_independent_fresh_readback")
    # A successful Save may move to the next (still incomplete) section, whose
    # validation message must not invalidate the preceding section's save.
    # The batch runner verifies the next heading and reopens the saved stage.
    # A navigation/DOM readback is not evidence of server persistence.
    return {"save_clicked": True, "server_saved_verified": False, "final_submission": False}
