# ICTUS FLOW — SKILLS & INTELLIGENCE LAYER

> **What this file is:** The complete technical specification for 10 pipeline skills with test benchmarks and regression testing. This is your build brief. Read it fully before writing any code.
>
> **How to use it:** Build each skill in the order specified in the Implementation Order section at the bottom. Do not skip ahead. Each skill depends on the ones before it.
>
> **Companion documents:** System Build Manual, Cowork Action Map, Operations Build Guide.
>
> **Key integration point:** Every skill reads from or writes to the client's `07-LEARNING` folder on Google Drive. The tracking Google Sheet per client is the operational hub — file status, corrections, notes. Skills 3 and 4 reference the tracking sheet directly.

---

## ARCHITECTURE OVERVIEW

Every skill follows **single-agent sequential processing** with structured learning data stored per client. Scaling research validates this: multi-agent coordination degrades performance by 39–70% on sequential tasks. The one exception is tender response (covered in the Change Report).

### Client Folder Structure on Google Drive

Each client gets this structure. The onboarding script (Skill 8) creates it. Skills read from and write to `07-LEARNING`.

```
[ClientName] — Ictus Flow/
├── 01-DROP FILES HERE              # Client uploads (INBOX)
├── 02-PROCESSING                   # Files being processed
├── 03-COMPLETED                    # Finished outputs
├── 04-ARCHIVE                      # Historical work
├── 05-BRAND-ASSETS                 # Logos, fonts, brand pack
├── 06-TEMPLATES                    # Client's existing templates (for Skill 9)
└── 07-LEARNING                     # Intelligence (Tier 1 — client-specific)
    ├── brand-profile.json          # Written by Skill 1
    ├── tone-profile.json           # Written by Skill 2
    ├── corrections.json            # Written by Skill 4
    ├── qa-stats.json               # Written by Skill 3
    └── output-formats.json         # Written by Skill 9
```

### Local Project Structure — Skills-Relevant Paths

```
ictus-flow-system/
├── prompts/                        # Layer 1 — Base prompts (one per skill/workflow)
├── scripts/
│   ├── skills/                     # All 10 skill scripts live here
│   └── utils/
│       └── prompt_builder.py       # 4-layer prompt assembly
├── learning/
│   ├── industry/construction/      # Tier 2 — anonymised cross-client
│   │   └── corrections.json
│   └── universal/                  # Tier 3 — cross-vertical
│       └── corrections.json
├── tests/                          # Test fixtures per skill
│   ├── [skill-name]/              # Inputs + expected outputs
│   └── benchmark-history.csv       # Monthly regression log
├── config/
│   └── workflows/
│       └── routing-rules.json      # Classification → handler mapping + confidence thresholds
└── pending-promotions.json         # Skill 5 output — awaiting approval
```

### Prompt Assembly at Runtime

Handlers build prompts in layers. Different client = different layers 3-4. The `scripts/utils/prompt_builder.py` module handles this.

| Layer | Name | Source | Scope |
|-------|------|--------|-------|
| 1 | Base | `prompts/[skill-name].txt` | Universal instructions. Same for all. |
| 2 | Industry | `learning/industry/[vertical]/corrections.json` | Shared corrections across same vertical. |
| 3 | Client corrections | Client's `07-LEARNING/corrections.json` on Drive | Client-specific fixes. |
| 4 | Brand + tone | Client's `brand-profile.json` and `tone-profile.json` on Drive | Only for output-generating workflows. |

### Separation Model

| Tier | Scope | Storage | Cross-contamination |
|------|-------|---------|---------------------|
| Tier 1 — Client-specific | Brand, tone, corrections | Client's `07-LEARNING` on Drive | Zero |
| Tier 2 — Industry | Anonymised corrections shared across same vertical | Local `learning/industry/` | Promoted after your approval only |
| Tier 3 — Universal | Pure extraction improvements | Local `learning/universal/` | Promoted after appearing across 2+ verticals |

---

## TESTING STANDARD

Apply this standard to every skill you build.

