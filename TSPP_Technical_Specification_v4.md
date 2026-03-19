# Technical Specification: Two-Stage Parser with Provenance (TSPP)

**Project:** Clinical AI Hackathon – MDT Data Extraction  
**Architecture Version:** 4.0  
**Purpose:** Engineering specification for program construction. This document defines
how the program works, how it prevents hallucination, how it handles errors, and how
it protects patient data. Clinical field definitions are in `field_reference_v2.md`.

---

## 1. Architecture Overview

The system is split into three stages with a mandatory data minimisation step between
Stage 1 and Stage 2. The core principle is that **AI is only used for interpretation,
never for reading**. The Word document is read deterministically — what goes into the
AI is pre-structured text, not raw files.

```
Word Document (.docx)
        │
        ▼
┌───────────────────────────────────────┐
│  STAGE 1: Deterministic Segmenter     │
│  python-docx only. Zero AI.           │
│  Splits each table cell into          │
│  sentences, classifies each sentence  │
│  into a typed bucket by keyword.      │
│  Extracts patient identifiers into    │
│  a separate isolated block.           │
└───────────────────────────────────────┘
        │  case_NNN_raw.json
        ▼
┌───────────────────────────────────────┐
│  STAGE 1 VALIDATION                   │
│  Checks each case has meaningful      │
│  content before proceeding.           │
│  Flags structurally sparse cases.     │
└───────────────────────────────────────┘
        │  (passes or flags)
        ▼
┌───────────────────────────────────────┐
│  DATA MINIMISATION                    │
│  Word-boundary regex strips PII.      │
│  Tokens stored for reverse-sub        │
│  at Stage 3. Identifiers kept         │
│  locally only — never sent to API.    │
└───────────────────────────────────────┘
        │  case_NNN_anonymised.json
        ▼
┌───────────────────────────────────────┐
│  STAGE 2: LLM Structurer              │
│  Gemini API (JSON mode only).         │
│  Temperature = 0.                     │
│  Every field: value + source_text     │
│  + confidence. Rate-limited.          │
│  Post-response: fuzzy source_text     │
│  validation against original input.  │
└───────────────────────────────────────┘
        │  case_NNN_structured.json
        ▼
┌───────────────────────────────────────┐
│  STAGE 3: Excel Assembler             │
│  Reverse-substitutes PII tokens       │
│  back into source_text strings.       │
│  Re-joins identifiers locally.        │
│  Applies safety flags.                │
│  Produces 3-sheet workbook.           │
└───────────────────────────────────────┘
        │
        ▼
MDT_Extraction_YYYYMMDD_HHMMSS.xlsx
```

---

## 2. Stage 1 — Deterministic Segmenter

**Goal:** Read the Word document and produce structured JSON with zero interpretation.
The segmenter must not make any judgment about clinical content — it only reads,
splits at the sentence level, and classifies each sentence by keyword matching.

### 2.1 How it works

- Uses `python-docx` to iterate over `Document.tables`
- Each table = one MDT case
- For each table, iterate over every cell in every row
- Extract the full text content of each cell using `cell.text`
- **Split each cell's text into individual sentences** using a simple sentence
  splitter (split on `. `, `.\n`, `! `, `? `, and also strip and split on a
  trailing `.` at end-of-string with no following space — use
  `re.split(r'(?<=[.!?])\s+', text.strip())` as the implementation).
  Do not use an NLP library.
- Classify each sentence individually into a bucket (see section 2.2)
- Accumulate all sentences for each bucket across the entire table
- Output is one JSON file per case: `output/json/case_NNN_raw.json`

**Why sentence-level splitting is essential:** A single table cell may contain
multiple clinical concepts (e.g. "Baseline rectal MRI: mrT3c. CT CAP: M0.").
If the whole cell is classified as one unit, MRI and CT content will land in the
same bucket and Stage 2 will conflate them. Splitting at sentence level before
classification is the fix.

### 2.2 Text segmentation — sentence classification rules

Each sentence is tested against these rules **in priority order** (first match wins).
The priority order is defined below from highest to lowest:

