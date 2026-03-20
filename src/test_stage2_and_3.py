import pytest
from src.safety_flags import apply_safety_flags

def test_apply_safety_flags():
    data = {
        'is_restaging_mri': True,
        'mri_staging': {'mrT_stage': {'value': 'mrT3', 'source_text': 'mrT3', 'confidence': 'low'}},
        'restaging_mri': {'restaging_mrT_stage': {'value': 'mrT2', 'source_text': 'mrT2', 'confidence': 'high'}},
        'ct_staging': {'ct_M_stage': {'value': 'M0', 'source_text': 'M0', 'confidence': 'high'}}
    }
    raw_segments = {
        'ct_findings': 'CT CAP: M0.',
        'clinical_history': 'Patient has liver metastases.'
    }
    result = apply_safety_flags(data, raw_segments)
    assert result['verification_required'] == True
    assert "Low confidence MRI staging" in result['verification_reasons']
    assert "Both baseline and restaging T stage present" in result['verification_reasons']
    assert "CT M0 contradicts clinical notes suggesting metastatic disease" in result['verification_reasons']
    assert "liver metastases" in result['ct_staging']['ct_M_stage']['contradiction_note']

def test_source_text_is_valid():
    from src.stage2_structurer import source_text_is_valid
    segments = {'mri': 'Baseline rectal MRI: mrT3c'}
    assert source_text_is_valid('Baseline rectal MRI: mrT3c', segments) == True
    assert source_text_is_valid('Completely fabricated text', segments) == False
    assert source_text_is_valid('Baseline rectal MRI:', segments) == True # fuzzy matches 100% of needle tokens
