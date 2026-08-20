import json

import nibabel as nib
import numpy as np
import pytest

from dtwin.benchmark.openswisshcc_alignment import _sha256
from dtwin.benchmark.openswisshcc_lesion_localizer import (
    CASE_SCHEMA,
    RUN_SCHEMA,
    index_inputs,
    run_localizer_scores,
)
from dtwin.core import PipelineError


def save(path,data):
    nib.save(nib.Nifti1Image(np.asarray(data,dtype=np.uint8),np.eye(4)),path)


def fixture(tmp_path):
    root=tmp_path/'inputs';rows=[]
    for n,case in enumerate(('anon-a','anon-b')):
        c=root/case;c.mkdir(parents=True);image=c/'t1.nii.gz';liver=c/'liver.nii.gz';save(image,np.zeros((8,8,8)));mask=np.zeros((8,8,8));mask[1:7,1:7,1:7]=1;save(liver,mask)
        files=[]
        for role,path in [('t1_venous',image),('liver_mask_venous',liver)]:files.append({'role':role,'relative_path':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':_sha256(path)})
        rows.append({'schema':'argos-public-liver-mri-input-v1','case_id':case,'files':files,'research_only':True,'clinical_use_allowed':False})
    manifest=tmp_path/'inputs.jsonl';manifest.write_text('\n'.join(json.dumps(row) for row in rows));return root,manifest


class FakeLocalizer:
    task='liver_lesions_mr';model_version='fake-v1'
    def localize(self,image_path,liver_mask_path,output_dir):
        output_dir.mkdir();data=np.zeros((8,8,8));data[2:4,2:4,2:4]=1;data[0,0,0]=1;path=output_dir/'liver_lesions.nii.gz';save(path,data);return path


def test_runner_persists_model_candidates_without_decision_or_ground_truth(tmp_path):
    root,manifest=fixture(tmp_path);out=tmp_path/'run';summary=run_localizer_scores(manifest_path=manifest,input_root=root,output_root=out,case_ids=['anon-a'],localizer=FakeLocalizer(),expected_source_case_count=2,selection_signature='signed')
    case=json.loads((out/'anon-a'/'localizer_manifest.json').read_text())
    assert summary['schema']==RUN_SCHEMA and summary['final_decision'] is None and summary['ground_truth_read'] is False
    assert case['schema']==CASE_SCHEMA and case['ground_truth_lesion_mask_used'] is False and case['features']['inside_liver_voxels']==8
    assert case['features']['outside_liver_voxels_removed']==1 and case['features']['component_count']==1
    assert _sha256(out/'anon-a'/'liver_lesion_candidates_in_liver.nii.gz')==case['filtered_candidate_mask_sha256']


def test_input_hash_change_is_rejected(tmp_path):
    root,manifest=fixture(tmp_path);(root/'anon-a'/'t1.nii.gz').write_bytes(b'changed')
    with pytest.raises(PipelineError,match='Hash ou bytes'):index_inputs(manifest,root,expected_case_count=2)


def test_runner_supports_explicit_non_venous_sequence_roles(tmp_path):
    root, manifest = fixture(tmp_path)
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    for row in rows:
        row['files'][0]['role'] = 't2_spir'
        row['files'][1]['role'] = 'liver_mask'
    manifest.write_text('\n'.join(json.dumps(row) for row in rows))
    out = tmp_path / 'run'
    summary = run_localizer_scores(
        manifest_path=manifest, input_root=root, output_root=out,
        case_ids=['anon-a'], localizer=FakeLocalizer(),
        expected_source_case_count=2, input_role='t2_spir',
        liver_mask_role='liver_mask',
    )
    case = json.loads((out / 'anon-a' / 'localizer_manifest.json').read_text())
    assert summary['input_role'] == 't2_spir'
    assert summary['liver_mask_role'] == 'liver_mask'
    assert case['input_role'] == 't2_spir'
    assert case['liver_mask_role'] == 'liver_mask'


def test_dataset_lesion_mask_is_rejected(tmp_path):
    root,manifest=fixture(tmp_path);rows=[json.loads(line) for line in manifest.read_text().splitlines()];rows[0]['files'].append({'role':'lesion_mask','relative_path':'anon-a/lesion.nii.gz','bytes':0,'sha256':'0'*64});manifest.write_text('\n'.join(json.dumps(row) for row in rows))
    with pytest.raises(PipelineError,match='proibido'):index_inputs(manifest,root,expected_case_count=2)


def test_duplicate_or_missing_selection_is_rejected(tmp_path):
    root,manifest=fixture(tmp_path)
    with pytest.raises(PipelineError,match='Selecao'):run_localizer_scores(manifest_path=manifest,input_root=root,output_root=tmp_path/'run',case_ids=['anon-a','anon-a'],localizer=FakeLocalizer(),expected_source_case_count=2)


class SlowLocalizer(FakeLocalizer):
    def localize(self,image_path,liver_mask_path,output_dir):
        import time;path=super().localize(image_path,liver_mask_path,output_dir);time.sleep(.02);return path


def test_time_gate_aborts_without_publishing_partial_run(tmp_path):
    root,manifest=fixture(tmp_path);out=tmp_path/'run'
    with pytest.raises(PipelineError,match='excedeu'):run_localizer_scores(manifest_path=manifest,input_root=root,output_root=out,case_ids=['anon-a'],localizer=SlowLocalizer(),expected_source_case_count=2,max_localizer_seconds=.001)
    assert not out.exists()