| Priority | Bucket | Rule — sentence must contain ALL of these |
| :--- | :--- | :--- |
| 1 | `restaging_mri_findings` | (`MRI` or `mri` or `magnetic resonance`) AND any of: `restaging`, `post-treatment`, `post-CRT`, `post-SCPRT`, `response assessment`, `re-staging`, `post treatment`, `after treatment`, `following SCPRT`, `following CRT`, `following radiotherapy` |
| 2 | `mri_findings` | `MRI` or `mri` or `magnetic resonance` (and did NOT match rule 1) |
| 3 | `ct_findings` | `re.search(r'\bCT\b', sentence, re.IGNORECASE)` returns a match, or sentence contains `computed tomography`. The word-boundary regex prevents false matches on words like "impact", "direct", "expect". |
| 4 | `pathology` | any of: `biopsy`, `histology`, `histological`, `MMR`, `MSI`, `mutation`, `KRAS`, `NRAS`, `BRAF`, `HER2`, `adenocarcinoma`, `carcinoma` |
| 5 | `mdt_outcome` | any of: `outcome`, `decision`, `plan`, `MDT`, `for surgery`, `for radiotherapy`, `for chemotherapy`, `curative`, `palliative`, `TME`, `SCPRT`, `CRT` |
| 6 | `demographics` | any of: `NHS`, `DOB`, `date of birth`, `consultant`, `hospital number` |
| 7 | `diagnosis` | any of: `diagnosis`, `diagnosed`, `cancer`, `tumour`, `tumor`, `sigmoid`, `rectal`, `colorectal`, `adenocarcinoma` (if not already captured by pathology) |
| 8 | `clinical_history` | catch-all — any sentence not matching rules 1–7 |

**Conflict resolution:** Priority order is strictly top-down. A sentence matching
rule 1 criteria is always placed in `restaging_mri_findings` regardless of whether
it also matches rules 2–7. No sentence is discarded. No sentence appears in more
than one bucket.

**Case-insensitive matching throughout.** All keyword checks must use
`.lower()` comparison or `re.IGNORECASE`.

### 2.3 Patient identifier extraction

Before segmentation runs, the program extracts patient identifiers by scanning the
table for known patterns and places them in a **separate top-level block**:

- NHS number: regex `\d{3}[\s\-]?\d{3}[\s\-]?\d{4}`
- Date of birth: regex `\d{2}[\/\-]\d{2}[\/\-]\d{4}` (first match that is not
  an event date — context: within 5 tokens of "DOB", "date of birth", "born")
- Patient name: text in the demographics row that does not match NHS or date patterns
- Hospital number: text matching local hospital number format (alphanumeric, 6–8
  chars, e.g. H123456)
- Consultant: text following "consultant:", "Mr", "Mrs", "Dr", "Prof" in the
  demographics row
- MDT date: text matching date pattern in the same cell as "MDT", "outcome",
  or "decision"

**The `patient_identifiers` block is isolated from `raw_segments`.** It is the
only copy of the identifiers that exists. The anonymised JSON sent to the API
will not contain this block.

### 2.4 Stage 1 output schema

```json
{
  "case_index": 0,
  "patient_identifiers": {
    "nhs_number": "999 000 0001",
    "patient_name": "Alice B",
    "dob": "01/01/1965",
    "hospital_number": "H123456",
    "consultant": "Mr J Smith",
    "mdt_date": "15/01/2025"
  },
  "raw_segments": {
    "demographics": "NHS Number: 9990001. DOB: 01/01/1965. Consultant: Mr J Smith.",
    "diagnosis": "Diagnosis: Sigmoid Adenocarcinoma.",
    "mri_findings": "Baseline rectal MRI 10/01/2025: mrT3c, mrN2, CRM threatened at 0.8mm, EMVI positive. Tumour at 7cm from anal verge.",
    "restaging_mri_findings": "Restaging MRI 20/03/2025 post-SCPRT: mrT2, mrN0, CRM clear.",
    "ct_findings": "CT CAP 12/01/2025: No liver or lung metastases. No peritoneal disease. M0.",
    "pathology": "Biopsy: moderately differentiated adenocarcinoma. MMR: Proficient (pMMR). KRAS wild-type.",
    "mdt_outcome": "MDT 15/01/2025. Outcome: For SCPRT then restaging MRI then TME surgery. Curative intent.",
    "clinical_history": "Patient presented with change in bowel habit. Previous colonoscopy 2023 normal."
  },
  "is_restaging_mri": true,
  "token_map": {},
  "metadata": {
    "table_index": 0,
    "source_file": "hackathon-mdt-outcome-proformas.docx",
    "extraction_timestamp": "2026-03-17T09:00:00Z"
  }
}
```

