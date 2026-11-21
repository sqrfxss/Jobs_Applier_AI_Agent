# Academic application workflow — standalone user guide

This is a standalone, local
research and application-preparation flow. It does not submit university
applications or sign in automatically to a university portal. The upstream AIHawk
job-application browser is a separate system with its own security risks.

## 1. Prepare a private manifest

Create a file named `application.json` in a protected local directory
(not in the public GitHub repository). Replace every example value:

```json
{
  "title": "My reviewed MSc application",
  "official_application_url": "https://admissions.example.edu/apply",
  "official_hosts": ["example.edu"],
  "applicant_id": "local-reference",
  "fields": {
    "programme": "Example MSc",
    "full_name": "Replace with your official name",
    "email": "replace@example.com"
  },
  "attachments": ["cv.pdf"],
  "source_urls": ["https://example.edu/admissions"],
  "portal_bindings": [
    {"field": "full_name", "selector": "input[name='fullName']", "kind": "text"},
    {"field": "email", "selector": "input[name='email']", "kind": "text"},
    {"field": "cv.pdf", "selector": "input[type='file']", "kind": "upload"}
  ]
}
```

All `example.edu` values are **illustrative**; they are not actual verified
admission or application links. Only use an institution's independently
confirmed domains and the actual URL of its application portal.

Attachments must exist in the manifest's directory or use valid local paths.
Their contents are hashed; the preview does not embed file bytes. Keep the
manifest, the preview HTML and actual CV in a private user directory.

## 2. Capture evidence from an official public source

Use an exact phrase that appears on a current official page. This example
captures the Maastricht homepage identity, **not** an admission rule:

```powershell
py -m aihawk.academic_ops capture --url "https://www.maastrichtuniversity.nl/" --host "maastrichtuniversity.nl" --phrase "Maastricht" --requirement institution_homepage --out .\maastricht-homepage.json
```

A capture contains the URL, retrieval timestamp, SHA-256 document digest and
surrounding excerpt. A successful exact-text match cannot prove that the
requirement was correctly interpreted, is current for a specific intake,
or applies to a specific degree. Institution-owned domains must be independently
established before adding them to a host allowlist.

The fetcher rejects disallowed redirect destinations, oversized responses,
non-public IPs returned during DNS prechecks and unsupported MIME types. The
network still needs egress protections against DNS rebinding, and some portals
do not render essential content in public HTML.

## 3. Generate the review

```powershell
py -m aihawk.academic_ops preview .\application.json .\application-review.html
```

Open the HTML file locally. Verify identity, programme, claimed eligibility,
language requirements, document authenticity, translations, legalization,
tuition/deposit requirements and the current deadline. This file is static:
no scripts or live form and no submit button.

## 4. Human-controlled manual handoff

```powershell
py -m aihawk.academic_ops handoff .\application.json
```

This operation requires an actual interactive terminal and an exact typed
fingerprint challenge. It opens the allowlisted institutional URL in a browser.
The operator must complete and submit the university application manually.
No automatic browser-fill or submission permission is granted.

## 5. Optional controlled form preparation (manual submit)

The original academic flow remains fully usable without a browser library.
To **prepare typed fields** in a visible local browser, install the optional
Playwright dependency and Chromium browser:

```powershell
py -m pip install -e ".[academic-browser]"
py -m playwright install chromium
```

**File uploads without native picker dialogs:** when a reviewed mapping uses
`kind: "upload"`, Playwright calls `locator.set_input_files(path)` directly.
This works even for hidden HTML file inputs, without invoking Windows
`Open` dialogs. The code checks exact attachment hashes and confirms the
selected filename. It does not click a university's separate `Upload`
button or claim that the server has received the file: that remains a
site-specific action and needs separate verification.

**Important browser-session boundary:** A normal Chrome window that was
already logged into a university is not automatically controllable by
Playwright. If that window was not launched with an authorized debugging
connection, the tool cannot reuse its session and must use a separate
Playwright-managed browser context. Do not silently fall back to automated
native file-dialog clicking, repeatedly open pickers, copy Chrome credentials
or export authentication cookies to bridge sessions.

