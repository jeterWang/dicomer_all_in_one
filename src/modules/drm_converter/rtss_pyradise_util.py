import os
import numpy as np
import pyradise.data as ps_data
import pyradise.fileio as ps_io
from typing import Any


def generate_rtss_with_pyradise(
    dicom_series_dir: str, mask: np.ndarray, output_path: str, roi_name: str = "mask"
):
    """
    用pyradise根据mask和DICOM序列自动生成RT Structure Set (RTSS)
    Args:
        dicom_series_dir: DICOM序列文件夹路径
        mask: 3D numpy数组，shape为(Rows, Cols, NumSlices)
        output_path: 输出RTSS DICOM文件路径
        roi_name: ROI名称，默认'mask'
    """
    # 1. 加载DICOM序列
    dcm_crawler = ps_io.SubjectDicomCrawler(dicom_series_dir)
    dicom_series_info = dcm_crawler.execute()
    if not dicom_series_info:
        raise RuntimeError(f"未找到DICOM序列: {dicom_series_dir}")

    # 2. 构造Subject对象
    # 这里只构造一个分割结构，名为roi_name
    organ = ps_data.Organ(roi_name)
    annotator = ps_data.Annotator("auto")
    seg_img = ps_data.SegmentationImage(mask, organ, annotator)
    subject = ps_data.Subject("subject")
    subject.add_image(seg_img)

    # 3. 选择参考DICOM序列（取第一个）
    reference_modality = dicom_series_info[0].modality
    selection = ps_io.NoRTSSInfoSelector()
    dicom_series_info = selection.execute(dicom_series_info)

    # 4. 配置RTSS转换器（默认用3D算法）
    conv_conf = ps_io.RTSSConverter3DConfiguration()
    converter = ps_io.SubjectToRTSSConverter(
        subject, dicom_series_info, reference_modality, conv_conf
    )
    rtss = converter.convert()

    # 5. 保存RTSS
    writer = ps_io.DicomSeriesSubjectWriter()
    rtss_combination = ((os.path.basename(output_path), rtss),)
    writer.write(
        rtss_combination, os.path.dirname(output_path), "subject", dicom_series_info
    )
    print(f"[pyradise] RTSS已保存: {output_path}")