Note: `token_map` starts empty at Stage 1. It is populated by the data
minimisation step (section 3.1) with entries like
`{"[NHS_NUMBER]": "999 000 0001", "[PATIENT_NAME]": "Alice B", ...}` and
written back to `case_NNN_raw.json` before Stage 2 runs. It is used in Stage 3
for reverse-substitution of tokens in `source_text` strings.

Note: `is_restaging_mri` is set programmatically here — `true` if
`restaging_mri_findings` is non-empty, `false` otherwise. It is **never** left to
the LLM to determine.

### 2.5 Stage 1 validation — pre-flight check before Stage 2

Before passing any case to Stage 2, the program checks:

1. Is `mri_findings` non-empty OR `ct_findings` non-empty? (At least one imaging
   segment must have content — if both are empty, the case is almost certainly a
   mis-read table and Stage 2 will produce garbage.)
2. Is `mdt_outcome` non-empty? (If empty, the MDT decision cannot be extracted
   and the case will fail its most critical field.)
3. Does `raw_segments` have at least 4 non-empty buckets out of 8?

If any check fails, the case is written to `output/json/case_NNN_flagged.json`
with `stage1_validation_failed: true` and a reason string. It is skipped by
Stage 2 and written to the Excel with all fields `not_found` and
`verification_required: true`, reason: `"Stage 1 validation failed — check
source document structure"`.

This prevents silent failure on cases where the proforma structure deviates
from the expected format.

---

## 3. Data Minimisation

**Goal:** Ensure no patient-identifiable information ever leaves the local machine.
This step runs after Stage 1 validation, before any API call is made.

### 3.1 What is stripped

A pre-processing function reads `case_NNN_raw.json` and produces
`case_NNN_anonymised.json`. It applies substitution to every string value within
`raw_segments` using the following rules:

| Content | Regex pattern | Replacement token |
| :--- | :--- | :--- |
| NHS number | `\d{3}[\s\-]?\d{3}[\s\-]?\d{4}` | `[NHS_NUMBER]` |
| Patient name | `\b{escaped_name}\b` (word boundary, case-insensitive) | `[PATIENT_NAME]` |
| Date of birth | exact match of `patient_identifiers.dob` value | `[DOB]` |
| Hospital number | exact match of `patient_identifiers.hospital_number` value | `[HOSP_NUMBER]` |

**Word-boundary matching is mandatory for patient name.** Plain substring
matching (e.g. `str.replace("Ann", "[PATIENT_NAME]")`) will corrupt clinical words
containing common name substrings (e.g. "management" → "manage[PATIENT_NAME]t",
"significant" → "signi[PATIENT_NAME]t"). Use `re.sub(r'\b' + re.escape(name) +
r'\b', '[PATIENT_NAME]', text, flags=re.IGNORECASE)`.

**Token map preservation.** At the same time as generating `case_NNN_anonymised.json`,
the program records the substitution map for each case:

```json
"token_map": {
  "[NHS_NUMBER]": "999 000 0001",
  "[PATIENT_NAME]": "Alice B",
  "[DOB]": "01/01/1965",
  "[HOSP_NUMBER]": "H123456"
}
```

This token map is stored in `case_NNN_raw.json` (never transmitted) and used in
Stage 3 to reverse-substitute tokens back into `source_text` strings before they
are written to the Excel Source Evidence sheet (see section 6.2).

### 3.2 What the anonymised JSON contains

The `patient_identifiers` block is removed entirely. The `raw_segments` values
contain placeholder tokens in place of any PII. `is_restaging_mri` and `metadata`
are retained. `case_index` is retained as the only linking key.

### 3.3 Re-join and reverse-substitution in Stage 3

After Stage 2 completes:

