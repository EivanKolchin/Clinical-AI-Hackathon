# Clinical AI Hackathon — Project Task Division

**Project:** Two-Stage Parser with Provenance (TSPP) — MDT Data Extraction  
**Team:** You + Eivan  
**Date:** March 19, 2026

---

## Overview

This document divides the implementation work into two parallel tracks:
- **Track A (You):** Document parsing and patient data privacy
- **Track B (Eivan):** LLM integration and clinical output

---

## Track A: You — Stages 1 & Data Minimisation

### Stage 1: Deterministic Segmenter

**What:** Read clinical Word documents and segment content without any AI interpretation.

**How:**
1. Use `python-docx` library to read `.docx` files
2. Iterate over `Document.tables` — each table represents one MDT case
3. For each table cell:
   - Extract full text using `cell.text`
   - Split into sentences using regex: `re.split(r'(?<=[.!?])\s+', text.strip())`
   - Classify each sentence individually into one of 8 buckets (see below)
4. Extract patient identifiers into separate isolated block
5. Validate case has meaningful content before flagging as ready for Stage 2
6. Output: `output/json/case_NNN_raw.json`

**8 Classification Buckets** (priority order — first match wins):
1. `restaging_mri_findings` — contains MRI + (restaging, post-treatment, post-CRT, response assessment, etc.)
2. `mri_findings` — contains MRI (baseline only)
3. `ct_findings` — word boundary match for CT, not embedded in other words
4. `pathology` — biopsy, histology, MMR, MSI, mutations, KRAS, NRAS, BRAF, HER2, adenocarcinoma
5. `mdt_outcome` — outcome, decision, plan, MDT, for surgery, for radiotherapy, for chemotherapy, curative, palliative, TME, SCPRT, CRT
6. `demographics` — NHS, DOB, date of birth, consultant, hospital number
7. `diagnosis` — diagnosis, diagnosed, cancer, tumour, tumor, sigmoid, rectal, colorectal, adenocarcinoma
8. `clinical_history` — catch-all for anything not matching 1–7

**Patient Identifier Extraction:**
Extract **before** segmentation runs and place in separate `patient_identifiers` block:
- NHS number: regex `\d{3}[\s\-]?\d{3}[\s\-]?\d{4}`
- Date of birth: regex `\d{2}[\/\-]\d{2}[\/\-]\d{4}` (context: DOB, date of birth, born)
- Patient name: text in demographics row not matching NHS/date patterns
- Hospital number: alphanumeric 6–8 chars, e.g. H123456
- Consultant: text following "consultant:", "Mr", "Mrs", "Dr", "Prof"
- MDT date: date pattern in same cell as "MDT", "outcome", "decision"

**Stage 1 Validation** (pre-flight check):
- Is `mri_findings` OR `ct_findings` non-empty? (need at least one imaging segment)
- Is `mdt_outcome` non-empty? (critical field)
- Does `raw_segments` have ≥4 non-empty buckets out of 8?

If validation fails, flag case as `case_NNN_flagged.json` with `stage1_validation_failed: true` and skip to Stage 2 (Eivan will handle flagged cases).

