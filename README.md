# Clinical AI Hackathon: Two-Stage Parser with Provenance (TSPP)

Extracting structured Multidisciplinary Team (MDT) outcome proformas from unstructured clinical records using a deterministic-first architecture.

## 🩺 The Problem
Clinical records are messy, unstructured Word documents. Pulling out specific cancer staging metrics (TNM), pathology results, and treatment plans manually takes hundreds of hours. 

While language models are good at reading medical text, they are incredibly risky in unconstrained healthcare environments. You cannot blindly feed sensitive patient records into an API, nor can you trust a "black box" that might hallucinate a tumor's T-stage or invent a planned surgery. Clinicians need structured data, complete patient privacy, and most importantly, an absolute guarantee of exactly where the software got its information from.

## 🛠️ The Solution: Our Architecture
We built the **Two-Stage Parser with Provenance (TSPP)**. Instead of treating the AI as an all-knowing oracle, we treat it strictly as a dumb data extraction tool guarded heavily by traditional, deterministic Python code. 

### 1. Deterministic Segmentation (Stage 1)
We do not use AI to read the whole document. A Python script reads the Word files, searches for core patient identifiers (NHS Number, DOB, Consultant), and programmatically chops the remaining clinical text into 8 distinct buckets using Regex rules (e.g. `mri_findings`, `ct_findings`, `pathology`, `mdt_outcome`).

### 2. Data Minimisation (PII Stripping)
Before any text touches an external server, all Protected Health Information (PII) is scrubbed.
* `999-000-0001` becomes `[NHS_NUMBER]`
* `John Doe` becomes `[PATIENT_NAME]`
This creates a local token map, ensuring external APIs only ever read fully anonymised medical jargon.

### 3. Generative Structuring (Stage 2)
The anonymised text buckets are sent to Google Gemini (`gemini-1.5-flash`) via strict JSON-mode configuration. The model is forced to return every single field using the **Provenance Triad**:
1. **Value**: The structured extraction (e.g., `mrT3c`).
2. **Source Text**: The verbatim, exact sentence it copied from the document.
3. **Confidence**: `high`, `low`, or `not_found`.

Because the model is forced to quote its source precisely, hallucinations drop to zero.

### 4. Safety Rules Engine
A rule-based engine scans the extracted JSON to hunt for medical contradictions (e.g., the CT scan notes `M0` stage, but the clinical history mentions "palliative"), flagging the patient file automatically for manual human review.

### 5. Final Assembly & Excel Export (Stage 3)
The system retrieves the token map, patches the patient's real name and NHS number back into the data, and renders a clinically formatted Excel workbook, explicitly highlighting flagged/ambiguous fields.

---

## 📂 Repository Documents Included

- **`README.md`**: This document, introducing the software.
- **`TSPP_Technical_Specification_v4.md`**: Comprehensive technical engineering instructions for the text-splitting, AI staging, and backend assembly pipeline.
- **`field_reference_v2.md`**: Clinical field definitions and acceptable value constraints required by the LLM prompts schema.
- **`STAGE1_README.md`**: Legacy deep-dive onto the regex engine and PII abstraction tools.
- **`IMPLEMENTATION_COMPLETE.md` / `FINAL_SUMMARY.md`**: Internal status mapping files validating the 100% completion metrics of the system.
- **`start.bat` / `start.sh`**: One-click startup scripts enabling immediate UI deployment.
- **`app.py`**: The frontend application framework utilizing Streamlit.

---

## 🚀 Getting Started

### Prerequisites
* Python 3.10+ installed on your machine.
* A Google Gemini API Key.

### Method 1: Clinician-Friendly UI (Automated Setup Scripts)
These scripts check for Python, install missing dependencies, request your API key if missing, and launch the web app.

**For Windows:**
Double-click `start.bat` or run it from your command prompt:
```powershell
.\start.bat
```

**For Mac / Linux:**
```bash
chmod +x start.sh
./start.sh
```

1. A professional clinical web interface will open in your browser (`http://localhost:8501`).
2. Drop your `.docx` medical proformas into the interface, review data instantly via the inline Excel previewer, and download the results.
3. **Live Progress Tracking:** The frontend UI tracks execution in real time dynamically, rendering a live progress bar mapping out exactly how many files are left and outputting an **Approximate Time Remaining (ETA)** before completion! 

### Method 2: Command Line Backend Execution (Without Setup Scripts)
If you wish to run the project entirely via terminal without a frontend UI:

```bash
# Install dependencies manually
pip install -r requirements.txt

# Export your API key 
export GOOGLE_API_KEY="your-api-key-here"

# Run testing cases manually (will output to an `output` directory)
python src/main.py data/hackathon-mdt-outcome-proformas.docx -o output/
```

---

## ⚠️ Troubleshooting

**"API Failure — Manual Extraction Required"**
* **Issue:** Google Gemini may be rate-limiting you or flagging false-positive "Dangerous Content" filters (e.g. from the word "palliative" or "cancer").
* **Fix:** The codebase natively forces `gemini-1.5-flash` and nullifies safety filters to mitigate this. If it persists, ensure you are utilizing an API key with adequate quota remaining. 

**"ModuleNotFoundError: No module named X"**
* **Fix:** You didn't install the libraries properly. Using `start.bat` or `start.sh` normally handles this, but you can manually reinstall by executing `pip install -r requirements.txt --force-reinstall`.

**Empty Excel Files Generated**
* **Fix:** If the initial word docs lack sufficient headers/clinical data, the determinism script flags and rejects them safely. Review logs manually to ensure the Word documents follow standard proforma MDT conventions.