On a Windows computer with Google Chrome or Microsoft Edge already installed,
`aihawk-academic autofill`, `autofill-stages`, and `inspect` can now
fall back automatically to that local browser when Playwright's bundled
Chromium is missing. A separate browser download is not mandatory in that
case. This fallback uses a new Playwright-controlled browser context, not
your normal signed-in Chrome profile. Browser login is still manual.

Use:

```powershell
aihawk-academic preview .\\application.json .\\application-review.html
aihawk-academic autofill .\\application.json
```

Before preparing a real form, create a **read-only field inventory**:

```powershell
aihawk-academic inspect .\\application.json .\\private-field-inventory.json
```

The visible browser lets you sign in manually. This command inspects
labels, required indicators, control types and select options only. It
does not read existing values, passwords, cookies or hidden inputs.
Inspect results contain untrusted page text and are never automatically
approved as selectors. Review the suggestions and manually map the intended
fields before using `autofill`.

The `portal_bindings` above are **synthetic examples**, not selectors verified
on a real university website. Inspect the institution's actual form and fill
the mapping only with validated input/select/upload selectors. Every field
must reference an existing reviewed value or a locally approved attachment.
Attachment bytes are hashed again before and after form preparation. A
changed or missing attachment cancels the operation and requires a new review.
Text and select inputs and files may be prepared; submit buttons and consent
checkboxes are deliberately excluded.

The operator reviews the preview and types a fingerprint challenge, manually
logs in (if needed), and stays at the university form. During the automated
field-preparation phase, all Playwright-routed HTTP requests are aborted to
reduce the risk of background transmission; the browser may behave differently
on forms that expect network validation. The operator types a second challenge
to regain manual browser control and must click final Submit directly.
No AI agent chooses or clicks submission controls.

**Browser limitation:** a website can cause side effects through previously
opened WebSocket connections or other browser behaviour that request routing
does not intercept. This implementation is not an isolation sandbox for
malicious pages and is not a guarantee that every real university site can be
automated. Only operate on verified, trusted university application pages.

## 6. Multi-page university portals — manual stage transitions

Use a separate `portal_stages` array when the portal has more than one
screen. Do not also set `portal_bindings`. Example manifest fields below
are **synthetic**; the host, exact URL paths and selectors must be inspected
and verified on the intended university site before use:

```json
{
  "title": "Example MSc multi-page application",
  "official_application_url": "https://admissions.example.edu/apply",
  "official_hosts": ["example.edu"],
  "applicant_id": "local-private-reference",
  "fields": {
    "legal_name": "Replace with reviewed name",
    "programme": "Example MSc"
  },
  "attachments": [],
  "portal_stages": [
    {
      "name": "Identity",
      "expected_host": "admissions.example.edu",
      "expected_path": "/apply",
      "bindings": [
        {"field": "legal_name", "selector": "#legal-name", "kind": "text"}
      ]
    },
    {
      "name": "Programme",
      "expected_host": "admissions.example.edu",
      "expected_path": "/apply/programme",
      "bindings": [
        {"field": "programme", "selector": "#programme", "kind": "select"}
      ]
    }
  ]
}
```

```powershell
aihawk-academic preview .\\application.json .\\application-review.html
aihawk-academic autofill-stages .\\application.json
```

The static preview lists the field mappings and expected routes of **all**
stages and carries one fingerprint for the entire plan. The terminal requires
a distinct typed approval for each stage. At each page, the program checks
the current HTTPS host and exact path before filling, without clicking
`Next`, `Save` or `Submit`. **You** must navigate between stages
manually. Changing any mapping or stage route invalidates the review digest.
Query parameters are ignored for the stage-path comparison, but no URL
parameters are ever copied into the report.

This workflow is for operator-controlled preparation only; validation
requirements, CAPTCHA, institutional consent and actual submission remain
under the operator's control. It is not verified on live authenticated
university portals.