**Output Schema: `case_NNN_raw.json`**
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
    "demographics": "NHS Number: 9990001. DOB: 01/01/1965...",
    "diagnosis": "Diagnosis: Sigmoid Adenocarcinoma.",
    "mri_findings": "Baseline rectal MRI 10/01/2025: mrT3c, mrN2...",
    "restaging_mri_findings": "Restaging MRI 20/03/2025 post-SCPRT: mrT2...",
    "ct_findings": "CT CAP 12/01/2025: No liver or lung metastases...",
    "pathology": "Biopsy: moderately differentiated adenocarcinoma...",
    "mdt_outcome": "MDT 15/01/2025. Outcome: For SCPRT then...",
    "clinical_history": "Patient presented with change in bowel habit..."
  },
  "is_restaging_mri": true,
  "token_map": {},
  "metadata": {
    "table_index": 0,
    "source_file": "hackathon-mdt-outcome-proformas.docx",
    "extraction_timestamp": "2026-03-19T09:00:00Z"
  }
}
```

Note: `token_map` starts empty here. It gets populated by Data Minimisation step (next).  
Note: `is_restaging_mri` is set programmatically: `true` if `restaging_mri_findings` is non-empty, `false` otherwise.

---

### Data Minimisation

**What:** Remove all patient-identifiable information from segmented text before sending to external API.

**How:**
1. Read `case_NNN_raw.json`
2. For each string value in `raw_segments`, apply substitution:
   - NHS numbers (`\d{3}[\s\-]?\d{3}[\s\-]?\d{4}`) → `[NHS_NUMBER]`
   - Patient name (word boundary regex, case-insensitive) → `[PATIENT_NAME]`
   - DOB (exact match) → `[DOB]`
   - Hospital number (exact match) → `[HOSP_NUMBER]`
3. **Critical:** Use word-boundary regex for name to prevent corruption of clinical terms:
   ```python
   re.sub(r'\b' + re.escape(name) + r'\b', '[PATIENT_NAME]', text, flags=re.IGNORECASE)
   ```
   This prevents "Ann" matching in "management" or "Ann" in "significant".
4. Record all substitutions in `token_map`
5. Output: `case_NNN_anonymised.json` (sent to Eivan) + update `token_map` in `case_NNN_raw.json` (kept locally)

**Output Schema: `case_NNN_anonymised.json`**
```json
{
  "case_index": 0,
  "raw_segments": {
    "demographics": "[NHS_NUMBER]. [DOB]. Consultant: [PATIENT_NAME].",
    "diagnosis": "Diagnosis: Sigmoid Adenocarcinoma.",
    "mri_findings": "Baseline rectal MRI 10/01/2025: mrT3c, mrN2...",
    "restaging_mri_findings": "Restaging MRI 20/03/2025 post-SCPRT: mrT2...",
    "ct_findings": "CT CAP 12/01/2025: No liver or lung metastases...",
    "pathology": "Biopsy: moderately differentiated adenocarcinoma...",
    "mdt_outcome": "MDT 15/01/2025. Outcome: For SCPRT then...",
    "clinical_history": "Patient presented with change in bowel habit..."
  },
  "is_restaging_mri": true,
  "metadata": {
    "table_index": 0,
    "source_file": "hackathon-mdt-outcome-proformas.docx",
    "extraction_timestamp": "2026-03-19T09:00:00Z"
  }
}
```

Note: `patient_identifiers` block is **removed entirely**. Only `raw_segments`, `is_restaging_mri`, and `metadata` are included.

**Token Map Schema** (stored in `case_NNN_raw.json`):
```json
"token_map": {
  "[NHS_NUMBER]": "999 000 0001",
  "[PATIENT_NAME]": "Alice B",
  "[DOB]": "01/01/1965",
  "[HOSP_NUMBER]": "H123456"
}
```

---

### Your Deliverables

1. **Python module: `stage1_segmenter.py`**
   - Function: `segment_document(docx_path: str, output_dir: str) -> None`
   - Reads Word document, produces `case_NNN_raw.json` files (one per table)
   - Handles validation, flags sparse cases as `case_NNN_flagged.json`

2. **Python module: `data_minimisation.py`**
   - Function: `anonymise_case(raw_json_path: str, anonymised_output_path: str) -> None`
   - Reads `case_NNN_raw.json`, produces `case_NNN_anonymised.json`
   - Populates `token_map` in original `case_NNN_raw.json`
   - Ensures word-boundary name matching to prevent clinical term corruption

3. **Integration function: `stage1_and_anonymise_pipeline(docx_path: str, output_dir: str) -> None`**
   - Orchestrates segmenter + data minimisation in sequence
   - Produces both raw JSON (with token map) and anonymised JSON

4. **Test file: `test_stage1.py`**
   - Unit tests for sentence splitting
   - Unit tests for classification logic (all 8 buckets)
   - Unit tests for PII extraction (NHS, DOB, name patterns)
   - Integration test on sample docx file
   - Validation test (ensure invalid cases are flagged)

---

## Track B: Eivan — Stages 2 & 3

### Stage 2: LLM Structurer (Gemini API)

**What:** Extract structured clinical fields from anonymised text using Gemini API with hallucination prevention.

**How:**
1. Read `case_NNN_anonymised.json`
2. Call Gemini API with:
   - Mode: JSON mode (structured output schema enforced)
   - Temperature: 0 (deterministic)
   - Max tokens: 8192
   - System prompt: Forces provenance triad, forbids inference
   - Input: `raw_segments` as labelled JSON string in user message
3. Validate response in 3 passes:
   - **Pass 1:** JSON validity (strip markdown fences if needed)
   - **Pass 2:** Schema compliance (all fields have value/source_text/confidence keys)
   - **Pass 3:** Hallucination detection (fuzzy match source_text against input segments)
4. Detect clinical ambiguities programmatically
5. Output: `case_NNN_structured.json`
6. Handle retries (3 attempts: 2s, 4s, 8s backoff) on timeout/connection error
7. Log all API calls (timestamp, case_index, HTTP status, response time ms, field counts)

**Provenance Triad (enforced by prompt):**
Every extracted field must return exactly:
```json
"field_name": {
  "value": "extracted value or null",
  "source_text": "exact verbatim sentence from input or null",
  "confidence": "high" | "low" | "not_found"
}
```

**Extraction Rules (encoded in prompt):**
- `source_text` must be **verbatim** from input — never paraphrased, reconstructed, or merged
- If field absent: `value: null`, `source_text: null`, `confidence: "not_found"`
- If present but ambiguous/partial: `confidence: "low"` (never infer)
- MRI fields ONLY from `mri_findings` segment
- Restaging fields ONLY from `restaging_mri_findings` segment
- CT fields ONLY from `ct_findings` segment
- **Critical:** Do NOT convert qualitative descriptions (e.g. "good response") to numbered grades (e.g. mrTRG2) — patient safety rule

**Hallucination Detection (Pass 3):**
For every `source_text` value:
```python
def source_text_is_valid(source_text: str, original_segments: dict) -> bool:
    haystack = " ".join(str(v) for v in original_segments.values()).lower().strip()
    needle = source_text.lower().strip()
    
    # Exact match first
    if needle in haystack:
        return True
    
    # Fuzzy fallback: 85%+ token overlap
    needle_tokens = set(needle.split())
    haystack_tokens = set(haystack.split())
    if len(needle_tokens) == 0:
        return False
    overlap = len(needle_tokens & haystack_tokens) / len(needle_tokens)
    return overlap >= 0.85