1. Stage 3 reads `case_NNN_raw.json` and extracts `patient_identifiers` and
   `token_map`
2. `patient_identifiers` is appended to the assembled Excel row directly
3. For every `source_text` string in the structured JSON, the program iterates
   over `token_map` and replaces each placeholder token with its original value
   before writing to Sheet 2 (Source Evidence)

This means Sheet 2 shows clean, readable source text — not `[HOSP_NUMBER]`
placeholders — while the API never received the actual values.

### 3.4 Compliance comment block (include verbatim in source code)

```python
# DATA MINIMISATION — DCB0129 / DTAC
# ------------------------------------
# Patient-identifiable fields (NHS number, name, DOB, hospital number)
# are removed from all text before it is sent to the Gemini API.
# Word-boundary regex is used for name matching to prevent corruption
# of clinical terms containing common name substrings.
# A token map preserves the original values for reverse-substitution
# at Stage 3 assembly — so the Source Evidence sheet shows clean text.
# The API receives only anonymised clinical text snippets.
# No patient data is transmitted to any external service at any point.
# This design ensures the system cannot be the proximate cause of a
# patient data breach via API interception or logging.
```

---

## 4. Stage 2 — LLM Structurer with Provenance

**Goal:** Use the Gemini API to extract structured clinical fields from the
anonymised text segments. Every extracted value must be traceable to the exact
sentence it came from.

### 4.1 Anti-hallucination: the Provenance Triad

This is the primary mechanism that prevents hallucination from entering the output
silently. The API prompt instructs the model that **every field, without exception,
must be returned in this exact structure:**

```json
"field_name": {
  "value": "the extracted value",
  "source_text": "the exact sentence from the input this was taken from",
  "confidence": "high"
}
```

**Rules enforced by the prompt:**

- `source_text` must be a verbatim copy of a sentence from the input text.
  The model must not paraphrase, reconstruct, summarise, or merge sentences.
- If a field is not present in the source text: `value: null`,
  `source_text: null`, `confidence: "not_found"`.
- If a field is present but ambiguous, partially stated, or requires any
  inference beyond reading what is written: `confidence: "low"`.
- `confidence` accepts exactly three values: `"high"`, `"low"`, `"not_found"`.
- The model must never infer clinical meaning from qualitative descriptions
  (e.g. must not convert "good response" to a grade). See `field_reference_v2.md`.
- CT fields must only be populated from CT source text. MRI fields must only
  be populated from MRI source text. Restaging fields only from
  restaging_mri_findings. Baseline fields only from mri_findings.

### 4.2 API call configuration

- **Mode:** JSON mode (structured output / response schema enforced)
- **Temperature:** `0` — deterministic, no creativity
- **Max tokens:** `8192` — the few-shot example and full field list in the
  system prompt are large; 4096 risks truncating the response on complex cases.
- **System prompt:** States the model is a data extraction tool only. Explicitly
  forbids clinical interpretation, diagnosis, inference, or recommendations.
- **Input:** The `raw_segments` object from `case_NNN_anonymised.json`, serialised
  as a JSON string in the user message. Each segment is labelled with its bucket
  name so the model knows the source type of each sentence.
- **Output:** A single flat JSON object containing all fields

### 4.3 Rate limiting

The Gemini API has per-minute request limits. The following must be implemented
to prevent failures during a full 50-case run:

- Add `time.sleep(1.5)` between each API call (gives ~40 calls/minute, within
  free tier limits)
- Use `tqdm` progress bar so progress is visible during the demo run
- Log elapsed time per case to console

### 4.4 Post-response validation and hallucination detection

Before `case_NNN_structured.json` is written, the response is validated in three
passes:

**Pass 1 — JSON validity**
Is the response valid JSON? If not: strip markdown fences (` ```json ` and ` ``` `)
and attempt `json.loads()` again. If still invalid: log raw response, set all
fields to `not_found`, set `validation_error: "non_json_response"`.

**Pass 2 — Schema compliance**
Does every field contain all three keys: `value`, `source_text`, `confidence`?
Does `confidence` contain only `"high"`, `"low"`, or `"not_found"`?
For any field failing this check: force `confidence: "low"`, log the violation.

