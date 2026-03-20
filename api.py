"""
FastAPI server for Clinical MDT Pipeline.
Connects React frontend to Stage 1-3 processing pipeline.
Handles multiple file formats: .docx, .pdf, .xlsx, .csv, .txt
"""

import os
import json
import tempfile
from pathlib import Path
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Import our pipeline
from src.stage1_segmenter import segment_document
from src.multi_format_parser import parse_clinical_document
from src.data_minimisation import anonymise_case
from src.stage2_structurer import structure_case
from src.stage3_assembler import assemble_excel


app = FastAPI(
    title="Clinical MDT API",
    description="AI-powered clinical data extraction pipeline",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProcessingStatus(BaseModel):
    """Processing status response."""
    case_index: int
    status: str  # 'processing', 'completed', 'failed'
    fields_extracted: int = 0
    verification_required: bool = False


class UploadResponse(BaseModel):
    """Response after file upload."""
    total_cases: int
    passed_validation: int
    failed_validation: int
    file_format: str
    message: str


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Clinical MDT Pipeline API",
        "version": "1.0.0"
    }


@app.post("/process", response_model=UploadResponse)
async def process_document(file: UploadFile = File(...)):
    """
    Process clinical document in any supported format.

    Supported formats:
    - .docx (Word documents)
    - .pdf (PDF files)
    - .xlsx (Excel spreadsheets)
    - .csv (CSV files)
    - .txt (Plain text)

    Returns: Summary of cases extracted
    """
    # Validate file
    file_extension = Path(file.filename).suffix.lower()
    supported_formats = ['.docx', '.pdf', '.xlsx', '.csv', '.txt']

    if file_extension not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {file_extension}. Supported: {supported_formats}"
        )

    try:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        # Step 1: Parse document based on format
        print(f"\n📄 Parsing {file_extension} document...")
        cases_raw, source_format = parse_clinical_document(tmp_path)

        if not cases_raw:
            raise ValueError("No cases found in document")

        print(f"✓ Extracted {len(cases_raw)} cases from {source_format.upper()}")

        # Step 2: Segment into buckets (Stage 1)
        print(f"\n🔄 Stage 1: Segmentation...")

        # For non-.docx formats, we need to convert to docx-like structure
        # For now, create a temporary docx from the parsed data
        if file_extension != '.docx':
            tmp_docx = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
            from docx import Document
            doc = Document()

            for case_idx, case in enumerate(cases_raw):
                table = doc.add_table(rows=1, cols=1)
                # Add case content to table
                if 'text_content' in case:
                    cell = table.rows[0].cells[0]
                    cell.text = case['text_content']
                elif 'cells' in case:
                    # Reconstruct table from cells
                    content = "\n".join([c['text'] for c in case['cells']])
                    cell = table.rows[0].cells[0]
                    cell.text = content

            doc.save(tmp_docx.name)
            docx_path = tmp_docx.name
        else:
            docx_path = tmp_path

        # Run Stage 1
        segmented_cases = segment_document(docx_path, "output/json")

        # Count validation results
        passed = sum(1 for c in segmented_cases if not c["metadata"].get("stage1_validation_failed"))
        failed = len(segmented_cases) - passed

        # Step 3: Anonymise valid cases
        print(f"\n🔐 Data Minimisation: Anonymising {passed} valid cases...")
        anonymised_count = 0
        for case in segmented_cases:
            if not case["metadata"].get("stage1_validation_failed"):
                try:
                    raw_file = Path("output/json") / f"case_{case['case_index']:03d}.json"
                    anonymise_case(str(raw_file), "output/json")
                    anonymised_count += 1
                except Exception as e:
                    print(f"⚠️  Anonymisation failed for case {case['case_index']}: {e}")

        print(f"✓ Anonymised {anonymised_count} cases")

        # Clean up temp files
        try:
            os.unlink(tmp_path)
            if file_extension != '.docx':
                os.unlink(docx_path)
        except:
            pass

        return UploadResponse(
            total_cases=len(segmented_cases),
            passed_validation=passed,
            failed_validation=failed,
            file_format=source_format.upper(),
            message=f"Successfully processed {passed}/{len(segmented_cases)} cases"
        )

    except Exception as e:
        print(f"❌ Error processing document: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/process-with-llm")