```

If validation fails: force `confidence: "low"` and add field to hallucination flag list.

**Clinical Ambiguity Detection:**
Detect programmatically after response:
1. Both baseline T stage and restaging T stage present → flag "Both baseline and restaging T stage present — verify correct field assignment"
2. CT M0 but clinical notes mention metastases → flag "CT M0 contradicts clinical notes suggesting metastatic disease", add `contradiction_note` to field

**Safety Flags (8 trigger rules):**
After response, check:
1. Any MRI staging field (`mrT_stage`, `mrN_stage`, `mrCRM_status`, `mrEMVI_status`) has `confidence == "low"` → "Low confidence MRI staging"
2. `treatment_intent` is `null` or `"not_stated"` → "MDT treatment intent missing"
3. T stage found BUT M stage absent AND CT report present → "T stage found but M stage absent despite CT report present"
4. Restaging MRI present BUT no baseline MRI staging → "Restaging MRI present but no baseline MRI staging found"
5. Any `source_text` failed fuzzy validation → "Hallucination check failed — verify source text"
6. `value` is not null BUT `source_text` is null → "Value present with no source text — unverifiable"
7. Clinical ambiguity detected (items 1–2 above) → specific reason
8. Stage 1 validation failed for case → "Stage 1 validation failed — check source document"

Set `verification_required: true` if any rule triggers. Concatenate reasons as pipe-separated string.

**Rate Limiting:**
- Add `time.sleep(1.5)` between API calls (gives ~40 calls/min, within free tier)
- Use `tqdm` progress bar for demo visibility
- Log elapsed time per case to console

**API Call Logging:**
To `logs/api_responses.log`:
```
[2026-03-19 14:30:45] case_index=0 | HTTP 200 | 425ms | fields_extracted=32 | fields_flagged=2
```

No patient data in logs.

**Output Schema: `case_NNN_structured.json`**
```json
{
  "case_index": 0,
  "mri_staging": {
    "mrT_stage": {
      "value": "mrT3c",
      "source_text": "Baseline rectal MRI: mrT3c",
      "confidence": "high"
    },
    "mrN_stage": {
      "value": "mrN2",
      "source_text": "Baseline rectal MRI: mrT3c, mrN2",
      "confidence": "high"
    },
    "mrCRM_status": {
      "value": "threatened",
      "source_text": "CRM threatened at 0.8mm",
      "confidence": "high"
    },
    "mrCRM_distance_mm": {
      "value": "0.8",
      "source_text": "CRM threatened at 0.8mm",
      "confidence": "high"
    },
    "mrEMVI_status": {
      "value": "positive",
      "source_text": "EMVI positive",
      "confidence": "high"
    },
    "mrMRF_status": {
      "value": "threatened",
      "source_text": "CRM threatened",
      "confidence": "low"
    },
    "tumour_height_cm": {
      "value": "7.0",
      "source_text": "Tumour at 7cm from anal verge",
      "confidence": "high"
    },
    "mri_date": {
      "value": "10/01/2025",
      "source_text": "Baseline rectal MRI 10/01/2025",
      "confidence": "high"
    }
  },
  "restaging_mri": {
    "restaging_mrT_stage": {
      "value": "mrT2",
      "source_text": "Restaging MRI 20/03/2025 post-SCPRT: mrT2",
      "confidence": "high"
    },
    "restaging_mrN_stage": {
      "value": "mrN0",
      "source_text": "Restaging MRI 20/03/2025: mrT2, mrN0",
      "confidence": "high"
    },
    "restaging_mrCRM_status": {
      "value": "clear",
      "source_text": "CRM clear",
      "confidence": "high"
    },
    "restaging_mrEMVI_status": {
      "value": "negative",
      "source_text": "EMVI negative",
      "confidence": "high"
    },
    "mrTRG": {
      "value": null,
      "source_text": null,
      "confidence": "not_found"
    },
    "restaging_mri_date": {
      "value": "20/03/2025",
      "source_text": "Restaging MRI 20/03/2025",
      "confidence": "high"
    }
  },
  "ct_staging": {
    "ct_M_stage": {
      "value": "M0",
      "source_text": "CT CAP: No liver or lung metastases. M0.",
      "confidence": "high"
    },
    "ct_liver_mets": {
      "value": "absent",
      "source_text": "No liver metastases",
      "confidence": "high"
    },
    "ct_lung_mets": {
      "value": "absent",
      "source_text": "No lung metastases",
      "confidence": "high"
    },
    "ct_peritoneal_disease": {
      "value": "absent",
      "source_text": "No peritoneal disease",
      "confidence": "high"
    },
    "ct_date": {
      "value": "12/01/2025",
      "source_text": "CT CAP 12/01/2025",
      "confidence": "high"
    }
  },
  "pathology": {
    "histology_type": {
      "value": "adenocarcinoma",
      "source_text": "moderately differentiated adenocarcinoma",
      "confidence": "high"
    },
    "mmr_status": {
      "value": "proficient",
      "source_text": "MMR: Proficient (pMMR)",
      "confidence": "high"
    },
    "kras_status": {
      "value": "wild-type",
      "source_text": "KRAS wild-type",
      "confidence": "high"
    }
  },
  "mdt_decision": {
    "treatment_intent": {
      "value": "curative",
      "source_text": "Curative intent",
      "confidence": "high"
    },
    "primary_treatment_modality": {
      "value": "SCPRT then TME",
      "source_text": "For SCPRT then restaging MRI then TME surgery",
      "confidence": "high"
    }
  },
  "verification_required": false,
  "verification_reasons": null,
  "metadata": {
    "case_index": 0,
    "api_response_time_ms": 425,
    "fields_extracted": 32,
    "fields_flagged": 0
  }
}
```

---

### Stage 3: Excel Assembler

**What:** Produce a clean, navigable 3-sheet Excel workbook with clinical data, audit trail, and safety flags.

**How:**
1. Read `case_NNN_raw.json` to recover `patient_identifiers` and `token_map` (never transmitted to API)
2. Read `case_NNN_structured.json` (from Stage 2)
3. For every `source_text` value in structured JSON, reverse-substitute tokens:
   ```python
   for token, original_value in token_map.items():
       source_text = source_text.replace(token, original_value)
   ```
4. Assemble 3-sheet workbook

**Sheet 1: "MDT Data"**
- One row per MDT discussion (if patient appears on two dates, two rows)
- Sort by `mdt_date` ascending (parse DD/MM/YYYY)
- Column headers from mapping (see below)
- **Header colour-banding by field group:**
  - Light grey (`#F2F2F2`): patient identifiers
  - Light blue (`#DDEEFF`): baseline MRI staging
  - Light teal (`#DDFFEE`): restaging MRI
  - Light yellow (`#FFFADD`): CT staging
  - Light green (`#EEFFDD`): pathology and biomarkers
  - Light orange (`#FFE8CC`): MDT decision
  - Light red (`#FFE0E0`): verification flags