- **Test cases:** 5–10 inputs with known correct outputs per skill. Stored in `tests/[skill-name]/`.
- **Regression:** After any prompt change, test suite re-runs. Accuracy drop = rollback.
- **Monthly benchmark:** All suites run monthly. Results logged to `tests/benchmark-history.csv`.

---

## JSON SCHEMAS

All learning data must conform to these structures. Validate against them.

### brand-profile.json

```json
{
  "colours": {
    "primary": "#hex",
    "secondary": "#hex",
    "accent": "#hex"
  },
  "fonts": {
    "primary": "Font Name",
    "secondary": "Font Name"
  },
  "layout": {
    "date_format": "DD/MM/YYYY",
    "reference_pattern": "PREFIX-NNNN",
    "logo_position": "top-left"
  },
  "gaps": ["list of fields that could not be determined"],
  "source_doc_count": 10,
  "generated_at": "ISO-8601"
}
```

### tone-profile.json

```json
{
  "formality": 3,
  "sentence_length": "medium",
  "vocabulary_complexity": "plain",
  "salutation": "Hi [Name]",
  "signoff": "Kind regards",
  "voice": "active",
  "jargon_level": "moderate",
  "characteristic_phrases": ["phrase1", "phrase2"],
  "anti_patterns": ["phrases never used"],
  "source_doc_count": 10,
  "generated_at": "ISO-8601"
}
```

### corrections.json

```json
{
  "corrections": [
    {
      "id": "uuid",
      "timestamp": "ISO-8601",
      "workflow": "invoice-processor",
      "category": "numerical_error",
      "field": "vat_amount",
      "original_value": "200.00",
      "corrected_value": "240.00",
      "cause": "Applied 20% to net instead of gross",
      "source": "auto-diff | manual | tracking-sheet",
      "promoted_to": null
    }
  ]
}
```

### qa-stats.json

```json
{
  "workflows": {
    "invoice-processor": {
      "total_checked": 52,
      "consecutive_pass": 50,
      "graduated": true,
      "graduation_date": "ISO-8601",
      "spot_check_frequency": 5,
      "last_fail": null
    }
  }
}
```

### output-formats.json

```json
{
  "formats": {
    "invoice_tracker": {
      "type": "spreadsheet",
      "columns": [
        {"name": "Date", "position": 1, "type": "date", "format": "DD/MM/YYYY"},
        {"name": "Supplier", "position": 2, "type": "text"}
      ],
      "conditional_formatting": [],
      "sheet_name": "Invoices"
    }
  },
  "generated_at": "ISO-8601"
}
```

---

## SKILL 1: BRAND PROFILER

**Purpose:** Scans client documents from `05-BRAND-ASSETS` to extract visual identity: colours, fonts, layout, date format, reference numbering. Replaces the manual brand asset collection in the Build Guide's onboarding checklist. Referenced by all output-generating workflows and the QA agent.

### How It Works

1. Collect 10–20 documents during onboarding. Client places them in `05-BRAND-ASSETS` on Drive.
2. Script downloads each, sends to **Opus** for structured extraction of colours (hex), fonts, layout patterns, date format, reference numbering.
3. Consensus logic where documents disagree (majority wins).
4. Gap detection — identifies what couldn't be determined, generates questions for client.
5. Writes `brand-profile.json` to `07-LEARNING` on Drive.
6. Updates the client config file (`config/clients/[code].json`) to set `brand.profile_generated: true`.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 1: Brand Profiler.

Create scripts/skills/brand_profiler.py that:
1. Accepts a client code (e.g. "GILM"). Loads client config from config/clients/.
2. Downloads all files from the client's 05-BRAND-ASSETS folder on Drive (using scripts/utils/drive_client.py).
3. For each document, extracts: colour palette (hex values), fonts used, date format pattern, reference/invoice numbering pattern, logo position, layout conventions.
4. Uses Claude API (Opus via MODEL_COMPLEX) for the extraction — send document content with a structured extraction prompt requiring JSON output.
5. Aggregates results across all documents using consensus logic (majority wins for each field).
6. Detects gaps — any field where confidence is low or documents conflict without clear majority.
7. Outputs brand-profile.json conforming to the schema in SKILLS_SPEC.md. Uploads to client's 07-LEARNING on Drive.
8. Updates client config to set brand.profile_generated = true.
9. Prints a summary: fields extracted, confidence levels, gaps requiring client input.

