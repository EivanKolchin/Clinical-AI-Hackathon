# Field Reference: Stage 2 Extraction Schema
**Document type:** Clinical field definitions for Stage 2 LLM prompt construction  
**Used by:** Prompt 3 in the TSPP implementation sequence  
**Not for:** Program logic or error handling — see TSPP_Technical_Specification_v4.md

Every field in this document must be extracted using the provenance triad:
```json
"field_name": {
  "value": "...",
  "source_text": "exact sentence from input",
  "confidence": "high" | "low" | "not_found"
}
```

**Three rules that apply to every field without exception:**
1. `source_text` must be a verbatim copy of a sentence from the input.
   Do not paraphrase, reconstruct, merge, or summarise.
2. If a field is absent: `value: null`, `source_text: null`,
   `confidence: "not_found"`. Never infer or guess.
3. If present but ambiguous, incomplete, or requires any inference:
   `confidence: "low"`. Never mark an inferred value as `"high"`.

---

## Group A — MRI Staging (highest priority)

Baseline fields are extracted **only** from the `mri_findings` input segment.
Restaging fields are extracted **only** from the `restaging_mri_findings` input
segment. These two groups must never be conflated. A value found in
`restaging_mri_findings` must never populate a baseline field, and vice versa.

### A1 — Baseline MRI fields

Source segment: `mri_findings` only.

| Field name | Description | Accepted values |
| :--- | :--- | :--- |
| `mrT_stage` | T stage from baseline rectal MRI | `mrT0`, `mrT1`, `mrT2`, `mrT3a`, `mrT3b`, `mrT3c`, `mrT3d`, `mrT4a`, `mrT4b` |
| `mrN_stage` | Nodal stage from baseline rectal MRI | `mrN0`, `mrN1`, `mrN2` |
| `mrCRM_status` | Circumferential resection margin status | `clear`, `threatened`, `involved` |
| `mrCRM_distance_mm` | Distance from tumour to mesorectal fascia | Numeric string in mm, e.g. `"0.8"` |
| `mrEMVI_status` | Extramural vascular invasion on MRI | `positive`, `negative`, `indeterminate` |
| `mrMRF_status` | Mesorectal fascia involvement | `clear`, `threatened`, `involved` |
| `tumour_height_cm` | Tumour height from anal verge | Numeric string in cm, e.g. `"7.0"` |
| `mri_date` | Date of baseline rectal MRI | DD/MM/YYYY |

**CRM status derivation rule:**
CRM status can be derived mathematically from a stated distance — this is not
clinical inference, it is arithmetic:
- Distance stated as ≤1mm → `mrCRM_status: "threatened"`
- Distance stated as 0mm or tumour touching/breaching fascia → `mrCRM_status: "involved"`
- Distance stated as >1mm → `mrCRM_status: "clear"`

If the distance is given but no status is stated in the text, derive the status
using these rules and set `confidence: "high"` (the rule is deterministic).
Record the distance in `mrCRM_distance_mm` and the derived status in `mrCRM_status`.
Both fields use the same `source_text`.

If the status is stated in the text (e.g. "CRM threatened"), extract it directly
at `confidence: "high"`. Do not override a stated status with a derived one.

**mrT3 sub-classification rule:**
mrT3 is sub-classified by depth of extramural spread beyond the muscularis propria:
- mrT3a: <1mm
- mrT3b: 1–5mm  
- mrT3c: 5–15mm
- mrT3d: >15mm

If the sub-classification is explicitly stated (e.g. "mrT3c"), extract it directly
at `confidence: "high"`. If only "T3" or "mrT3" is documented without a
sub-class letter, record `"mrT3"` and set `confidence: "low"` — the sub-class
cannot be inferred.

**mrT staging notation:** The correct prefix is `mr` (lowercase). If the source
text uses "T3c" without the `mr` prefix, extract as `"mrT3c"` and set
`confidence: "high"` — the `mr` prefix is a notation convention, not new
information.

---

### A2 — Restaging MRI fields

Source segment: `restaging_mri_findings` only.
Only populated when `is_restaging_mri` is `true` (set programmatically by Stage 1).

