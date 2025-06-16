import os
import numpy as np
import pydicom
from highdicom.rt import RTStructSet
from typing import List

def generate_rtss_with_highdicom(dicom_series_dir: str, mask: np.ndarray, roi_name: str, output_path: str):
    """
    用highdicom根据mask和DICOM序列自动生成RT Structure Set (RTSS)
    Args:
        dicom_series_dir: DICOM序列文件夹路径
        mask: 3D numpy数组，shape为(Rows, Cols, NumSlices)
        roi_name: ROI名称
        output_path: 输出RTSS DICOM文件路径
    """
    # 1. 读取DICOM序列，按InstanceNumber排序
    dicom_files = [f for f in os.listdir(dicom_series_dir) if f.lower().endswith('.dcm') and not f.startswith('RTSTRUCT')]
    if not dicom_files:
        raise RuntimeError(f"未找到DICOM序列文件: {dicom_series_dir}")
    dicom_datasets = []
    for f in dicom_files:
        ds = pydicom.dcmread(os.path.join(dicom_series_dir, f))
        dicom_datasets.append(ds)
    # 按InstanceNumber排序
    dicom_datasets.sort(key=lambda ds: int(ds.InstanceNumber))
    # 2. 检查mask shape
    rows, cols = dicom_datasets[0].Rows, dicom_datasets[0].Columns
    num_slices = len(dicom_datasets)
    if mask.shape != (rows, cols, num_slices):
        raise ValueError(f"mask shape {mask.shape} 与DICOM序列不一致，应为({rows}, {cols}, {num_slices})")
    # 3. 创建RTStructSet
    rtss = RTStructSet(referenced_series=dicom_datasets)
    # 4. 添加ROI
    rtss.add_roi(
        name=roi_name,
        mask=mask,
        frame_of_reference_uid=dicom_datasets[0].FrameOfReferenceUID,
        use_pin_hole=False
    )
    # 5. 保存RTSS
    rtss.save_as(output_path)
    print(f"RTSS已保存: {output_path}") 