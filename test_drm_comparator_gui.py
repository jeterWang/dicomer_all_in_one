#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试DRM比较器GUI集成
验证GUI是否正确集成到主窗口中
"""

import os
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_gui_integration():
    """测试GUI集成"""
    print("测试DRM比较器GUI集成")
    print("=" * 40)
    
    app = QApplication(sys.argv)
    
    try:
        # 导入主窗口
        from gui.main_window import MainWindow
        
        # 创建主窗口
        print("创建主窗口...")
        window = MainWindow()
        
        # 检查标签页
        tab_count = window.tab_widget.count()
        print(f"标签页总数: {tab_count}")
        
        # 查找DRM比较器标签页
        drm_comparator_found = False
        for i in range(tab_count):
            tab_text = window.tab_widget.tabText(i)
            print(f"标签页 {i}: {tab_text}")
            if "DRM比较器" in tab_text:
                drm_comparator_found = True
                print(f"✓ 找到DRM比较器标签页，索引: {i}")
                
                # 切换到DRM比较器标签页
                window.tab_widget.setCurrentIndex(i)
                current_widget = window.tab_widget.currentWidget()
                print(f"当前标签页组件类型: {type(current_widget).__name__}")
                
                # 检查DRM比较器GUI的关键组件
                if hasattr(current_widget, 'comparator'):
                    print("✓ DRM比较器组件存在")
                if hasattr(current_widget, 'btn_apply_transform'):
                    print("✓ 应用变换按钮存在")
                if hasattr(current_widget, 'btn_compare_methods'):
                    print("✓ 比较方法按钮存在")
                if hasattr(current_widget, 'log_text'):
                    print("✓ 日志文本区域存在")
                
                break
        
        if drm_comparator_found:
            print("✅ DRM比较器GUI集成成功!")
        else:
            print("❌ 未找到DRM比较器标签页")
            return False
        
        # 显示窗口（短暂显示）
        window.show()
        
        # 设置定时器自动关闭
        timer = QTimer()
        timer.timeout.connect(app.quit)
        timer.start(3000)  # 3秒后关闭
        
        print("GUI窗口已显示，3秒后自动关闭...")
        app.exec_()
        
        return True
        
    except Exception as e:
        print(f"❌ GUI集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_standalone_drm_gui():
    """测试独立的DRM比较器GUI"""
    print("\n测试独立DRM比较器GUI")
    print("=" * 40)
    
    app = QApplication(sys.argv)
    
    try:
        # 直接导入DRM比较器GUI
        from gui.modules.drm_comparator_gui import DrmComparatorGUI
        
        print("创建DRM比较器GUI...")
        drm_gui = DrmComparatorGUI()
        
        # 检查关键组件
        components = [
            ('comparator', 'DRM比较器核心组件'),
            ('btn_apply_transform', '应用变换按钮'),
            ('btn_compare_methods', '比较方法按钮'),
            ('btn_save_result', '保存结果按钮'),
            ('progress_bar', '进度条'),
            ('log_text', '日志文本区域'),
            ('nifti_label', 'NIfTI文件标签'),
            ('rigid_label', '刚体变换标签'),
            ('dvf_label', 'DVF变换标签'),
            ('target_label', '目标图像标签')
        ]
        
        print("检查GUI组件:")
        all_components_exist = True
        for attr_name, description in components:
            if hasattr(drm_gui, attr_name):
                print(f"✓ {description}")
            else:
                print(f"❌ 缺少 {description}")
                all_components_exist = False
        
        if all_components_exist:
            print("✅ 所有GUI组件都存在")
        else:
            print("⚠️ 部分GUI组件缺失")
        
        # 显示窗口
        drm_gui.show()
        
        # 设置定时器自动关闭
        timer = QTimer()
        timer.timeout.connect(app.quit)
        timer.start(2000)  # 2秒后关闭
        
        print("独立GUI窗口已显示，2秒后自动关闭...")
        app.exec_()
        
        return all_components_exist
        
    except Exception as e:
        print(f"❌ 独立GUI测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_file_structure():
    """检查文件结构"""
    print("\n检查文件结构")
    print("=" * 40)
    
    files_to_check = [
        "src/gui/modules/drm_comparator_gui.py",
        "src/modules/drm_comparator/drm_comparator.py",
        "src/gui/main_window.py"
    ]
    
    all_files_exist = True
    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"✓ {file_path}")
        else:
            print(f"❌ {file_path} - 文件不存在")
            all_files_exist = False
    
    return all_files_exist

if __name__ == "__main__":
    print("🧪 DRM比较器GUI集成测试")
    print("=" * 60)
    
    try:
        # 检查文件结构
        files_ok = check_file_structure()
        
        if not files_ok:
            print("❌ 文件结构检查失败，无法继续测试")
            sys.exit(1)
        
        # 测试独立GUI
        standalone_ok = test_standalone_drm_gui()
        
        # 测试GUI集成
        integration_ok = test_gui_integration()
        
        # 总结
        print("\n" + "=" * 60)
        print("📋 测试结果总结")
        print("=" * 60)
        print(f"✅ 文件结构检查: {'通过' if files_ok else '失败'}")
        print(f"✅ 独立GUI测试: {'通过' if standalone_ok else '失败'}")
        print(f"✅ GUI集成测试: {'通过' if integration_ok else '失败'}")
        
        if all([files_ok, standalone_ok, integration_ok]):
            print(f"\n🎉 所有测试通过！DRM比较器GUI已成功集成")
            print(f"💡 现在可以在主窗口的'DRM比较器'标签页中使用该功能")
        else:
            print(f"\n⚠️ 部分测试失败，请检查错误信息")
            
    except Exception as e:
        print(f"\n❌ 测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
