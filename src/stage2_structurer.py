import json
import time
import os
import google.generativeai as genai
from tqdm import tqdm
from safety_flags import apply_safety_flags

# Expected field scaffold to guarantee schema compliance and deterministic fallbacks
EMPTY_FIELD = {"value": None, "source_text": None, "confidence": "not_found"}

def _empty_structured(case_index: int, is_restaging_mri: bool = False, stage1_failed: bool = False, reason: str | None = None) -> dict:
    mri_fields = ["mrT_stage", "mrN_stage", "mrCRM_status", "mrCRM_distance_mm", "mrEMVI_status", "mrMRF_status", "tumour_height_cm", "mri_date"]
    restaging_fields = ["restaging_mrT_stage", "restaging_mrN_stage", "restaging_mrCRM_status", "restaging_mrEMVI_status", "mrTRG", "restaging_mri_date"]
    ct_fields = ["ct_M_stage", "ct_liver_mets", "ct_lung_mets", "ct_peritoneal_disease", "ct_date"]
    path_fields = ["histology_type", "histology_grade", "mmr_status", "msi_status", "kras_status", "nras_status", "braf_status", "her2_status", "pathology_date"]
    mdt_fields = ["treatment_intent", "primary_treatment_modality", "planned_surgery", "neoadjuvant_treatment", "mdt_outcome_verbatim"]

    def block(keys):
        return {k: EMPTY_FIELD.copy() for k in keys}

    structured = {
        "case_index": case_index,
        "is_restaging_mri": is_restaging_mri,
        "mri_staging": block(mri_fields),
        "restaging_mri": block(restaging_fields),
        "ct_staging": block(ct_fields),
        "pathology": block(path_fields),
        "mdt_decision": block(mdt_fields),
    }
    if stage1_failed:
        structured["stage1_validation_failed"] = True
        structured["verification_required"] = True
        structured["verification_reasons"] = reason or "Stage 1 validation failed \u2014 check source document"
    return structured


def source_text_is_valid(source_text: str, original_segments: dict) -> bool:
    haystack = " ".join(str(v) for v in original_segments.values()).lower().strip()
    needle = source_text.lower().strip()
    
    if needle in haystack:
        return True
    
    needle_tokens = set(needle.split())
    haystack_tokens = set(haystack.split())
    if len(needle_tokens) == 0:
        return False
    overlap = len(needle_tokens & haystack_tokens) / len(needle_tokens)
    return overlap >= 0.85

def validate_response(response_json: dict, original_segments: dict) -> dict:
    # Pass 2: Schema compliance & Pass 3: hallucination detection
    allowed_conf = {"high", "low", "not_found"}

    def ensure_field(dct):
        if not isinstance(dct, dict):
            return EMPTY_FIELD.copy()
        field = dct.copy()
        if "value" not in field:
            field["value"] = None
        if "source_text" not in field:
            field["source_text"] = None
        if field.get("confidence") not in allowed_conf:
            field["confidence"] = "low"
        # Pass 3 hallucination check
        st = field.get("source_text")
        if st:
            if not source_text_is_valid(st, original_segments):
                field["confidence"] = "low"
                field["hallucination_flag"] = True
        return field

    for group, fields in list(response_json.items()):
        if isinstance(fields, dict) and group != 'metadata':
            for key, field in list(fields.items()):
                fields[key] = ensure_field(field)
    return response_json


def structure_case(anonymised_json_path: str, output_dir: str) -> str:
    """
    Structure a case using Gemini API.
    
    Args:
        anonymised_json_path: Path to case_*_anonymised.json file
        output_dir: Directory to write case_*_structured.json output
        
    Returns:
        Path to the generated structured JSON file
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set")
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash') # Latest stable model with JSON support
    
    with open(anonymised_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    segments = data.get('raw_segments', {})
    case_index = data.get('case_index', 0)
    is_restaging_mri = data.get('is_restaging_mri', False)
    stage1_failed = data.get('stage1_validation_failed', False)
    
    # Generate output path
    structured_output_path = os.path.join(output_dir, f"case_{case_index:03d}_structured.json")
    
    # If stage 1 failed, write not-found doc and skip API
    if stage1_failed:
        final_data = apply_safety_flags(_empty_structured(case_index, is_restaging_mri, True), segments)
        with open(structured_output_path, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=2)
        return structured_output_path
    
    # System + user content to enforce provenance triad and bucket discipline
    system_prompt = (
        "You are a clinical data extraction tool. Read only the provided JSON segments. "
        "Return JSON ONLY. Every field must be a Provenance Triad: value, source_text (verbatim), confidence in {high, low, not_found}. "
        "No inference, no paraphrase, no merging sentences. MRI fields ONLY from mri_findings. Restaging ONLY from restaging_mri_findings. "
        "CT fields ONLY from ct_findings. If absent, use null/null/not_found."
    )
    
    # Dynamically generate the expected output JSON structure schema template
    empty_schema = _empty_structured(case_index)
    schema_template = {k: v for k, v in empty_schema.items() if k not in ["case_index", "is_restaging_mri", "stage1_validation_failed", "verification_required", "verification_reasons"]}
    
    prompt = f"""
{system_prompt}

