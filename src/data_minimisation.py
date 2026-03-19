"""
Data Minimisation: Strip PII from segmented text before API transmission.
Uses word-boundary regex for name matching to prevent clinical term corruption.
Preserves token map for Stage 3 reverse-substitution.
"""

import json
import re
from pathlib import Path
from typing import Dict, Tuple


class DataMinimiser:
    """Anonymise clinical text while preserving token map for later reversal."""
    
    def __init__(self, raw_json_path: str):
        """Load raw case JSON."""
        self.raw_json_path = Path(raw_json_path)
        with open(self.raw_json_path, 'r') as f:
            self.case = json.load(f)
        self.token_map = {}
    
    def anonymise(self) -> (Dict, Dict):
        """
        Remove PII from raw_segments.
        Returns: (anonymised_case, token_map)
        """
        identifiers = self.case.get("patient_identifiers", {})
        
        # Build anonymisation rules
        pii_replacements = []
        
        # NHS number
        if identifiers.get("nhs_number"):
            nhs = identifiers["nhs_number"]
            pattern = r'\d{3}[\s\-]?\d{3}[\s\-]?\d{4}'
            pii_replacements.append((pattern, "[NHS_NUMBER]", nhs, True))
            self.token_map["[NHS_NUMBER]"] = nhs
        
        # Patient name (word boundary to not corrupt clinical terms)
        if identifiers.get("patient_name"):
            name = identifiers["patient_name"]
            # Use word boundary regex
            pattern = r'\b' + re.escape(name) + r'\b'
            pii_replacements.append((pattern, "[PATIENT_NAME]", name, False))
            self.token_map["[PATIENT_NAME]"] = name
        
        # Date of birth (exact match)
        if identifiers.get("dob"):
            dob = identifiers["dob"]
            pattern = re.escape(dob)
            pii_replacements.append((pattern, "[DOB]", dob, False))
            self.token_map["[DOB]"] = dob
        
        # Hospital number (exact match)
        if identifiers.get("hospital_number"):
            hosp = identifiers["hospital_number"]
            pattern = re.escape(hosp)
            pii_replacements.append((pattern, "[HOSP_NUMBER]", hosp, False))
            self.token_map["[HOSP_NUMBER]"] = hosp
        
        # Apply replacements to raw_segments
        anonymised_segments = {}
        for bucket, text in self.case.get("raw_segments", {}).items():
            anonymised_text = text
            for pattern, token, original_value, is_regex_pattern in pii_replacements:
                if is_regex_pattern:
                    anonymised_text = re.sub(pattern, token, anonymised_text, flags=re.IGNORECASE)
                else:
                    anonymised_text = re.sub(pattern, token, anonymised_text, flags=re.IGNORECASE)
            anonymised_segments[bucket] = anonymised_text
        
        # Build anonymised case (remove patient_identifiers block)
        anonymised_case = {
            "case_index": self.case["case_index"],
            "raw_segments": anonymised_segments,
            "is_restaging_mri": self.case["is_restaging_mri"],
            "metadata": self.case.get("metadata", {})
        }
        
        return anonymised_case, self.token_map
    
    def save_anonymised(self, output_dir: str = "output/json") -> str:
        """
        Save anonymised JSON to file.
        Update token_map in original raw JSON.
        Returns: path to anonymised JSON
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Anonymise
        anonymised_case, token_map = self.anonymise()
        
        # Save anonymised case
        case_idx = self.case["case_index"]
        anonymised_file = output_path / f"case_{case_idx:03d}_anonymised.json"
        with open(anonymised_file, 'w') as f:
            json.dump(anonymised_case, f, indent=2)
        
        # Update token_map in raw JSON and save back
        self.case["token_map"] = token_map
        with open(self.raw_json_path, 'w') as f:
            json.dump(self.case, f, indent=2)
        
        return str(anonymised_file)


def anonymise_case(raw_json_path: str, output_dir: str = "output/json") -> Tuple[str, Dict]:
    """
    Main entry point for Data Minimisation.
    Reads raw JSON, anonymises PII, outputs JSON and token map.
    Returns: (anonymised_json_path, token_map)
    """
    minimiser = DataMinimiser(raw_json_path)
    anonymised_case, token_map = minimiser.anonymise()
    output_file = minimiser.save_anonymised(output_dir)
    print(f"✓ Anonymised: {Path(output_file).name}")
    return output_file, token_map
