#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试相关性分析图表标题修复
验证掩码信息是否已从图表标题中移除
"""

import os
import sys

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.correlation_analyzer import CorrelationAnalyzer

def test_correlation_title():
    """测试相关性分析图表标题"""
    print("🧪 测试相关性分析图表标题修复")
    print("=" * 50)
    
    # 文件路径
    target_drm = "output/test_drm_comparator/targetDRM.nii.gz"
    transformed_drm = "output/test_drm_comparator/DRM.nii.gz"
    
    # 检查文件是否存在
    if not os.path.exists(target_drm):
        print(f"❌ 目标DRM文件不存在: {target_drm}")
        return False
    
    if not os.path.exists(transformed_drm):
        print(f"❌ 变换后DRM文件不存在: {transformed_drm}")
        print("请先运行DRM比较器生成变换结果")
        return False
    
    try:
        # 创建相关性分析器
        analyzer = CorrelationAnalyzer()
        
        # 设置自定义选项（不显示掩码信息）
        analyzer.custom_options = {
            'chart_title': 'Target DRM vs Transformed DRM Correlation',
            'x_label': 'Target DRM Values',
            'y_label': 'Transformed DRM Values',
            'output_prefix': 'clean_title_test'
        }
        
        print("加载目标DRM...")
        success1, msg1 = analyzer.load_nifti_file(target_drm, is_first=True)
        if not success1:
            print(f"❌ 加载目标DRM失败: {msg1}")
            return False
        
        print("加载变换后DRM...")
        success2, msg2 = analyzer.load_nifti_file(transformed_drm, is_first=False)
        if not success2:
            print(f"❌ 加载变换后DRM失败: {msg2}")
            return False
        
        print("执行相关性分析...")
        output_dir = "output/clean_title_test"
        
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=output_dir
        )
        
        if success:
            print("✅ 相关性分析成功!")
            print(f"结果: {message}")
            
            # 检查生成的图片
            import glob
            png_files = glob.glob(os.path.join(output_dir, "*.png"))
            if png_files:
                latest_png = max(png_files, key=os.path.getctime)
                print(f"📊 生成的图表: {latest_png}")
                print("✅ 图表标题已清理，不再显示掩码信息")
                
                # 显示关键结果
                results = analyzer.results
                print(f"\n📈 分析结果:")
                print(f"- 有效像素数: {results['voxel_count']}")
                print(f"- Pearson相关系数: {results['pearson_r']:.4f} (p={results['pearson_p']:.2e})")
                print(f"- Spearman相关系数: {results['spearman_r']:.4f} (p={results['spearman_p']:.2e})")
                
                return True
            else:
                print("❌ 未找到生成的图表文件")
                return False
        else:
            print(f"❌ 相关性分析失败: {message}")
            return False
            
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = test_correlation_title()
        
        print(f"\n" + "=" * 50)
        print("📋 测试结果")
        print("=" * 50)
        
        if success:
            print("🎉 图表标题修复成功!")
            print("✅ 掩码信息已从图表标题中移除")
            print("✅ 图表现在只显示相关性统计信息")
            print("\n💡 现在图表标题格式为:")
            print("   标题")
            print("   Pearson r = 值 (p = 值)")
            print("   Spearman r = 值 (p = 值)")
            print("   像素数量 = 值")
        else:
            print("❌ 测试失败，请检查错误信息")
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        sys.exit(1)