Create the extraction prompt in prompts/brand-profiler.txt.
Create test fixtures in tests/brand-profiler/ with 3 test sets (see SKILLS_SPEC.md for details).
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| A | 10 docs all Arial, blue #1E3A5F, DD/MM/YYYY | Clean profile, no gaps |
| B | Mixed fonts (6 Arial, 4 Calibri), two date formats | Arial primary, date flagged as gap |
| C | 5 poor quality photos only | Partial profile, multiple gaps flagged |

### Regression Testing

Re-run all 3 test sets after prompt changes. Non-gap fields must match expected. Gap detection must flag same fields.

---

## SKILL 2: TONE FINGERPRINTER

**Purpose:** Analyses client correspondence to extract communication voice: formality, sentence length, vocabulary, salutations, signoffs, jargon level. Referenced by correspondence drafting (Phase 1 letter service), blog writing (Phase 3), and QA agent tone checking.

### How It Works

1. Collect 10–20 pieces of actual client correspondence. Client places them in `05-BRAND-ASSETS` (or a subfolder).
2. Send each to **Sonnet** for structured analysis: formality (1-5), sentence length, vocabulary complexity, salutation/signoff, active/passive voice, jargon.
3. Aggregate across samples (average numerical, mode categorical). Identify characteristic phrases (3+ samples) and anti-patterns (never used).
4. Write `tone-profile.json` to `07-LEARNING` on Drive.
5. Update client config to set `tone.profile_generated: true`.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 2: Tone Fingerprinter.

Create scripts/skills/tone_fingerprinter.py that:
1. Accepts a client code. Loads client config.
2. Downloads correspondence samples from the client's 05-BRAND-ASSETS folder on Drive.
3. For each document, sends to Claude API (Sonnet via MODEL_STANDARD) for structured tone analysis: formality (1-5 scale), average sentence length, vocabulary complexity (plain/moderate/technical), salutation pattern, signoff pattern, active vs passive voice ratio, jargon level.
4. Aggregates: average for numerical fields, mode for categorical. Identifies characteristic phrases appearing in 3+ samples. Identifies anti-patterns (phrases/styles never used).
5. Outputs tone-profile.json conforming to the schema in SKILLS_SPEC.md. Uploads to client's 07-LEARNING on Drive.
6. Updates client config to set tone.profile_generated = true.

Create the analysis prompt in prompts/tone-fingerprinter.txt.
Create test fixtures in tests/tone-fingerprinter/ with 3 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| A | 10 informal emails | Formality 2, plain vocabulary, short sentences |
| B | 10 formal letters | Formality 5, technical vocabulary, long sentences |
| C | Mixed 5 formal + 5 casual | Formality 3, mixed voice |

### Regression Testing

Formality within ±1 of expected. Vocabulary complexity must match. Salutation/signoff must match patterns.

---

## SKILL 3: QA OVERSIGHT AGENT

**Purpose:** Full oversight. Scores on 5 dimensions: factual accuracy, completeness, tone match, format compliance, internal consistency. Loads client corrections to check known patterns. Graduation logic: full QA for first 50 docs per workflow, then spot-check. High-value workflows (RAMS, contracts, tenders, payment certs) **never graduate** — this is hardcoded in `routing-rules.json` under `never_graduate_qa`.

### How It Works

1. Load client learning profile from `07-LEARNING` on Drive (brand + tone + corrections).
2. Send original document + processed output + profile to **Sonnet**.
3. Score 5 dimensions (0-100 each). PASS=80+, FLAG=60-79, FAIL=<60.
4. Overall: PASS if all pass, FLAG if any flag, FAIL if any fail.
5. Graduation tracking in `qa-stats.json` on Drive. After 50 consecutive PASS, graduate to 1-in-5 spot check. Any FAIL resets counter.
6. Log result to client's Google Sheet tracking sheet (status column + QA score column).

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 3: QA Oversight Agent.

