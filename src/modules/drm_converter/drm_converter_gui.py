import sys
import os
import logging
import traceback
from pathlib import Path
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QLabel, QLineEdit, QTextEdit, QProgressBar,
                           QFileDialog, QMessageBox, QGroupBox, QGridLayout)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QFont

from .drm_converter_main import DRMConverter, save_binary_mask_nii


class DRMConverterWorker(QThread):
    """DRM转换工作线程"""
    
    progress_updated = pyqtSignal(str)  # 进度更新信号
    conversion_finished = pyqtSignal(bool, str)  # 转换完成信号
    log_updated = pyqtSignal(str)  # 日志更新信号
    
    def __init__(self, drm_folder_path, output_folder_path):
        super().__init__()
        self.drm_folder_path = drm_folder_path
        self.output_folder_path = output_folder_path
        self.converter = DRMConverter()
        
        # 设置日志处理器，将日志重定向到信号
        self.setup_logging()
        
    def setup_logging(self):
        """设置线程专用的日志处理器"""
        class ThreadLogHandler(logging.Handler):
            def __init__(self, worker):
                super().__init__()
                self.worker = worker
                
            def emit(self, record):
                try:
                    log_message = self.format(record)
                    self.worker.log_updated.emit(log_message)
                except:
                    pass  # 忽略日志错误，防止崩溃
        
        self.log_handler = ThreadLogHandler(self)
        self.log_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%H:%M:%S'
        ))
        
        # 为DRM转换器的logger添加处理器
        drm_logger = logging.getLogger('src.modules.drm_converter.drm_converter_main')
        drm_logger.addHandler(self.log_handler)
        drm_logger.setLevel(logging.INFO)
        
    def run(self):
        """执行DRM转换"""
        try:
            self.progress_updated.emit("初始化转换器...")
            self.log_updated.emit("=== 开始DRM转换 ===")
            
            # 确保工作目录正确 - 这是关键！
            import os
            original_cwd = os.getcwd()
            
            # 如果当前目录不在项目根目录，切换到项目根目录
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if os.path.exists(os.path.join(project_root, 'main.py')):
                os.chdir(project_root)
                self.log_updated.emit(f"工作目录切换到: {os.getcwd()}")
            
            # 验证路径
            if not os.path.exists(self.drm_folder_path):
                raise FileNotFoundError(f"DRM文件夹不存在: {self.drm_folder_path}")
            
            self.log_updated.emit(f"DRM文件夹: {self.drm_folder_path}")
            self.log_updated.emit(f"输出文件夹: {self.output_folder_path}")
            
            # 执行转换
            self.progress_updated.emit("正在转换中...")
            
            success = self.converter.convert_drm_folder(
                self.drm_folder_path, 
                self.output_folder_path
            )
            
            if success:
                self.conversion_finished.emit(True, "DRM转换成功完成！所有文件已保存为完整的DICOM series。")
                self.log_updated.emit("=== 转换成功完成 ===")
            else:
                self.conversion_finished.emit(False, "DRM转换失败，请查看日志详情。")
                self.log_updated.emit("=== 转换失败 ===")
                
        except Exception as e:
            import traceback
            error_msg = f"DRM转换出错: {str(e)}"
            error_detail = traceback.format_exc()
            
            self.log_updated.emit(f"错误详情: {error_detail}")
            self.conversion_finished.emit(False, error_msg)
        
        finally:
            # 恢复原始工作目录
            try:
                os.chdir(original_cwd)
            except:
                pass
                
            # 清理日志处理器
            try:
                drm_logger = logging.getLogger('src.modules.drm_converter.drm_converter_main')
                drm_logger.removeHandler(self.log_handler)
            except:
                pass


