# Position-specific motivation letters in AIHawk

The `motivation-auto` workflow generates a **new, position-specific English motivation letter** from each official university opportunity in a private queue. It uses the applicant's own searchable CV and institutionally attributable page text, not a universal mail-merge paragraph. Each output is a new, editable DOCX in **Times New Roman**, using the one-page A4 structure of the supplied CUAS example: prominent title, programme and institution subtitle, thin divider, salutation, five substantive paragraphs and closing signature.

The renderer creates a fresh document instead of editing the sample, preventing inherited headers, stamps, watermarks, comments or template metadata. It does not add a ChatGPT or AI watermark. The letter remains a draft until the applicant approves its factual claims and final wording.

## Private queue

Store the CV and queue **outside any Git repository**, for example in a private university application folder:

```json
{
  "applicant_name": "Example Researcher",
  "cv_file": "CV.pdf",
  "positions": [
    {
      "institution": "Example Biomedical Institute",
      "programme": "Biomedical Artificial Intelligence",
      "degree": "PhD",
      "official_url": "https://graduate.example.edu/phd",
      "official_hosts": ["graduate.example.edu"],
      "forbidden_organizations": ["Unrelated University"]
    }
  ]
}
```

`official_hosts` must be established from the university's website, not guessed or derived from an untrusted listing. URLs must lead to accessible, public institutional pages with enough substantive text. If evidence cannot be obtained, the position fails instead of receiving a fabricated generic letter.

Install the optional writing dependencies and configure the **OpenAI API** credentials in the private local environment:

```powershell
pip install ".[academic-writing]"
$env:OPENAI_API_KEY = "YOUR_API_KEY"
$env:OPENAI_MODEL = "YOUR_AVAILABLE_API_MODEL"
aihawk-academic motivation-auto .\position-queue.json
```

The ChatGPT app subscription does **not** automatically give locally installed AIHawk access to the OpenAI API or its usage allowance. An API key and an available model must be separately configured. Do not commit the API key, CV or generated documents to GitHub.

The command processes a maximum of 50 positions per run, obtains an official source for each, makes a private source-audited brief and asks the configured model to draft five new paragraphs. Every resulting DOCX is validated against length, wrong-institution names, unsupported numerals, placeholders and obvious generated-by branding. Its accompanying `.review.json` records document and source fingerprints, without claiming submission.

The output follows this structure:

```text
private-folder/
  position-queue.json
  CV.pdf
  motivation_letters/
    institution-programme-fingerprint/
      cv-source.pdf
      official-source-audit.json
      position-brief.json
      MotivationLetter_TimesNewRoman.docx
      MotivationLetter_TimesNewRoman.review.json
  motivation_batch_review.json
```

Existing letters and previously edited briefs are **never silently overwritten**. Failures and missing source evidence are reported for individual positions. No form is submitted, no recommendation request is sent and no irreversible decision is made in this workflow.

## Quality requirements and limitations

- Match the **actual programme**: write about the documented research themes or training modules rather than generic praise.
- Represent applicant qualifications precisely. Academic biomechanics, movement-signal modelling and applied machine learning are not equivalent to molecular biology expertise, and eligibility cannot be inferred from transferable computing skills.
- Do not fabricate publications, dataset sizes, model accuracy, research group affiliations, supervisor interest or confirmed admission eligibility.
- Preserve five substantial paragraphs, a formal salutation, appropriate sign-off and a coherent academic motivation. For a PhD, focus on the doctoral research transition rather than explaining why the candidate seeks a second master's degree.
- Review final English and science claims manually; validation of numeric tokens and the presence of official evidence **does not prove** that every qualitative assertion is correct.
- A one-page Word template does not guarantee that *every* target letter renders on a single page with all available fonts; run an office renderer or Microsoft Word page-count inspection on the final output before submission.
- `motivation-auto` is a self-contained writing module; integration with the live opportunity crawler, application eligibility rules, upload receipts and autonomous submission is **not** finished.
- The earlier `motivation-batch` command remains independent for batches that already have separately reviewed position briefs.

## Example BMAI review case

The private Max Planck BMAI motivation draft uses the CV's documented degrees, gait and force-platform research, MATLAB/Python laboratory programming and GRF prediction publications. The one-page Word document is a **review draft**. Its upload, any supervisor or referee selection, and final university submission were not performed by the letter-generation command.

## BMAI live format issue and verified PDF output

The authenticated BMAI 2027 portal rejected the initial DOCX motivation
letter. The institution's field allows txt, doc, pptx, pdf, jpg, jpeg and png,
but not docx. Renaming a DOCX to .pdf is not conversion.

The single-letter command has a --pdf flag to export the reviewed Times New
Roman Word document with Word on Windows or LibreOffice elsewhere:

    aihawk-academic motivation-letter private-position.json MotivationLetter.docx --pdf

In a position queue, set portal_allowed_extensions to an independently
verified list of allowed file types (e.g. ["txt","doc","pptx","pdf","jpg","jpeg","png"]).
When the field excludes DOCX and includes PDF, motivation-auto creates an
additional A4, one-page, source-checked PDF. The original Word draft is retained.
This operation does not upload files by itself.

In a real logged-in Max Planck application test on 21 November 2026, the
converted one-page letter was uploaded in Letter of Motivation, shown with a
file link and Remove control, and persisted after the ordinary Save on the
application View page. The portal lowercased the receipt's filename. The
matching local verified report is
26_BMAI_Motivation_Live_Upload_Verified.json (private application folder).

The attachment's bytes were not independently downloaded and rehashed.
A verified draft upload is not a final university application submission.
No referee invitations or final submission actions were performed.
