import os
import numpy as np
import SimpleITK as sitk
from platipy.imaging.dicom.io import write_rtstruct

# 1. 读取 DICOM series
dicom_dir = "output/forplatipy/img"  # 根据实际路径调整
reader = sitk.ImageSeriesReader()
series_IDs = reader.GetGDCMSeriesIDs(dicom_dir)
if not series_IDs:
    raise RuntimeError(f"No DICOM series found in {dicom_dir}")
series_file_names = reader.GetGDCMSeriesFileNames(dicom_dir, series_IDs[0])
reader.SetFileNames(series_file_names)
ref_img = reader.Execute()  # SimpleITK.Image

# 2. 生成球体掩膜（与参考影像空间一致）
size = ref_img.GetSize()
spacing = ref_img.GetSpacing()
origin = ref_img.GetOrigin()
direction = ref_img.GetDirection()

# 球心为影像中心，半径为体积较小轴的1/4
center = [origin[i] + spacing[i] * (size[i] / 2) for i in range(3)]
radius = min([spacing[i] * size[i] for i in range(3)]) / 4

# 生成球体掩膜
mask_array = np.zeros((size[2], size[1], size[0]), dtype=np.uint8)  # z, y, x
for z in range(size[2]):
    for y in range(size[1]):
        for x in range(size[0]):
            pt = ref_img.TransformIndexToPhysicalPoint((x, y, z))
            dist = np.sqrt(sum([(pt[i] - center[i]) ** 2 for i in range(3)]))
            if dist <= radius:
                mask_array[z, y, x] = 1

sphere_mask = sitk.GetImageFromArray(mask_array)
sphere_mask.CopyInformation(ref_img)

# 3. 构建结构集字典
structure_set = {"Sphere": sphere_mask}

# 4. 写入 RTSS
write_rtstruct(
    dicom_dir,
    structure_set,
    filename="output_rtss.dcm",
    description="Test RT Structure Set"
)

print("RTSS 已生成：output_rtss.dcm") 