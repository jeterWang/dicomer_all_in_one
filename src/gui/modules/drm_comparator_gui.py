#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DRM比较器GUI模块
提供完整的DRM图像配准、变换和重采样功能界面
"""

import os
from datetime import datetime
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                           QFormLayout, QPushButton, QLabel, QComboBox, 
                           QProgressBar, QTextEdit, QFileDialog, QCheckBox,
                           QLineEdit, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from modules.drm_comparator.drm_comparator import DrmComparator


class DrmComparatorWorker(QThread):
    """DRM比较器工作线程"""
    progress_updated = pyqtSignal(int, str)
    process_finished = pyqtSignal(bool, str)
    log_message = pyqtSignal(str)
    
    def __init__(self, comparator, operation, **kwargs):
        super().__init__()
        self.comparator = comparator
        self.operation = operation
        self.kwargs = kwargs
    
    def run(self):
        try:
            if self.operation == "apply_transformations":
                target_path = self.kwargs.get('target_path')
                direct_to_target = self.kwargs.get('direct_to_target', True)
                
                self.progress_updated.emit(20, "正在应用变换...")
                success, message = self.comparator.apply_transformations(
                    target_image_path=target_path,
                    direct_to_target=direct_to_target
                )
                
                if success:
                    self.progress_updated.emit(80, "变换应用成功")
                    self.process_finished.emit(True, message)
                else:
                    self.process_finished.emit(False, message)
                    
            elif self.operation == "compare_methods":
                target_path = self.kwargs.get('target_path')
                output_dir = self.kwargs.get('output_dir')
                
                self.progress_updated.emit(30, "正在比较重采样方法...")
                success, message = self.comparator.compare_resampling_methods(
                    target_path, output_dir
                )
                
                if success:
                    self.progress_updated.emit(100, "方法比较完成")
                    self.process_finished.emit(True, message)
                else:
                    self.process_finished.emit(False, message)
                    
        except Exception as e:
            self.process_finished.emit(False, f"处理过程中出错: {str(e)}")


class DrmComparatorGUI(QWidget):
    """DRM比较器GUI主界面"""
    
    def __init__(self):
        super().__init__()
        self.comparator = DrmComparator()
        self.worker = None
        
        # 文件路径存储
        self.nifti_path = None
        self.rigid_path = None
        self.dvf_path = None
        self.target_path = None
        self.output_dir = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化用户界面"""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        
        # 创建内容容器
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_widget.setMaximumWidth(900)
        
        # 步骤1: 文件加载
        self.create_file_loading_section(content_layout)
        
        # 步骤2: 变换选项
        self.create_transformation_options_section(content_layout)
        
        # 步骤3: 执行操作
        self.create_execution_section(content_layout)
        
        # 进度和状态
        self.create_progress_section(content_layout)
        
        # 日志区域
        self.create_log_section(content_layout)
        
        layout.addWidget(content_widget)
    
    def create_file_loading_section(self, parent_layout):
        """创建文件加载区域"""
        file_group = QGroupBox("步骤1: 加载输入文件")
        file_layout = QFormLayout(file_group)
        
        # NIfTI图像文件
        self.nifti_label = QLabel("未选择")
        btn_load_nifti = QPushButton("选择NIfTI图像")
        btn_load_nifti.clicked.connect(self.load_nifti_file)
        file_layout.addRow("NIfTI图像:", self.create_file_row(btn_load_nifti, self.nifti_label))
        
        # 刚体变换文件
        self.rigid_label = QLabel("未选择")
        btn_load_rigid = QPushButton("选择刚体变换")
        btn_load_rigid.clicked.connect(self.load_rigid_file)
        file_layout.addRow("刚体变换:", self.create_file_row(btn_load_rigid, self.rigid_label))
        
        # DVF变换文件
        self.dvf_label = QLabel("未选择")
        btn_load_dvf = QPushButton("选择DVF变换")
        btn_load_dvf.clicked.connect(self.load_dvf_file)
        file_layout.addRow("DVF变换:", self.create_file_row(btn_load_dvf, self.dvf_label))
        
        # 目标图像文件
        self.target_label = QLabel("未选择")
        btn_load_target = QPushButton("选择目标图像")
        btn_load_target.clicked.connect(self.load_target_file)
        file_layout.addRow("目标图像:", self.create_file_row(btn_load_target, self.target_label))
        
        parent_layout.addWidget(file_group)
    
    def create_file_row(self, button, label):
        """创建文件选择行"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(button)
        layout.addWidget(label, 1)
        return widget
    
    def create_transformation_options_section(self, parent_layout):
        """创建变换选项区域"""
        options_group = QGroupBox("步骤2: 变换选项")
        options_layout = QFormLayout(options_group)
        
        # 重采样方法选择
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "直接重采样到目标空间（推荐）",
            "传统分步重采样（调试用）"
        ])
        self.method_combo.setCurrentIndex(0)
        options_layout.addRow("重采样方法:", self.method_combo)
        
        # 输出目录
        self.output_label = QLabel("默认输出目录")
        btn_select_output = QPushButton("选择输出目录")
        btn_select_output.clicked.connect(self.select_output_directory)
        options_layout.addRow("输出目录:", self.create_file_row(btn_select_output, self.output_label))
        
        # 自定义输出文件名
        self.output_prefix = QLineEdit()
        self.output_prefix.setPlaceholderText("例如: DRM_transformed")
        options_layout.addRow("输出文件前缀:", self.output_prefix)
        
        parent_layout.addWidget(options_group)
    
    def create_execution_section(self, parent_layout):
        """创建执行操作区域"""
        exec_group = QGroupBox("步骤3: 执行操作")
        exec_layout = QVBoxLayout(exec_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        self.btn_apply_transform = QPushButton("应用变换")
        self.btn_apply_transform.setEnabled(False)
        self.btn_apply_transform.clicked.connect(self.apply_transformations)
        button_layout.addWidget(self.btn_apply_transform)
        
        self.btn_compare_methods = QPushButton("比较重采样方法")
        self.btn_compare_methods.setEnabled(False)
        self.btn_compare_methods.clicked.connect(self.compare_methods)
        button_layout.addWidget(self.btn_compare_methods)
        
        self.btn_save_result = QPushButton("保存结果")
        self.btn_save_result.setEnabled(False)
        self.btn_save_result.clicked.connect(self.save_result)
        button_layout.addWidget(self.btn_save_result)
        
        exec_layout.addLayout(button_layout)
        parent_layout.addWidget(exec_group)
    
    def create_progress_section(self, parent_layout):
        """创建进度显示区域"""
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        parent_layout.addWidget(self.progress_bar)
        
        # 状态标签
        self.status_label = QLabel("状态: 请加载所有必需文件")
        parent_layout.addWidget(self.status_label)
    
    def create_log_section(self, parent_layout):
        """创建日志区域"""
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        self.log_text.setMaximumHeight(300)
        parent_layout.addWidget(self.log_text)
    
    def load_nifti_file(self):
        """加载NIfTI文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择NIfTI图像文件", "", 
            "NIfTI文件 (*.nii *.nii.gz);;所有文件 (*.*)"
        )
        
        if file_path:
            self.nifti_path = file_path
            self.nifti_label.setText(os.path.basename(file_path))
            
            # 加载到比较器
            if self.comparator.load_nifti(file_path):
                self.log_message(f"✓ 成功加载NIfTI文件: {os.path.basename(file_path)}")
            else:
                self.log_message(f"✗ 加载NIfTI文件失败: {os.path.basename(file_path)}")
            
            self.check_enable_buttons()
    
    def load_rigid_file(self):
        """加载刚体变换文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择刚体变换文件", "", 
            "DICOM文件 (*.dcm);;所有文件 (*.*)"
        )
        
        if file_path:
            self.rigid_path = file_path
            self.rigid_label.setText(os.path.basename(file_path))
            
            # 加载到比较器
            if self.comparator.load_rigid_transform(file_path):
                self.log_message(f"✓ 成功加载刚体变换: {os.path.basename(file_path)}")
            else:
                self.log_message(f"✗ 加载刚体变换失败: {os.path.basename(file_path)}")
            
            self.check_enable_buttons()
    
    def load_dvf_file(self):
        """加载DVF变换文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择DVF变换文件", "", 
            "DICOM文件 (*.dcm);;所有文件 (*.*)"
        )
        
        if file_path:
            self.dvf_path = file_path
            self.dvf_label.setText(os.path.basename(file_path))
            
            # 加载到比较器
            if self.comparator.load_dvf(file_path):
                self.log_message(f"✓ 成功加载DVF变换: {os.path.basename(file_path)}")
            else:
                self.log_message(f"✗ 加载DVF变换失败: {os.path.basename(file_path)}")
            
            self.check_enable_buttons()
    
    def load_target_file(self):
        """加载目标图像文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择目标图像文件", "", 
            "NIfTI文件 (*.nii *.nii.gz);;所有文件 (*.*)"
        )
        
        if file_path:
            self.target_path = file_path
            self.target_label.setText(os.path.basename(file_path))
            self.log_message(f"✓ 已选择目标图像: {os.path.basename(file_path)}")
            
            # 设置默认输出目录
            if not self.output_dir:
                default_dir = os.path.join(os.path.dirname(file_path), "drm_comparator_output")
                self.output_dir = default_dir
                self.output_label.setText(f"默认: {os.path.basename(default_dir)}")
            
            self.check_enable_buttons()
    
    def select_output_directory(self):
        """选择输出目录"""
        start_dir = os.path.dirname(self.target_path) if self.target_path else os.getcwd()
        output_dir = QFileDialog.getExistingDirectory(
            self, "选择输出目录", start_dir, QFileDialog.ShowDirsOnly
        )
        
        if output_dir:
            self.output_dir = output_dir
            self.output_label.setText(output_dir)
            self.log_message(f"已设置输出目录: {output_dir}")
    
    def check_enable_buttons(self):
        """检查是否可以启用操作按钮"""
        all_loaded = all([
            self.nifti_path, self.rigid_path, self.dvf_path, self.target_path
        ])
        
        self.btn_apply_transform.setEnabled(all_loaded)
        self.btn_compare_methods.setEnabled(all_loaded)
        
        if all_loaded:
            self.status_label.setText("状态: 所有文件已加载，可以执行操作")
        else:
            missing = []
            if not self.nifti_path: missing.append("NIfTI图像")
            if not self.rigid_path: missing.append("刚体变换")
            if not self.dvf_path: missing.append("DVF变换")
            if not self.target_path: missing.append("目标图像")
            self.status_label.setText(f"状态: 缺少文件 - {', '.join(missing)}")
    
    def apply_transformations(self):
        """应用变换"""
        if not self.target_path:
            QMessageBox.warning(self, "警告", "请先选择目标图像文件")
            return
        
        # 确保输出目录存在
        if not self.output_dir:
            self.output_dir = os.path.join(os.path.dirname(self.target_path), "drm_comparator_output")
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 获取重采样方法
        direct_to_target = self.method_combo.currentIndex() == 0
        method_name = "直接重采样" if direct_to_target else "传统分步重采样"
        
        self.log_message(f"开始应用变换，使用{method_name}方法...")
        self.btn_apply_transform.setEnabled(False)
        
        # 启动工作线程
        self.worker = DrmComparatorWorker(
            self.comparator, "apply_transformations",
            target_path=self.target_path,
            direct_to_target=direct_to_target
        )
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.process_finished.connect(self.on_transformation_finished)
        self.worker.log_message.connect(self.log_message)
        self.worker.start()
    
    def compare_methods(self):
        """比较重采样方法"""
        if not self.target_path:
            QMessageBox.warning(self, "警告", "请先选择目标图像文件")
            return
        
        # 确保输出目录存在
        if not self.output_dir:
            self.output_dir = os.path.join(os.path.dirname(self.target_path), "drm_comparator_output")
        
        comparison_dir = os.path.join(self.output_dir, "method_comparison")
        os.makedirs(comparison_dir, exist_ok=True)
        
        self.log_message("开始比较两种重采样方法...")
        self.btn_compare_methods.setEnabled(False)
        
        # 启动工作线程
        self.worker = DrmComparatorWorker(
            self.comparator, "compare_methods",
            target_path=self.target_path,
            output_dir=comparison_dir
        )
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.process_finished.connect(self.on_comparison_finished)
        self.worker.log_message.connect(self.log_message)
        self.worker.start()
    
    def save_result(self):
        """保存结果"""
        if not hasattr(self.comparator, 'target_space_image') or self.comparator.target_space_image is None:
            QMessageBox.warning(self, "警告", "没有可保存的结果，请先执行变换")
            return
        
        # 生成默认文件名
        prefix = self.output_prefix.text().strip() or "DRM_transformed"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"{prefix}_{timestamp}.nii.gz"
        
        # 选择保存路径
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存变换结果", 
            os.path.join(self.output_dir or os.getcwd(), default_filename),
            "NIfTI文件 (*.nii.gz);;所有文件 (*.*)"
        )
        
        if file_path:
            success, message = self.comparator.save_target_space_image(file_path)
            if success:
                self.log_message(f"✓ 结果已保存: {file_path}")
                QMessageBox.information(self, "成功", f"结果已保存到:\n{file_path}")
            else:
                self.log_message(f"✗ 保存失败: {message}")
                QMessageBox.critical(self, "错误", f"保存失败:\n{message}")
    
    def update_progress(self, value, message):
        """更新进度"""
        self.progress_bar.setValue(value)
        self.status_label.setText(f"状态: {message}")
    
    def on_transformation_finished(self, success, message):
        """变换完成回调"""
        self.btn_apply_transform.setEnabled(True)
        
        if success:
            self.log_message(f"✓ 变换完成: {message}")
            self.btn_save_result.setEnabled(True)
            self.progress_bar.setValue(100)
            self.status_label.setText("状态: 变换完成，可以保存结果")
        else:
            self.log_message(f"✗ 变换失败: {message}")
            self.progress_bar.setValue(0)
            self.status_label.setText("状态: 变换失败")
    
    def on_comparison_finished(self, success, message):
        """比较完成回调"""
        self.btn_compare_methods.setEnabled(True)
        
        if success:
            self.log_message(f"✓ 方法比较完成")
            self.log_message(message)  # 显示详细比较结果
            self.progress_bar.setValue(100)
            self.status_label.setText("状态: 方法比较完成")
        else:
            self.log_message(f"✗ 方法比较失败: {message}")
            self.progress_bar.setValue(0)
            self.status_label.setText("状态: 方法比较失败")
    
    def log_message(self, message):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # 自动滚动到底部
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
