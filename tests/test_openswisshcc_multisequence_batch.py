import hashlib
import json

import pytest

from dtwin.benchmark.openswisshcc_multisequence_batch import (
    build_multisequence_cohort,
    build_multisequence_gallery,
)
from dtwin.benchmark.openswisshcc_multisequence_panel import SCHEMA
from dtwin.core import PipelineError


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def input_manifest(p):
    rows=[{"schema":"argos-public-liver-mri-input-v1","case_id":c,"research_only":True,"clinical_use_allowed":False,"files":[]} for c in ('anon-a','anon-b')]
    p.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')

def renderer(**kw):
    c=kw['case_id']; d=kw['output_root']/c; d.mkdir(); image=d/'panel.png'; image.write_bytes(c.encode())
    panels=[{"panel_number":1,"panel_total":1,"image":image.name,"bytes":image.stat().st_size,"sha256":sha(image),"trace_plane_index":2}]
    m={"schema":SCHEMA,"case_id":c,"panel_count":1,"panels":panels,"trace_role":"dwi_trace_run_03","t2_role":"t2_blade","coverage":{"gate_passed":True,"missing_trace_planes":[],"duplicate_trace_planes":[]},"ground_truth_read":False,"lesion_mask_used":False}
    (d/'multisequence_manifest.json').write_text(json.dumps(m),encoding='utf-8'); return m

def test_cohort_and_gallery_preserve_blinding_and_hashes(tmp_path):
    mf=tmp_path/'inputs.jsonl'; input_manifest(mf); cohort=tmp_path/'cohort'
    result=build_multisequence_cohort(input_root=tmp_path,manifest_path=mf,output_root=cohort,expected_case_count=2,renderer=renderer)
    assert result['case_count']==2 and result['ground_truth_read'] is False and result['inference_executed'] is False
    gallery=build_multisequence_gallery(panel_root=cohort,output_dir=tmp_path/'gallery',expected_case_count=2)
    assert gallery['panel_count']==2 and gallery['authoritative_approval'] is False
    assert (tmp_path/'gallery'/'index.html').read_text(encoding='utf-8').count('loading="lazy"')==2

def test_gallery_rejects_tampered_panel(tmp_path):
    mf=tmp_path/'inputs.jsonl'; input_manifest(mf); cohort=tmp_path/'cohort'
    build_multisequence_cohort(input_root=tmp_path,manifest_path=mf,output_root=cohort,expected_case_count=2,renderer=renderer)
    (cohort/'anon-a'/'panel.png').write_bytes(b'tampered')
    with pytest.raises(PipelineError,match='divergente'):
        build_multisequence_gallery(panel_root=cohort,output_dir=tmp_path/'gallery',expected_case_count=2)

def test_cohort_rejects_ground_truth_field(tmp_path):
    mf=tmp_path/'inputs.jsonl'; input_manifest(mf)
    rows=[json.loads(x) for x in mf.read_text().splitlines()]; rows[0]['label']='POSITIVE'; mf.write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises(PipelineError,match='ground truth'):
        build_multisequence_cohort(input_root=tmp_path,manifest_path=mf,output_root=tmp_path/'out',expected_case_count=2,renderer=renderer)