**Pass 3 — Source text verification (hallucination detection)**
For every field where `source_text` is not null, run a fuzzy match check against
the concatenated `raw_segments` from `case_NNN_anonymised.json`:

```python
def source_text_is_valid(source_text: str, original_segments: dict) -> bool:
    # Guard: join all segment values as strings (segments may be empty strings)
    haystack = " ".join(str(v) for v in original_segments.values()).lower().strip()
    needle = source_text.lower().strip()
    # Exact match first
    if needle in haystack:
        return True
    # Fuzzy fallback: check if 85%+ of needle tokens appear in haystack
    needle_tokens = set(needle.split())
    haystack_tokens = set(haystack.split())
    if len(needle_tokens) == 0:
        return False
    overlap = len(needle_tokens & haystack_tokens) / len(needle_tokens)
    return overlap >= 0.85
```

If this check returns `False`: the model likely fabricated or reconstructed the
sentence. Force `confidence: "low"` and add `"hallucination_check_failed"` to the
field's metadata. This triggers the verification flag downstream.

**Why fuzzy matching instead of exact substring:**
LLMs routinely normalise punctuation (curly quotes → straight quotes), change
whitespace, or alter en-dashes. Exact substring matching produces false
**negatives** on legitimate extractions — real source sentences that fail the
check purely due to minor formatting differences, incorrectly triggering the
hallucination flag. The 85% token overlap threshold catches genuine fabrication
while tolerating these minor differences.

### 4.5 Field extraction groups and priority

Fields are grouped by priority. If the response is truncated or an error occurs,
higher-priority groups take precedence. The full field definitions and accepted
values are in `field_reference_v2.md`.

- **Group A — MRI Staging** (highest): baseline MRI fields, restaging MRI fields
  including mrTRG. Source: `mri_findings` and `restaging_mri_findings` segments.
- **Group B — CT Staging**: M-stage and metastatic site fields only. CT is not
  used for T or N staging of rectal tumours — no T or N fields exist in this group.
  Source: `ct_findings` segment.
- **Group C — Pathology & Biomarkers**: MMR, MSI, mutation status, histology.
  Source: `pathology` segment.
- **Group D — MDT Decision**: treatment intent, modality, planned surgery, verbatim
  outcome. Source: `mdt_outcome` segment.
- **Group E — Identifiers**: NOT sent to the API. Re-joined from
  `case_NNN_raw.json` at Stage 3.

---

## 5. Error Handling and Safety Flags

### 5.1 Human Verification Required — trigger rules

After Stage 2 and post-response validation complete, the program evaluates the
following rules **programmatically** (not by the LLM) and sets
`verification_required = true` if any are met. Rules are calibrated to flag
genuinely problematic cases — not to flag every case where a field is absent.

| # | Trigger condition | Reason string |
| :--- | :--- | :--- |
| 1 | Any Group A MRI staging field (`mrT_stage`, `mrN_stage`, `mrCRM_status`, `mrEMVI_status`) has `confidence == "low"` | `"Low confidence MRI staging"` |
| 2 | `structured_json["treatment_intent"]["value"]` is `null` or `"not_stated"` | `"MDT treatment intent missing"` |
| 3 | `structured_json["mrT_stage"]["value"]` is not null AND `structured_json["ct_M_stage"]["value"]` is null AND `ct_findings` segment is non-empty | `"T stage found but M stage absent despite CT report present"` |
| 4 | `is_restaging_mri == true` AND `structured_json["mrT_stage"]["value"]` is null | `"Restaging MRI present but no baseline MRI staging found"` |
| 5 | Any `source_text` failed the fuzzy validation check (Pass 3) | `"Hallucination check failed — verify source text"` |
| 6 | `source_text` is null for a field where `value` is not null | `"Value present with no source text — unverifiable"` |
| 7 | A clinical ambiguity was detected (section 5.2) | Specific reason per ambiguity type |
| 8 | Stage 1 validation failed for this case | `"Stage 1 validation failed — check source document"` |

**Important calibration note on rule 3:** This rule only fires when a CT report
is actually present in `ct_findings` but no M stage was extracted from it.
It does NOT fire simply because `ct_M_stage` is `not_found` with an empty
`ct_findings` segment — that is a normal situation (no CT yet reported).
This prevents the majority of first-MDT cases from being incorrectly flagged.