class DRMConverterGUI(QWidget):
    """DRM转换器GUI界面"""
    
    def __init__(self):
        super().__init__()
        self.converter_worker = None
        self.setup_ui()
        self.setup_logging()
        
    def setup_ui(self):
        """设置界面"""
        self.setWindowTitle("DRM转换器 - NII.gz到DICOM Series")
        self.setMinimumSize(800, 700)
        
        # 主布局
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)
        
        # 标题
        title_label = QLabel("DRM转换器")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # 路径选择组
        path_group = QGroupBox("路径设置")
        path_layout = QGridLayout()
        path_group.setLayout(path_layout)
        
        # DRM文件夹路径
        path_layout.addWidget(QLabel("DRM文件夹路径:"), 0, 0)
        self.drm_folder_edit = QLineEdit()
        self.drm_folder_edit.setPlaceholderText("选择包含DRM.nii.gz和CT文件夹的目录")
        path_layout.addWidget(self.drm_folder_edit, 0, 1)
        
        self.browse_drm_btn = QPushButton("浏览...")
        self.browse_drm_btn.clicked.connect(self.browse_drm_folder)
        path_layout.addWidget(self.browse_drm_btn, 0, 2)
        
        # 输出文件夹路径
        path_layout.addWidget(QLabel("输出文件夹路径:"), 1, 0)
        self.output_folder_edit = QLineEdit()
        self.output_folder_edit.setPlaceholderText("选择DICOM series输出目录")
        path_layout.addWidget(self.output_folder_edit, 1, 1)
        
        self.browse_output_btn = QPushButton("浏览...")
        self.browse_output_btn.clicked.connect(self.browse_output_folder)
        path_layout.addWidget(self.browse_output_btn, 1, 2)
        
        main_layout.addWidget(path_group)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        self.convert_btn = QPushButton("开始转换")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.convert_btn.setMinimumHeight(40)
        
        self.clear_btn = QPushButton("清除")
        self.clear_btn.clicked.connect(self.clear_all)
        
        button_layout.addWidget(self.convert_btn)
        button_layout.addWidget(self.clear_btn)
        main_layout.addLayout(button_layout)
        
        # 进度显示
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 日志显示
        log_group = QGroupBox("转换日志")
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)
        
        self.log_text = QTextEdit()
        self.log_text.setMinimumHeight(300)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        main_layout.addWidget(log_group)
        
        # 添加说明文本
        help_text = """
使用说明：
1. 选择包含DRM.nii.gz文件和CT DICOM文件夹的目录
2. 选择输出目录（转换后的DICOM series将保存在此）
3. 点击"开始转换"按钮
4. 程序会自动找到DRM.nii.gz文件和CT文件夹，并使用CT的头文件信息创建DICOM series

重要改进：
✓ 所有DICOM文件现在共享相同的SeriesInstanceUID
✓ 正确设置StudyInstanceUID和FrameOfReferenceUID
✓ 每个切片有连续的InstanceNumber和准确的SliceLocation
✓ 确保生成的文件能被DICOM查看器识别为完整的series

注意：确保DRM文件夹中包含：
- DRM.nii.gz文件（或包含"drm"的.nii.gz文件）
- 包含CT DICOM文件的文件夹（文件夹名包含"CT"）
        """
        
        help_label = QLabel(help_text)
        help_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 10px; border-radius: 5px; }")
        help_label.setWordWrap(True)
        main_layout.addWidget(help_label)
        
        # === 新增：生成二值mask NII按钮 ===
        mask_btn_layout = QHBoxLayout()
        self.generate_mask_btn = QPushButton("生成二值mask NII")
        self.generate_mask_btn.clicked.connect(self.generate_mask_nii)
        mask_btn_layout.addWidget(self.generate_mask_btn)
        main_layout.addLayout(mask_btn_layout)
        
    def setup_logging(self):
        """设置日志"""
        # 简化日志处理，避免冲突
        # 只使用我们自己的信号系统，不干扰全局日志
        pass
        
    def browse_drm_folder(self):
        """浏览DRM文件夹"""
        folder = QFileDialog.getExistingDirectory(
            self, "选择DRM文件夹", self.drm_folder_edit.text()
        )
        if folder:
            self.drm_folder_edit.setText(folder)
            
    def browse_output_folder(self):
        """浏览输出文件夹"""
        folder = QFileDialog.getExistingDirectory(
            self, "选择输出文件夹", self.output_folder_edit.text()
        )
        if folder:
            self.output_folder_edit.setText(folder)
            
    def validate_inputs(self):
        """验证输入"""
        drm_folder = self.drm_folder_edit.text().strip()
        output_folder = self.output_folder_edit.text().strip()
        
        if not drm_folder:
            QMessageBox.warning(self, "警告", "请选择DRM文件夹！")
            return False
            
        if not output_folder:
            QMessageBox.warning(self, "警告", "请选择输出文件夹！")
            return False
            
        if not os.path.exists(drm_folder):
            QMessageBox.warning(self, "警告", "DRM文件夹不存在！")
            return False
            
        # 检查DRM文件夹内容
        has_nii = False
        has_ct_folder = False
        
        for item in os.listdir(drm_folder):
            if item.lower().endswith('.nii.gz') and 'drm' in item.lower():
                has_nii = True
            item_path = os.path.join(drm_folder, item)
            if os.path.isdir(item_path) and 'CT' in item:
                has_ct_folder = True
                
        if not has_nii:
            QMessageBox.warning(self, "警告", "在选择的文件夹中未找到DRM.nii.gz文件！")
            return False
            
        if not has_ct_folder:
            QMessageBox.warning(self, "警告", "在选择的文件夹中未找到CT文件夹！")
            return False
            
        return True
        
    def start_conversion(self):
        """开始转换"""
        if not self.validate_inputs():
            return
            
        # 禁用按钮
        self.convert_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度
        
        # 清除日志
        self.log_text.clear()
        
        # 标准化路径 - 这很重要！
        drm_folder = os.path.normpath(self.drm_folder_edit.text().strip())
        output_folder = os.path.normpath(self.output_folder_edit.text().strip())
        
        self.log_text.append(f"[开始] DRM文件夹: {drm_folder}")
        self.log_text.append(f"[开始] 输出文件夹: {output_folder}")
        
        # 创建并启动工作线程
        self.converter_worker = DRMConverterWorker(drm_folder, output_folder)
        
        # 连接所有信号
        self.converter_worker.progress_updated.connect(self.update_progress)
        self.converter_worker.conversion_finished.connect(self.conversion_finished)
        self.converter_worker.log_updated.connect(self.update_log)
        
        # 启动线程
        self.converter_worker.start()
        
    def update_progress(self, message):
        """更新进度"""
        self.log_text.append(f"[进度] {message}")
        
    def conversion_finished(self, success, message):
        """转换完成"""
        self.progress_bar.setVisible(False)
        self.convert_btn.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "成功", message)
            self.log_text.append(f"[完成] {message}")
        else:
            QMessageBox.critical(self, "错误", message)
            self.log_text.append(f"[错误] {message}")
            
        self.converter_worker = None
        
    def clear_all(self):
        """清除所有内容"""
        self.drm_folder_edit.clear()
        self.output_folder_edit.clear()
        self.log_text.clear()
        
    def closeEvent(self, event):
        """关闭事件"""
        if self.converter_worker and self.converter_worker.isRunning():
            reply = QMessageBox.question(
                self, "确认", "转换正在进行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.converter_worker.terminate()
                self.converter_worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def update_log(self, message):
        """更新日志"""
        self.log_text.append(f"[日志] {message}")
        
        # 滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.End)
        self.log_text.setTextCursor(cursor) 
        
    def generate_mask_nii(self):
        """选择NII文件并生成二值mask NII"""
        from PyQt5.QtWidgets import QFileDialog
        from .drm_converter_main import save_binary_mask_nii
        nii_path, _ = QFileDialog.getOpenFileName(self, "选择NII文件", "", "NIfTI文件 (*.nii *.nii.gz)")
        if not nii_path:
            return
        try:
            self.log_text.append(f"[mask] 处理: {nii_path}")
            save_binary_mask_nii(nii_path)
            if nii_path.endswith('.nii.gz'):
                out_path = nii_path.replace('.nii.gz', '_mask.nii.gz')
            else:
                out_path = nii_path.replace('.nii', '_mask.nii')
            self.log_text.append(f"[mask] 二值mask已保存: {out_path}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "成功", f"二值mask已保存: {out_path}")
        except Exception as e:
            self.log_text.append(f"[mask] 生成失败: {e}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"生成二值mask失败: {e}") 