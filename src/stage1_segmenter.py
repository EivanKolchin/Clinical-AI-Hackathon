"""
Stage 1: Deterministic Segmenter
Reads Word documents, segments text deterministically (zero AI).
Extracts tables, splits into sentences, classifies into 8 clinical buckets.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from docx import Document


class Stage1Segmenter:
    """Deterministic document segmenter with zero AI interpretation."""
    
    # Classification buckets in priority order (first match wins)
    BUCKETS = [
        "restaging_mri_findings",
        "mri_findings",
        "ct_findings",
        "pathology",
        "mdt_outcome",
        "demographics",
        "diagnosis",
        "clinical_history"
    ]
    
    # Classification rules: (bucket, required_keywords, forbidden_keywords)
    CLASSIFICATION_RULES = [
        {
            "bucket": "restaging_mri_findings",
            "must_have": ["mri", "magnetic resonance"],
            "must_have_any_of": [
                "restaging", "post-treatment", "post-crt", "post-scprt",
                "response assessment", "re-staging", "post treatment",
                "after treatment", "following scprt", "following crt",
                "following radiotherapy"
            ]
        },
        {
            "bucket": "mri_findings",
            "must_have": ["mri", "magnetic resonance"],
            "must_have_any_of": [],
            "exclude_if_matches": ["restaging"]
        },
        {
            "bucket": "ct_findings",
            "must_have_any_of": [
                " ct ", "ct scan", "computed tomography", "ct imaging",
                "ct staging", "abdominal ct"
            ]
        },
        {
            "bucket": "pathology",
            "must_have_any_of": [
                "biopsy", "histology", "histological", "mmr", "msi",
                "mutation", "kras", "nras", "braf", "her2", "adenocarcinoma",
                "carcinoma"
            ]
        },
        {
            "bucket": "mdt_outcome",
            "must_have_any_of": [
                "outcome", "decision", "plan", "mdt", "for surgery",
                "for radiotherapy", "for chemotherapy", "curative", "palliative",
                "tme", "scprt", "crt"
            ]
        },
        {
            "bucket": "demographics",
            "must_have_any_of": [
                "nhs", "dob", "date of birth", "consultant", "hospital number"
            ]
        },
        {
            "bucket": "diagnosis",
            "must_have_any_of": [
                "diagnosis", "diagnosed", "cancer", "tumour", "tumor",
                "sigmoid", "rectal", "colorectal", "adenocarcinoma"
            ]
        },
        {
            "bucket": "clinical_history",
            "is_catchall": True
        }
    ]
    
    def __init__(self, docx_path: str):
        """Initialize segmenter with Word document path."""
        self.docx_path = Path(docx_path)
        self.document = Document(str(self.docx_path))
        self.cases = []
        self.case_count = 0
    
    def split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using regex.
        Splits on . , .\n, ! , ? and trailing . with no following space.
        """
        if not text or not text.strip():
            return []
        
        # Use regex to split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        
        # Filter out empty strings and strip whitespace
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences
    
    def classify_sentence(self, sentence: str) -> str:
        """
        Classify a single sentence into a bucket.
        Uses priority order: first matching rule wins.
        """
        sentence_lower = sentence.lower()
        
        for rule in self.CLASSIFICATION_RULES:
            bucket = rule["bucket"]
            
            # Catch-all rule
            if rule.get("is_catchall"):
                return bucket
            
            # Regex pattern match
            if "regex_pattern" in rule:
                if re.search(rule["regex_pattern"], sentence, re.IGNORECASE):
                    # Check must_have_any_of if it exists
                    if rule.get("must_have_any_of"):
                        if any(kw in sentence_lower for kw in rule["must_have_any_of"]):
                            return bucket
                    else:
                        return bucket
            
            # must_have rule (ALL keywords must be present)
            if "must_have" in rule:
                if all(kw in sentence_lower for kw in rule["must_have"]):
                    # Additional check: must_have_any_of (at least one)
                    if rule.get("must_have_any_of"):
                        if any(kw in sentence_lower for kw in rule["must_have_any_of"]):
                            return bucket
                    else:
                        # If must_have matches and no must_have_any_of, check exclusions
                        if not self._has_exclusion(sentence_lower, rule):
                            return bucket
            
            # must_have_any_of rule (at least one keyword must be present)
            elif "must_have_any_of" in rule and rule["must_have_any_of"]:
                if any(kw in sentence_lower for kw in rule["must_have_any_of"]):
                    if not self._has_exclusion(sentence_lower, rule):
                        return bucket
        
        # Should not reach here due to catch-all, but default to clinical_history
        return "clinical_history"
    
    def _has_exclusion(self, sentence_lower: str, rule: Dict) -> bool:
        """Check if sentence matches any exclusion criteria."""
        if "exclude_if_matches" in rule:
            return any(excl in sentence_lower for excl in rule["exclude_if_matches"])
        return False
    
    def extract_patient_identifiers(self, table) -> Dict:
        """
        Extract patient identifiers from table.
        Returns dict with NHS, DOB, name, hospital number, consultant, MDT date.
        """
        identifiers = {
            "nhs_number": None,
            "patient_name": None,
            "dob": None,
            "hospital_number": None,
            "consultant": None,
            "mdt_date": None
        }
        
        # Extract all text from table
        all_text = " ".join([cell.text for row in table.rows for cell in row.cells])
        
        # NHS number: \d{3}[\s\-]?\d{3}[\s\-]?\d{4}
        nhs_match = re.search(r'\d{3}[\s\-]?\d{3}[\s\-]?\d{4}', all_text)
        if nhs_match:
            identifiers["nhs_number"] = nhs_match.group(0)
        
        # Date of birth: \d{2}[\/\-]\d{2}[\/\-]\d{4}
        # Look for context: DOB, date of birth, born
        dob_context = re.search(
            r'(?:dob|date\s+of\s+birth|born)\s*[:\s]+(\d{2}[\/\-]\d{2}[\/\-]\d{4})',
            all_text,
            re.IGNORECASE
        )
        if dob_context:
            identifiers["dob"] = dob_context.group(1)
        
        # Hospital number: alphanumeric 6-8 chars, often starts with H
        hosp_match = re.search(r'\b[A-Z]\d{5,7}\b', all_text)
        if hosp_match:
            identifiers["hospital_number"] = hosp_match.group(0)
        
        # Consultant: text following "consultant:", "Mr", "Mrs", "Dr", "Prof"
        consultant_match = re.search(
            r'(?:consultant|mr|mrs|dr|prof)\.?\s+([A-Z][a-z]+ [A-Z][a-z]+)',
            all_text,
            re.IGNORECASE
        )
        if consultant_match:
            identifiers["consultant"] = consultant_match.group(1)
        
        # MDT date: date in context of "MDT", "outcome", "decision"
        mdt_context = re.search(
            r'(?:mdt|outcome|decision)\s*[:\s]*(\d{2}[\/\-]\d{2}[\/\-]\d{4})',
            all_text,
            re.IGNORECASE
        )
        if mdt_context:
            identifiers["mdt_date"] = mdt_context.group(1)
        
        # Patient name: text in demographics not matching patterns
        # Conservative: look for "Patient:" or "Name:" followed by text
        name_match = re.search(
            r'(?:patient|name)\s*[:\s]+([A-Z][a-z]+ [A-Z]\.?)',
            all_text,
            re.IGNORECASE
        )
        if name_match:
            identifiers["patient_name"] = name_match.group(1)
        
        return identifiers
    
    def validate_stage1(self, raw_segments: Dict) -> Tuple[bool, Optional[str]]:
        """
        Validate case has meaningful content.
        Returns (is_valid, reason_if_invalid)
        """
        # Check 1: MDT outcome must be present
        has_outcome = bool(raw_segments.get("mdt_outcome"))
        if not has_outcome:
            return False, "MDT outcome segment is empty — cannot extract treatment decision"
        
        # Check 2: Must have imaging (MRI or CT) OR (pathology + diagnosis)
        has_imaging = bool(raw_segments.get("mri_findings") or raw_segments.get("ct_findings"))
        has_pathology_and_diagnosis = bool(
            raw_segments.get("pathology") and raw_segments.get("diagnosis")
        )
        if not (has_imaging or has_pathology_and_diagnosis):
            return False, "Need imaging report OR (pathology + diagnosis) — insufficient clinical data"
        
        # Check 3: Must have ≥3 non-empty buckets (MDT outcome + 2 others minimum)
        non_empty_count = sum(1 for v in raw_segments.values() if v)
        if non_empty_count < 3:
            return False, f"Only {non_empty_count} non-empty segments, need ≥3 — sparse content"
        
        return True, None
    
    def segment_table(self, table, table_index: int) -> Dict:
        """
        Segment a single table into clinical buckets.
        Returns case JSON.
        """
        # Extract identifiers first
        identifiers = self.extract_patient_identifiers(table)
        
        # Initialize segments
        segments = {bucket: "" for bucket in self.BUCKETS}
        
        # Process each cell
        for row in table.rows:
            for cell in row.cells:
                cell_text = cell.text
                if not cell_text.strip():
                    continue
                
                # Split cell into sentences
                sentences = self.split_into_sentences(cell_text)
                
                # Classify and accumulate
                for sentence in sentences:
                    bucket = self.classify_sentence(sentence)
                    if segments[bucket]:
                        segments[bucket] += " " + sentence
                    else:
                        segments[bucket] = sentence
        
        # Remove empty segments
        raw_segments = {k: v.strip() for k, v in segments.items() if v.strip()}
        
        # Check if is_restaging_mri
        is_restaging = bool(raw_segments.get("restaging_mri_findings"))
        
        # Validate stage 1
        is_valid, invalid_reason = self.validate_stage1(raw_segments)
        
        # Build case JSON
        case = {
            "case_index": self.case_count,
            "patient_identifiers": identifiers,
            "raw_segments": raw_segments,
            "is_restaging_mri": is_restaging,
            "token_map": {},
            "metadata": {
                "table_index": table_index,
                "source_file": self.docx_path.name,
                "extraction_timestamp": datetime.utcnow().isoformat() + "Z",
                "stage1_validation_failed": not is_valid,
                "validation_reason": invalid_reason
            }
        }
        
        self.case_count += 1
        return case
    
    def process(self, output_dir: str = "output/json") -> List[Dict]:
        """
        Process all tables in document.
        Returns list of case JSONs.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        all_cases = []
        
        for table_idx, table in enumerate(self.document.tables):
            case = self.segment_table(table, table_idx)
            all_cases.append(case)
            
            # Write to file
            is_valid = not case["metadata"]["stage1_validation_failed"]
            filename_prefix = "case" if is_valid else "case"
            filename = f"{filename_prefix}_{case['case_index']:03d}"
            
            if not is_valid:
                filename += "_flagged"
            
            output_file = output_path / f"{filename}.json"
            with open(output_file, 'w') as f:
                json.dump(case, f, indent=2)
            
            print(f"✓ {output_file.name}")
        
        return all_cases


def segment_document(docx_path: str, output_dir: str = "output/json") -> List[Dict]:
    """
    Main entry point for Stage 1.
    Reads Word document, segments into JSON cases.
    """
    segmenter = Stage1Segmenter(docx_path)
    return segmenter.process(output_dir)
