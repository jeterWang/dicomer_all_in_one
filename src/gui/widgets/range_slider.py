#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QSpinBox
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QSize
from PyQt5.QtGui import QPainter, QColor, QBrush, QPen, QLinearGradient

class RangeSlider(QWidget):
    """双滑块范围选择控件"""
    
    # 定义信号
    rangeChanged = pyqtSignal(int, int)  # 范围变化信号
    sliderReleased = pyqtSignal()  # 滑块释放信号
    
    def __init__(self, parent=None, min_value=0, max_value=100, lower=0, upper=100):
        super().__init__(parent)
        
        # 设置最小高度以确保控件可见
        self.setMinimumHeight(50)
        
        # 设置主布局
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)  # 增加内边距
        self.layout.setSpacing(10)  # 增加元素间距
        
        # 添加标签
        self.min_label = QLabel("范围:")
        self.min_label.setMinimumWidth(60)  # 设置最小宽度
        self.layout.addWidget(self.min_label)
        
        # 添加弹性空间，用于绘制滑块
        self.layout.addStretch(1)
        
        # 创建两个数值输入框
        self.lower_spinbox = QSpinBox()
        self.lower_spinbox.setMinimumWidth(60)  # 设置最小宽度
        self.lower_spinbox.setRange(min_value, max_value)
        self.lower_spinbox.setValue(lower)
        self.lower_spinbox.valueChanged.connect(self._lower_spin_changed)
        self.layout.addWidget(self.lower_spinbox)
        
        self.upper_spinbox = QSpinBox()
        self.upper_spinbox.setMinimumWidth(60)  # 设置最小宽度
        self.upper_spinbox.setRange(min_value, max_value)
        self.upper_spinbox.setValue(upper)
        self.upper_spinbox.valueChanged.connect(self._upper_spin_changed)
        self.layout.addWidget(self.upper_spinbox)
        
        # 设置内部变量
        self._min_value = min_value
        self._max_value = max_value
        self._lower = lower
        self._upper = upper
        
        # 初始化拖动状态
        self._moving_lower = False
        self._moving_upper = False
        self._hover_pos = None
        
        # 设置接受鼠标追踪
        self.setMouseTracking(True)
        
        # 更新下限和上限的显示
        self.lower_spinbox.setValue(lower)
        self.upper_spinbox.setValue(upper)
        
    def sizeHint(self):
        """返回建议的控件大小"""
        return QSize(400, 50)  # 增加建议大小
        
    def paintEvent(self, event):
        """绘制自定义双滑块外观"""
        super().paintEvent(event)
        
        # 创建画笔
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 计算滑块区域，保留左侧标签和右侧数值框的空间
        label_width = self.min_label.width() + 10  # 标签宽度加间距
        spin_width = self.lower_spinbox.width() + self.upper_spinbox.width() + 10  # 数值框宽度加间距
        
        slider_width = self.width() - label_width - spin_width - 20  # 控件总宽度减去其他元素宽度和边距
        
        # 确保滑块有最小宽度
        slider_width = max(100, slider_width)
        
        slider_left = label_width + 5
        slider_right = slider_left + slider_width
        
        # 计算滑块轨道区域
        track_height = 8
        track_y = self.height() // 2 - track_height // 2
        track_rect = QRectF(
            slider_left, 
            track_y,
            slider_width,
            track_height
        )
        
        # 计算滑块范围
        slider_range = self._max_value - self._min_value
        if slider_range <= 0:
            return
            
        # 计算滑块位置
        lower_pos = slider_left + (self._lower - self._min_value) / slider_range * slider_width
        upper_pos = slider_left + (self._upper - self._min_value) / slider_range * slider_width
        
        # 绘制轨道背景 - 使用渐变
        track_gradient = QLinearGradient(track_rect.topLeft(), track_rect.bottomRight())
        track_gradient.setColorAt(0, QColor(220, 220, 220))
        track_gradient.setColorAt(1, QColor(200, 200, 200))
        painter.setBrush(QBrush(track_gradient))
        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.drawRoundedRect(track_rect, track_height / 2, track_height / 2)
        
        # 绘制选中范围 - 使用渐变
        if lower_pos < upper_pos:
            selected_rect = QRectF(
                lower_pos,
                track_y,
                upper_pos - lower_pos,
                track_height
            )
            
            selected_gradient = QLinearGradient(
                selected_rect.topLeft(), 
                selected_rect.bottomRight()
        )
            selected_gradient.setColorAt(0, QColor(0, 120, 215))
            selected_gradient.setColorAt(1, QColor(30, 150, 245))
            
            painter.setBrush(QBrush(selected_gradient))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(selected_rect, track_height / 2, track_height / 2)
        
        # 绘制滑块手柄
        handle_radius = 10
        
        # 绘制下限滑块
        lower_handle_center = QRectF(
            lower_pos - handle_radius,
            track_y + track_height / 2 - handle_radius,
            handle_radius * 2,
            handle_radius * 2
        )
        
        # 鼠标悬停或拖动时的下限滑块效果
        if self._moving_lower or (self._hover_pos and lower_handle_center.contains(self._hover_pos)):
            # 绘制发光效果
            glow_pen = QPen(QColor(0, 120, 215, 100), 4)
            painter.setPen(glow_pen)
            painter.drawEllipse(lower_handle_center)
            
        # 绘制下限滑块本体
        lower_gradient = QLinearGradient(
            lower_handle_center.topLeft(), 
            lower_handle_center.bottomRight()
        )
        lower_gradient.setColorAt(0, QColor(255, 255, 255))
        lower_gradient.setColorAt(1, QColor(240, 240, 240))
        
        painter.setBrush(QBrush(lower_gradient))
        painter.setPen(QPen(QColor(150, 150, 150), 1))
        painter.drawEllipse(lower_handle_center)
        
        # 绘制上限滑块
        upper_handle_center = QRectF(
            upper_pos - handle_radius,
            track_y + track_height / 2 - handle_radius,
            handle_radius * 2,
            handle_radius * 2
        )
        
        # 鼠标悬停或拖动时的上限滑块效果
        if self._moving_upper or (self._hover_pos and upper_handle_center.contains(self._hover_pos)):
            # 绘制发光效果
            glow_pen = QPen(QColor(0, 120, 215, 100), 4)
            painter.setPen(glow_pen)
            painter.drawEllipse(upper_handle_center)
            
        # 绘制上限滑块本体
        upper_gradient = QLinearGradient(
            upper_handle_center.topLeft(), 
            upper_handle_center.bottomRight()
        )
        upper_gradient.setColorAt(0, QColor(255, 255, 255))
        upper_gradient.setColorAt(1, QColor(240, 240, 240))
        
        painter.setBrush(QBrush(upper_gradient))
        painter.setPen(QPen(QColor(150, 150, 150), 1))
        painter.drawEllipse(upper_handle_center)
        
        # 保存滑块区域供鼠标事件使用
        self._slider_left = slider_left
        self._slider_width = slider_width
        self._lower_handle = lower_handle_center
        self._upper_handle = upper_handle_center
        
    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        # 先将两个标志重置
        self._moving_lower = False
        self._moving_upper = False

        if hasattr(self, '_lower_handle') and hasattr(self, '_upper_handle'):
            # 判断点击的是哪个滑块
            if self._lower_handle.contains(event.pos()):
                self._moving_lower = True
            elif self._upper_handle.contains(event.pos()):
                self._moving_upper = True

        # 如果确实开始移动，可以立即调用 mouseMoveEvent 更新位置
        # （可选，因为拖动时 mouseMoveEvent 会自动触发）
        # if self._moving_lower or self._moving_upper:
        #     self.mouseMoveEvent(event)

        # 更新外观以显示按下的效果（例如辉光）
        self.update()
        
    def mouseMoveEvent(self, event):
        """处理鼠标移动事件"""
        # 更新鼠标位置用于高亮显示
        self._hover_pos = event.pos()
        
        if hasattr(self, '_slider_left') and hasattr(self, '_slider_width'):
            if self._moving_lower or self._moving_upper:
                # 计算鼠标位置对应的值
                x = event.pos().x()
                pos_ratio = max(0, min(1, (x - self._slider_left) / self._slider_width))
                value = int(self._min_value + pos_ratio * (self._max_value - self._min_value))

                if self._moving_lower:
                    # 确保下限不超过上限
                    value = min(value, self._upper)
                    if value != self._lower:
                        self._lower = value
                        self.lower_spinbox.setValue(value)
                        self.update()
                        self.rangeChanged.emit(self._lower, self._upper)
                if self._moving_upper:
                    # 确保上限不小于下限
                    value = max(value, self._lower)
                    if value != self._upper:
                        self._upper = value
                        self.upper_spinbox.setValue(value)
                        self.update()
                        self.rangeChanged.emit(self._lower, self._upper)
        else:
            # 如果没有移动滑块，也需要更新以显示悬停效果
            self.update()
        
    def mouseReleaseEvent(self, event):
        """处理鼠标释放事件"""
        self._moving_lower = False
        self._moving_upper = False
        self.update()
        self.sliderReleased.emit()
        
    def leaveEvent(self, event):
        """处理鼠标离开事件"""
        self._hover_pos = None
        self.update()
        
    def _lower_spin_changed(self, value):
        """处理下限输入框变化"""
        # 确保下限不超过上限
        if value > self._upper:
            value = self._upper
            self.lower_spinbox.setValue(value)
            
        if value != self._lower:
            self._lower = value
            self.update()
            self.rangeChanged.emit(self._lower, self._upper)
            
    def _upper_spin_changed(self, value):
        """处理上限输入框变化"""
        # 确保上限不小于下限
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