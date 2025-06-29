#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试使用英文标签避免字体问题
"""

import os
import sys

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.correlation_analyzer import CorrelationAnalyzer

def test_english_labels():
    """测试使用英文标签"""
    print("Testing English Labels for Font Compatibility")
    print("=" * 50)
    
    # 文件路径
    file1 = "data/drm_data/DRM.nii.gz"
    file2 = "data/drm_data/targetDRM.nii.gz"
    output_dir = "output/english_labels_test"
    
    # 检查文件
    if not os.path.exists(file1) or not os.path.exists(file2):
        print("Files not found, skipping test")
        return
    
    # 创建分析器
    analyzer = CorrelationAnalyzer()
    
    # 设置英文自定义选项
    analyzer.custom_options = {
        'chart_title': 'DRM vs Target DRM Correlation Analysis',
        'x_label': 'DRM Pixel Values',
        'y_label': 'Target DRM Pixel Values',
        'output_prefix': 'DRM_correlation_analysis'
    }
    
    print("Loading files...")
    success1, _ = analyzer.load_nifti_file(file1, is_first=True)
    success2, _ = analyzer.load_nifti_file(file2, is_first=False)
    
    if success1 and success2:
        print("Performing analysis...")
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=output_dir
        )
        
        if success:
            print("✓ Analysis successful!")
            print(f"Result: {message}")
            
            # 检查输出文件
            if os.path.exists(output_dir):
                files = os.listdir(output_dir)
                png_files = [f for f in files if f.endswith('.png')]
                csv_files = [f for f in files if f.endswith('.csv')]
                
                if png_files:
                    print(f"✓ Generated plot: {png_files[0]}")
                if csv_files:
                    print(f"✓ Generated CSV: {csv_files[0]}")
                    
                print("\nFiles should now have clean English labels without font issues!")
        else:
            print(f"✗ Analysis failed: {message}")
    else:
        print("✗ File loading failed")

def test_mixed_languages():
    """测试混合语言标签"""
    print("\n" + "=" * 50)
    print("Testing Mixed Language Labels")
    print("=" * 50)
    
    # 文件路径
    file1 = "data/drm_data/DRM.nii.gz"
    file2 = "data/drm_data/targetDRM.nii.gz"
    output_dir = "output/mixed_labels_test"
    
    # 检查文件
    if not os.path.exists(file1) or not os.path.exists(file2):
        print("Files not found, skipping test")
        return
    
    # 创建分析器
    analyzer = CorrelationAnalyzer()
    
    # 设置混合语言选项（应该能正常显示）
    analyzer.custom_options = {
        'chart_title': 'DRM Correlation Analysis',  # 英文标题
        'x_label': 'DRM Values',                    # 英文轴标签
        'y_label': 'Target DRM Values',             # 英文轴标签
        'output_prefix': 'mixed_lang_test'
    }
    
    print("Loading files...")
    success1, _ = analyzer.load_nifti_file(file1, is_first=True)
    success2, _ = analyzer.load_nifti_file(file2, is_first=False)
    
    if success1 and success2:
        print("Performing analysis...")
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=output_dir
        )
        
        if success:
            print("✓ Mixed language analysis successful!")
            
            # 检查输出文件
            if os.path.exists(output_dir):
                files = os.listdir(output_dir)
                png_files = [f for f in files if f.endswith('.png')]
                
                if png_files:
                    print(f"✓ Generated plot: {png_files[0]}")
                    print("Chart should display properly with English labels!")
        else:
            print(f"✗ Analysis failed: {message}")
    else:
        print("✗ File loading failed")

if __name__ == "__main__":
    test_english_labels()
    test_mixed_languages()
    print("\n" + "=" * 50)
    print("Font compatibility testing completed!")
    print("Recommendation: Use English labels for maximum compatibility")
    print("=" * 50)