Create scripts/skills/qa_oversight.py that:
1. Accepts: client_code, workflow_name, original_file_path, output_file_path.
2. Loads the client's brand-profile.json, tone-profile.json, and corrections.json from their 07-LEARNING folder on Drive.
3. Loads the never_graduate_qa list from config/workflows/routing-rules.json.
4. Sends all three (original, output, learning profile) to Claude API (Sonnet via MODEL_STANDARD) with a structured QA prompt.
5. Returns scores for 5 dimensions: factual_accuracy, completeness, tone_match, format_compliance, internal_consistency. Each 0-100.
6. Applies thresholds: PASS (80+), FLAG (60-79), FAIL (<60). Overall status = worst dimension.
7. Tracks graduation in qa-stats.json on Drive. After 50 consecutive PASS for a workflow, graduate to 1-in-5 spot check. Any FAIL resets the counter to 0. Workflows in never_graduate_qa are always fully checked.
8. Updates the client's Google Sheet tracking row for this file with QA status and score.

Create the QA prompt in prompts/qa-oversight.txt.
Create test fixtures in tests/qa-oversight/ with 6 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Perfect invoice extraction | All dimensions PASS |
| 2 | Wrong VAT (net+VAT≠gross) | Internal consistency FAIL |
| 3 | Missing supplier_name | Completeness FAIL |
| 4 | Formal letter for informal client | Tone FLAG or FAIL |
| 5 | MM/DD when profile says DD/MM | Format FLAG |
| 6 | Known correction pattern supplier | Accuracy FAIL with note |

### Regression Testing

All 6 tests must produce expected status and flag expected dimension after any prompt change.

---

## SKILL 4: CORRECTION LOGGER

