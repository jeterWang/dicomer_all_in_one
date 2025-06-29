import os
import numpy as np
import nibabel as nib
import SimpleITK as sitk
from rtss_pyradise_util import generate_rtss_with_pyradise


def test_generate_rtss_with_pyradise():
    # 路径配置（全部为绝对路径）
    dicom_series_dir = r"C:/Users/76090/codes/python/dicomer_all_in_one/data/drm_converter/FAPI_DRM/24042517_07255372_CT_2024-04-26_213155_Ga-68PETCT.WB(Chest+ABD)_CT.WB_n337__00000"
    nii_path = r"C:/Users/76090/codes/python/dicomer_all_in_one/data/drm_converter/FAPI_DRM/DRM.nii.gz"
    rtss_output_path = os.path.join(dicom_series_dir, "RTSTRUCT_pyradise_test.dcm")

    # 读取mask
    nii_img = nib.load(nii_path)
    mask = nii_img.get_fdata()
    # 若为概率图，转为bool
    if mask.dtype != np.bool_:
        mask = mask > 0.5
    mask = mask.astype(np.uint8)
    # 转为SimpleITK.Image
    mask_img = sitk.GetImageFromArray(mask)

    # 调用生成RTSS
    generate_rtss_with_pyradise(
        dicom_series_dir, mask_img, rtss_output_path, roi_name="mask"
    )
    print(f"测试完成，RTSS已保存: {rtss_output_path}")


if __name__ == "__main__":
    test_generate_rtss_with_pyradise()