async def process_with_llm(file: UploadFile = File(...)):
    """
    Full end-to-end processing: Stage 1 → Data Min → Stage 2 (LLM) → Stage 3 (Excel).
    Requires GOOGLE_API_KEY environment variable.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="GOOGLE_API_KEY environment variable not set"
        )

    try:
        # First, do basic processing
        basic_response = await process_document(file)

        # Then run Stages 2 & 3
        print(f"\n🤖 Stage 2: LLM Structuring...")
        json_dir = Path("output/json")
        excel_dir = Path("output/excel")

        # Get all anonymised files
        anonymised_files = list(json_dir.glob("case_*_anonymised.json"))

        if not anonymised_files:
            raise ValueError("No anonymised cases found for Stage 2")

        structured_files = []
        for anonymised_file in anonymised_files:
            case_idx = anonymised_file.stem.replace("case_", "").replace("_anonymised", "")
            try:
                result = structure_case(str(anonymised_file), str(json_dir))
                if result:
                    structured_files.append(result)
            except Exception as e:
                print(f"⚠️  Stage 2 failed for case {case_idx}: {e}")

        print(f"✓ Structured {len(structured_files)} cases")

        # Stage 3: Excel Assembly
        if structured_files:
            print(f"\n📊 Stage 3: Excel Assembly...")
            excel_file = assemble_excel(structured_files, str(excel_dir), str(json_dir))
            print(f"✓ Generated: {excel_file}")

            return {
                "status": "success",
                "message": "End-to-end processing complete",
                "total_cases": basic_response.total_cases,
                "passed_validation": basic_response.passed_validation,
                "structured_cases": len(structured_files),
                "excel_file": Path(excel_file).name,
                "file_format": basic_response.file_format
            }
        else:
            raise ValueError("No cases successfully structured")

    except Exception as e:
        print(f"❌ LLM processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get("/cases")
async def list_cases():
    """List all processed cases with their status."""
    json_dir = Path("output/json")
    if not json_dir.exists():
        return {"cases": []}

    cases = []
    for case_file in sorted(json_dir.glob("case_*_structured.json")):
        with open(case_file) as f:
            data = json.load(f)
            cases.append({
                "case_index": data.get("case_index"),
                "verification_required": data.get("verification_required", False),
                "file": case_file.name
            })

    return {"cases": cases, "total": len(cases)}


@app.get("/download/excel")
async def download_excel():
    """Download the latest generated Excel file."""
    excel_dir = Path("output/excel")
    if not excel_dir.exists():
        raise HTTPException(status_code=404, detail="No Excel files generated yet")

    # Get most recent Excel file
    excel_files = list(excel_dir.glob("MDT_Extraction_*.xlsx"))
    if not excel_files:
        raise HTTPException(status_code=404, detail="No Excel files found")

    latest_file = max(excel_files, key=lambda p: p.stat().st_mtime)
    return FileResponse(
        path=latest_file,
        filename=latest_file.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/docs", include_in_schema=False)
async def get_docs():
    """API documentation."""
    return {
        "endpoints": {
            "/health": "Health check",
            "/process": "Process document (Stage 1 only)",
            "/process-with-llm": "Full pipeline (Stages 1-3 with LLM)",
            "/cases": "List all processed cases",
            "/download/excel": "Download Excel report"
        },
        "supported_formats": [".docx", ".pdf", ".xlsx", ".csv", ".txt"],
        "environment_variables": {
            "GOOGLE_API_KEY": "Required for LLM processing (Stage 2)"
        }
    }


if __name__ == "__main__":
    print("🚀 Starting Clinical MDT API...")
    print("📍 API available at: http://localhost:8000")
    print("📚 Docs at: http://localhost:8000/docs")
    print("🔗 Frontend: http://localhost:3000")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000)
