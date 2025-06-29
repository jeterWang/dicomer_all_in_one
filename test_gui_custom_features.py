#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试GUI中的自定义功能
验证新增的自定义选项是否正常工作
"""

import os
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gui.main_window import MainWindow

def test_gui_features():
    """测试GUI自定义功能"""
    print("测试GUI自定义功能")
    print("=" * 40)
    
    app = QApplication(sys.argv)
    
    # 创建主窗口
    window = MainWindow()
    
    # 检查NIfTI相关性分析标签页是否存在
    tab_count = window.tab_widget.count()
    print(f"标签页总数: {tab_count}")
    
    # 查找NIfTI相关性分析标签页
    nifti_tab_index = -1
    for i in range(tab_count):
        tab_text = window.tab_widget.tabText(i)
        print(f"标签页 {i}: {tab_text}")
        if "NIfTI相关性分析" in tab_text:
            nifti_tab_index = i
            break
    
    if nifti_tab_index >= 0:
        print(f"✓ 找到NIfTI相关性分析标签页，索引: {nifti_tab_index}")
        
        # 切换到NIfTI标签页
        window.tab_widget.setCurrentIndex(nifti_tab_index)
        
        # 检查自定义选项控件是否存在
        custom_controls = [
            ('nifti_chart_title', '图表标题输入框'),
            ('nifti_x_label', 'X轴标签输入框'),
            ('nifti_y_label', 'Y轴标签输入框'),
            ('nifti_output_prefix', '输出前缀输入框')
        ]
        
        print("\n检查自定义控件:")
        for attr_name, description in custom_controls:
            if hasattr(window, attr_name):
                control = getattr(window, attr_name)
                print(f"✓ {description}: {type(control).__name__}")
                
                # 测试设置值
                test_value = f"测试_{attr_name}"
                control.setText(test_value)
                if control.text() == test_value:
                    print(f"  └─ 值设置测试通过: '{test_value}'")
                else:
                    print(f"  └─ 值设置测试失败")
            else:
                print(f"✗ 缺少 {description}")
        
        # 检查相关性分析标签页的自定义控件
        print("\n检查DICOM相关性分析自定义控件:")
        dicom_controls = [
            ('correlation_chart_title', '图表标题输入框'),
            ('correlation_x_label', 'X轴标签输入框'),
            ('correlation_y_label', 'Y轴标签输入框'),
            ('correlation_output_prefix', '输出前缀输入框')
        ]
        
        for attr_name, description in dicom_controls:
            if hasattr(window, attr_name):
                control = getattr(window, attr_name)
                print(f"✓ {description}: {type(control).__name__}")
            else:
                print(f"✗ 缺少 {description}")
        
        print("\n✓ GUI自定义功能检查完成!")
        
    else:
        print("✗ 未找到NIfTI相关性分析标签页")
    
    # 设置定时器自动关闭应用程序
    timer = QTimer()
    timer.timeout.connect(app.quit)
    timer.start(2000)  # 2秒后自动关闭
    
    # 显示窗口
    window.show()
    
    # 运行应用程序
    app.exec_()
    
    print("GUI测试完成")

if __name__ == "__main__":
    test_gui_features()