## 7. Standalone status and duplicate-prevention registry

Record an application in the private local SQLite registry after preparation,
and inspect its state without contacting any university:

```powershell
aihawk-academic track-prepared .\\application.json
aihawk-academic track-status .\\application.json
```

**Only after you personally submit the form**, use:

```powershell
aihawk-academic track-submitted .\\application.json --proof .\\receipt.pdf
```

The final command asks you to type a submission-specific challenge in an
interactive terminal. Without that challenge it makes no status change.
Evidence files must be inside the manifest's private directory. The tool
records only the SHA-256 of a proof file, not the receipt's contents.
An application recorded as submitted cannot be silently prepared or reported
again. A reported submission is **not** official university acceptance or
confirmed receipt; verify the confirmation page or correspondence yourself.

The registry database `academic-private.sqlite` is stored beside the
manifest. Never place this directory in public version control. For
additional control use `--db` with a private absolute filename.

## 8. Eligibility assessment

`python -m aihawk.academic_cli evaluate input.json result.json` evaluates
explicitly supplied programme facts without performing network access.
An apparent match is **preliminary**; even with valid source URL and timestamp
metadata, confirmation requires a current official page and a human review.
Missing requirements generate `needs_review`, not an invented yes.

`aihawk.academic_programs` separately models TOEFL Home Edition vs. test
centre exams, scores, legalization and certified-translation timing, fees,
deposits, tuition and spouse-related visa checks. Fees that are not provided
are unknown, never automatically zero. Immigration decisions are not inferred
from academic admission rules.

## 9. Development and verification

The academic extension includes isolated pytest tests for:
- Conservative eligibility and test-format matching
- Official-source metadata, URL allowlists and safe public fetching
- Human review, edit invalidation, one-use approval, redacted audit
- Static HTML preview and interactive manual opening
- JSON CLI and application attachment hashing
- Fee, tuition, deposit, documentation timing and family-visa flags
- Explicit field mapping, no-submit browser preparation, and a separate synthetic Chromium integration test

Run in the configured `develop` checkout with Python 3.11 or 3.12 and
the project's developer dependencies. GitHub Actions has a standalone test
workflow across Linux/Windows and Python 3.11/3.12. The upstream AIHawk
tests remain a separate, heavier suite.

## Not production complete

The existing browser executor still permits uncontrolled actions by a
model. This academic extension **does not wire its approval token to that
executor** and must not be described as a safe automated submission system.
Actual authenticated admissions portals differ in legal agreements, identity
proof, third-party sign-on, file uploads, required consents and response
confirmation. Each demands a tested, site-specific browser adapter with
enforced human control before any automated submission can be enabled.
No automatic applications have been sent by this extension.


## Dedicated persistent login and server-verified uploads (experimental)

This new workflow avoids repeatedly attaching to a personal Chrome session.
It keeps authentication in a **separate profile inside the private application
folder**. It never reads or copies cookies from the user's personal Chrome,
uses no remote debugging access to personal tabs and never opens native file
picker dialogs. The session is reused on subsequent runs until it expires.

The dedicated browser can be used for inspection and preparation with the same
private profile:

```powershell
aihawk-academic inspect .\\application.json .\\private-field-inventory.json --persistent
aihawk-academic autofill .\\application.json --persistent
aihawk-academic autofill-stages .\\multi-stage-application.json --persistent
```

The `aihawk-academic session .\\application.json` command opens this
private browser for a login check, but **session-only cookies may be discarded
when Chrome closes**. Therefore the safer option is to authenticate in the
visible browser during the **same `upload-reviewed` command** that performs
the uploads. Persistent cookies may survive a restart; the code never claims
that every university's login remains valid indefinitely.

Review a complete file-to-control mapping in the private manifest before
running the upload workflow. This is a **synthetic example**, not verified
Max Planck selectors or endpoints:

