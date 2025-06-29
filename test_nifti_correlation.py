#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试NIfTI文件相关性分析
专门用于测试 data/drm_data/DRM.nii.gz 和 data/drm_data/targetDRM.nii.gz 的相关性
"""

import os
import sys
import logging
import pandas as pd
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.correlation_analyzer import CorrelationAnalyzer

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('nifti_correlation_test.log', encoding='utf-8')
        ]
    )

def test_nifti_correlation():
    """测试NIfTI文件相关性分析"""
    print("=" * 60)
    print("测试NIfTI文件相关性分析")
    print("=" * 60)
    
    # 设置文件路径
    nifti1_path = "data/drm_data/DRM.nii.gz"
    nifti2_path = "data/drm_data/targetDRM.nii.gz"
    output_dir = "output/nifti_correlation_test"
    
    # 检查文件是否存在
    if not os.path.exists(nifti1_path):
        print(f"错误: 文件不存在 - {nifti1_path}")
        return False
        
    if not os.path.exists(nifti2_path):
        print(f"错误: 文件不存在 - {nifti2_path}")
        return False
    
    print(f"第一个NIfTI文件: {nifti1_path}")
    print(f"第二个NIfTI文件: {nifti2_path}")
    print(f"输出目录: {output_dir}")
    
    # 创建相关性分析器
    analyzer = CorrelationAnalyzer()
    
    # 加载第一个NIfTI文件
    print("\n步骤1: 加载第一个NIfTI文件...")
    success, message = analyzer.load_nifti_file(nifti1_path, is_first=True)
    if not success:
        print(f"加载第一个NIfTI文件失败: {message}")
        return False
    print(f"成功: {message}")
    
    # 加载第二个NIfTI文件
    print("\n步骤2: 加载第二个NIfTI文件...")
    success, message = analyzer.load_nifti_file(nifti2_path, is_first=False)
    if not success:
        print(f"加载第二个NIfTI文件失败: {message}")
        return False
    print(f"成功: {message}")
    
    # 测试不同的掩码选项
    mask_options = [
        ("non_zero_first", "第一个图像的所有非零像素"),
        ("non_zero_both", "两个图像都非零的像素"),
        ("positive_first", "第一个图像的所有正值像素"),
        ("threshold_first", "第一个图像超过阈值的像素(>0.1)")
    ]
    
    print(f"\n步骤3: 分析相关性...")
    print(f"将测试 {len(mask_options)} 种不同的掩码选项:")
    
    results = []
    
    for mask_option, description in mask_options:
        print(f"\n--- 测试掩码选项: {description} ---")
        
        # 为每种掩码选项创建单独的输出目录
        option_output_dir = os.path.join(output_dir, mask_option)
        
        # 分析相关性
        success, message = analyzer.analyze_nifti_correlation(
            mask_option=mask_option,
            threshold=0.1,
            output_dir=option_output_dir
        )
        
        if success:
            print(f"✓ 成功: {message}")
            
            # 获取结果
            result = analyzer.results.copy()
            result['mask_option_name'] = description
            results.append(result)
            
        else:
            print(f"✗ 失败: {message}")
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("分析结果汇总")
    print("=" * 60)
    
    if results:
        print(f"成功分析了 {len(results)} 种掩码选项:")
        print()
        
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['mask_option_name']}")
            print(f"   体素数量: {result['voxel_count']:,}")
            print(f"   Pearson相关系数: r={result['pearson_r']:.4f}, p={result['pearson_p']:.2e}")
            print(f"   Spearman相关系数: r={result['spearman_r']:.4f}, p={result['spearman_p']:.2e}")
            print()
        
        # 找出最佳结果
        best_result = max(results, key=lambda x: abs(x['pearson_r']) if not pd.isna(x['pearson_r']) else 0)
        print(f"最高相关性结果: {best_result['mask_option_name']}")
        print(f"Pearson r = {best_result['pearson_r']:.4f}")
        
        print(f"\n所有结果已保存到: {output_dir}")
        return True
    else:
        print("没有成功的分析结果")
        return False

if __name__ == "__main__":
    setup_logging()
    
    try:
        success = test_nifti_correlation()
        if success:
            print("\n✓ 测试完成!")
        else:
            print("\n✗ 测试失败!")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试过程中出现异常: {e}")
        logging.error(f"测试异常: {e}", exc_info=True)
        sys.exit(1)
