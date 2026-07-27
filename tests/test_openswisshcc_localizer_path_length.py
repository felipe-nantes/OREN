from pathlib import Path

import nibabel as nib
import numpy as np

from dtwin.benchmark import openswisshcc_lesion_localizer as localizer


def test_atomic_mask_uses_short_temporary_basename(tmp_path, monkeypatch):
    reference = nib.Nifti1Image(np.zeros((2, 2, 2), dtype=np.uint8), np.eye(4))
    destination = tmp_path / "liver_lesion_candidates_in_liver.nii.gz"
    monkeypatch.setattr(localizer.uuid, "uuid4", lambda: type("U", (), {"hex": "a" * 32})())
    observed = []
    original_save = localizer.nib.save

    def recording_save(image, path):
        observed.append(Path(path).name)
        original_save(image, path)

    monkeypatch.setattr(localizer.nib, "save", recording_save)
    localizer._save_mask_atomic(np.zeros((2, 2, 2), dtype=bool), reference, destination)
    assert observed == ["._m_aaaaaaaa.nii.gz"]
    assert destination.is_file()
    assert not (tmp_path / observed[0]).exists()