All triggered reasons are concatenated into `verification_reasons` as a
pipe-separated string.

### 5.2 Clinically dangerous ambiguity detection

Detected programmatically after Stage 2 returns. These are the two scenarios
that matter most:

**Scenario A — Two staging values for the same primary field:**
If `structured_json["mrT_stage"]["value"]` is not null AND
`structured_json["restaging_mrT_stage"]["value"]` is not null,
set `verification_required = true`, reason:
`"Both baseline and restaging T stage present — verify correct field assignment"`.
Both values must be preserved in their respective fields — do not discard either.

**Scenario B — Contradictory M-stage:**
If `structured_json["ct_M_stage"]["value"] == "M0"` AND any of the following
keywords appear in `raw_segments["clinical_history"]` or
`raw_segments["mdt_outcome"]`: `liver metastases`, `lung mets`, `peritoneal`,
`M1`, `metastatic`:
- Force `structured_json["ct_M_stage"]["confidence"] = "low"`
- Set `verification_required = true`
- Reason: `"CT M0 contradicts clinical notes suggesting metastatic disease"`
- Add a `contradiction_note` key directly to the `ct_M_stage` field object:
  ```json
  "ct_M_stage": {
    "value": "M0",
    "source_text": "CT CAP: No distant metastases. M0.",
    "confidence": "low",
    "contradiction_note": "Conflicting text found: '<the contradicting sentence>'"
  }
  ```
  Where `<the contradicting sentence>` is the specific sentence from
  `clinical_history` or `mdt_outcome` that contains the metastatic keyword.

### 5.3 API failure handling

| Failure type | Behaviour |
| :--- | :--- |
| Timeout or connection error | Retry up to 3 times: wait 2s, 4s, 8s between attempts. On third failure: all fields `not_found`, `verification_required: true`, reason: `"API failure — manual extraction required"` |
| Non-JSON response | Strip fences, retry once. On second failure: all fields `not_found` |
| Schema violation | Log raw response. Set violating fields to `confidence: "low"`. Continue. |
| Model refusal | Log. Set `verification_required: true`, reason: `"API refusal — manual extraction required"` |

All API calls logged to `logs/api_responses.log`: timestamp, `case_index`,
HTTP status, response time ms, fields extracted count, fields flagged count.
**Log contains no patient data** — only case index and metadata.

---

## 6. Stage 3 — Excel Assembler

**Goal:** Produce a clean, navigable three-sheet workbook. Re-join identifiers,
reverse-substitute PII tokens in source text, apply styling.

### 6.1 Pre-assembly: token reverse-substitution

Before any sheet is written, for every `source_text` value in
`case_NNN_structured.json`:

```python
for token, original_value in token_map.items():
    source_text = source_text.replace(token, original_value)
```

This ensures Sheet 2 (Source Evidence) shows clean, readable clinical text
with real identifiers rather than `[HOSP_NUMBER]` placeholder tokens.

### 6.2 Column name mapping

Every JSON field name maps to a human-readable clinical column header.
Gemini must use **exactly** these column names in the Excel output — do not
invent alternatives:

