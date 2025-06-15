#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试DRM转换后的数值精度
"""

import pydicom
import numpy as np
import os

def test_precision():
    """测试转换后的数值精度"""
    dicom_dir = "output/drm_converter_test/FAPI_DRM_DRM_DICOM"
    
    if not os.path.exists(dicom_dir):
        print(f"目录不存在: {dicom_dir}")
        return
    
    dcm_files = [f for f in os.listdir(dicom_dir) if f.endswith('.dcm')]
    if not dcm_files:
        print("未找到DICOM文件")
        return
    
    # 读取第一个文件进行测试
    first_file = os.path.join(dicom_dir, dcm_files[0])
    ds = pydicom.dcmread(first_file)
    
    print("=" * 60)
    print("DICOM数值精度测试")
    print("=" * 60)
    
    # 显示rescale参数
    slope = float(ds.RescaleSlope) if hasattr(ds, 'RescaleSlope') else 1.0
    intercept = float(ds.RescaleIntercept) if hasattr(ds, 'RescaleIntercept') else 0.0
    
    print(f"RescaleSlope: {slope}")
    print(f"RescaleIntercept: {intercept}")
    print(f"RescaleType: {getattr(ds, 'RescaleType', 'N/A')}")
    
    # 获取原始像素数据
    pixel_array = ds.pixel_array
    print(f"像素数据类型: {pixel_array.dtype}")
    print(f"像素数据形状: {pixel_array.shape}")
    print(f"原始像素值范围: {np.min(pixel_array)} 到 {np.max(pixel_array)}")
    
    # 计算真实数值（应用rescale参数）
    real_values = pixel_array * slope + intercept
    print(f"真实数值范围: {np.min(real_values):.10f} 到 {np.max(real_values):.10f}")
    
    # 检查一些具体数值
    print("\n像素值示例（原始 -> 真实）:")
    sample_indices = [(0, 0), (50, 50), (100, 100), (150, 150)]
    for i, j in sample_indices:
        if i < pixel_array.shape[0] and j < pixel_array.shape[1]:
            original = pixel_array[i, j]
            real = original * slope + intercept
            print(f"  位置({i},{j}): {original} -> {real:.10f}")
    
    # 计算精度损失
    print(f"\n精度分析:")
    print(f"理论最小分辨率: {slope:.12f}")
    print(f"对于0-10范围的数据，精度约为: {slope*10:.10f}")
    
    # 检查多个文件的一致性
    if len(dcm_files) >= 3:
        print(f"\n检查多个文件的一致性:")
        for i, filename in enumerate(dcm_files[:3]):
            filepath = os.path.join(dicom_dir, filename)
            test_ds = pydicom.dcmread(filepath)
            test_slope = float(test_ds.RescaleSlope) if hasattr(test_ds, 'RescaleSlope') else 1.0
            test_intercept = float(test_ds.RescaleIntercept) if hasattr(test_ds, 'RescaleIntercept') else 0.0
            test_array = test_ds.pixel_array
            test_real = test_array * test_slope + test_intercept
            
            print(f"  文件 {i+1}: Slope={test_slope:.10f}, Intercept={test_intercept:.10f}")
            print(f"    真实值范围: {np.min(test_real):.6f} 到 {np.max(test_real):.6f}")

if __name__ == "__main__":
    test_precision() 