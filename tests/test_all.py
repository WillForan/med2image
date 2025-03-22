from unittest.mock import MagicMock
from med2image import med2image
from nibabel.testing import data_path
import os

def test_findnii():
    """
    Correctly setup for .nii.gz
    """
    args = MagicMock()
    args.inputFile = data_path / "standard.nii.gz"
    nii_obj = med2image.object_factoryCreate(args)
    assert type(nii_obj.C_convert) == med2image.med2image_nii

def test_finddcm(tmp_path):
    """
    Can use both '.dcm' and 'MR.....'
    """
    args = MagicMock()
    ex_path = data_path / "0.dcm"
    args.inputFile = ex_path
    dcm_obj = med2image.object_factoryCreate(args)
    assert type(dcm_obj.C_convert) == med2image.med2image_dcm

    ex_MR = tmp_path / "MR.0000000.0000000.000000"
    os.system(f"ln -sf '{ex_path}' '{ex_MR}'")
    args.inputFile = ex_MR
    dcm_objMR = med2image.object_factoryCreate(args)
    assert type(dcm_objMR.C_convert) == med2image.med2image_dcm
