#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试RTSS轮廓质心计算和自动推导刚体变换参数
"""

import os
import sys
import logging
from pathlib import Path

# 将项目根目录添加到Python路径
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# 导入图像刚体位移模块
from src.modules.image_regid_mover import ImageRigidMover

def setup_logging():
    """设置日志记录"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
def test_centroid_calculation():
    """测试轮廓质心计算功能"""
    # 创建刚体位移器实例
    rigid_mover = ImageRigidMover()
    
    # 设置数据目录路径
    data_root = os.path.join(project_root, 'data', 'image_regid_mover', 'cwk')
    fixed_dir = os.path.join(data_root, 'fixed')
    moving_dir = os.path.join(data_root, 'moving')
    
    print(f"数据根目录: {data_root}")
    print(f"固定图像目录: {fixed_dir}")
    print(f"移动图像目录: {moving_dir}")
    
    # 加载固定图像和RTSS
    print("\n正在加载固定图像数据...")
    success, message, _ = rigid_mover.load_directory(fixed_dir, is_fixed=True)
    if not success:
        print(f"加载固定图像失败: {message}")
        return
    print(f"加载固定图像成功: {message}")
    
    # 加载移动图像和RTSS
    print("\n正在加载移动图像数据...")
    success, message, _ = rigid_mover.load_directory(moving_dir, is_fixed=False)
    if not success:
        print(f"加载移动图像失败: {message}")
        return
    print(f"加载移动图像成功: {message}")
    
    # 检查是否有RTSS
    if not rigid_mover.fixed_data.get('rtss'):
        print("错误: 固定图像数据中没有RTSS")
        return
        
    if not rigid_mover.moving_data.get('rtss'):
        print("错误: 移动图像数据中没有RTSS")
        return
    
    # 计算固定图像的RTSS质心
    print("\n计算固定图像RTSS质心...")
    fixed_centroid = rigid_mover.calculate_centroid_from_rtss(rigid_mover.fixed_data['rtss'])
    if fixed_centroid is None:
        print("无法计算固定图像RTSS的质心")
        return
    print(f"固定图像轮廓质心: ({fixed_centroid[0]:.2f}, {fixed_centroid[1]:.2f}, {fixed_centroid[2]:.2f})")
    
    # 计算移动图像的RTSS质心
    print("\n计算移动图像RTSS质心...")
    moving_centroid = rigid_mover.calculate_centroid_from_rtss(rigid_mover.moving_data['rtss'])
    if moving_centroid is None:
        print("无法计算移动图像RTSS的质心")
        return
    print(f"移动图像轮廓质心: ({moving_centroid[0]:.2f}, {moving_centroid[1]:.2f}, {moving_centroid[2]:.2f})")
    
    # 计算变换参数
    print("\n根据质心差异计算变换参数...")
    success, message, transform_params = rigid_mover.calculate_transform_from_centroids()
    if not success:
        print(f"计算变换参数失败: {message}")
        return
        
    # 显示计算结果
    print(f"计算得到的变换参数:")
    print(f"  平移参数: TX={transform_params['tx']:.2f}mm, TY={transform_params['ty']:.2f}mm, TZ={transform_params['tz']:.2f}mm")
    print(f"  旋转参数: RX={transform_params['rx']:.2f}度, RY={transform_params['ry']:.2f}度, RZ={transform_params['rz']:.2f}度")
    
    print("\n测试完成!")

if __name__ == "__main__":
    setup_logging()
    test_centroid_calculation() 