| JSON field | Excel column header |
| :--- | :--- |
| `nhs_number` | `NHS Number` |
| `patient_name` | `Patient Name` |
| `dob` | `Date of Birth` |
| `hospital_number` | `Hospital Number` |
| `consultant` | `Consultant` |
| `mdt_date` | `MDT Date` |
| `mrT_stage` | `Baseline MRI: mrT Stage` |
| `mrN_stage` | `Baseline MRI: mrN Stage` |
| `mrCRM_status` | `Baseline MRI: CRM Status` |
| `mrCRM_distance_mm` | `Baseline MRI: CRM Distance (mm)` |
| `mrEMVI_status` | `Baseline MRI: EMVI Status` |
| `mrMRF_status` | `Baseline MRI: MRF Status` |
| `tumour_height_cm` | `Tumour Height from Anal Verge (cm)` |
| `mri_date` | `Baseline MRI Date` |
| `is_restaging_mri` | `Restaging MRI Present` |
| `restaging_mrT_stage` | `Restaging MRI: mrT Stage` |
| `restaging_mrN_stage` | `Restaging MRI: mrN Stage` |
| `restaging_mrCRM_status` | `Restaging MRI: CRM Status` |
| `restaging_mrEMVI_status` | `Restaging MRI: EMVI Status` |
| `mrTRG` | `Restaging MRI: Tumour Regression Grade (mrTRG)` |
| `restaging_mri_date` | `Restaging MRI Date` |
| `ct_M_stage` | `CT: M Stage` |
| `ct_liver_mets` | `CT: Liver Metastases` |
| `ct_lung_mets` | `CT: Lung Metastases` |
| `ct_peritoneal_disease` | `CT: Peritoneal Disease` |
| `ct_date` | `CT Date` |
| `histology_type` | `Histology Type` |
| `histology_grade` | `Histology Grade` |
| `mmr_status` | `MMR Status` |
| `msi_status` | `MSI Status` |
| `kras_status` | `KRAS Status` |
| `nras_status` | `NRAS Status` |
| `braf_status` | `BRAF Status` |
| `her2_status` | `HER2 Status` |
| `pathology_date` | `Pathology Date` |
| `treatment_intent` | `MDT Treatment Intent` |
| `primary_treatment_modality` | `Primary Treatment Modality` |
| `planned_surgery` | `Planned Surgery` |
| `neoadjuvant_treatment` | `Neoadjuvant Treatment Planned` |
| `mdt_outcome_verbatim` | `MDT Outcome (Verbatim)` |
| `verification_required` | `Human Verification Required` |
| `verification_reasons` | `Verification Reasons` |

### 6.3 Sheet 1 — "MDT Data"

- One row per MDT discussion. If a patient appears on two MDT dates, two rows
  ordered by MDT date ascending. Sort key: `mdt_date` parsed as DD/MM/YYYY.
- Patient identifiers re-joined from `case_NNN_raw.json` — first time identifiers
  and extracted data exist in the same file.
- Column headers from the mapping table above (section 6.2).
- **Header row colour banding by group** (openpyxl PatternFill):
  - Light grey (`#F2F2F2`): patient identifier columns
  - Light blue (`#DDEEFF`): baseline MRI staging columns
  - Light teal (`#DDFFEE`): restaging MRI columns
  - Light yellow (`#FFFADD`): CT staging columns
  - Light green (`#EEFFDD`): pathology and biomarker columns
  - Light orange (`#FFE8CC`): MDT decision columns
  - Light red (`#FFE0E0`): verification flag columns
- **Data rows:** rows where `verification_required == true` highlighted amber
  (`#FFC000`). All other rows white.
- `Human Verification Required` column: `YES` if true, `NO` if false.
- Cell A1 comment (openpyxl Comment): `"Amber rows require manual review against
  the Source Evidence sheet before this data is used clinically."`
- Freeze top row and first two columns simultaneously:
  `ws.freeze_panes = ws['C2']` — this single openpyxl call freezes row 1
  and columns A–B together. Do not make two separate freeze_panes assignments.
- Column widths: auto-fit using `column_dimensions[col].width` calculated from
  max character length in each column, capped at 40.

### 6.4 Sheet 2 — "Source Evidence"

One row per extracted field per case. This is the primary audit trail.

Columns (in order):
`Patient ID` | `Patient Name` | `MDT Date` | `Field Name` | `Clinical Label` |
`Extracted Value` | `Source Text` | `Confidence`

- `Source Text` contains the reverse-substituted text (real identifiers, not tokens)
- `Confidence` cell background: green (`#CCFFCC`) for `high`, amber (`#FFC000`)
  for `low`, grey (`#DDDDDD`) for `not_found`
- Only rows where `value` is not null are written — omit `not_found` rows to keep
  the sheet navigable
- Sheet is sorted by Patient ID then Field Name

**Data sensitivity note:** Sheet 2 contains verbatim clinical sentences and patient
identifiers. This sheet has the same sensitivity as the source Word documents and
must be handled accordingly. The compliance comment in section 3.4 applies.

### 6.5 Sheet 3 — "Extraction QC"