Input segments (labelled buckets):
{json.dumps(segments, indent=2)}

Return a single JSON object matching exactly this schema containing the detailed fields.
Every field must be populated with either the extracted data or the default not_found state.
Expected Schema:
{json.dumps(schema_template, indent=2)}
"""
    
    start_time = time.time()
    for attempt in range(3):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                    max_output_tokens=8192
                )
            )
            raw_output = response.text
            
            # Pass 1: JSON Validity and stripping markdown fences
            raw_output_clean = raw_output.replace("```json", "").replace("```", "").strip()
            structured_data = json.loads(raw_output_clean)
            
            # Validation (Pass 2 & 3)
            validated_data = validate_response(structured_data, segments)
            validated_data['case_index'] = case_index
            validated_data['is_restaging_mri'] = is_restaging_mri
            
            # Apply Safety Flags
            final_data = apply_safety_flags(validated_data, segments)
            
            time_ms = int((time.time() - start_time) * 1000)
            final_data['metadata'] = {
                "case_index": case_index,
                "api_response_time_ms": time_ms,
                "fields_extracted": sum(1 for g in final_data.values() if isinstance(g, dict) for f in g.values() if isinstance(f, dict) and f.get('value') is not None),
                "fields_flagged": len(final_data.get('verification_reasons', '').split(' | ')) if final_data.get('verification_reasons') else 0
            }
            
            with open(structured_output_path, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, indent=2)
                
            os.makedirs('logs', exist_ok=True)
            with open('logs/api_responses.log', 'a') as log_file:
                log_file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] case_index={case_index} | HTTP 200 | {time_ms}ms | fields_extracted={final_data['metadata']['fields_extracted']} | fields_flagged={final_data['metadata']['fields_flagged']}\n")
                
            return structured_output_path
        except json.JSONDecodeError:
            if attempt == 2:
                final_data = apply_safety_flags(_empty_structured(case_index, is_restaging_mri), segments)
                final_data['verification_required'] = True
                final_data['verification_reasons'] = "API failure — manual extraction required"
                with open(structured_output_path, 'w', encoding='utf-8') as f:
                    json.dump(final_data, f, indent=2)
                return structured_output_path
            time.sleep(2 ** (attempt + 1)) # Backoff
        except Exception:
            if attempt == 2:
                final_data = apply_safety_flags(_empty_structured(case_index, is_restaging_mri), segments)
                final_data['verification_required'] = True
                final_data['verification_reasons'] = "API failure — manual extraction required"
                with open(structured_output_path, 'w', encoding='utf-8') as f:
                    json.dump(final_data, f, indent=2)
                return structured_output_path
            time.sleep(2 ** (attempt + 1)) # Backoff

def stage2_and_3_pipeline(anonymised_json_dir: str, raw_json_dir: str, output_dir: str, api_key: str):
    from stage3_assembler import assemble_excel
    import glob
    
    os.makedirs(output_dir, exist_ok=True)
    files = glob.glob(os.path.join(anonymised_json_dir, 'case_*_anonymised.json'))
    
    print(f"Starting Stage 2 LLM processing for {len(files)} cases...")
    for file_path in tqdm(files, desc="Structuring Cases"):
        filename = os.path.basename(file_path)
        case_id = filename.split('_')[1]
        out_path = os.path.join(output_dir, f"case_{case_id}_structured.json")
        
        structure_case(file_path, out_path, api_key)
        time.sleep(1.5) # Rate limit: ~40 calls / min
        
    print("Starting Stage 3 Excel Assembly...")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    excel_path = os.path.join(output_dir, f"MDT_Extraction_{timestamp}.xlsx")
    assemble_excel(raw_json_dir, output_dir, excel_path)
    print(f"Pipeline complete. Output saved to {excel_path}.")
