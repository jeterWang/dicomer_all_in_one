#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试自定义NIfTI相关性分析功能
验证自定义图表标题、轴标签和输出文件前缀
"""

import os
import sys

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.correlation_analyzer import CorrelationAnalyzer

def test_custom_analysis():
    """测试自定义选项的相关性分析"""
    print("测试自定义NIfTI相关性分析功能")
    print("=" * 50)
    
    # 文件路径
    file1 = "data/drm_data/DRM.nii.gz"
    file2 = "data/drm_data/targetDRM.nii.gz"
    output_dir = "output/custom_analysis_test"
    
    # 检查文件
    if not os.path.exists(file1):
        print(f"文件不存在: {file1}")
        return
    if not os.path.exists(file2):
        print(f"文件不存在: {file2}")
        return
    
    # 创建分析器
    analyzer = CorrelationAnalyzer()
    
    # 设置自定义选项
    custom_options = {
        'chart_title': 'DRM vs Target DRM 相关性分析',
        'x_label': 'DRM 像素值',
        'y_label': 'Target DRM 像素值',
        'output_prefix': 'DRM_analysis'
    }
    
    analyzer.custom_options = custom_options
    
    print("自定义选项:")
    print(f"  图表标题: {custom_options['chart_title']}")
    print(f"  X轴标签: {custom_options['x_label']}")
    print(f"  Y轴标签: {custom_options['y_label']}")
    print(f"  输出前缀: {custom_options['output_prefix']}")
    print()
    
    # 加载文件
    print("加载第一个文件...")
    success1, msg1 = analyzer.load_nifti_file(file1, is_first=True)
    print(f"结果: {msg1}")
    
    print("加载第二个文件...")
    success2, msg2 = analyzer.load_nifti_file(file2, is_first=False)
    print(f"结果: {msg2}")
    
    if success1 and success2:
        print("\n分析相关性（使用自定义选项）...")
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
            
            # 检查输出文件
            print(f"\n检查输出文件:")
            output_files = os.listdir(output_dir)
            for file in output_files:
                if file.startswith(custom_options['output_prefix']):
                    print(f"✓ 找到自定义前缀文件: {file}")
                    
        else:
            print(f"✗ 分析失败: {message}")
    else:
        print("文件加载失败，无法进行分析")

def test_multiple_custom_options():
    """测试多种不同的自定义选项"""
    print("\n" + "=" * 50)
    print("测试多种自定义选项")
    print("=" * 50)
    
    # 文件路径
    file1 = "data/drm_data/DRM.nii.gz"
    file2 = "data/drm_data/targetDRM.nii.gz"
    
    # 不同的自定义选项组合
    test_cases = [
        {
            'name': '医学影像分析',
            'options': {
                'chart_title': '医学影像相关性分析',
                'x_label': '原始影像强度',
                'y_label': '目标影像强度',
                'output_prefix': 'medical_analysis'
            },
            'output_dir': 'output/medical_test'
        },
        {
            'name': '简洁版本',
            'options': {
                'chart_title': 'Image Correlation',
                'x_label': 'Image A',
                'y_label': 'Image B',
                'output_prefix': 'simple'
            },
            'output_dir': 'output/simple_test'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {test_case['name']}")
        print("-" * 30)
        
        # 创建新的分析器
        analyzer = CorrelationAnalyzer()
        analyzer.custom_options = test_case['options']
        
        # 加载文件
        analyzer.load_nifti_file(file1, is_first=True)
        analyzer.load_nifti_file(file2, is_first=False)
        
        # 分析
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=test_case['output_dir']
        )
        
        if success:
            print(f"✓ {test_case['name']} 分析成功")
            # 检查文件是否使用了正确的前缀
            output_files = os.listdir(test_case['output_dir'])
            prefix_files = [f for f in output_files if f.startswith(test_case['options']['output_prefix'])]
            print(f"  生成了 {len(prefix_files)} 个带自定义前缀的文件")
        else:
            print(f"✗ {test_case['name']} 分析失败: {message}")

if __name__ == "__main__":
    try:
        test_custom_analysis()
        test_multiple_custom_options()
        print("\n✓ 所有测试完成!")
    except Exception as e:
        print(f"\n✗ 测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