- **Data row highlighting:** amber (`#FFC000`) if `verification_required == true`, else white
- `Human Verification Required` column: `YES` if true, `NO` if false
- Cell A1 comment: "Amber rows require manual review against the Source Evidence sheet before this data is used clinically."
- Freeze panes: `ws.freeze_panes = ws['C2']` (freezes row 1 and columns A–B)
- Column widths: auto-fit, capped at 40 chars

**Sheet 2: "Source Evidence"**
Columns (in order): `Patient ID` | `Patient Name` | `MDT Date` | `Field Name` | `Clinical Label` | `Extracted Value` | `Source Text` | `Confidence`

- One row per extracted field per case
- `Source Text` contains reverse-substituted text (real identifiers, not `[TOKENS]`)
- `Confidence` cell background:
  - Green (`#CCFFCC`) for "high"
  - Amber (`#FFC000`) for "low"
  - Grey (`#DDDDDD`) for "not_found"
- Only include rows where `value` is not null (omit `not_found` rows to keep sheet navigable)

**Sheet 3 (Optional): "Flags & Notes"**
- One row per flagged case
- Columns: `Case Index` | `Patient ID` | `MDT Date` | `Verification Reasons` | `Notes`

**Column Name Mapping** (JSON field → Excel header):
```
nhs_number → NHS Number
patient_name → Patient Name
dob → Date of Birth
hospital_number → Hospital Number
consultant → Consultant
mdt_date → MDT Date
mrT_stage → Baseline MRI: mrT Stage
mrN_stage → Baseline MRI: mrN Stage
mrCRM_status → Baseline MRI: CRM Status
mrCRM_distance_mm → Baseline MRI: CRM Distance (mm)
mrEMVI_status → Baseline MRI: EMVI Status
mrMRF_status → Baseline MRI: MRF Status
tumour_height_cm → Tumour Height from Anal Verge (cm)
mri_date → Baseline MRI Date
is_restaging_mri → Restaging MRI Present
restaging_mrT_stage → Restaging MRI: mrT Stage
restaging_mrN_stage → Restaging MRI: mrN Stage
restaging_mrCRM_status → Restaging MRI: CRM Status
restaging_mrEMVI_status → Restaging MRI: EMVI Status
mrTRG → Restaging MRI: Tumour Regression Grade (mrTRG)
restaging_mri_date → Restaging MRI Date
ct_M_stage → CT: M Stage
ct_liver_mets → CT: Liver Metastases
ct_lung_mets → CT: Lung Metastases
ct_peritoneal_disease → CT: Peritoneal Disease
ct_date → CT Date
histology_type → Histology Type
histology_grade → Histology Grade
mmr_status → MMR Status
msi_status → MSI Status
kras_status → KRAS Status
nras_status → NRAS Status
braf_status → BRAF Status
her2_status → HER2 Status
pathology_date → Pathology Date
treatment_intent → MDT Treatment Intent
primary_treatment_modality → Primary Treatment Modality
planned_surgery → Planned Surgery
neoadjuvant_treatment → Neoadjuvant Treatment Planned
mdt_outcome_verbatim → MDT Outcome (Verbatim)
verification_required → Human Verification Required
verification_reasons → Verification Reasons
```

