#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
创建图表标题修复前后的对比图
展示掩码信息移除的效果
"""

import matplotlib.pyplot as plt
import numpy as np
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

def create_comparison_plots():
    """创建修复前后的对比图"""
    print("📊 创建图表标题修复对比图")
    print("=" * 40)
    
    # 生成示例数据
    np.random.seed(42)
    n_points = 300
    x = np.random.normal(50, 15, n_points)
    y = 0.8 * x + np.random.normal(0, 8, n_points)
    
    # 计算相关性
    pearson_r = np.corrcoef(x, y)[0, 1]
    
    # 创建对比图
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # 修复前的图表（包含掩码信息）
    ax1.scatter(x, y, alpha=0.6, s=20, color='blue')
    ax1.set_xlabel('Target DRM Values')
    ax1.set_ylabel('Transformed DRM Values')
    ax1.set_title(
        'Target DRM vs Transformed DRM Correlation\n'
        '掩码: 两个图像都非零的像素\n'  # 这行会被移除
        f'Pearson r = {pearson_r:.4f} (p = 1.62e-40)\n'
        f'Spearman r = 0.6579 (p = 4.48e-39)\n'
        f'像素数量 = {n_points}',
        fontsize=10,
        color='red'  # 用红色标示问题
    )
    ax1.grid(True, alpha=0.3)
    ax1.text(0.02, 0.98, '修复前', transform=ax1.transAxes, 
             fontsize=14, fontweight='bold', color='red',
             verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
    
    # 修复后的图表（不包含掩码信息）
    ax2.scatter(x, y, alpha=0.6, s=20, color='green')
    ax2.set_xlabel('Target DRM Values')
    ax2.set_ylabel('Transformed DRM Values')
    ax2.set_title(
        'Target DRM vs Transformed DRM Correlation\n'
        # 掩码信息已移除
        f'Pearson r = {pearson_r:.4f} (p = 1.62e-40)\n'
        f'Spearman r = 0.6579 (p = 4.48e-39)\n'
        f'像素数量 = {n_points}',
        fontsize=10,
        color='green'  # 用绿色标示修复
    )
    ax2.grid(True, alpha=0.3)
    ax2.text(0.02, 0.98, '修复后', transform=ax2.transAxes, 
             fontsize=14, fontweight='bold', color='green',
             verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))
    
    # 添加说明
    fig.suptitle('相关性分析图表标题修复对比', fontsize=16, fontweight='bold')
    
    # 在底部添加说明文字
    fig.text(0.5, 0.02, 
             '修复说明: 移除了"掩码: 两个图像都非零的像素"这行调试信息，使图表更简洁美观',
             ha='center', fontsize=12, style='italic',
             bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))
    
    plt.tight_layout()
    plt.subplots_adjust(top=0.85, bottom=0.15)
    
    # 保存对比图
    output_dir = "output/title_fix_comparison"
    os.makedirs(output_dir, exist_ok=True)
    
    comparison_path = os.path.join(output_dir, "title_fix_comparison.png")
    plt.savefig(comparison_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✅ 对比图已保存: {comparison_path}")
    
    # 创建单独的修复后示例图
    create_clean_example()
    
    return comparison_path

def create_clean_example():
    """创建修复后的干净示例图"""
    # 生成示例数据
    np.random.seed(42)
    n_points = 385
    x = np.random.normal(45, 12, n_points)
    y = 0.75 * x + np.random.normal(0, 6, n_points)
    
    # 计算相关性
    pearson_r = np.corrcoef(x, y)[0, 1]
    
    plt.figure(figsize=(10, 8))
    plt.scatter(x, y, alpha=0.6, s=30, color='steelblue', edgecolors='white', linewidth=0.5)
    
    plt.xlabel('Target DRM Values', fontsize=12)
    plt.ylabel('Direct Resampled DRM Values', fontsize=12)
    plt.title(
        'Target DRM vs Direct Resampled DRM Correlation\n'
        f'Pearson r = {pearson_r:.4f} (p = 1.23e-20)\n'
        f'Spearman r = 0.3838 (p = 5.84e-15)\n'
        f'像素数量 = {n_points}',
        fontsize=14,
        pad=20
    )
    
    plt.grid(True, alpha=0.3)
    
    # 添加趋势线
    z = np.polyfit(x, y, 1)
    p = np.poly1d(z)
    plt.plot(x, p(x), "r--", alpha=0.8, linewidth=2, label=f'趋势线 (斜率={z[0]:.3f})')
    plt.legend()
    
    # 美化图表
    plt.gca().spines['top'].set_visible(False)
    plt.gca().spines['right'].set_visible(False)
    plt.gca().spines['left'].set_color('gray')
    plt.gca().spines['bottom'].set_color('gray')
    
    output_dir = "output/title_fix_comparison"
    clean_path = os.path.join(output_dir, "clean_title_example.png")
    plt.savefig(clean_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✅ 干净示例图已保存: {clean_path}")
    return clean_path

if __name__ == "__main__":
    try:
        print("🎨 创建相关性分析图表标题修复对比")
        print("=" * 60)
        
        comparison_path = create_comparison_plots()
        
        print(f"\n" + "=" * 60)
        print("📋 生成结果")
        print("=" * 60)
        print(f"✅ 对比图: {comparison_path}")
        print(f"✅ 示例图: output/title_fix_comparison/clean_title_example.png")
        
        print(f"\n🎉 图表标题修复完成!")
        print(f"📝 修复内容:")
        print(f"   - 移除了'掩码: 两个图像都非零的像素'这行调试信息")
        print(f"   - 保留了所有重要的统计信息")
        print(f"   - 图表更加简洁美观")
        
        print(f"\n💡 现在的图表标题格式:")
        print(f"   标题")
        print(f"   Pearson r = 值 (p = 值)")
        print(f"   Spearman r = 值 (p = 值)")
        print(f"   像素数量 = 值")
        
    except Exception as e:
        print(f"❌ 创建对比图时出错: {e}")
        import traceback
        traceback.print_exc()
