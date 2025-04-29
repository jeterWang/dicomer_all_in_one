#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QSizePolicy
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QSurfaceFormat

# 导入PyVista相关组件
import pyvista as pv
from pyvistaqt import QtInteractor

class VTKWidget(QFrame):
    """集成PyVista到Qt的控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置 OpenGL 格式，避免渲染问题
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setVersion(3, 2)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setSamples(4)  # 启用多重采样
        fmt.setDepthBufferSize(24)  # 设置深度缓冲区大小
        QSurfaceFormat.setDefaultFormat(fmt)
        
        # 创建自己的布局
        self.vtk_layout = QVBoxLayout(self)
        self.vtk_layout.setContentsMargins(0, 0, 0, 0)  # 完全移除边距
        self.vtk_layout.setSpacing(0)  # 移除间距
        
        # 设置尺寸策略，使其能够扩展填充可用空间
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # 设置最小尺寸，确保有足够的显示空间
        self.setMinimumSize(800, 600)
        
        try:
            # 创建Qt集成的PyVista渲染器（启用禁用抗锯齿）
            self.plotter = QtInteractor(self, auto_update=True, multi_samples=4, line_smoothing=True)
            
            # 确保plotter也采用扩展的尺寸策略
            self.plotter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            
            # 设置背景色和渲染样式
            self.plotter.set_background('white')
            
            # 添加到自己的布局中
            self.vtk_layout.addWidget(self.plotter, 1)  # 添加权重1使其填充所有可用空间
            
            # 设置样式
            self.setFrameStyle(QFrame.NoFrame)
            
            # 确保能获取焦点
            self.setFocusPolicy(Qt.StrongFocus)
            
            # 添加一个简单的测试绘制，确认渲染窗口工作正常
            print("正在测试VTK渲染窗口...")
            sphere = pv.Sphere()
            self.plotter.add_mesh(sphere, opacity=0.0)  # 透明的球，只为了测试渲染功能
            self.plotter.reset_camera()
            self.plotter.update()
            print("VTK测试完成")
        
        except Exception as e:
            import traceback
            print(f"VTK初始化错误: {str(e)}")
            traceback.print_exc() 