**Output file:** `MDT_Extraction_YYYYMMDD_HHMMSS.xlsx`

---

### Eivan's Deliverables

1. **Python module: `stage2_structurer.py`**
   - Function: `structure_case(anonymised_json_path: str, structured_output_path: str, api_key: str) -> None`
   - Calls Gemini API with anonymised JSON
   - Implements all 3 validation passes + hallucination detection
   - Handles retries, logs API calls
   - Produces `case_NNN_structured.json`

2. **Python module: `safety_flags.py`**
   - Function: `apply_safety_flags(structured_json: dict) -> dict`
   - Checks all 8 trigger rules
   - Sets `verification_required` and `verification_reasons`
   - Detects clinical ambiguities

3. **Python module: `stage3_assembler.py`**
   - Function: `assemble_excel(raw_json_dir: str, structured_json_dir: str, output_file: str) -> None`
   - Reverse-substitutes PII tokens in source text
   - Builds 3-sheet Excel workbook with all styling
   - Produces final `MDT_Extraction_YYYYMMDD_HHMMSS.xlsx`

4. **Integration function: `stage2_and_3_pipeline(anonymised_json_dir: str, raw_json_dir: str, output_dir: str, api_key: str) -> None`**
   - Orchestrates Stage 2 structuring + safety flags + Stage 3 assembly

5. **Test file: `test_stage2_and_3.py`**
   - Unit tests for provenance triad parsing
   - Unit tests for hallucination detection (fuzzy matching)
   - Unit tests for safety flag logic (all 8 triggers)
   - Unit tests for Excel building (styling, cell formatting)
   - Integration test on sample anonymised JSON

