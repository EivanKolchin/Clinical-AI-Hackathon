import json

def apply_safety_flags(structured_json: dict, raw_segments: dict = None) -> dict:
    flags = []
    if raw_segments is None:
        raw_segments = {}
    
    # 1. Low confidence MRI staging
    mri_fields = ['mrT_stage', 'mrN_stage', 'mrCRM_status', 'mrEMVI_status']
    for field in mri_fields:
        if structured_json.get('mri_staging', {}).get(field, {}).get('confidence') == 'low':
            flags.append("Low confidence MRI staging")
            break
            
    # 2. MDT treatment intent missing
    intent = structured_json.get('mdt_decision', {}).get('treatment_intent', {}).get('value')
    if intent is None or intent == "not_stated":
        flags.append("MDT treatment intent missing")
        
    # 3. T stage found BUT M stage absent AND CT report present
    t_stage = structured_json.get('mri_staging', {}).get('mrT_stage', {}).get('value')
    m_stage = structured_json.get('ct_staging', {}).get('ct_M_stage', {}).get('value')
    ct_present = bool(raw_segments.get('ct_findings', '').strip())
    if t_stage is not None and m_stage is None and ct_present:
        flags.append("T stage found but M stage absent despite CT report present")
        
    # 4. Restaging MRI present BUT no baseline MRI staging
    is_restaging = structured_json.get('is_restaging_mri', False)
    if is_restaging and t_stage is None:
        flags.append("Restaging MRI present but no baseline MRI staging found")
        
    # 5 & 6. Hallucination check failed & Value present with no source text
    hallucination_failed = False
    
    def check_fields(data):
        nonlocal hallucination_failed
        for k, v in data.items():
            if isinstance(v, dict) and 'confidence' in v:
                if v.get('hallucination_flag') == True:
                    hallucination_failed = True
                if v.get('value') is not None and v.get('source_text') is None:
                    flags.append("Value present with no source text \u2014 unverifiable")
            elif isinstance(v, dict):
                check_fields(v)

    check_fields(structured_json)
    
    if hallucination_failed:
        flags.append("Hallucination check failed \u2014 verify source text")

    # 7. Clinical Ambiguity Detection
    # Scenario A:
    restaging_t = structured_json.get('restaging_mri', {}).get('restaging_mrT_stage', {}).get('value')
    if t_stage and restaging_t:
        flags.append("Both baseline and restaging T stage present \u2014 verify correct field assignment")

    # Scenario B:
    if m_stage == 'M0':
        combined_notes_raw = (raw_segments.get('clinical_history', '') + " " + raw_segments.get('mdt_outcome', ''))
        combined_notes_lc = combined_notes_raw.lower()
        for kw in ['liver metastases', 'lung mets', 'peritoneal', 'm1', 'metastatic']:
            if kw in combined_notes_lc:
                ct_m_field = structured_json.setdefault('ct_staging', {}).setdefault('ct_M_stage', {})
                ct_m_field['confidence'] = "low"
                sentences = combined_notes_raw.replace('\n', '.').split('.')
                matching = next((s.strip() for s in sentences if kw in s.lower()), "Contradicting notes.")
                ct_m_field['contradiction_note'] = f"Conflicting text found: '{matching}'"
                flags.append("CT M0 contradicts clinical notes suggesting metastatic disease")
                break

    # 8. Stage 1 validation failed
    if structured_json.get('stage1_validation_failed'):
        flags.append("Stage 1 validation failed \u2014 check source document")

    # Set flags
    if flags:
        structured_json['verification_required'] = True
        structured_json['verification_reasons'] = " | ".join(set(flags))
    else:
        structured_json['verification_required'] = False
        structured_json['verification_reasons'] = None

    return structured_json
