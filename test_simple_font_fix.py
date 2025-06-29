#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单的字体修复测试
"""

import os
import sys

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.correlation_analyzer import CorrelationAnalyzer

def test_simple_analysis():
    """简单测试分析功能"""
    print("简单字体修复测试")
    print("=" * 30)
    
    # 文件路径
    file1 = "data/drm_data/DRM.nii.gz"
    file2 = "data/drm_data/targetDRM.nii.gz"
    output_dir = "output/simple_font_test"
    
    # 检查文件
    if not os.path.exists(file1) or not os.path.exists(file2):
        print("文件不存在，跳过测试")
        return
    
    # 创建分析器
    analyzer = CorrelationAnalyzer()
    
    # 设置简单的自定义选项
    analyzer.custom_options = {
        'chart_title': 'Font Fix Test',
        'x_label': 'Image 1 Values',
        'y_label': 'Image 2 Values',
        'output_prefix': 'font_test'
    }
    
    print("加载文件...")
    success1, _ = analyzer.load_nifti_file(file1, is_first=True)
    success2, _ = analyzer.load_nifti_file(file2, is_first=False)
    
    if success1 and success2:
        print("执行分析...")
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=output_dir
        )
        
        if success:
            print("✓ 分析成功!")
            print(f"结果: {message}")
            
            # 检查输出文件
            if os.path.exists(output_dir):
                files = os.listdir(output_dir)
                png_files = [f for f in files if f.endswith('.png')]
                if png_files:
                    print(f"✓ 生成图像: {png_files[0]}")
                    print("请检查图像中是否还有字体问题")
        else:
            print(f"✗ 分析失败: {message}")
    else:
        print("✗ 文件加载失败")

if __name__ == "__main__":
    test_simple_analysis()