**Purpose:** The compound advantage engine. Captures every correction through auto-diff (file changes detected in Drive) and manual notes (`CORRECTION:` prefix in the client's Google Sheet tracking sheet). Categorises errors, builds client-specific knowledge base feeding into QA agent and prompt refinement.

### How It Works

**Auto-diff path:** When file moves from `02-PROCESSING` to `03-COMPLETED`, check if modified (Drive API `modifiedTime`). If yes, download both versions. JSON: field-by-field diff. Documents: text diff. Send diff to Sonnet for categorisation: `numerical_error`, `missing_data`, `wrong_classification`, `formatting_error`, `tone_mismatch`, `factual_error`. Append to `corrections.json` in `07-LEARNING`.

**Manual notes path:** Reads the client's Google Sheet tracking sheet for Notes column entries starting with `CORRECTION:`. Sonnet categorises, appends to `corrections.json`.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 4: Correction Logger.

Create scripts/skills/correction_logger.py with two modes:

AUTO-DIFF MODE (run after file completion):
1. Accepts: client_code, file_id.
2. Downloads original output and final version from Drive (02-PROCESSING vs 03-COMPLETED).
3. Compares: JSON files field-by-field, documents via text diff.
4. Sends diff to Claude API (Sonnet) for categorisation into: numerical_error, missing_data, wrong_classification, formatting_error, tone_mismatch, factual_error.
5. Appends structured correction to corrections.json in client's 07-LEARNING on Drive (conforming to schema).

MANUAL NOTES MODE (run daily):
1. Accepts: client_code.
2. Reads the client's Google Sheet tracking sheet (via sheets_client.py).
3. Finds Notes column entries starting with "CORRECTION:".
4. Sends each to Sonnet for categorisation.
5. Appends to corrections.json on Drive.
6. Marks the tracking sheet row as "correction logged" to avoid re-processing.

Create the categorisation prompt in prompts/correction-logger.txt.
Create test fixtures in tests/correction-logger/ with 4 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Change VAT in output JSON | `numerical_error` logged |
| 2 | No edits, move to COMPLETED | No correction logged |
| 3 | `CORRECTION:` note in sheet | Categorised and logged |
| 4 | Three field changes at once | One entry per field |

### Regression Testing

Each correction must be correctly categorised with right field/value data.

---

## SKILL 5: PATTERN DETECTOR

**Purpose:** Scans corrections across clients weekly. Identifies recurring patterns (same error across 2+ clients). Proposes anonymised corrections for promotion to industry or universal tier. You approve before anything changes. Only valuable once you have 2+ clients.

### How It Works

1. Read all `corrections.json` from all clients' `07-LEARNING` folders on Drive. Anonymise.
2. Group by (category, workflow, cause).
3. Patterns in 2+ clients sent to Sonnet for correction rule generation.
4. Write to `pending-promotions.json` in project root.
5. Email summary via Resend. You review and approve/reject.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 5: Pattern Detector.

Create scripts/skills/pattern_detector.py that:
1. Loads all client configs from config/clients/.
2. Downloads corrections.json from each client's 07-LEARNING folder on Drive.
3. Anonymises all client-specific data (company names, values, amounts, etc.).
4. Groups corrections by (category, workflow, cause).
5. Any pattern appearing in 2+ clients: sends to Claude API (Sonnet) to generate a correction rule.
6. Writes proposed rules to pending-promotions.json in project root.
7. Sends email summary via Resend (using scripts/utils/resend_client.py) for manual review.

Also create a companion script scripts/skills/approve_promotion.py that:
1. Reads pending-promotions.json.
2. Accepts rule ID + approve/reject decision.
3. On approve: writes rule to learning/industry/[vertical]/corrections.json or learning/universal/corrections.json.
4. On reject: removes from pending.

Create the pattern analysis prompt in prompts/pattern-detector.txt.
Create test fixtures in tests/pattern-detector/ with 3 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Same VAT error across 3 clients | Pattern detected, industry promotion proposed |
| 2 | Unique errors per client | No patterns detected |
| 3 | Approve a promotion | Rule in industry corrections, removed from pending |

### Regression Testing

Same seeded data must produce same patterns detected.

---

## SKILL 6: PROMPT REFINER

**Purpose:** Translates approved corrections into prompt amendments. Critical safety: auto-runs regression tests after every change. Accuracy drop = automatic rollback.

### How It Works

1. Read approved rules from `learning/industry/` or `learning/universal/`.
2. Identify target prompt file in `prompts/`.
3. Sonnet writes 1-3 sentence amendment.
4. Backup prompt, apply amendment under `# LEARNED CORRECTIONS` section.
5. Run regression tests for that skill/workflow. Pass = keep. Fail = rollback from backup.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 6: Prompt Refiner.

Create scripts/skills/prompt_refiner.py that:
1. Accepts: a correction rule (from approved promotions or manual input).
2. Identifies which prompt file (prompts/*.txt) the correction applies to.
3. Sends the rule + current prompt content to Claude API (Sonnet) to generate a 1-3 sentence amendment.
4. Backs up the current prompt file to prompts/_backups/[filename].[timestamp].txt.
5. Appends the amendment under a "# LEARNED CORRECTIONS" section at the end of the prompt file.
6. Runs the full regression test suite for that skill (from tests/[skill-name]/).
7. If any test fails: rollback from backup, log the failure to tests/benchmark-history.csv.
8. If all tests pass: keep the change, log success to benchmark-history.csv.

Create the prompts/_backups/ folder.
Create test fixtures in tests/prompt-refiner/ with 2 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Valid correction applied | Tests pass, amendment visible in prompt |
| 2 | Conflicting correction | Tests fail, rollback executed, failure logged |

### Regression Testing

The refiner IS the regression mechanism. Test that backups work, rollbacks work, amendments format correctly.

---

## SKILL 7: OCR PRE-PROCESSOR

**Purpose:** Pre-processes low-quality images before classification/extraction. Auto-rotate, de-skew, contrast enhance, OCR. Only triggered when the classifier confidence is <0.70 on an image file, or when any handler receives a non-text-searchable PDF. Essential for construction clients photographing invoices and delivery notes on site.

### How It Works

1. Detect file type. PDF: check if text-searchable. Image: proceed.
2. Enhance: auto-rotate (EXIF), de-skew, contrast (adaptive histogram), sharpen.
3. Image PDFs: OCR with `pytesseract`, create text-searchable overlay.
4. Save enhanced file to `02-PROCESSING`, keep original in `02-PROCESSING/_raw`.
5. Return enhanced file path for re-classification or handler processing.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 7: OCR Pre-Processor.

Create scripts/skills/ocr_preprocessor.py that:
1. Accepts a file path (PDF or image) and client_code.
2. For PDFs: checks if text-searchable (tries to extract text, if empty or very short = image PDF). If text-searchable, return original path unchanged.
3. For images and image-PDFs, applies: auto-rotate using EXIF data, de-skew detection and correction, adaptive histogram contrast enhancement, sharpen.
4. For image PDFs: runs pytesseract OCR, creates text-searchable PDF with text overlay.
5. Saves enhanced file, keeps original in a _raw subfolder within 02-PROCESSING on Drive.
6. Returns the enhanced file path for downstream processing.
7. Logs processing to client's tracking sheet (OCR applied: yes/no, confidence improvement).

Dependencies: Pillow, pytesseract, pdf2image, reportlab (for PDF overlay).
Create test fixtures in tests/ocr-preprocessor/ with 4 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Clean text PDF | No preprocessing applied, original returned |
| 2 | Good phone photo of invoice | Enhanced, OCR text extracted |
| 3 | Dark tilted photo of delivery note | De-skewed, contrast enhanced, text extracted |
| 4 | 3-page scanned PDF (image-only) | All pages enhanced, text layer added |

### Regression Testing

OCR text vs known transcriptions. Target: 90%+ accuracy on good photos, 75%+ on poor.

---

## SKILL 8: CLIENT ONBOARDER

**Purpose:** One command, full onboarding. Orchestrates Drive folder creation, sample upload, brand profiling, tone fingerprinting, config setup, tracking sheet, and Quick Start Guide. Replaces the manual process in Build Step 8 of the System Build Manual. Makes scaling from 1 to 10 clients viable.

### How It Works

Sequential execution:
1. Create Google Drive folder structure (all 7 folders including `07-LEARNING`).
2. Share root folder with client email and service account.
3. Upload sample documents to `05-BRAND-ASSETS` if provided.
4. Run Brand Profiler (Skill 1) on the samples.
5. Run Tone Fingerprinter (Skill 2) on correspondence samples.
6. Create empty `corrections.json`, `qa-stats.json`, and `output-formats.json` with valid schema structure in `07-LEARNING`.
7. Create Google Sheet tracking sheet from template.
8. Create client config file in `config/clients/[code].json`.
9. Generate Quick Start Guide (from `templates/client-quick-start.docx`).
10. Send welcome email via Resend with Quick Start Guide attached.
11. Print summary with gaps requiring client input.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 8: Client Onboarder.

Create scripts/skills/client_onboarder.py that accepts: client_name, client_email, client_code (optional — auto-generates from first 4 chars if not provided), sample_docs_folder (optional local path).

Then sequentially:
1. Creates the full Google Drive folder structure: [ClientName] — Ictus Flow / with subfolders 01-DROP FILES HERE, 02-PROCESSING, 03-COMPLETED, 04-ARCHIVE, 05-BRAND-ASSETS, 06-TEMPLATES, 07-LEARNING.
2. Shares root folder with client_email (Editor) and service account (Editor).
3. Records all folder IDs.
4. If sample_docs_folder provided: uploads files to 05-BRAND-ASSETS.
5. If samples exist: runs Brand Profiler (Skill 1). If no samples: creates empty brand-profile.json with all fields as gaps.
6. If correspondence samples exist: runs Tone Fingerprinter (Skill 2). If none: creates empty tone-profile.json.
7. Creates empty corrections.json, qa-stats.json, output-formats.json with valid schema in 07-LEARNING on Drive.
8. Creates Google Sheet tracking sheet for the client (using sheets_client.py) with columns: File Name, Date Received, Classification, Confidence, Status, Workflow, QA Score, QA Status, Notes, Completed Date.
9. Writes client config to config/clients/[code].json with all folder IDs, sheet ID, and profile status.
10. Generates Quick Start Guide document for the client.
11. Sends welcome email via Resend with the Quick Start Guide.
12. Prints summary: folders created, profiles generated, gaps needing client input, tracking sheet URL.

Must handle partial failures gracefully — if brand profiling fails, continue with the rest and report the failure at the end.

Create test fixtures in tests/client-onboarder/ with 3 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Full onboarding with 10 sample docs | All folders, profiles, config, sheet, guide created |
| 2 | No sample documents provided | Folders created, empty profiles with all-gaps, config created |
| 3 | Invalid client email | Sharing fails gracefully, everything else completes, failure reported |

### Regression Testing

Full onboarding produces all expected files and config entries. Profiles conform to schema.

---

## SKILL 9: OUTPUT FORMAT MATCHER

**Purpose:** Analyses client's existing templates from `06-TEMPLATES` and creates replication specs so your outputs match their structure. Reduces client friction — their bookkeeper sees the same column order and formatting they're used to.

### How It Works

1. Client provides existing templates in `06-TEMPLATES` on Drive.
2. Script downloads and analyses: spreadsheets (columns, types, conditional formatting, formulas), Word docs (layout, styles, sections).
3. Sonnet creates structured replication spec.
4. Save to `output-formats.json` in `07-LEARNING` on Drive.
5. Handlers reference spec via `prompt_builder.py` when generating outputs.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 9: Output Format Matcher.

Create scripts/skills/output_format_matcher.py that:
1. Accepts a client_code. Loads client config.
2. Downloads all files from the client's 06-TEMPLATES folder on Drive.
3. For spreadsheets (xlsx, csv): extracts column names, column order, data types, conditional formatting rules, formula patterns, sheet names using openpyxl.
4. For Word docs (docx): extracts layout (margins, orientation), heading styles, font usage, section structure using python-docx.
5. For PDFs: extracts layout structure using PyPDF2.
6. Sends extracted structure to Claude API (Sonnet) to create a structured replication spec.
7. Saves output-formats.json to client's 07-LEARNING on Drive conforming to the schema in SKILLS_SPEC.md.
8. Provides a helper function get_format_spec(client_code, output_type) that handlers can call to get the format spec for a given output type.

Create the analysis prompt in prompts/output-format-matcher.txt.
Create test fixtures in tests/output-format-matcher/ with 3 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Invoice tracker Excel with 14 columns + conditional formatting | All columns, order, and formatting captured |
| 2 | Word letterhead template | Layout, fonts, margins captured |
| 3 | Generate output using captured spec | Output matches original structure |

### Regression Testing

Re-analyse same template, compare spec field-by-field. Columns and formatting must match.

---

## SKILL 10: ENHANCED FILE CLASSIFIER

**Purpose:** Enhancement of the base Haiku classifier from Build Step 3. Adds hard confidence thresholds (from `routing-rules.json`), client correction pattern integration, OCR triggering for poor images, and classification learning from corrections.

### Confidence Thresholds

Defined in `config/workflows/routing-rules.json`:

| Confidence | Action | Status |
|------------|--------|--------|
| ≥ 0.90 | Auto-route to handler | NEW |
| 0.70–0.89 | Route but flag for spot-check | SPOT_CHECK |
| < 0.70 | Hold. If image: trigger OCR (Skill 7), re-classify. If still low: hold for manual. | NEEDS_CLASSIFICATION |

### How It Works

1. Run base Haiku classification (from `scripts/classifier.py`).
2. Apply confidence thresholds from `routing-rules.json`.
3. Load client's `corrections.json` from `07-LEARNING`, filter for `wrong_classification` entries, append as additional context to classification prompt.
4. For <0.70 confidence on image files: trigger OCR Pre-Processor (Skill 7), then re-classify with enhanced file.
5. Manual classification corrections feed back via Correction Logger (Skill 4) and Pattern Detector (Skill 5).
6. Log classification result to client's Google Sheet tracking row.

### Claude Code Prompt

```
Read SKILLS_SPEC.md. Build Skill 10: Enhanced File Classifier.

Create scripts/skills/enhanced_classifier.py that wraps and enhances scripts/classifier.py:
1. Accepts: client_code, file_id (Drive file ID).
2. Downloads the file from the client's 01-INBOX on Drive.
3. Runs base Haiku classification with the prompt from prompts/classifier.txt.
4. Applies confidence thresholds from config/workflows/routing-rules.json.
5. Loads corrections.json from client's 07-LEARNING on Drive. Filters for wrong_classification entries. If any exist, appends them as additional context to the classification prompt and re-runs.
6. If confidence < 0.70 and file is an image or image-PDF: triggers OCR Pre-Processor (Skill 7), then re-classifies with the enhanced file.
7. If still < 0.70 after OCR: sets status to NEEDS_CLASSIFICATION for manual review.
8. Returns: classification type, confidence score, status (NEW / SPOT_CHECK / NEEDS_CLASSIFICATION).
9. Updates the client's Google Sheet tracking row with classification, confidence, and status.

Create the enhanced classification prompt in prompts/file-classifier.txt (extends the base classifier.txt).
Create test fixtures in tests/file-classifier/ with 5 test sets.
```

### Test Cases

| Test | Input | Expected Output |
|------|-------|-----------------|
| 1 | Clean invoice PDF | INVOICE, confidence >0.90, status NEW |
| 2 | Ambiguous payment application | Confidence 0.70-0.90, status SPOT_CHECK |
| 3 | Illegible phone photo | Confidence <0.70, OCR triggered, re-classified |
| 4 | Known misclassification pattern in corrections | Correctly classified using correction data |
| 5 | Unknown document type | OTHER, low confidence, NEEDS_CLASSIFICATION |

### Regression Testing

All 5 files: correct type, correct confidence range, correct status.

---

## IMPLEMENTATION ORDER

Build in this order. Each depends on the previous. Split into launch-critical and post-launch.

### Pre-Launch (Required for First Client)

| Phase | Skill | Depends On | Why This Order |
|-------|-------|------------|----------------|
| 1 | Skill 7: OCR Pre-Processor | — | Standalone. Site photos need this from day one. |
| 2 | Skill 10: Enhanced Classifier | Skill 7 | Needs OCR for low-confidence images. Replaces basic classifier. |
| 3 | Skill 1: Brand Profiler | — | Foundation for output formatting. Run at onboarding. |
| 4 | Skill 2: Tone Fingerprinter | — | Foundation for communications. Run at onboarding. |
| 5 | Skill 8: Client Onboarder | Skills 1, 2 | Orchestrates onboarding. Even a basic version saves time. |

### Post-Launch (Build After First Client is Live)

| Phase | Skill | Depends On | Why This Order |
|-------|-------|------------|----------------|
| 6 | Skill 9: Output Format Matcher | Skills 1, 2 | Completes the client profile trio. Reduces friction. |
| 7 | Skill 3: QA Oversight Agent | Skills 1, 2, 9 | Needs profiles to check against. Quality gate. |
| 8 | Skill 4: Correction Logger | Skill 3 | Captures QA failures and manual fixes. Starts learning. |

### Scale Phase (Build Once You Have 2+ Clients)

| Phase | Skill | Depends On | Why This Order |
|-------|-------|------------|----------------|
| 9 | Skill 5: Pattern Detector | Skill 4 | Needs corrections from multiple clients to find patterns. |
| 10 | Skill 6: Prompt Refiner | Skills 4, 5 | Needs patterns to refine from. The self-improvement engine. |
