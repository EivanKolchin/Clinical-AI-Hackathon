from src.stage1_segmenter import segment_document
cases = segment_document('data/hackathon-mdt-outcome-proformas.docx', 'test_output')
fails = [c for c in cases if c['metadata'].get('stage1_validation_failed')]
print(f"Total: {len(cases)}, Fails: {len(fails)}")
for f in fails[:5]:
    print(f"Failed case: {f.get('metadata', {}).get('validation_reason')}")
