import hashlib, json
from pathlib import Path
import pytest
from dtwin.benchmark.openswisshcc_multisequence_batch import COHORT_SCHEMA
from dtwin.benchmark.openswisshcc_multisequence_gate import CONFIRMATIONS, create_multisequence_review, verify_multisequence_review
from dtwin.benchmark.openswisshcc_multisequence_panel import SCHEMA
from dtwin.core import PipelineError

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def cohort(tmp_path):
    root=tmp_path/'cohort'; case=root/'anon-a'; case.mkdir(parents=True); image=case/'p.png'; image.write_bytes(b'panel')
    panel={"panel_number":1,"image":"p.png","sha256":sha(image),"bytes":5,"trace_plane_index":2}
    manifest={"schema":SCHEMA,"case_id":"anon-a","ground_truth_read":False,"lesion_mask_used":False,"panel_count":1,"panels":[panel],"coverage":{"gate_passed":True,"missing_trace_planes":[],"duplicate_trace_planes":[],"unavailable_tiles":[]}}
    mp=case/'multisequence_manifest.json'; mp.write_text(json.dumps(manifest))
    cases=[{"case_id":"anon-a","panel_count":1,"trace_role":"dwi_trace_run_03","t2_role":"t2_blade","manifest_sha256":sha(mp)}]
    cm={"schema":COHORT_SCHEMA,"case_count":1,"panel_count":1,"cases":cases,"cohort_signature":"cohort","research_only":True,"clinical_use_allowed":False,"ground_truth_read":False,"lesion_mask_used":False,"inference_executed":False}
    (root/'cohort_manifest.json').write_text(json.dumps(cm)); return root

def test_signed_review_verifies_and_detects_panel_change(tmp_path):
    root=cohort(tmp_path); out=tmp_path/'review.json'; flags={k:True for k in CONFIRMATIONS}
    review=create_multisequence_review(panel_root=root,output_path=out,reviewer='human',confirmations=flags,expected_case_count=1)
    assert verify_multisequence_review(panel_root=root,review_path=out,expected_case_count=1)['review_signature']==review['review_signature']
    (root/'anon-a'/'p.png').write_bytes(b'changed')
    with pytest.raises(PipelineError,match='Painel v9 divergente'):
        verify_multisequence_review(panel_root=root,review_path=out,expected_case_count=1)

def test_review_requires_every_confirmation(tmp_path):
    root=cohort(tmp_path); flags={k:True for k in CONFIRMATIONS}; flags['out_of_fov_tiles_reviewed']=False
    with pytest.raises(PipelineError,match='confirmacoes'):
        create_multisequence_review(panel_root=root,output_path=tmp_path/'r.json',reviewer='human',confirmations=flags,expected_case_count=1)
