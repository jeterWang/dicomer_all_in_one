#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import logging
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from src.gui.main_window import MainWindow

# 配置基础日志记录
log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
# 可以将日志级别设置为 INFO 以查看更详细的输出
logging.basicConfig(level=logging.WARNING, format=log_format)

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # --- 设置应用程序图标 ---
    try:
        # 获取当前文件所在目录 (项目根目录)
        # __file__ 在某些打包场景下可能不存在，做个简单判断
        if '__file__' in globals():
             current_dir = os.path.dirname(os.path.abspath(__file__))
             # 构建图标文件的绝对路径
             icon_path = os.path.join(current_dir, 'src', 'source', 'icon.svg')

             if os.path.exists(icon_path):
                 app_icon = QIcon(icon_path)
                 app.setWindowIcon(app_icon)
                 logging.info(f"应用程序图标已设置为: {icon_path}")
             else:
                 logging.warning(f"未找到图标文件: {icon_path}，将使用默认图标。")
        else:
             logging.warning("无法确定 __file__ 路径，跳过图标设置。")
    except Exception as e:
        logging.error(f"设置应用程序图标时出错: {e}", exc_info=True)
    # --- 图标设置结束 ---

    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 