"""
Main orchestration script.
Runs all stages in sequence: Stage 1 → Data Minimisation.
"""

import argparse
import sys
from pathlib import Path
from stage1_segmenter import segment_document
from data_minimisation import anonymise_case


def main(docx_path: str, output_dir: str = "output"):
    """
    End-to-end pipeline: Stage 1 → Data Minimisation.
    
    Args:
        docx_path: Path to input Word document
        output_dir: Output directory for JSON files
    """
    print("=" * 60)
    print("TSPP Stage 1 & Data Minimisation Pipeline")
    print("=" * 60)
    
    docx_file = Path(docx_path)
    if not docx_file.exists():
        print(f"❌ Error: {docx_path} not found")
        sys.exit(1)
    
    json_dir = Path(output_dir) / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📄 Input: {docx_file.name}")
    print(f"📁 Output: {json_dir}\n")
    
    # Stage 1: Segmentation
    print("Stage 1: Deterministic Segmenter")
    print("-" * 40)
    try:
        cases = segment_document(str(docx_file), str(json_dir))
        print(f"✓ Segmented {len(cases)} cases\n")
    except Exception as e:
        print(f"❌ Stage 1 failed: {e}")
        sys.exit(1)
    
    # Data Minimisation
    print("Data Minimisation: PII Anonymisation")
    print("-" * 40)
    anonymised_count = 0
    for case in cases:
        # Skip flagged cases from anonymisation (they're invalid anyway)
        if case["metadata"].get("stage1_validation_failed"):
            print(f"⊘ Skipping flagged case {case['case_index']:03d} (validation failed)")
            continue
        
        try:
            raw_file = json_dir / f"case_{case['case_index']:03d}.json"
            anonymised_file, token_map = anonymise_case(str(raw_file), str(json_dir))
            anonymised_count += 1
        except Exception as e:
            print(f"❌ Data minimisation failed for case {case['case_index']}: {e}")
            sys.exit(1)
    
    print(f"✓ Anonymised {anonymised_count} cases\n")
    
    # Summary
    print("=" * 60)
    print("Summary:")
    print(f"  Total cases processed: {len(cases)}")
    flagged_count = sum(1 for c in cases if c["metadata"].get("stage1_validation_failed"))
    if flagged_count > 0:
        print(f"  Flagged cases (validation failed): {flagged_count}")
    print(f"  Valid cases anonymised: {anonymised_count}")
    print(f"\n✅ Pipeline complete!")
    print(f"Output files:")
    print(f"  Raw JSON: {json_dir}/*.json (with patient identifiers)")
    print(f"  Anonymised JSON: {json_dir}/*_anonymised.json (ready for Stage 2)")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TSPP Stage 1 & Data Minimisation Pipeline"
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
