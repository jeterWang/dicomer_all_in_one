#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import QWidget, QSlider, QHBoxLayout, QLabel, QSpinBox, QGridLayout
from PyQt5.QtCore import Qt, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QColor, QBrush

class RangeSlider(QWidget):
    """双滑块范围选择控件"""
    
    # 定义信号
    rangeChanged = pyqtSignal(int, int)  # 范围变化信号
    
    def __init__(self, parent=None, min_value=0, max_value=100, lower=0, upper=100):
        super().__init__(parent)
        
        # 设置主布局
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 添加标签
        self.min_label = QLabel("范围:")
        self.layout.addWidget(self.min_label, 0, 0)
        
        # 创建底层滑块（仅用于显示范围）
        self.base_slider = QSlider(Qt.Horizontal)
        self.base_slider.setRange(min_value, max_value)
        self.base_slider.setEnabled(False)  # 禁用交互
        self.layout.addWidget(self.base_slider, 0, 1)
        
        # 创建两个数值输入框
        self.lower_spinbox = QSpinBox()
        self.lower_spinbox.setRange(min_value, max_value)
        self.lower_spinbox.setValue(lower)
        self.lower_spinbox.valueChanged.connect(self._lower_spin_changed)
        self.layout.addWidget(self.lower_spinbox, 0, 2)
        
        self.upper_spinbox = QSpinBox()
        self.upper_spinbox.setRange(min_value, max_value)
        self.upper_spinbox.setValue(upper)
        self.upper_spinbox.valueChanged.connect(self._upper_spin_changed)
        self.layout.addWidget(self.upper_spinbox, 0, 3)
        
        # 设置内部变量
        self._min_value = min_value
        self._max_value = max_value
        self._lower = lower
        self._upper = upper
        
        # 连接信号
        self.lower_spinbox.valueChanged.connect(self.update)
        self.upper_spinbox.valueChanged.connect(self.update)
        
    def paintEvent(self, event):
        """绘制自定义双滑块外观"""
        super().paintEvent(event)
        
        # 创建画笔
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 获取滑块位置
        slider_rect = self.base_slider.geometry()
        
        # 计算滑块轨道区域
        track_height = 10
        track_rect = QRect(
            slider_rect.left(), 
            slider_rect.top() + (slider_rect.height() - track_height) // 2,
            slider_rect.width(),
            track_height
        )
        
        # 绘制轨道背景
        painter.setBrush(QBrush(QColor(200, 200, 200)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(track_rect, 5, 5)
        
        # 计算选中范围
        range_width = self._max_value - self._min_value
        if range_width <= 0:
            return
            
        left_pos = (self._lower - self._min_value) / range_width * slider_rect.width() + slider_rect.left()
        right_pos = (self._upper - self._min_value) / range_width * slider_rect.width() + slider_rect.left()
        
        # 绘制选中范围
        selected_rect = QRect(
            int(left_pos),
            track_rect.top(),
            int(right_pos - left_pos),
            track_rect.height()
        )
        
        painter.setBrush(QBrush(QColor(0, 120, 215)))
        painter.drawRoundedRect(selected_rect, 5, 5)
        
        # 绘制两个滑块手柄
        handle_size = 16
        
        # 左滑块
        left_handle = QRect(
            int(left_pos - handle_size // 2),
            track_rect.top() + (track_rect.height() - handle_size) // 2,
            handle_size,
            handle_size
        )
        painter.setBrush(QBrush(QColor(240, 240, 240)))
        painter.setPen(QColor(180, 180, 180))
        painter.drawEllipse(left_handle)
        
        # 右滑块
        right_handle = QRect(
            int(right_pos - handle_size // 2),
            track_rect.top() + (track_rect.height() - handle_size) // 2,
            handle_size,
            handle_size
        )
        painter.setBrush(QBrush(QColor(240, 240, 240)))
        painter.setPen(QColor(180, 180, 180))
        painter.drawEllipse(right_handle)
        
    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        slider_rect = self.base_slider.geometry()
        if not slider_rect.contains(event.pos()):
            return super().mousePressEvent(event)
            
        # 确定点击了哪个滑块
        range_width = self._max_value - self._min_value
        left_pos = (self._lower - self._min_value) / range_width * slider_rect.width() + slider_rect.left()
        right_pos = (self._upper - self._min_value) / range_width * slider_rect.width() + slider_rect.left()
        
        # 简单判断哪个滑块更近
        if abs(event.x() - left_pos) < abs(event.x() - right_pos):
            self._moving_lower = True
            self._moving_upper = False
        else:
            self._moving_lower = False
            self._moving_upper = True
            
        self.mouseMoveEvent(event)
        
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        if not hasattr(self, '_moving_lower') or (not self._moving_lower and not self._moving_upper):
            return super().mouseMoveEvent(event)
            
        slider_rect = self.base_slider.geometry()
        if slider_rect.width() <= 0:
            return
            
        # 计算位置对应的值
        pos_ratio = max(0, min(1, (event.x() - slider_rect.left()) / slider_rect.width()))
        value = int(self._min_value + pos_ratio * (self._max_value - self._min_value))
        
        if self._moving_lower:
            # 确保最小值不超过最大值
            value = min(value, self._upper)
            if value != self._lower:
                self._lower = value
                self.lower_spinbox.setValue(value)
                self.update()
                self.rangeChanged.emit(self._lower, self._upper)
        else:
            # 确保最大值不小于最小值
            value = max(value, self._lower)
            if value != self._upper:
                self._upper = value
                self.upper_spinbox.setValue(value)
                self.update()
                self.rangeChanged.emit(self._lower, self._upper)
                
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        self._moving_lower = False
        self._moving_upper = False
        super().mouseReleaseEvent(event)
        
    def _lower_spin_changed(self, value):
        """处理最小值输入框变化"""
        # 确保最小值不超过最大值
        if value > self._upper:
            value = self._upper
            self.lower_spinbox.setValue(value)
            
        if value != self._lower:
            self._lower = value
            self.update()
            self.rangeChanged.emit(self._lower, self._upper)
            
    def _upper_spin_changed(self, value):
        """处理最大值输入框变化"""
        # 确保最大值不小于最小值
        if value < self._lower:
            value = self._lower
            self.upper_spinbox.setValue(value)
            
        if value != self._upper:
            self._upper = value
            self.update()
            self.rangeChanged.emit(self._lower, self._upper)
            
    def setRange(self, min_value, max_value):
        """设置可选范围"""
        self._min_value = min_value
        self._max_value = max_value
        self.base_slider.setRange(min_value, max_value)
        self.lower_spinbox.setRange(min_value, max_value)
        self.upper_spinbox.setRange(min_value, max_value)
        self.update()
        
    def setLower(self, value):
        """设置下限值"""
        self.lower_spinbox.setValue(value)
        
    def setUpper(self, value):
        """设置上限值"""
        self.upper_spinbox.setValue(value)
        
    def lower(self):
        """获取下限值"""
        return self._lower
        
    def upper(self):
        """获取上限值"""
        return self._upper 