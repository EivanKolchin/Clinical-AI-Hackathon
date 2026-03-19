# Stage 1 & Data Minimisation: Quick Start

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run unit tests
cd src
python test_stage1.py
```

## Usage

### Basic Usage

```bash
cd src
python main.py ../data/hackathon-mdt-outcome-proformas.docx
```

This will:
1. Read the Word document
2. Extract tables as MDT cases
3. Segment and classify text into 8 clinical buckets
4. Validate each case
5. Anonymise PII (NHS numbers, names, DOB, hospital numbers)
6. Output JSON files to `output/json/`

### Output Files

- `case_NNN.json` — Raw segmented case (with patient identifiers, token map)
- `case_NNN_anonymised.json` — Anonymised version (safe for API transmission)
- `case_NNN_flagged.json` — Cases that failed Stage 1 validation

### Example Raw JSON Structure

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
    "demographics": "NHS Number: 9990001...",
    "diagnosis": "Diagnosis: Sigmoid Adenocarcinoma...",
    "mri_findings": "Baseline rectal MRI 10/01/2025: mrT3c...",
    "..."
  },
  "is_restaging_mri": true,
  "token_map": {
    "[NHS_NUMBER]": "999 000 0001",
    "[PATIENT_NAME]": "Alice B",
    "[DOB]": "01/01/1965",
    "[HOSP_NUMBER]": "H123456"
  },
  "metadata": {
    "table_index": 0,
    "source_file": "hackathon-mdt-outcome-proformas.docx",
    "extraction_timestamp": "2026-03-19T09:00:00Z",
    "stage1_validation_failed": false,
    "validation_reason": null
  }
}
```

### Example Anonymised JSON Structure

```json
{
  "case_index": 0,
  "raw_segments": {
    "demographics": "[NHS_NUMBER]. [DOB]. Consultant: [PATIENT_NAME].",
    "diagnosis": "Diagnosis: Sigmoid Adenocarcinoma...",
    "..."
  },
  "is_restaging_mri": true,
  "metadata": {
    "table_index": 0,
    "source_file": "hackathon-mdt-outcome-proformas.docx",
    "extraction_timestamp": "2026-03-19T09:00:00Z"
  }
}
```

Note: `patient_identifiers` block is removed entirely. Ready for Stage 2 API transmission.

## Classification Buckets (Priority Order)

1. **restaging_mri_findings** — MRI + (restaging, post-treatment, post-CRT, response assessment, etc.)
2. **mri_findings** — MRI baseline imaging only
3. **ct_findings** — CT/computed tomography (word boundary to avoid false matches)
4. **pathology** — Biopsy results, MMR/MSI status, biomarkers
5. **mdt_outcome** — Treatment decisions, MDT outcome, planned surgery
6. **demographics** — Patient identifiers, NHS number, DOB, consultant
7. **diagnosis** — Clinical diagnosis, cancer type, staging
8. **clinical_history** — Catch-all for other content

## Stage 1 Validation Rules

A case is flagged if ANY of these are true:
- No `mri_findings` AND no `ct_findings` (missing imaging)
- No `mdt_outcome` (missing decision)
- < 4 non-empty segments (sparse/malformed case)

Flagged cases are output to `case_NNN_flagged.json` and skipped during anonymisation. They require manual review.

## Data Minimisation Rules

PII is stripped using regex patterns:
- NHS numbers: `\d{3}[\s\-]?\d{3}[\s\-]?\d{4}` → `[NHS_NUMBER]`
- Patient names: Word-boundary regex to prevent corruption of clinical terms
- Date of birth: Exact match → `[DOB]`
- Hospital number: Exact match → `[HOSP_NUMBER]`

**Word boundary matching is critical:** Prevents "Ann" from matching inside "management".

Token map is preserved in `case_NNN.json` for Stage 3 reverse-substitution.

## Troubleshooting

**"No imaging segment found"**
- Case failed Stage 1 validation. Check the source Word document structure.
- Could mean mri_findings AND ct_findings are both empty.

**"MDT outcome segment is empty"**
- Critical field missing. Case cannot be processed.

**"Only N non-empty segments, need ≥4"**
- Document appears malformed or has sparse content.
- May need manual inspection of the source Word document.

**Unicode/encoding errors**
- Ensure Word document is saved as `.docx` (not `.doc`)

## Integration with Stage 2

Once you have anonymised JSON files ready:
1. Pass `output/json/*_anonymised.json` to Eivan's Stage 2 (LLM Structurer)
2. Also keep `case_NNN.json` locally (contains token map for Stage 3)
3. Eivan will produce `case_NNN_structured.json`
4. Both files go to Stage 3 for Excel assembly

---

**Questions?** See PROJECT_DIVISION.md for detailed specifications.
