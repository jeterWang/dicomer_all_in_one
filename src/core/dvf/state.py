#!/usr/bin/env python
# -*- coding: utf-8 -*-

class State:
    """状态管理类，用于存储和管理可视化的参数状态"""
    
    def __init__(self, image_shape):
        """
        初始化状态
        
        Args:
            image_shape: 图像数组的形状，通常为 (z, y, x)
        """
        # 记录图像形状
        self.image_shape = image_shape
        
        # Week 0图像的状态
        self.slice_min_week0 = 0
        self.slice_max_week0 = image_shape[0] - 1
        self.window_week0 = 2000
        self.level_week0 = 0
        self.opacity_week0 = 1.0
        
        # Week 4图像的状态
        self.slice_min_week4 = 0
        self.slice_max_week4 = image_shape[0] - 1
        self.window_week4 = 2000
        self.level_week4 = 0
        self.opacity_week4 = 1.0
        
        # 点云的状态
        self.point_size = 5
        self.point_slice_min = 0
        self.point_slice_max = image_shape[0] - 1
        self.show_arrows = True
        
        # 当前显示的对象（用于更新）
        self.current_mapper_week0 = None
        self.current_mapper_week4 = None
        self.current_points = None
        self.current_arrows = None 