---

## Integration Points

### JSON Schemas (Agree on these formats)

**Between You → Eivan:**
1. `case_NNN_raw.json` (from Stage 1) — see schema above
2. `case_NNN_anonymised.json` (from Data Minimisation) — see schema above
3. `case_NNN_flagged.json` (sparse/invalid cases) — minimal schema:
   ```json
   {
     "case_index": 0,
     "stage1_validation_failed": true,
     "reason": "mri_findings and ct_findings both empty"
   }
   ```

**Between Eivan → You (feedback loop):**
- `case_NNN_structured.json` (from Stage 2) — see schema above
- If errors in structure, may need to revisit Stage 1 segmentation

### Directory Structure (Set up git repo)

```
clinical-ai-solution/
├── data/
│   └── hackathon-mdt-outcome-proformas.docx  (input)
├── output/
│   ├── json/
│   │   ├── case_000_raw.json
│   │   ├── case_000_anonymised.json
│   │   ├── case_000_structured.json
│   │   └── ...
│   └── excel/
│       └── MDT_Extraction_YYYYMMDD_HHMMSS.xlsx
├── logs/
│   └── api_responses.log
├── src/
│   ├── stage1_segmenter.py
│   ├── data_minimisation.py
│   ├── stage2_structurer.py
│   ├── safety_flags.py
│   ├── stage3_assembler.py
│   ├── main.py  (orchestrates all stages)
│   ├── test_stage1.py
│   └── test_stage2_and_3.py
├── docs/
│   ├── TSPP_Technical_Specification_v4.md  (reference)
│   ├── field_reference_v2.md  (reference)
│   └── PROJECT_DIVISION.md  (this file)
└── README.md
```

---

## Collaboration Checklist

Before you start coding:
- [ ] Agree on JSON schemas for intermediate files
- [ ] Set up shared git repo with directory structure
- [ ] You grab `TSPP_Technical_Specification_v4.md` and `field_reference_v2.md` as reference docs
- [ ] Eivan designs Stage 2 system prompt (will iterate)

During development:
- [ ] You share sample `case_NNN_raw.json` and `case_NNN_anonymised.json` early
- [ ] Eivan tests Stage 2 prompt on sample data, gives feedback on segmentation if needed
- [ ] Both run unit tests continuously

Final integration:
- [ ] End-to-end test on full `hackathon-mdt-outcome-proformas.docx`
- [ ] Validate Excel output against spec
- [ ] Demo-ready by end of project sprint

---

## Parallel Work Timeline

**Week 1:**
- You: Build Stage 1 parser, test on sample docx
- Eivan: Design Stage 2 system prompt, set up Gemini API skeleton, design safety flag triggers

**Week 2:**
- You: Build Data Minimisation (anonymisation + token map)
- Eivan: Implement Stage 2 structurer, post-response validation, hallucination detection

**Week 3:**
- You: Final testing of Stage 1 + Data Minimisation
- Eivan: Build Stage 3 (Excel assembly + styling)

**Week 3 (final days):**
- Both: Integration testing, fix issues, prepare demo

---

## Key Reference Documents

In `/Users/efi/Music/Kris/Clinical/Clinical-AI-Hackathon/`:
- `TSPP_Technical_Specification_v4.md` — Full engineering spec (you focus on sections 1–3, Eivan on 4–6)
- `field_reference_v2.md` — All 40+ extractable clinical fields (Eivan will use extensively)
- Sample data: `data/hackathon-mdt-outcome-proformas.docx`

---

## Summary

| Aspect | You | Eivan |
| --- | --- | --- |
| **Responsibility** | Parsing & Privacy | LLM & Output |
| **Stages** | 1 + Data Minimisation | 2 + 3 |
| **Tech Stack** | python-docx, regex | Gemini API, openpyxl |
| **Input** | `.docx` file | Anonymised JSON |
| **Output** | Raw JSON + Anonymised JSON | Structured JSON + Excel |
| **Complexity** | Medium | High (hallucination prevention critical) |
| **Dependencies** | None (first) | Depends on your output |

**Success metrics:**
- Excel has all cases with values linked to source sentences
- No hallucinated extraction passes validation
- Flagged rows correctly identify ambiguous/risky cases
- Patient identifiers never reach Gemini API
- All tests pass
- Demo runs smoothly on sample data

---

**Created:** March 19, 2026  
**Status:** Ready for development