```json
{
  "title": "Synthetic university programme",
  "official_application_url": "https://admissions.example.edu/apply",
  "official_hosts": ["example.edu"],
  "applicant_id": "private-case",
  "fields": {},
  "attachments": ["proof.pdf"],
  "portal_uploads": [
    {
      "field": "proof.pdf",
      "input_selector": "#proof",
      "upload_button_selector": "#proof-upload",
      "container_selector": "#proof-container",
      "receipt_selector": ".file a",
      "remove_selector": "button.remove",
      "expected_path": "/apply",
      "upload_endpoint_path": "/file/ajax"
    }
  ]
}
```

The file must physically exist within the private manifest directory.
Both the file hash and all portal selectors are included in the review
fingerprint. The university's exact file-upload endpoint must be inspected
before configuration; **never guess it**.

```powershell
aihawk-academic upload-reviewed .\\application.json
```

One typed approval covers the reviewed batch. The browser session is opened
once, then reused for each mapped file. For each step, the program:

1. Checks the exact official hostname, path and specific file container.
2. Refuses existing conflicting files and changed attachment hashes.
3. Selects the attachment using Playwright `set_input_files`, which never
   opens a Windows file chooser, even for hidden file inputs.
4. Permits only the explicitly approved AJAX POST upload path while its
   dedicated Upload control is clicked.
5. Requires **both a successful HTTP response from the exact approved
   upload endpoint and a matching file link plus Remove control** in the
   expected portal container. A UI link alone does not prove an upload.
6. Prevents duplicate uploads if an HTML file-input `change` event starts the
   POST before the separate Upload button is clicked.
7. Writes an atomic private checkpoint under
   `.aihawk-uploads-<fingerprint>.json` with an OS-managed exclusive lock.
   On process crash, the operating system releases the lock; an uncertain
   upload remains unverified and is **never blindly retried**.
8. On subsequent runs, rechecks the portal's exact file-list receipt before
   treating any previous attempt as completed.

The browser's saved profile contains authentication secrets and **must remain
private**. Do not zip, publish, synchronize or commit the
`.aihawk-academic-session` directory. It cannot be placed in a Git checkout.
The local machine owner may revoke the site session by signing out and
deleting this dedicated private profile when the browser is closed.

This implementation deliberately does **not** automate institutional consent,
referee requests, CAPTCHA/SSO verification, final submission or payment.
Browser-route interception is a defense in depth, not a full JavaScript or
WebSocket security boundary. A real university form adapter must be validated
before running it against an authenticated portal; synthetic tests alone do
not establish university compatibility.


### Multiple documents in one upload field

Some portals permit multiple files in a single degree/transcript section.
An original-language certificate and a certified translation must never
silently overwrite each other. Include both files in the reviewed
`attachments` array. For the *second* file, the mapping may explicitly
declare `"expected_existing_files": ["original.pdf"]`, referencing the
already approved original. The code then requires exactly the approved prior
receipt set and a corresponding Remove control for each file. A different
existing document, unexpected extra link, missing original or altered
attachment hash stops execution. The portal must expose a suitable
reviewed input selector for adding another file; this is site-specific.

### Historical, redacted form readiness audit

An earlier university form capture can be checked offline without another
browser connection:

```powershell
aihawk-academic audit-snapshot .\\private-uia-snapshot.txt .\\private-readiness.json --host admissions.example.edu
```

The output identifies previously empty marked-required text controls,
unselected options requiring attention, and file inputs empty **at the
time of capture**. It cannot determine current upload status or whether a
referee was invited since the capture. Never treat it as a live application
completion check. The command rejects unredacted input values.

On the BMAI 2027 historical capture, the six starred referee identity/contact
inputs were empty at capture; other required application fields and current
referee status must be checked in the authenticated portal.

A visible dedicated Playwright Chrome session reached the public BMAI portal,
whereas headless Chrome returned HTTP 403 in local testing. The new BMAI
workflow still needs a legitimate initial sign-in and independent verification
of its authenticated AJAX endpoints, receipt controls and file mappings. It
is not a verified fully automatic BMAI application.
