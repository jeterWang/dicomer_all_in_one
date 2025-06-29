#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试DRM比较器的直接重采样功能
验证新的优化方法是否能减少插值误差
"""

import os
import sys
import SimpleITK as sitk

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.drm_comparator.drm_comparator import DrmComparator
from modules.correlation_analyzer import CorrelationAnalyzer

def test_direct_resampling():
    """测试直接重采样功能"""
    print("🚀 测试DRM比较器直接重采样功能")
    print("=" * 60)
    
    # 文件路径
    nifti_path = "data/drm_data/DRM.nii.gz"
    rigid_path = "data/drm_data/moving.dcm"
    dvf_path = "data/drm_data/deformable.dcm"
    target_path = "data/drm_data/targetDRM.nii.gz"
    
    # 检查文件是否存在
    files_to_check = [
        (nifti_path, "原始DRM"),
        (rigid_path, "刚体变换"),
        (dvf_path, "DVF变换"),
        (target_path, "目标DRM")
    ]
    
    print("步骤1: 检查输入文件")
    print("-" * 30)
    for file_path, description in files_to_check:
        if os.path.exists(file_path):
            print(f"✅ {description}: {file_path}")
        else:
            print(f"❌ {description}: 文件不存在 - {file_path}")
            return False
    
    # 创建DRM比较器
    print(f"\n步骤2: 创建DRM比较器并加载数据")
    print("-" * 30)
    
    comparator = DrmComparator()
    
    # 加载数据
    print("加载NIfTI图像...")
    if not comparator.load_nifti(nifti_path):
        print("❌ 加载NIfTI图像失败")
        return False
    
    print("加载刚体变换...")
    if not comparator.load_rigid_transform(rigid_path):
        print("❌ 加载刚体变换失败")
        return False
    
    print("加载DVF变换...")
    if not comparator.load_dvf(dvf_path):
        print("❌ 加载DVF变换失败")
        return False
    
    print("✅ 所有数据加载成功")
    
    # 测试新的直接重采样方法
    print(f"\n步骤3: 测试直接重采样到目标空间")
    print("-" * 30)
    
    success, message = comparator.apply_transformations(
        target_image_path=target_path,
        direct_to_target=True  # 使用新的直接重采样方法
    )
    
    if success:
        print("✅ 直接重采样成功!")
        print(f"结果: {message}")
        
        # 保存结果
        output_dir = "output/direct_resampling_test"
        os.makedirs(output_dir, exist_ok=True)
        
        direct_output = os.path.join(output_dir, "direct_resampling_result.nii.gz")
        success_save, save_msg = comparator.save_target_space_image(direct_output)
        
        if success_save:
            print(f"✅ 结果已保存: {direct_output}")
        else:
            print(f"❌ 保存失败: {save_msg}")
            
    else:
        print(f"❌ 直接重采样失败: {message}")
        return False
    
    return True

def test_method_comparison():
    """测试两种重采样方法的对比"""
    print(f"\n🔬 测试两种重采样方法的对比")
    print("=" * 60)
    
    # 文件路径
    nifti_path = "data/drm_data/DRM.nii.gz"
    rigid_path = "data/drm_data/moving.dcm"
    dvf_path = "data/drm_data/deformable.dcm"
    target_path = "data/drm_data/targetDRM.nii.gz"
    
    # 创建新的比较器实例
    comparator = DrmComparator()
    
    # 加载数据
    print("重新加载数据进行对比测试...")
    comparator.load_nifti(nifti_path)
    comparator.load_rigid_transform(rigid_path)
    comparator.load_dvf(dvf_path)
    
    # 执行对比测试
    output_dir = "output/resampling_comparison"
    success, comparison_result = comparator.compare_resampling_methods(
        target_path, output_dir
    )
    
    if success:
        print("✅ 对比测试完成!")
        print(comparison_result)
    else:
        print(f"❌ 对比测试失败: {comparison_result}")
        return False
    
    return True

def test_correlation_analysis_with_direct_method():
    """使用直接重采样结果进行相关性分析"""
    print(f"\n📊 使用直接重采样结果进行相关性分析")
    print("=" * 60)
    
    # 文件路径
    target_drm = "data/drm_data/targetDRM.nii.gz"
    direct_result = "output/direct_resampling_test/direct_resampling_result.nii.gz"
    
    # 检查文件是否存在
    if not os.path.exists(direct_result):
        print(f"❌ 直接重采样结果文件不存在: {direct_result}")
        print("请先运行直接重采样测试")
        return False
    
    # 创建相关性分析器
    analyzer = CorrelationAnalyzer()
    
    # 设置自定义选项
    analyzer.custom_options = {
        'chart_title': 'Target DRM vs Direct Resampled DRM Correlation',
        'x_label': 'Target DRM Values',
        'y_label': 'Direct Resampled DRM Values',
        'output_prefix': 'direct_resampling_correlation'
    }
    
    print("加载目标DRM...")
    success1, msg1 = analyzer.load_nifti_file(target_drm, is_first=True)
    print(f"结果: {msg1}")
    
    print("加载直接重采样结果...")
    success2, msg2 = analyzer.load_nifti_file(direct_result, is_first=False)
    print(f"结果: {msg2}")
    
    if success1 and success2:
        print("执行相关性分析...")
        output_dir = "output/direct_resampling_correlation"
        
        success, message = analyzer.analyze_nifti_correlation(
            mask_option="non_zero_both",
            output_dir=output_dir
        )
        
        if success:
            print("✅ 相关性分析成功!")
            print(f"结果: {message}")
            
            # 显示关键结果
            results = analyzer.results
            print(f"\n📈 分析结果:")
            print(f"- 有效像素数: {results['voxel_count']}")
            print(f"- Pearson相关系数: {results['pearson_r']:.4f} (p={results['pearson_p']:.2e})")
            print(f"- Spearman相关系数: {results['spearman_r']:.4f} (p={results['spearman_p']:.2e})")
            
        else:
            print(f"❌ 相关性分析失败: {message}")
            return False
    else:
        print("❌ 文件加载失败")
        return False
    
    return True

if __name__ == "__main__":
    try:
        print("🧪 DRM比较器直接重采样功能测试")
        print("=" * 80)
        
        # 测试1: 基本的直接重采样功能
        test1_success = test_direct_resampling()
        
        # 测试2: 两种方法的对比
        test2_success = test_method_comparison()
        
        # 测试3: 使用直接重采样结果进行相关性分析
        test3_success = test_correlation_analysis_with_direct_method()
        
        # 总结
        print(f"\n" + "=" * 80)
        print("📋 测试结果总结")
        print("=" * 80)
        print(f"✅ 直接重采样功能: {'通过' if test1_success else '失败'}")
        print(f"✅ 方法对比测试: {'通过' if test2_success else '失败'}")
        print(f"✅ 相关性分析: {'通过' if test3_success else '失败'}")
        
        if all([test1_success, test2_success, test3_success]):
            print(f"\n🎉 所有测试通过！直接重采样功能工作正常")
            print(f"💡 建议: 使用直接重采样方法以获得更高精度")
        else:
            print(f"\n⚠️  部分测试失败，请检查错误信息")
            
    except Exception as e:
        print(f"\n❌ 测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
