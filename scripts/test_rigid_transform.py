#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试刚体变换功能
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
    
def test_rigid_transform():
    """测试刚体变换功能"""
    # 创建刚体位移器实例
    rigid_mover = ImageRigidMover()
    
    # 设置数据目录路径
    data_root = os.path.join(project_root, 'data', 'image_regid_mover', 'cwk')
    fixed_dir = os.path.join(data_root, 'fixed')
    moving_dir = os.path.join(data_root, 'moving')
    output_dir = os.path.join(data_root, 'output')
    
    # 创建输出目录（如果不存在）
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"数据根目录: {data_root}")
    print(f"固定图像目录: {fixed_dir}")
    print(f"移动图像目录: {moving_dir}")
    print(f"输出目录: {output_dir}")
    
    # 设置进度更新回调
    def on_progress_updated(progress, message):
        print(f"进度: {progress}% - {message}")
    
    # 设置处理完成回调
    def on_process_finished(success, message):
        print(f"完成: {'成功' if success else '失败'} - {message}")
    
    # 连接信号
    rigid_mover.progress_updated.connect(on_progress_updated)
    rigid_mover.process_finished.connect(on_process_finished)
    
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
    
    # 计算变换参数（如果有RTSS）
    if rigid_mover.fixed_data.get('rtss') and rigid_mover.moving_data.get('rtss'):
        print("\n根据RTSS质心计算变换参数...")
        success, message, params = rigid_mover.calculate_transform_from_centroids()
        if success:
            print(f"成功计算变换参数: {message}")
            print(f"平移参数: TX={params['tx']:.2f}mm, TY={params['ty']:.2f}mm, TZ={params['tz']:.2f}mm")
            print(f"旋转参数: RX={params['rx']:.2f}度, RY={params['ry']:.2f}度, RZ={params['rz']:.2f}度")
        else:
            print(f"计算变换参数失败: {message}")
            # 设置一些示例参数
            rigid_mover.set_transform_parameters(1.0, -1.5, -2.5, 0, 0, 0)
    else:
        # 如果没有RTSS，设置一些示例参数
        print("\n没有RTSS，使用示例变换参数...")
        rigid_mover.set_transform_parameters(1.0, -1.5, -2.5, 0, 0, 0)
    
    # 执行刚体变换
    print("\n执行刚体变换...")
    rigid_mover.output_dir = output_dir
    success, message = rigid_mover.perform_rigid_transform(
        output_dir,
        output_image=True,
        output_rtss=True
    )
    
    if success:
        print(f"刚体变换成功: {message}")
    else:
        print(f"刚体变换失败: {message}")
    
    print("\n测试完成!")

if __name__ == "__main__":
    setup_logging()
    test_rigid_transform() 