"""
Main orchestration script.
Runs all stages in sequence: Stage 1 → Data Minimisation → Stage 2 → Stage 3.
"""

import argparse
import sys
import os
import glob
from pathlib import Path
from stage1_segmenter import segment_document
from data_minimisation import anonymise_case
from stage2_structurer import structure_case
from stage3_assembler import assemble_excel
from safety_flags import apply_safety_flags


def main(docx_path: str, output_dir: str = "output"):
    """
    End-to-end pipeline: Stage 1 → Data Minimisation → Stage 2 → Stage 3.
    
    Args:
        docx_path: Path to input Word document
        output_dir: Output directory for JSON and Excel files
    """
    print("=" * 60)
    print("TSPP Complete Pipeline (Stages 1-3)")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("GOOGLE_API_KEY"):
        print("\n⚠️  Warning: GOOGLE_API_KEY not set")
        print("   Set it with: export GOOGLE_API_KEY='your-key'")
        print("   From: https://aistudio.google.com/apikey")
        print("   Stages 2-3 will be skipped.\n")
        run_stage2_and_3 = False
    else:
        run_stage2_and_3 = True
    
    docx_file = Path(docx_path)
    if not docx_file.exists():
        print(f"❌ Error: {docx_path} not found")
        sys.exit(1)
    
    json_dir = Path(output_dir) / "json"
    excel_dir = Path(output_dir) / "excel"
    json_dir.mkdir(parents=True, exist_ok=True)
    excel_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📄 Input: {docx_file.name}")
    print(f"📁 Output (JSON): {json_dir}")
    print(f"📁 Output (Excel): {excel_dir}\n")
    
    # ============ STAGE 1: Segmentation ============
    print("Stage 1: Deterministic Segmenter")
    print("-" * 40)
    try:
        cases = segment_document(str(docx_file), str(json_dir))
        print(f"✓ Segmented {len(cases)} cases\n")
    except Exception as e:
        print(f"❌ Stage 1 failed: {e}")
        sys.exit(1)
    
    # ============ DATA MINIMISATION ============
    print("Data Minimisation: PII Anonymisation")
    print("-" * 40)
    anonymised_count = 0
    anonymised_files = []
    for case in cases:
        # Skip flagged cases from anonymisation (they're invalid anyway)
        if case["metadata"].get("stage1_validation_failed"):
            print(f"⊘ Skipping flagged case {case['case_index']:03d} (validation failed)")
            continue
        
        try:
            raw_file = json_dir / f"case_{case['case_index']:03d}.json"
            anonymised_file, token_map = anonymise_case(str(raw_file), str(json_dir))
            anonymised_count += 1
            anonymised_files.append(str(anonymised_file))
        except Exception as e:
            print(f"❌ Data minimisation failed for case {case['case_index']}: {e}")
            sys.exit(1)
    
    print(f"✓ Anonymised {anonymised_count} cases\n")
    
    if not run_stage2_and_3:
        print("=" * 60)
        print("Summary:")
        print(f"  Total cases processed: {len(cases)}")
        flagged_count = sum(1 for c in cases if c["metadata"].get("stage1_validation_failed"))
        if flagged_count > 0:
            print(f"  Flagged cases (validation failed): {flagged_count}")
        print(f"  Valid cases anonymised: {anonymised_count}")
        print(f"\n✅ Stages 1-Data Min complete!")
        print(f"Output files:")
        print(f"  Raw JSON: {json_dir}/*.json (with patient identifiers)")
        print(f"  Anonymised JSON: {json_dir}/*_anonymised.json (ready for Stage 2)")
        print("=" * 60)
        return
    
    # ============ STAGE 2: LLM Structurer ============
    print("Stage 2: LLM Structuring with Gemini")
    print("-" * 40)
    structured_files = []
    
    for anonymised_file in anonymised_files:
        case_idx = Path(anonymised_file).stem.replace("case_", "").replace("_anonymised", "")
        try:
            print(f"  Processing case {case_idx}...")
            result = structure_case(anonymised_file, str(json_dir))
            if result and Path(result).exists():
                structured_files.append(result)
            else:
                print(f"⚠️  Stage 2 returned unexpected result for case {case_idx}")
        except Exception as e:
            print(f"❌ Stage 2 failed for case {case_idx}: {e}")
            continue
    
    print(f"✓ Structured {len(structured_files)} cases\n")
    
    # ============ SAFETY FLAGS ============
    print("Applying Safety Flags")
    print("-" * 40)
    flagged_count = 0
    for struct_file in structured_files:
        try:
            result = apply_safety_flags(struct_file)
            if result and result.get("flags"):
                flagged_count += 1
                print(f"⚠️  Case {Path(struct_file).stem.replace('case_', '').replace('_structured', '')} flagged for review")
        except Exception as e:
            print(f"⚠️  Safety flag check failed: {e}")
            continue
    
    print(f"✓ {flagged_count} cases flagged for review\n")
    
    # ============ STAGE 3: Excel Assembly ============
    print("Stage 3: Excel Assembly")
    print("-" * 40)
    try:
        # Get all structured files
        structured_files = sorted(glob.glob(str(json_dir / "*_structured.json")))
        if structured_files:
            output_file = assemble_excel(structured_files, str(excel_dir), str(json_dir))
            print(f"✓ Excel workbook: {output_file}\n")
        else:
            print("⚠️  No structured files found for Excel assembly\n")
    except Exception as e:
        print(f"❌ Stage 3 failed: {e}\n")
        sys.exit(1)
    
    # ============ SUMMARY ============
    print("=" * 60)
    print("Summary:")
    print(f"  Total cases processed: {len(cases)}")
    flagged_count = sum(1 for c in cases if c["metadata"].get("stage1_validation_failed"))
    if flagged_count > 0:
        print(f"  Flagged cases (validation failed): {flagged_count}")
    print(f"  Valid cases anonymised: {anonymised_count}")
    print(f"  Cases structured (Stage 2): {len(structured_files)}")
    print(f"\n✅ Pipeline complete!")
    print(f"Output files:")
    print(f"  JSON: {json_dir}/case_*_structured.json")
    print(f"  Excel: {excel_dir}/MDT_Extraction_*.xlsx")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TSPP Complete Pipeline (Stages 1-3)"
    )
    parser.add_argument(
        "docx",
        help="Path to input Word document (.docx)"
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory (default: output)"
    )
    
    args = parser.parse_args()
    main(args.docx, args.output)