Written as a simple key-value table starting at cell A1:

| Metric | Value |
| :--- | :--- |
| Run timestamp | YYYY-MM-DD HH:MM:SS |
| Source file | hackathon-mdt-outcome-proformas.docx |
| Total cases processed | n |
| Cases passing Stage 1 validation | n |
| Cases failing Stage 1 validation | n |
| Fields populated — high confidence | x of 33 extracted fields |
| Fields populated — low confidence | y of 33 extracted fields |
| Fields not found | z of 33 extracted fields |
| Average fields populated per case | calculated |
| Cases flagged for human verification | n |
| Most commonly missing fields (top 5) | listed by field name |
| API calls made | n |
| API failures / retries | n |

Note: "33 extracted fields" refers to the 33 fields extracted by Stage 2
(Groups A–D: 8 baseline MRI + 6 restaging MRI + 5 CT + 9 pathology + 5 MDT
decision). Group E identifiers are re-joined separately and not counted.

---

## 7. Output Files and Data Handling

| File | Location | Contains PII? | Delete after run? |
| :--- | :--- | :--- | :--- |
| `case_NNN_raw.json` | `output/json/` | Yes — full identifiers + token map | Yes, after Excel confirmed |
| `case_NNN_anonymised.json` | `output/json/` | No — tokens only | Yes, after Excel confirmed |
| `case_NNN_structured.json` | `output/json/` | No — tokens in source_text | Yes, after Excel confirmed |
| `case_NNN_flagged.json` | `output/json/` | Partial | Yes, after Excel confirmed |
| `MDT_Extraction_*.xlsx` | `output/` | Yes — Sheet 1 and Sheet 2 | No — this is the deliverable |
| `logs/api_responses.log` | `logs/` | No — case index only | No — retain for audit |

The output Excel file must be treated as a clinical document. Sheet 2 in particular
contains verbatim clinical text alongside patient identifiers and should not be
shared beyond the clinical team with access to the source documents.

---

## 8. Implementation Plan

Execute strictly in this order. Do not proceed to the next step until the
verification check for the current step passes.

| Step | Task | Verification check |
| :--- | :--- | :--- |
| 1 | `pip install python-docx pandas openpyxl tqdm` | All imports succeed without error |
| 2 | Build Stage 1 sentence splitter and segmenter. Run on Case 0 only. | Print all 8 bucket contents. Confirm `mri_findings` and `restaging_mri_findings` are correctly separated. Confirm no sentence appears in two buckets. Confirm no sentence is missing. |
| 3 | Build Stage 1 identifier extractor. Run on Case 0. | `patient_identifiers` block contains correct NHS number, name, DOB, consultant, MDT date. |
| 4 | Build Stage 1 validation check. Deliberately pass a truncated/empty table. | Validation correctly identifies the sparse case and writes `stage1_validation_failed: true`. |
| 5 | Build data minimisation step with word-boundary name matching and token map. Run on Case 0. | Search all string values in `case_NNN_anonymised.json` for NHS number, name, DOB regex. None found. Confirm "management" is not corrupted if patient name is "Ann". |
| 6 | Build Stage 2 prompt and API wrapper. Run on Case 0. | Structured JSON produced. Every field has all three triad keys. All `source_text` values pass the fuzzy check. `time.sleep(1.5)` is present between calls. |
| 7 | Build post-response validation (Passes 1–3). | Manually inject a fabricated `source_text` value. Confirm Pass 3 catches it and forces `confidence: "low"`. |
| 8 | Build safety flag logic (sections 5.1 and 5.2). Test on Case 0. | `verification_required` and `verification_reasons` correctly populated. Rule 3 does NOT fire on a case with empty `ct_findings`. |
| 9 | Run Stages 1–2 on all 50 cases with rate limiting. | All cases produce `case_NNN_structured.json`. No API rate limit errors. Log written. |
| 10 | Build Stage 3: token reverse-substitution, identifier re-join, Excel assembly. | Sheet 2 shows real identifiers in `Source Text`, not `[HOSP_NUMBER]`. Sheet 1 amber rows correct. Column banding applied. All column headers match section 6.2 mapping exactly. QC sheet populated. |
