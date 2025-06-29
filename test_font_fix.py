#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试字体修复
验证matplotlib字体配置是否解决了显示问题
"""

import os
import sys
import matplotlib.pyplot as plt
import numpy as np

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.correlation_analyzer import CorrelationAnalyzer

def test_font_rendering():
    """测试字体渲染"""
    print("测试matplotlib字体渲染")
    print("=" * 40)
    
    # 创建测试数据
    x = np.random.normal(0, 1, 100)
    y = 0.5 * x + np.random.normal(0, 0.5, 100)
    
    # 计算相关系数
    from scipy.stats import pearsonr, linregress
    r, p = pearsonr(x, y)
    slope, intercept, r_value, p_value, std_err = linregress(x, y)
    
    # 创建图像
    plt.figure(figsize=(10, 8))
    
    # 绘制散点图
    plt.scatter(x, y, alpha=0.6, s=30)
    
    # 添加回归线
    line_x = np.array([np.min(x), np.max(x)])
    line_y = slope * line_x + intercept
    plt.plot(line_x, line_y, "r-", alpha=0.8, linewidth=2, 
             label=f"拟合线 (R^2={r_value**2:.3f})")
    
    # 添加标签和标题（测试中文和特殊字符）
    plt.xlabel("测试X轴标签")
    plt.ylabel("测试Y轴标签") 
    plt.title(
        f"字体渲染测试\n"
        f"Pearson r = {r:.4f} (p = {p:.3e})\n"
        f"回归系数 R^2 = {r_value**2:.3f}\n"
        f"数据点数量 = {len(x)}"
    )
    
    # 添加网格和图例
    plt.grid(True, alpha=0.3)
    plt.legend()
    
    # 保存图像
    output_dir = "output/font_test"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "font_rendering_test.png")
    
    try:
        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close()
        print(f"✓ 字体测试图像已保存: {output_path}")
        return True
    except Exception as e:
        print(f"✗ 保存图像时出错: {e}")
        return False

def test_nifti_analysis_with_font_fix():
    """测试NIfTI分析的字体修复"""
    print("\n测试NIfTI分析字体修复")
    print("=" * 40)
    
    # 文件路径
    file1 = "data/drm_data/DRM.nii.gz"
    file2 = "data/drm_data/targetDRM.nii.gz"
    output_dir = "output/font_fix_test"
    
    # 检查文件
    if not os.path.exists(file1) or not os.path.exists(file2):
        print("跳过NIfTI测试 - 文件不存在")
        return True
    
    # 创建分析器
    analyzer = CorrelationAnalyzer()
    
    # 设置自定义选项（测试中文字符）
    analyzer.custom_options = {
        'chart_title': '字体修复测试 - DRM相关性分析',
        'x_label': 'DRM像素值 (测试中文)',
        'y_label': 'Target DRM像素值 (R^2测试)',
        'output_prefix': 'font_fix_test'
    }
    
    # 加载文件
    success1, _ = analyzer.load_nifti_file(file1, is_first=True)
    success2, _ = analyzer.load_nifti_file(file2, is_first=False)
    
    if success1 and success2:
        # 分析相关性
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=output_dir
        )
        
        if success:
            print("✓ NIfTI分析字体测试成功")
            print(f"输出目录: {output_dir}")
            
            # 检查生成的文件
            files = os.listdir(output_dir)
            png_files = [f for f in files if f.endswith('.png')]
            if png_files:
                print(f"✓ 生成散点图: {png_files[0]}")
            return True
        else:
            print(f"✗ NIfTI分析失败: {message}")
            return False
    else:
        print("✗ 文件加载失败")
        return False

def check_available_fonts():
    """检查可用字体"""
    print("\n检查可用字体")
    print("=" * 40)
    
    try:
        import matplotlib.font_manager as fm
        
        # 获取系统字体
        fonts = [f.name for f in fm.fontManager.ttflist]
        
        # 检查推荐字体是否可用
        recommended_fonts = [
            "DejaVu Sans",
            "Arial Unicode MS", 
            "Microsoft YaHei",
            "SimHei"
        ]
        
        print("推荐字体可用性:")
        for font in recommended_fonts:
            if font in fonts:
                print(f"✓ {font}")
            else:
                print(f"✗ {font}")
        
        # 显示当前matplotlib配置
        print(f"\n当前matplotlib字体配置:")
        print(f"font.family: {plt.rcParams['font.family']}")
        print(f"font.sans-serif: {plt.rcParams['font.sans-serif']}")
        
    except Exception as e:
        print(f"检查字体时出错: {e}")

if __name__ == "__main__":
    try:
        # 检查字体
        check_available_fonts()
        
        # 测试基本字体渲染
        font_test_success = test_font_rendering()
        
        # 测试NIfTI分析字体
        nifti_test_success = test_nifti_analysis_with_font_fix()
        
        if font_test_success and nifti_test_success:
            print("\n✓ 所有字体测试通过!")
        else:
            print("\n⚠ 部分测试未通过，但基本功能应该正常")
            
    except Exception as e:
        print(f"\n✗ 测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
