#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QFileDialog, QGroupBox, QFormLayout,
                           QMessageBox, QFrame, QSplitter, QSlider, QCheckBox,
                           QGridLayout, QSpinBox, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer
from PyQt5.QtGui import QColor

# 导入我们自己的DVF处理模块
from src.core.dvf import read_ct_series, read_point_cloud, read_displacement_field, print_image_info, ImagePlotter
from src.gui.widgets.vtk_widget import VTKWidget
from src.gui.widgets.range_slider import RangeSlider

class DVFViewer(QWidget):
    def __init__(self):
        super().__init__()
        
        # 渲染标志，不再需要定时器
        self.needs_update = False  # 标记是否需要更新
        self.current_update_area = 'all'  # 跟踪当前操作的区域
        
        self.init_ui()
        
    def init_ui(self):
        # 创建主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)  # 完全移除边距
        main_layout.setSpacing(0)  # 移除间距
        self.setLayout(main_layout)
        
        # 创建分割器，用于分隔控制面板和3D视图
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)  # 减小分割线宽度
        main_layout.addWidget(splitter)
        
        # 创建左侧控制区域
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)  # 增加边距
        left_layout.setSpacing(15)  # 增加控件间距
        
        # 创建控制面板
        control_panel = QGroupBox("DVF 控制面板")
        control_layout = QFormLayout()
        control_layout.setSpacing(10)  # 增加表单元素间距
        control_panel.setLayout(control_layout)
        
        # 添加患者ID输入
        self.patient_id_label = QLabel("患者ID:")
        self.patient_id_input = QLabel("未选择")
        control_layout.addRow(self.patient_id_label, self.patient_id_input)
        
        # 添加实例ID输入
        self.instance_id_label = QLabel("实例ID:")
        self.instance_id_input = QLabel("未选择")
        control_layout.addRow(self.instance_id_label, self.instance_id_input)
        
        # 添加选择数据按钮
        self.select_data_btn = QPushButton("选择数据")
        self.select_data_btn.setMinimumHeight(30)  # 增加按钮高度
        self.select_data_btn.clicked.connect(self.select_data)
        control_layout.addRow(self.select_data_btn)
        
        # 添加显示DVF按钮
        self.show_dvf_btn = QPushButton("显示DVF")
        self.show_dvf_btn.setMinimumHeight(30)  # 增加按钮高度
        self.show_dvf_btn.clicked.connect(self.show_dvf)
        self.show_dvf_btn.setEnabled(False)
        control_layout.addRow(self.show_dvf_btn)
        
        # 添加状态标签
        self.status_label = QLabel("就绪")
        control_layout.addRow(QLabel("状态:"), self.status_label)
        
        # 添加水平分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        
        # 将控制面板添加到左侧布局
        left_layout.addWidget(control_panel)
        left_layout.addWidget(line)
        
        # 添加一个消息区域
        message_box = QGroupBox("消息")
        message_layout = QVBoxLayout()
        message_layout.setContentsMargins(10, 10, 10, 10)  # 增加边距
        message_layout.setSpacing(5)
        self.message_label = QLabel("欢迎使用DVF查看器。请选择数据。")
        message_layout.addWidget(self.message_label)
        message_box.setLayout(message_layout)
        left_layout.addWidget(message_box)
        
        # 添加可视化控制组
        vis_control_box = QGroupBox("可视化控制")
        vis_control_box.setVisible(False)  # 初始时隐藏，加载数据后显示
        self.vis_control_box = vis_control_box
        vis_layout = QVBoxLayout()
        vis_layout.setContentsMargins(10, 15, 10, 15)  # 增加边距
        vis_layout.setSpacing(20)  # 增加组件间距
        vis_control_box.setLayout(vis_layout)
        
        # Week 0 控制组
        week0_group = QGroupBox("Week 0 CT")
        week0_layout = QGridLayout()
        week0_layout.setContentsMargins(10, 10, 10, 10)  # 增加边距
        week0_layout.setSpacing(10)  # 增加元素间距
        week0_group.setLayout(week0_layout)
        
        # Week 0 切片范围滑块
        self.w0_slice_range = RangeSlider()
        self.w0_slice_range.min_label.setText("切片范围:")
        self.w0_slice_range.rangeChanged.connect(self.on_w0_slice_range_changed)
        self.w0_slice_range.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week0_layout.addWidget(self.w0_slice_range, 0, 0, 1, 3)
        
        # Week 0 Window 滑块
        week0_layout.addWidget(QLabel("Window:"), 1, 0)
        self.w0_window_slider = QSlider(Qt.Horizontal)
        self.w0_window_slider.setMinimumWidth(150)  # 设置最小宽度
        self.w0_window_slider.setRange(100, 5000)
        self.w0_window_slider.setValue(2000)
        self.w0_window_slider.valueChanged.connect(self.on_w0_window_changed)
        self.w0_window_slider.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week0_layout.addWidget(self.w0_window_slider, 1, 1)
        self.w0_window_value = QSpinBox()
        self.w0_window_value.setMinimumWidth(70)  # 设置最小宽度
        self.w0_window_value.setRange(100, 5000)
        self.w0_window_value.setValue(2000)
        self.w0_window_value.valueChanged.connect(self.w0_window_slider.setValue)
        week0_layout.addWidget(self.w0_window_value, 1, 2)
        
        # Week 0 Level 滑块
        week0_layout.addWidget(QLabel("Level:"), 2, 0)
        self.w0_level_slider = QSlider(Qt.Horizontal)
        self.w0_level_slider.setMinimumWidth(150)  # 设置最小宽度
        self.w0_level_slider.setRange(-1000, 3000)
        self.w0_level_slider.setValue(0)
        self.w0_level_slider.valueChanged.connect(self.on_w0_level_changed)
        self.w0_level_slider.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week0_layout.addWidget(self.w0_level_slider, 2, 1)
        self.w0_level_value = QSpinBox()
        self.w0_level_value.setMinimumWidth(70)  # 设置最小宽度
        self.w0_level_value.setRange(-1000, 3000)
        self.w0_level_value.setValue(0)
        self.w0_level_value.valueChanged.connect(self.w0_level_slider.setValue)
        week0_layout.addWidget(self.w0_level_value, 2, 2)
        
        # Week 0 Opacity 滑块
        week0_layout.addWidget(QLabel("Opacity:"), 3, 0)
        self.w0_opacity_slider = QSlider(Qt.Horizontal)
        self.w0_opacity_slider.setMinimumWidth(150)  # 设置最小宽度
        self.w0_opacity_slider.setRange(0, 100)
        self.w0_opacity_slider.setValue(100)
        self.w0_opacity_slider.valueChanged.connect(self.on_w0_opacity_changed)
        self.w0_opacity_slider.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week0_layout.addWidget(self.w0_opacity_slider, 3, 1)
        self.w0_opacity_value = QSpinBox()
        self.w0_opacity_value.setMinimumWidth(70)  # 设置最小宽度
        self.w0_opacity_value.setRange(0, 100)
        self.w0_opacity_value.setValue(100)
        self.w0_opacity_value.valueChanged.connect(self.w0_opacity_slider.setValue)
        week0_layout.addWidget(self.w0_opacity_value, 3, 2)
        
        vis_layout.addWidget(week0_group)
        
        # Week 4 控制组
        week4_group = QGroupBox("Week 4 CT")
        week4_layout = QGridLayout()
        week4_layout.setContentsMargins(10, 10, 10, 10)  # 增加边距
        week4_layout.setSpacing(10)  # 增加元素间距
        week4_group.setLayout(week4_layout)
        
        # Week 4 切片范围滑块 - 移除外部标签，只使用控件内部的标签
        self.w4_slice_range = RangeSlider()
        self.w4_slice_range.min_label.setText("切片范围:")
        self.w4_slice_range.rangeChanged.connect(self.on_w4_slice_range_changed)
        self.w4_slice_range.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week4_layout.addWidget(self.w4_slice_range, 0, 0, 1, 3)
        
        # Week 4 Window 滑块
        week4_layout.addWidget(QLabel("Window:"), 1, 0)
        self.w4_window_slider = QSlider(Qt.Horizontal)
        self.w4_window_slider.setMinimumWidth(150)  # 设置最小宽度
        self.w4_window_slider.setRange(100, 5000)
        self.w4_window_slider.setValue(2000)
        self.w4_window_slider.valueChanged.connect(self.on_w4_window_changed)
        self.w4_window_slider.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week4_layout.addWidget(self.w4_window_slider, 1, 1)
        self.w4_window_value = QSpinBox()
        self.w4_window_value.setMinimumWidth(70)  # 设置最小宽度
        self.w4_window_value.setRange(100, 5000)
        self.w4_window_value.setValue(2000)
        self.w4_window_value.valueChanged.connect(self.w4_window_slider.setValue)
        week4_layout.addWidget(self.w4_window_value, 1, 2)
        
        # Week 4 Level 滑块
        week4_layout.addWidget(QLabel("Level:"), 2, 0)
        self.w4_level_slider = QSlider(Qt.Horizontal)
        self.w4_level_slider.setMinimumWidth(150)  # 设置最小宽度
        self.w4_level_slider.setRange(-1000, 3000)
        self.w4_level_slider.setValue(0)
        self.w4_level_slider.valueChanged.connect(self.on_w4_level_changed)
        self.w4_level_slider.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week4_layout.addWidget(self.w4_level_slider, 2, 1)
        self.w4_level_value = QSpinBox()
        self.w4_level_value.setMinimumWidth(70)  # 设置最小宽度
        self.w4_level_value.setRange(-1000, 3000)
        self.w4_level_value.setValue(0)
        self.w4_level_value.valueChanged.connect(self.w4_level_slider.setValue)
        week4_layout.addWidget(self.w4_level_value, 2, 2)
        
        # Week 4 Opacity 滑块
        week4_layout.addWidget(QLabel("Opacity:"), 3, 0)
        self.w4_opacity_slider = QSlider(Qt.Horizontal)
        self.w4_opacity_slider.setMinimumWidth(150)  # 设置最小宽度
        self.w4_opacity_slider.setRange(0, 100)
        self.w4_opacity_slider.setValue(100)
        self.w4_opacity_slider.valueChanged.connect(self.on_w4_opacity_changed)
        self.w4_opacity_slider.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        week4_layout.addWidget(self.w4_opacity_slider, 3, 1)
        self.w4_opacity_value = QSpinBox()
        self.w4_opacity_value.setMinimumWidth(70)  # 设置最小宽度
        self.w4_opacity_value.setRange(0, 100)
        self.w4_opacity_value.setValue(100)
        self.w4_opacity_value.valueChanged.connect(self.w4_opacity_slider.setValue)
        week4_layout.addWidget(self.w4_opacity_value, 3, 2)
        
        vis_layout.addWidget(week4_group)
        
        # 点云控制组
        points_group = QGroupBox("点云控制")
        points_layout = QGridLayout()
        points_layout.setContentsMargins(10, 10, 10, 10)  # 增加边距
        points_layout.setSpacing(10)  # 增加元素间距
        points_group.setLayout(points_layout)
        
        # 点云大小滑块
        points_layout.addWidget(QLabel("点大小:"), 0, 0)
        self.point_size_slider = QSlider(Qt.Horizontal)
        self.point_size_slider.setMinimumWidth(150)  # 设置最小宽度
        self.point_size_slider.setRange(1, 20)
        self.point_size_slider.setValue(5)
        self.point_size_slider.valueChanged.connect(self.on_point_size_changed)
        self.point_size_slider.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        points_layout.addWidget(self.point_size_slider, 0, 1)
        self.point_size_value = QSpinBox()
        self.point_size_value.setMinimumWidth(70)  # 设置最小宽度
        self.point_size_value.setRange(1, 20)
        self.point_size_value.setValue(5)
        self.point_size_value.valueChanged.connect(self.point_size_slider.setValue)
        points_layout.addWidget(self.point_size_value, 0, 2)
        
        # 点云切片范围 - 移除外部标签，只使用控件内部的标签
        self.point_slice_range = RangeSlider()
        self.point_slice_range.min_label.setText("切片范围:")
        self.point_slice_range.rangeChanged.connect(self.on_point_slice_range_changed)
        self.point_slice_range.sliderReleased.connect(self.on_slider_released)  # 添加释放事件
        points_layout.addWidget(self.point_slice_range, 1, 0, 1, 3)
        
        # 显示箭头复选框
        self.show_arrows_check = QCheckBox("显示位移箭头")
        self.show_arrows_check.setChecked(True)
        self.show_arrows_check.stateChanged.connect(self.on_show_arrows_changed)
        points_layout.addWidget(self.show_arrows_check, 2, 0, 1, 3)
        
        vis_layout.addWidget(points_group)
        
        # 添加视图控制到左侧面板
        left_layout.addWidget(vis_control_box)
        
        # 添加弹性空间
        left_layout.addStretch(1)
        
        # 设置左侧面板的固定宽度
        left_panel.setFixedWidth(400)  # 增加宽度，适应控制元素
        
        # 创建右侧3D视图区域
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)  # 完全移除边距
        right_layout.setSpacing(0)  # 移除间距
        
        # 创建VTK视图并添加到右侧布局
        self.vtk_widget = VTKWidget(right_panel)
        right_layout.addWidget(self.vtk_widget)  # 添加到布局中
        
        # 设置VTK小部件的大小策略
        self.vtk_widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding
        )
        
        # 将左右面板添加到分割器
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        
        # 设置分割器不可移动
        splitter.setCollapsible(0, False)  # 左侧面板不可折叠
        splitter.setCollapsible(1, False)  # 右侧面板不可折叠
        
        # 设置分割器的初始大小比例
        splitter.setStretchFactor(0, 0)  # 左侧面板不伸缩
        splitter.setStretchFactor(1, 1)  # 右侧面板可伸缩
        
        # 初始化数据路径
        self.ct_directory_week0 = None
        self.ct_directory_week4 = None
        self.point_cloud_path = None
        self.displacement_path = None
        
        # 初始化图像绘制器
        self.plotter = None
        
    def show_dvf(self):
        """显示DVF可视化"""
        if not all([self.ct_directory_week0, self.ct_directory_week4, 
                  self.point_cloud_path, self.displacement_path]):
            QMessageBox.warning(self, "警告", "请先选择完整的数据！")
            return
            
        self.status_label.setText("加载中...")
        self.message_label.setText("正在加载数据和创建可视化，请稍候...")
        
        try:
            # 清空之前的可视化
            if self.plotter is not None:
                self.vtk_widget.plotter.clear()
            
            # 读取Week 0的CT序列
            ct_image_week0 = read_ct_series(self.ct_directory_week0)
            
            # 读取Week 4的CT序列
            ct_image_week4 = read_ct_series(self.ct_directory_week4)
            
            # 读取原始点云数据
            points = read_point_cloud(self.point_cloud_path)
            
            # 计算Week 4的X方向偏移量
            offset_x = 0
            
            # 读取位移场并计算位移后的点云
            displaced_points = read_displacement_field(self.displacement_path, points, offset_x)
            
            # 打印图像信息
            self.message_label.setText(self.message_label.text() + "\n创建可视化中...")
            
            # 设置VTK窗口设置
            self.vtk_widget.plotter.set_background('white')
            
            # 创建可视化器并使用VTK小部件的plotter - 不创建PyVista滑块
            self.plotter = ImagePlotter(ct_image_week0, ct_image_week4, points, displaced_points, 
                                       plotter=self.vtk_widget.plotter, use_qt_controls=True)
            
            # 初始化Qt控制器的值
            max_slice_w0 = self.plotter.array_week0.shape[0] - 1
            max_slice_w4 = self.plotter.array_week4.shape[0] - 1
            
            # 设置Week 0切片范围
            self.w0_slice_range.setRange(0, max_slice_w0)
            self.w0_slice_range.setLower(0)
            self.w0_slice_range.setUpper(max_slice_w0)
            
            # 设置Week 4切片范围
            self.w4_slice_range.setRange(0, max_slice_w4)
            self.w4_slice_range.setLower(0)
            self.w4_slice_range.setUpper(max_slice_w4)
            
            # 设置点云切片范围
            self.point_slice_range.setRange(0, max_slice_w0)
            self.point_slice_range.setLower(0)
            self.point_slice_range.setUpper(max_slice_w0)
            
            # 显示可视化控制面板
            self.vis_control_box.setVisible(True)
            
            # 进行完全更新
            self.plotter.update_volume(full_update=True)
            
            # 手动添加一些简单的内容，确保渲染窗口正常工作
            self.vtk_widget.plotter.add_axes()
            
            # 强制初始视图
            self.vtk_widget.plotter.view_isometric()
            self.vtk_widget.plotter.reset_camera()
            
            # 强制刷新渲染
            self.vtk_widget.plotter.update()
            if hasattr(self.vtk_widget.plotter, 'ren_win'):
                self.vtk_widget.plotter.ren_win.Render()
            
            # 确保控件获得焦点
            self.vtk_widget.setFocus()
            
            # 手动更新布局以确保渲染区域正确大小
            self.vtk_widget.adjustSize()
            self.adjustSize()
            
            # 更新状态
            self.status_label.setText("已显示")
            self.message_label.setText("可视化已显示。")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"显示DVF时出错: {str(e)}")
            self.status_label.setText("出错")
            self.message_label.setText(f"显示DVF时出错: {str(e)}")
        
    # Week 0 控制槽
    @pyqtSlot(int, int)
    def on_w0_slice_range_changed(self, lower, upper):
        if self.plotter:
            self.plotter.state.slice_min_week0 = lower
            self.plotter.state.slice_max_week0 = upper
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week0'
            
    @pyqtSlot(int)
    def on_w0_window_changed(self, value):
        self.w0_window_value.setValue(value)
        if self.plotter:
            self.plotter.state.window_week0 = value
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week0'
            
    @pyqtSlot(int)
    def on_w0_level_changed(self, value):
        self.w0_level_value.setValue(value)
        if self.plotter:
            self.plotter.state.level_week0 = value
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week0'
            
    @pyqtSlot(int)
    def on_w0_opacity_changed(self, value):
        self.w0_opacity_value.setValue(value)
        if self.plotter:
            self.plotter.state.opacity_week0 = value / 100.0  # 转换为0-1
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week0'
    
    # Week 4 控制槽
    @pyqtSlot(int, int)
    def on_w4_slice_range_changed(self, lower, upper):
        if self.plotter:
            self.plotter.state.slice_min_week4 = lower
            self.plotter.state.slice_max_week4 = upper
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week4'
            
    @pyqtSlot(int)
    def on_w4_window_changed(self, value):
        self.w4_window_value.setValue(value)
        if self.plotter:
            self.plotter.state.window_week4 = value
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week4'
            
    @pyqtSlot(int)
    def on_w4_level_changed(self, value):
        self.w4_level_value.setValue(value)
        if self.plotter:
            self.plotter.state.level_week4 = value
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week4'
            
    @pyqtSlot(int)
    def on_w4_opacity_changed(self, value):
        self.w4_opacity_value.setValue(value)
        if self.plotter:
            self.plotter.state.opacity_week4 = value / 100.0  # 转换为0-1
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'week4'
    
    # 点云控制槽
    @pyqtSlot(int)
    def on_point_size_changed(self, value):
        self.point_size_value.setValue(value)
        if self.plotter:
            self.plotter.state.point_size = value
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'points'
            
    @pyqtSlot(int, int)
    def on_point_slice_range_changed(self, lower, upper):
        if self.plotter:
            self.plotter.state.point_slice_min = lower
            self.plotter.state.point_slice_max = upper
            # 标记需要更新区域
            self.needs_update = True
            self.current_update_area = 'points'
            
    @pyqtSlot(int)
    def on_show_arrows_changed(self, state):
        if self.plotter:
            self.plotter.state.show_arrows = state == Qt.Checked
            # 立即执行渲染（复选框操作不频繁）
            print("显示箭头状态改变，执行渲染...")
            self.plotter.update_volume(update_where='points')
            
    def select_data(self):
        """选择数据目录"""
        try:
            # 选择患者数据目录
            patient_dir = QFileDialog.getExistingDirectory(self, "选择患者数据目录", "data")
            if not patient_dir:
                return
                
            # 获取患者ID（目录名）
            patient_id = os.path.basename(patient_dir)
            self.patient_id_input.setText(patient_id)
            
            # 构建数据路径
            images_dir = os.path.join(patient_dir, "images")
            instances_dir = os.path.join(patient_dir, "instances")
            
            # 检查目录是否存在
            if not os.path.exists(images_dir):
                QMessageBox.warning(self, "警告", "未找到images目录！")
                return
                
            if not os.path.exists(instances_dir):
                QMessageBox.warning(self, "警告", "未找到instances目录！")
                return
                
            # 查找week0和week4目录
            ct_week0_dir = os.path.join(images_dir, "week0_CT")
            ct_week4_dir = os.path.join(images_dir, "week4_CT")
            
            if not os.path.exists(ct_week0_dir):
                QMessageBox.warning(self, "警告", "未找到week0_CT目录！")
                return
                
            if not os.path.exists(ct_week4_dir):
                QMessageBox.warning(self, "警告", "未找到week4_CT目录！")
                return
                
            # 获取实例目录（第一个实例）
            instance_dirs = [d for d in os.listdir(instances_dir) 
                           if os.path.isdir(os.path.join(instances_dir, d))]
            if not instance_dirs:
                QMessageBox.warning(self, "警告", "未找到实例目录！")
                return
                
            instance_id = instance_dirs[0]
            self.instance_id_input.setText(instance_id)
            
            # 构建点云和位移路径
            instance_dir = os.path.join(instances_dir, instance_id)
            voxel_disp_dir = os.path.join(instance_dir, "voxel_disp")
            
            point_cloud_path = os.path.join(instance_dir, "voxel_coord.csv")
            displacement_path = os.path.join(voxel_disp_dir, "week0_CT_week4_CT_voxel_disp.csv")
            
            if not os.path.exists(point_cloud_path):
                QMessageBox.warning(self, "警告", f"未找到点云文件: {point_cloud_path}")
                return
                
            if not os.path.exists(displacement_path):
                QMessageBox.warning(self, "警告", f"未找到位移文件: {displacement_path}")
                return
                
            # 保存路径
            self.ct_directory_week0 = ct_week0_dir
            self.ct_directory_week4 = ct_week4_dir
            self.point_cloud_path = point_cloud_path
            self.displacement_path = displacement_path
            
            # 更新状态
            self.status_label.setText("数据已加载")
            self.message_label.setText(f"数据已加载:\n"
                                     f"患者ID: {patient_id}\n"
                                     f"实例ID: {instance_id}\n"
                                     f"Week 0 CT: {ct_week0_dir}\n"
                                     f"Week 4 CT: {ct_week4_dir}")
            
            # 启用显示按钮
            self.show_dvf_btn.setEnabled(True)
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"选择数据时出错: {str(e)}")
            self.status_label.setText("出错")
            
    def adjustSize(self):
        # 实现调整大小的逻辑
        pass 

    def on_slider_released(self):
        """当滑块释放时立即执行渲染"""
        if self.plotter and self.needs_update:
            # 根据当前操作的区域执行对应的渲染
            print(f"滑块释放，执行渲染区域: {self.current_update_area}...")
            self.plotter.update_volume(update_where=self.current_update_area)
            self.needs_update = False 