#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QTabWidget, QMenuBar, QMenu, QAction, QStatusBar)
from PyQt5.QtCore import Qt

from .widgets.dicom_editor import DicomEditor
from .widgets.dvf_viewer import DVFViewer
# 后续可以添加其他模块的导入

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DICOM All-in-One 工具')
        self.setGeometry(100, 100, 1600, 900)
        
        self.init_ui()
        
    def init_ui(self):
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 创建状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # 添加各个功能模块
        self.add_dicom_editor()
        self.add_dvf_viewer()
        # 后续可以添加其他模块
        
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu('文件')
        open_action = QAction('打开', self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu('工具')
        editor_action = QAction('DICOM编辑器', self)
        editor_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(0))
        tools_menu.addAction(editor_action)
        
        dvf_action = QAction('DVF查看器', self)
        dvf_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(1))
        tools_menu.addAction(dvf_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu('帮助')
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
    def add_dicom_editor(self):
        """添加DICOM编辑器标签页"""
        editor = DicomEditor()
        self.tab_widget.addTab(editor, "DICOM编辑器")
        
    def add_dvf_viewer(self):
        """添加DVF查看器标签页"""
        dvf_viewer = DVFViewer()
        self.tab_widget.addTab(dvf_viewer, "DVF查看器")
        
    def open_file(self):
        """打开文件"""
        # TODO: 实现文件打开功能
        pass
        
    def show_about(self):
        """显示关于对话框"""
        # TODO: 实现关于对话框
        pass 