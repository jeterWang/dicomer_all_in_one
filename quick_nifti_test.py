#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速测试NIfTI相关性分析功能
直接调用相关性分析器，不使用GUI
"""

import os
import sys

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.correlation_analyzer import CorrelationAnalyzer

def quick_test():
    """快速测试两个DRM文件的相关性"""
    print("快速测试 DRM.nii.gz 和 targetDRM.nii.gz 的相关性")
    print("=" * 50)
    
    # 文件路径
    file1 = "data/drm_data/DRM.nii.gz"
    file2 = "data/drm_data/targetDRM.nii.gz"
    output_dir = "output/quick_test"
    
    # 检查文件
    if not os.path.exists(file1):
        print(f"文件不存在: {file1}")
        return
    if not os.path.exists(file2):
        print(f"文件不存在: {file2}")
        return
    
    # 创建分析器
    analyzer = CorrelationAnalyzer()
    
    # 加载文件
    print("加载第一个文件...")
    success1, msg1 = analyzer.load_nifti_file(file1, is_first=True)
    print(f"结果: {msg1}")
    
    print("加载第二个文件...")
    success2, msg2 = analyzer.load_nifti_file(file2, is_first=False)
    print(f"结果: {msg2}")
    
    if success1 and success2:
        print("\n分析相关性（使用最佳掩码选项）...")
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=output_dir
        )
        
        if success:
            print("✓ 分析成功!")
            print(f"结果: {message}")
            
            # 显示关键结果
            results = analyzer.results
            print(f"\n关键结果:")
            print(f"- 有效像素数: {results['voxel_count']}")
            print(f"- Pearson相关系数: {results['pearson_r']:.4f} (p={results['pearson_p']:.2e})")
            print(f"- Spearman相关系数: {results['spearman_r']:.4f} (p={results['spearman_p']:.2e})")
            
        else:
            print(f"✗ 分析失败: {message}")
    else:
        print("文件加载失败，无法进行分析")

if __name__ == "__main__":
    quick_test()
