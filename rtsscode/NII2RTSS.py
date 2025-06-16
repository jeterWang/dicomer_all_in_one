import os
import matplotlib.pyplot as plt
from pathlib import Path
import SimpleITK as sitk
import numpy as np
import logging
import matplotlib



from rt_utils import RTStructBuilder

logger = logging.getLogger(__name__)


def convert_nifti(
        dcm_path, mask_input, output_file, color_map=matplotlib.colormaps.get_cmap("rainbow")
):
    logger.info("Will convert the following Nifti masks to RTStruct:")

    masks = {}
    if isinstance(mask_input, dict):
        masks = mask_input
    else:
        for mask in mask_input:
            mask_parts = mask.split(",")
            masks[mask_parts[0]] = mask_parts[1]

    if not isinstance(dcm_path, Path):
        dcm_path = Path(dcm_path)

    dcm_series_path = None
    if dcm_path.is_file():
        dcm_series_path = dcm_path.parent
    else:
        dcm_series_path = dcm_path

    rtstruct = RTStructBuilder.create_new(dicom_series_path=str(dcm_series_path))

    for mask_name in masks:
        color = color_map(hash(mask_name) % 256)
        color = color[:3]
        color = [int(c * 255) for c in color]

        mask = masks[mask_name]
        if not isinstance(mask, sitk.Image):
            mask = sitk.ReadImage(str(mask))

        bool_arr = sitk.GetArrayFromImage(mask) != 0
        bool_arr = np.transpose(bool_arr, (1, 2, 0))
        rtstruct.add_roi(mask=bool_arr, color=color, name=mask_name)

    rtstruct.save(str(output_file))


def nifti_to_rtstruct(dcm_path, mask_dict, output_file, color_map=None):
    output_dir = Path(output_file).parent
    os.makedirs(output_dir, exist_ok=True)

    if color_map is None:
        color_map = plt.get_cmap("rainbow")

    convert_nifti(
        dcm_path=dcm_path,
        mask_input=mask_dict,
        output_file=output_file,
        color_map=color_map
    )

    print(f"RTSTRUCT saved to {output_file}")


if __name__ == "__main__":
    dicom_directory = r'C:\Users\elekta\Desktop\jiteng\code\dicomer_all_in_one\output\rtsstest\img'

    masks = {
        "OGSE": r'C:\Users\elekta\Desktop\jiteng\code\dicomer_all_in_one\output\rtsstest\DRM_mask.nii.gz',
    }

    output_rt_filename = r'C:\Users\elekta\Desktop\jiteng\code\dicomer_all_in_one\rtsscode'

    # 执行转换
    nifti_to_rtstruct(dicom_directory, masks, output_rt_filename)







# import os
# import matplotlib.pyplot as plt
# from pathlib import Path
# import logging
# 
# from platipy.dicom.io.nifti_to_rtstruct import convert_nifti
# logger = logging.getLogger(__name__)
# 
# 
# def nifti_to_rtstruct(dcm_path, mask_dict, output_file, color_map=None):
# 
#     output_dir = Path(output_file).parent
#     os.makedirs(output_dir, exist_ok=True)
# 
#     if color_map is None:
#         color_map = plt.get_cmap("rainbow")
# 
#     convert_nifti(
#         dcm_path=dcm_path,
#         mask_input=mask_dict,
#         output_file=output_file,
#         color_map=color_map
#     )
# 
#     print(f"RTSTRUCT saved to {output_file}")


# if __name__ == "__main__":
# 
#     dicom_directory = r'F:\DataPrecessing\OGSE_V4\Data\HYPET2OGSE\week0\HYPET2OGSEBioCellularity\images\week4_PT'
# 
#     masks = {
#         "OGSE": r'F:\DataPrecessing\OGSE_V4\Data\HYPET2OGSE\week0\mask3D.nii',
#     }
# 
#     output_rt_filename = r'F:\DataPrecessing\OGSE_V4\Data\HYPET2OGSE\week0\HYPET2OGSEBioCellularity\images\week4_PT\RTSS.dcm'
# 
#     执行转换
#     nifti_to_rtstruct(dicom_directory, masks, output_rt_filename)