| Field name | Description | Accepted values |
| :--- | :--- | :--- |
| `restaging_mrT_stage` | T stage on restaging scan | Same as `mrT_stage` |
| `restaging_mrN_stage` | Nodal stage on restaging scan | `mrN0`, `mrN1`, `mrN2` |
| `restaging_mrCRM_status` | CRM status on restaging scan | `clear`, `threatened`, `involved` |
| `restaging_mrEMVI_status` | EMVI status on restaging scan | `positive`, `negative`, `indeterminate` |
| `mrTRG` | MRI tumour regression grade | `mrTRG1`, `mrTRG2`, `mrTRG3`, `mrTRG4`, `mrTRG5` |
| `restaging_mri_date` | Date of restaging MRI | DD/MM/YYYY |

**mrTRG extraction rule — critical:**
Extract mrTRG **only if a numbered grade is explicitly stated** in the source text
(e.g. "mrTRG2", "TRG 3", "tumour regression grade 1").

If the source text describes the response qualitatively without a numbered grade
(e.g. "good response", "complete response", "minimal residual tumour", "poor
response"), set `value: null`, `source_text: null`, `confidence: "not_found"`.

**Do not convert qualitative descriptions to numbered grades.** This is a
patient-safety requirement. An inferred grade could influence a treatment decision
and there is no safe fallback. The human verification flag will alert the
clinician that mrTRG requires manual review.

The mrTRG scale for reference (do not use for inference — for recognition only):
mrTRG1 = complete response, mrTRG2 = near-complete response, mrTRG3 = partial
response, mrTRG4 = minimal response, mrTRG5 = no response.

---

## Group B — CT Staging

**Scope of CT in rectal cancer:** CT is used for M-staging (detecting distant
metastases) only. CT does not provide T staging or N staging for rectal tumours —
those are determined by MRI. There are no T or N fields in this group.
Do not create T or N fields from CT text under any circumstances.

Source segment: `ct_findings` only.

| Field name | Description | Accepted values |
| :--- | :--- | :--- |
| `ct_M_stage` | Overall metastatic stage from CT | `M0`, `M1a`, `M1b`, `M1c` |
| `ct_liver_mets` | Liver metastases on CT | `present`, `absent`, `not_assessed` |
| `ct_lung_mets` | Lung metastases on CT | `present`, `absent`, `not_assessed` |
| `ct_peritoneal_disease` | Peritoneal disease on CT | `present`, `absent`, `not_assessed` |
| `ct_date` | Date of CT scan | DD/MM/YYYY |

**M-stage classification rule:**
- M0: no distant metastases
- M1a: metastases confined to one non-peritoneal organ or site
- M1b: metastases in two or more non-peritoneal organs or sites
- M1c: peritoneal metastases, with or without organ involvement

If CT reports metastatic disease but does not specify number of sites or organs
(e.g. "metastatic disease present"), extract `M1` and set `confidence: "low"`.

If `ct_findings` segment is empty, set all CT fields to `not_found`. Do not
attempt to derive M stage from MRI or clinical history text.

---

## Group C — Pathology and Biomarkers

Source segment: `pathology` only. If pathology results appear across multiple
sentences in the segment, use the most recent result. If dates cannot be
determined from the text, use the result that appears latest in the document.

| Field name | Description | Accepted values |
| :--- | :--- | :--- |
| `histology_type` | Tumour histological type | Free text — extract verbatim (e.g. `"moderately differentiated adenocarcinoma"`) |
| `histology_grade` | Differentiation grade | `well differentiated`, `moderately differentiated`, `poorly differentiated`, `undifferentiated` |
| `mmr_status` | Mismatch repair protein status | `Deficient (dMMR)`, `Proficient (pMMR)` |
| `msi_status` | Microsatellite instability status | `MSI-H`, `MSS`, `MSI-L`, `not_tested` |
| `kras_status` | KRAS mutation status | `mutant`, `wild-type`, `not_tested` |
| `nras_status` | NRAS mutation status | `mutant`, `wild-type`, `not_tested` |
| `braf_status` | BRAF mutation status | `mutant (V600E)`, `wild-type`, `not_tested` |
| `her2_status` | HER2 amplification status | `positive`, `negative`, `not_tested` |
| `pathology_date` | Date of pathology report | DD/MM/YYYY |

**MMR / MSI rule:**
dMMR and MSI-H are clinically equivalent findings from different testing methods.
If only one is documented, record it and set the other to `not_found`.
Do not infer one from the other — they must be independently stated.

**Variant notation for MMR:** The source text may use `"MMR deficient"`,
`"MMR-D"`, `"dMMR"`, or `"MMR proficient"`, `"MMR-P"`, `"pMMR"`. Normalise all
deficient variants to `"Deficient (dMMR)"` and all proficient variants to
`"Proficient (pMMR)"`. Set `confidence: "high"` for any of these recognised
notations — they are unambiguous.

---

## Group D — MDT Decision

Source segment: `mdt_outcome` only.

| Field name | Description | Accepted values |
| :--- | :--- | :--- |
| `treatment_intent` | Overall treatment intent | `curative`, `palliative`, `not_stated` |
| `primary_treatment_modality` | First treatment in the plan | `surgery_first`, `SCPRT`, `long_course_CRT`, `chemotherapy`, `watch_and_wait`, `surveillance`, `palliative_chemotherapy`, `best_supportive_care` |
| `planned_surgery` | Planned surgical procedure | `TME`, `PME`, `Hartmanns`, `APE`, `anterior_resection`, `local_excision`, `defunctioning_stoma_only`, `not_stated` |
| `neoadjuvant_treatment` | Neoadjuvant therapy planned before surgery | `yes`, `no`, `not_stated` |
| `mdt_outcome_verbatim` | The exact outcome sentence as written | Verbatim string |

**Important:** `mdt_date` is **not** extracted by the LLM. It is extracted
programmatically by Stage 1 and stored in `patient_identifiers.mdt_date`.
Do not include `mdt_date` in the Stage 2 API prompt or output schema.

**Treatment modality notes:**
SCPRT = short-course pre-operative radiotherapy (5×5Gy over 1 week).
Long-course CRT = chemoradiotherapy (45–50Gy over 5–6 weeks with capecitabine).
If an abbreviation is used without expansion and is unambiguous (e.g. "SCPRT",
"TME"), set `confidence: "high"`. If the abbreviation is ambiguous or unclear,
set `confidence: "low"`.

**`neoadjuvant_treatment` derivation rule:**
If `primary_treatment_modality` is `SCPRT`, `long_course_CRT`, or
`chemotherapy` and the plan involves surgery afterwards, set
`neoadjuvant_treatment: "yes"`. If surgery is the first planned treatment with
nothing before it, set `neoadjuvant_treatment: "no"`. This is a logical reading
of the outcome sentence, not clinical inference — `confidence: "high"` applies.

**`mdt_outcome_verbatim`:** Extract the complete outcome sentence exactly as
written. The `source_text` for this field is identical to `value`. This is
correct and expected behaviour for a verbatim field.

---

## Group E — Patient and MDT Identifiers

**These fields are NOT extracted by the LLM.** They come from Stage 1 and are
re-joined at Stage 3. Do not include them in the Stage 2 prompt or expect them
in the Stage 2 output.

| Field | Source |
| :--- | :--- |
| `nhs_number` | `patient_identifiers.nhs_number` (Stage 1) |
| `patient_name` | `patient_identifiers.patient_name` (Stage 1) |
| `dob` | `patient_identifiers.dob` (Stage 1) |
| `hospital_number` | `patient_identifiers.hospital_number` (Stage 1) |
| `consultant` | `patient_identifiers.consultant` (Stage 1) |
| `mdt_date` | `patient_identifiers.mdt_date` (Stage 1) |

---

## Extraction Rules for Stage 2 System Prompt

Include these rules verbatim in the system prompt sent to the Gemini API:

1. You are a data extraction tool. Return only valid JSON. No preamble,
   explanation, or markdown fences.
2. Every field must include exactly three keys: `value`, `source_text`,
   `confidence`.
3. `source_text` must be a verbatim copy of a sentence from the input text.
   Do not paraphrase, reconstruct, merge sentences, or summarise.
4. If a field is not present in the source text: `value: null`,
   `source_text: null`, `confidence: "not_found"`.
5. If a field is present but ambiguous, partially stated, or abbreviated
   unclearly: `confidence: "low"`.
6. Never set `confidence: "high"` on a value that required inference beyond
   reading what is written.
7. Baseline MRI fields must only be populated from the `mri_findings` segment.
   Restaging MRI fields must only be populated from the `restaging_mri_findings`
   segment. Never cross-populate.
8. CT fields must only be populated from the `ct_findings` segment. CT does not
   provide T or N staging for rectal cancer. Do not populate T or N fields from CT.
9. Do not convert qualitative descriptions to numbered grades (e.g. do not
   convert "good response" to mrTRG2). Set `not_found` instead.
10. Do not add clinical judgment, diagnosis, interpretation, or treatment
    recommendations. Extract only what is explicitly stated in the text.

---

## Few-Shot Example

Include this example in the Stage 2 prompt. It demonstrates: correct triad
structure, correct null handling (`not_found`), CRM derivation from distance,
mrTRG not_found when no numbered grade is stated, and the verbatim field pattern.

### Input passed to the API

```
mri_findings: "Baseline rectal MRI 10/01/2025: mrT3c tumour, mrN2 nodal disease, CRM threatened at 0.8mm, EMVI positive. Tumour at 7cm from anal verge."

restaging_mri_findings: "Restaging MRI 20/03/2025 following SCPRT: good tumour response, mrT2, mrN0. CRM now clear."

ct_findings: "CT CAP 12/01/2025: No liver or lung metastases. No peritoneal disease. M0."

pathology: "Biopsy [HOSP_NUMBER]: moderately differentiated adenocarcinoma. MMR Proficient (pMMR). KRAS wild-type."

mdt_outcome: "Outcome: For short-course pre-operative radiotherapy (SCPRT) then restaging MRI then TME surgery. Curative intent."
```

### Expected output

```json
{
  "mrT_stage": {
    "value": "mrT3c",
    "source_text": "Baseline rectal MRI 10/01/2025: mrT3c tumour, mrN2 nodal disease, CRM threatened at 0.8mm, EMVI positive.",
    "confidence": "high"
  },
  "mrN_stage": {
    "value": "mrN2",
    "source_text": "Baseline rectal MRI 10/01/2025: mrT3c tumour, mrN2 nodal disease, CRM threatened at 0.8mm, EMVI positive.",
    "confidence": "high"
  },
  "mrCRM_status": {
    "value": "threatened",
    "source_text": "Baseline rectal MRI 10/01/2025: mrT3c tumour, mrN2 nodal disease, CRM threatened at 0.8mm, EMVI positive.",
    "confidence": "high"
  },
  "mrCRM_distance_mm": {
    "value": "0.8",
    "source_text": "Baseline rectal MRI 10/01/2025: mrT3c tumour, mrN2 nodal disease, CRM threatened at 0.8mm, EMVI positive.",
    "confidence": "high"
  },
  "mrEMVI_status": {
    "value": "positive",
    "source_text": "Baseline rectal MRI 10/01/2025: mrT3c tumour, mrN2 nodal disease, CRM threatened at 0.8mm, EMVI positive.",
    "confidence": "high"
  },
  "mrMRF_status": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "tumour_height_cm": {
    "value": "7.0",
    "source_text": "Tumour at 7cm from anal verge.",
    "confidence": "high"
  },
  "mri_date": {
    "value": "10/01/2025",
    "source_text": "Baseline rectal MRI 10/01/2025: mrT3c tumour, mrN2 nodal disease, CRM threatened at 0.8mm, EMVI positive.",
    "confidence": "high"
  },
  "restaging_mrT_stage": {
    "value": "mrT2",
    "source_text": "Restaging MRI 20/03/2025 following SCPRT: good tumour response, mrT2, mrN0.",
    "confidence": "high"
  },
  "restaging_mrN_stage": {
    "value": "mrN0",
    "source_text": "Restaging MRI 20/03/2025 following SCPRT: good tumour response, mrT2, mrN0.",
    "confidence": "high"
  },
  "restaging_mrCRM_status": {
    "value": "clear",
    "source_text": "CRM now clear.",
    "confidence": "high"
  },
  "restaging_mrEMVI_status": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "mrTRG": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "restaging_mri_date": {
    "value": "20/03/2025",
    "source_text": "Restaging MRI 20/03/2025 following SCPRT: good tumour response, mrT2, mrN0.",
    "confidence": "high"
  },
  "ct_M_stage": {
    "value": "M0",
    "source_text": "CT CAP 12/01/2025: No liver or lung metastases. No peritoneal disease. M0.",
    "confidence": "high"
  },
  "ct_liver_mets": {
    "value": "absent",
    "source_text": "CT CAP 12/01/2025: No liver or lung metastases. No peritoneal disease. M0.",
    "confidence": "high"
  },
  "ct_lung_mets": {
    "value": "absent",
    "source_text": "CT CAP 12/01/2025: No liver or lung metastases. No peritoneal disease. M0.",
    "confidence": "high"
  },
  "ct_peritoneal_disease": {
    "value": "absent",
    "source_text": "CT CAP 12/01/2025: No liver or lung metastases. No peritoneal disease. M0.",
    "confidence": "high"
  },
  "ct_date": {
    "value": "12/01/2025",
    "source_text": "CT CAP 12/01/2025: No liver or lung metastases. No peritoneal disease. M0.",
    "confidence": "high"
  },
  "histology_type": {
    "value": "moderately differentiated adenocarcinoma",
    "source_text": "Biopsy [HOSP_NUMBER]: moderately differentiated adenocarcinoma.",
    "confidence": "high"
  },
  "histology_grade": {
    "value": "moderately differentiated",
    "source_text": "Biopsy [HOSP_NUMBER]: moderately differentiated adenocarcinoma.",
    "confidence": "high"
  },
  "mmr_status": {
    "value": "Proficient (pMMR)",
    "source_text": "MMR Proficient (pMMR). KRAS wild-type.",
    "confidence": "high"
  },
  "msi_status": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "kras_status": {
    "value": "wild-type",
    "source_text": "MMR Proficient (pMMR). KRAS wild-type.",
    "confidence": "high"
  },
  "nras_status": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "braf_status": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "her2_status": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "pathology_date": {
    "value": null,
    "source_text": null,
    "confidence": "not_found"
  },
  "treatment_intent": {
    "value": "curative",
    "source_text": "Curative intent.",
    "confidence": "high"
  },
  "primary_treatment_modality": {
    "value": "SCPRT",
    "source_text": "Outcome: For short-course pre-operative radiotherapy (SCPRT) then restaging MRI then TME surgery.",
    "confidence": "high"
  },
  "planned_surgery": {
    "value": "TME",
    "source_text": "Outcome: For short-course pre-operative radiotherapy (SCPRT) then restaging MRI then TME surgery.",
    "confidence": "high"
  },
  "neoadjuvant_treatment": {
    "value": "yes",
    "source_text": "Outcome: For short-course pre-operative radiotherapy (SCPRT) then restaging MRI then TME surgery.",
    "confidence": "high"
  },
  "mdt_outcome_verbatim": {
    "value": "Outcome: For short-course pre-operative radiotherapy (SCPRT) then restaging MRI then TME surgery. Curative intent.",
    "source_text": "Outcome: For short-course pre-operative radiotherapy (SCPRT) then restaging MRI then TME surgery. Curative intent.",
    "confidence": "high"
  }
}
```

**Note on mrTRG in this example:** The restaging segment says "good tumour
response" — a qualitative phrase with no numbered grade. Per the mrTRG rule,
this correctly returns `not_found`. The human verification flag will alert the
clinician that mrTRG requires manual review. This is the safe behaviour.

**Note on `[HOSP_NUMBER]` in source_text:** The LLM correctly echoes the
anonymisation token as it appears in its input. At Stage 3, the reverse-
substitution step replaces this token with the real hospital number before the
value is written to the Source Evidence sheet.
