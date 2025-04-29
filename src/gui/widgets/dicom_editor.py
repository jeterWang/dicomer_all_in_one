#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QTreeWidget, QTreeWidgetItem, QFileDialog, 
                           QTableWidget, QTableWidgetItem, QHeaderView, 
                           QMessageBox, QLineEdit, QSplitter, QGroupBox, 
                           QFormLayout)
from PyQt5.QtCore import Qt, QSize

from src.core.dicom_utils import (
    read_dicom_file,
    save_dicom_file,
    find_dicom_files,
    get_dicom_attribute,
    convert_value
)

class DicomEditor(QWidget):
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.current_dataset = None
        self.dicom_files = []
        self.dicom_dir = ""
        self.init_ui()
        
    def init_ui(self):
        # 创建主布局
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)
        
        # 创建左侧面板 - 文件浏览器
        self.file_panel = QGroupBox("DICOM 文件")
        file_layout = QVBoxLayout()
        self.file_panel.setLayout(file_layout)
        
        # 添加打开文件夹按钮
        open_btn = QPushButton("打开文件夹")
        open_btn.clicked.connect(self.open_directory)
        file_layout.addWidget(open_btn)
        
        # 添加文件树
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["文件名"])
        self.file_tree.itemClicked.connect(self.on_file_selected)
        file_layout.addWidget(self.file_tree)
        
        # 创建中间面板 - DICOM属性表
        self.attr_panel = QGroupBox("DICOM 属性")
        attr_layout = QVBoxLayout()
        self.attr_panel.setLayout(attr_layout)
        
        # 添加属性表
        self.attr_table = QTableWidget()
        self.attr_table.setColumnCount(4)
        self.attr_table.setHorizontalHeaderLabels(["标签", "描述", "VR", "值"])
        self.attr_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.attr_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.attr_table.itemDoubleClicked.connect(self.on_item_double_clicked)
        attr_layout.addWidget(self.attr_table)
        
        # 创建右侧面板 - 编辑区域
        self.edit_panel = QGroupBox("编辑属性")
        edit_layout = QFormLayout()
        self.edit_panel.setLayout(edit_layout)
        
        # 添加编辑字段
        self.tag_label = QLabel("")
        self.name_label = QLabel("")
        self.vr_label = QLabel("")
        self.value_edit = QLineEdit()
        edit_layout.addRow(QLabel("标签:"), self.tag_label)
        edit_layout.addRow(QLabel("描述:"), self.name_label)
        edit_layout.addRow(QLabel("VR:"), self.vr_label)
        edit_layout.addRow(QLabel("值:"), self.value_edit)
        
        # 添加保存按钮
        self.save_btn = QPushButton("保存修改")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_changes)
        edit_layout.addRow("", self.save_btn)
        
        # 添加批量修改按钮
        self.batch_edit_btn = QPushButton("批量修改所有文件")
        self.batch_edit_btn.setEnabled(False)
        self.batch_edit_btn.clicked.connect(self.batch_edit)
        edit_layout.addRow("", self.batch_edit_btn)
        
        # 创建分割器以允许调整面板大小
        splitter1 = QSplitter(Qt.Horizontal)
        splitter1.addWidget(self.file_panel)
        
        splitter2 = QSplitter(Qt.Horizontal)
        splitter2.addWidget(self.attr_panel)
        splitter2.addWidget(self.edit_panel)
        
        splitter3 = QSplitter(Qt.Horizontal)
        splitter3.addWidget(splitter1)
        splitter3.addWidget(splitter2)
        splitter3.setSizes([300, 900])
        
        main_layout.addWidget(splitter3)
        
    def open_directory(self):
        """打开DICOM文件夹"""
        self.dicom_dir = QFileDialog.getExistingDirectory(self, "选择DICOM文件夹", ".")
        if not self.dicom_dir:
            return
            
        self.dicom_files = []
        self.file_tree.clear()
        
        # 使用工具函数查找DICOM文件
        self.dicom_files = find_dicom_files(self.dicom_dir)
        
        # 构建文件树
        for file_path in self.dicom_files:
            rel_path = os.path.relpath(os.path.dirname(file_path), self.dicom_dir)
            file_name = os.path.basename(file_path)
            
            if rel_path == '.':
                item = QTreeWidgetItem(self.file_tree, [file_name])
            else:
                # 查找或创建父目录项
                parent = None
                for i in range(self.file_tree.topLevelItemCount()):
                    if self.file_tree.topLevelItem(i).text(0) == rel_path:
                        parent = self.file_tree.topLevelItem(i)
                        break
                if not parent:
                    parent = QTreeWidgetItem(self.file_tree, [rel_path])
                item = QTreeWidgetItem(parent, [file_name])
                
            item.setData(0, Qt.UserRole, file_path)
            
        if self.dicom_files:
            self.batch_edit_btn.setEnabled(True)
        else:
            QMessageBox.warning(self, "警告", "未找到DICOM文件！")
                
    def on_file_selected(self, item, column):
        """选择文件时的处理函数"""
        file_path = item.data(0, Qt.UserRole)
        if not file_path:
            return  # 这可能是目录项
        
        try:
            self.current_file = file_path
            self.current_dataset = read_dicom_file(file_path)
            if self.current_dataset:
                self.display_attributes()
                self.save_btn.setEnabled(True)
            else:
                QMessageBox.critical(self, "错误", "无法读取DICOM文件")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法读取DICOM文件: {str(e)}")
            
    def display_attributes(self):
        """显示DICOM属性"""
        if not self.current_dataset:
            return
            
        # 清空表格
        self.attr_table.setRowCount(0)
        
        # 遍历DICOM数据集的元素
        for i, elem in enumerate(self.current_dataset):
            self.attr_table.insertRow(i)
            
            # 获取属性信息
            attr_info = get_dicom_attribute(self.current_dataset, elem.tag)
            
            # 显示标签
            tag_item = QTableWidgetItem(attr_info['tag'])
            self.attr_table.setItem(i, 0, tag_item)
            
            # 显示描述
            name_item = QTableWidgetItem(attr_info['name'])
            self.attr_table.setItem(i, 1, name_item)
            
            # 显示VR
            vr_item = QTableWidgetItem(attr_info['vr'])
            self.attr_table.setItem(i, 2, vr_item)
            
            # 显示值
            value_item = QTableWidgetItem(attr_info['value'])
            self.attr_table.setItem(i, 3, value_item)
            
            # 存储原始标签数据
            tag_item.setData(Qt.UserRole, elem.tag)
            
        self.attr_table.resizeRowsToContents()
            
    def on_item_double_clicked(self, item):
        """双击属性表项时的处理函数"""
        row = item.row()
        
        # 获取标签信息
        tag_item = self.attr_table.item(row, 0)
        name_item = self.attr_table.item(row, 1)
        vr_item = self.attr_table.item(row, 2)
        value_item = self.attr_table.item(row, 3)
        
        if all([tag_item, name_item, vr_item, value_item]):
            tag = tag_item.data(Qt.UserRole)
            
            # 更新编辑区域
            self.tag_label.setText(tag_item.text())
            self.name_label.setText(name_item.text())
            self.vr_label.setText(vr_item.text())
            self.value_edit.setText(value_item.text())
            
            # 标记当前编辑的行
            self.value_edit.setProperty("current_row", row)
            self.value_edit.setProperty("current_tag", tag)
            
    def save_changes(self):
        """保存对当前DICOM文件的更改"""
        if not self.current_dataset or not self.current_file:
            return
            
        row = self.value_edit.property("current_row")
        tag = self.value_edit.property("current_tag")
        
        if row is None or tag is None:
            QMessageBox.warning(self, "警告", "请先选择要编辑的属性！")
            return
            
        new_value = self.value_edit.text()
        vr = self.vr_label.text()
        
        try:
            # 转换值
            converted_value = convert_value(new_value, vr)
            
            # 更新DICOM数据集
            if vr == 'SQ':
                QMessageBox.warning(self, "警告", "目前不支持编辑序列值！")
                return
                
            self.current_dataset[tag].value = converted_value
            
            # 保存DICOM文件
            if save_dicom_file(self.current_dataset, self.current_file):
                # 更新显示
                self.display_attributes()
                QMessageBox.information(self, "成功", "DICOM文件已成功更新！")
            else:
                QMessageBox.critical(self, "错误", "保存DICOM文件失败")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存DICOM文件时出错: {str(e)}")
            
    def batch_edit(self):
        """对所有DICOM文件进行批量修改"""
        row = self.value_edit.property("current_row")
        tag = self.value_edit.property("current_tag")
        
        if row is None or tag is None:
            QMessageBox.warning(self, "警告", "请先选择要批量编辑的属性！")
            return
            
        new_value = self.value_edit.text()
        vr = self.vr_label.text()
        
        reply = QMessageBox.question(self, "确认",
                                    f"确认将所有DICOM文件的 '{self.name_label.text()}' 修改为 '{new_value}'？",
                                    QMessageBox.Yes | QMessageBox.No)
                                    
        if reply == QMessageBox.No:
            return
            
        error_files = []
        
        try:
            for file_path in self.dicom_files:
                try:
                    ds = read_dicom_file(file_path)
                    if not ds:
                        error_files.append(f"{file_path} - 无法读取文件")
                        continue
                    
                    # 检查是否存在该标签
                    if tag in ds:
                        element = ds[tag]
                        vr = getattr(element, 'VR', '')
                        
                        # 转换值
                        try:
                            converted_value = convert_value(new_value, vr)
                        except ValueError:
                            error_files.append(f"{file_path} - 无法转换值")
                            continue
                            
                        # 更新DICOM数据集
                        if vr == 'SQ':
                            error_files.append(f"{file_path} - 不支持编辑序列值")
                            continue
                            
                        ds[tag].value = converted_value
                        
                        # 保存DICOM文件
                        if not save_dicom_file(ds, file_path):
                            error_files.append(f"{file_path} - 保存失败")
                            
                except Exception as e:
                    error_files.append(f"{file_path} - {str(e)}")
                    
            # 更新当前显示（如果适用）
            if self.current_dataset and self.current_file:
                self.current_dataset = read_dicom_file(self.current_file)
                self.display_attributes()
                
            if error_files:
                error_msg = "以下文件处理失败:\n" + "\n".join(error_files[:10])
                if len(error_files) > 10:
                    error_msg += f"\n...以及另外 {len(error_files) - 10} 个文件"
                QMessageBox.warning(self, "批量修改结果", error_msg)
            else:
                QMessageBox.information(self, "成功", "所有DICOM文件已成功更新！")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"批量修改时出错: {str(e)}") 