import SimpleITK as sitk

from dtwin.benchmark.openswisshcc_multisequence_geometry import _geometry_matches


def _image():
    image = sitk.Image([8, 9, 10], sitk.sitkFloat32)
    image.SetSpacing((1.2, 1.3, 3.0))
    image.SetOrigin((10.0, -5.0, 2.0))
    image.SetDirection((-0.999780683333377, 0.0, 0.020942425330449897,
                        0.0, -1.0, 0.0,
                        0.020942426636996053, 0.0, 0.9997806833607452))
    return image


def test_geometry_accepts_submicrometric_nifti_rounding():
    left = _image()
    right = _image()
    direction = list(right.GetDirection())
    direction[0] += 4e-11
    direction[2] += 2e-9
    right.SetDirection(direction)
    assert _geometry_matches(left, right)


def test_geometry_rejects_material_origin_shift():
    left = _image()
    right = _image()
    right.SetOrigin((10.01, -5.0, 2.0))
    assert not _geometry_matches(left, right)


def test_geometry_rejects_size_difference():
    assert not _geometry_matches(_image(), sitk.Image([8, 9, 11], sitk.sitkFloat32))
