#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查生成的DICOM文件的关键标签
"""

import pydicom
import os

def check_dicom_tags():
    """检查DICOM文件的关键标签"""
    dicom_dir = "output/drm_converter_test/FAPI_DRM_DRM_DICOM"
    
    if not os.path.exists(dicom_dir):
        print(f"目录不存在: {dicom_dir}")
        return
    
    dcm_files = [f for f in os.listdir(dicom_dir) if f.endswith('.dcm')]
    dcm_files.sort()
    
    print(f"找到 {len(dcm_files)} 个DICOM文件")
    print("=" * 80)
    
    # 检查前5个文件
    for i, filename in enumerate(dcm_files[:5]):
        filepath = os.path.join(dicom_dir, filename)
        ds = pydicom.dcmread(filepath)
        
        print(f"文件 {i+1}: {filename}")
        print(f"  StudyInstanceUID: {getattr(ds, 'StudyInstanceUID', 'N/A')}")
        print(f"  SeriesInstanceUID: {getattr(ds, 'SeriesInstanceUID', 'N/A')}")
        print(f"  SOPInstanceUID: {getattr(ds, 'SOPInstanceUID', 'N/A')}")
        print(f"  InstanceNumber: {getattr(ds, 'InstanceNumber', 'N/A')}")
        print(f"  SeriesNumber: {getattr(ds, 'SeriesNumber', 'N/A')}")
        print(f"  SeriesDescription: {getattr(ds, 'SeriesDescription', 'N/A')}")
        print(f"  SliceLocation: {getattr(ds, 'SliceLocation', 'N/A')}")
        print(f"  ImagePositionPatient: {getattr(ds, 'ImagePositionPatient', 'N/A')}")
        print(f"  Rows x Columns: {getattr(ds, 'Rows', 'N/A')} x {getattr(ds, 'Columns', 'N/A')}")
        print(f"  NumberOfFrames: {getattr(ds, 'NumberOfFrames', 'N/A')}")
        print("-" * 50)
    
    # 检查最后几个文件
    print("\n最后几个文件:")
    for i, filename in enumerate(dcm_files[-3:]):
        filepath = os.path.join(dicom_dir, filename)
        ds = pydicom.dcmread(filepath)
        
        print(f"文件 {len(dcm_files)-2+i}: {filename}")
        print(f"  InstanceNumber: {getattr(ds, 'InstanceNumber', 'N/A')}")
        print(f"  SliceLocation: {getattr(ds, 'SliceLocation', 'N/A')}")
        print(f"  ImagePositionPatient Z: {getattr(ds, 'ImagePositionPatient', ['N/A'])[2] if hasattr(ds, 'ImagePositionPatient') else 'N/A'}")
        print("-" * 30)

if __name__ == "__main__":
    check_dicom_tags() 