#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                           QTabWidget, QMenuBar, QMenu, QAction, QStatusBar,
                           QFileDialog, QPushButton, QLabel, QComboBox, QGridLayout,
                           QProgressBar, QTextEdit, QSplitter, QGroupBox, QFormLayout,
                           QDoubleSpinBox, QCheckBox)
from PyQt5.QtCore import Qt
import os
import logging
import glob # 添加 glob 模块导入，用于文件搜索

from .widgets.dicom_editor import DicomEditor
from .widgets.dvf_viewer import DVFViewer
from .modules.rtss_copier import RTSSCopier  # 导入RTSS复制器模块
from src.modules.dvf_applier import DVFApplier  # 导入DVF应用器模块
from src.modules.image_regid_mover import ImageRigidMover  # 导入刚体位移模块
from src.modules.correlation_analyzer import CorrelationAnalyzer  # 导入相关性分析模块
from src.modules.drm_converter.drm_converter_gui import DRMConverterGUI  # 导入DRM转换器模块
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
        self.add_rtss_copier()  # 添加RTSS复制器
        self.add_dvf_pet_applicator_tab() # 添加DVF应用器标签页
        self.add_image_rigid_mover_tab() # 添加刚体位移标签页
        self.add_correlation_analyzer_tab() # 添加相关性分析标签页
        self.add_drm_converter_tab()  # 添加DRM转换器标签页
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
        
        rtss_action = QAction('RTSS复制器', self)
        rtss_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(2))
        tools_menu.addAction(rtss_action)
        
        correlation_action = QAction('相关性分析', self)
        correlation_action.triggered.connect(lambda: self.tab_widget.setCurrentIndex(5))
        tools_menu.addAction(correlation_action)
        
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
        
    def add_rtss_copier(self):
        """添加RTSS复制器标签页"""
        rtss_copier = RTSSCopier()
        self.tab_widget.addTab(rtss_copier, "RTSS复制器")

    def add_dvf_pet_applicator_tab(self):
        """添加DVF到PET应用标签页"""
        self.dvf_pet_tab = QWidget()
        layout = QVBoxLayout(self.dvf_pet_tab)
        layout.setAlignment(Qt.AlignTop) # 内容顶部对齐

        # 创建一个容器QWidget用于按钮和标签，并设置最大宽度
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_widget.setMaximumWidth(800) # 调整宽度以适应更多内容

        # 文件选择按钮部分
        buttons_widget = QWidget()
        buttons_layout = QGridLayout(buttons_widget)
        
        # 选择根目录按钮
        btn_select_data_root = QPushButton("选择数据根目录 (如 data/dvf_applyer/cwk)")
        btn_select_data_root.clicked.connect(self.select_data_root)
        buttons_layout.addWidget(btn_select_data_root, 0, 0, 1, 2)
        
        # 数据根目录的显示标签
        self.data_root_label = QLabel("数据根目录: 未选择")
        buttons_layout.addWidget(self.data_root_label, 1, 0, 1, 2)

        # 添加源CT和源PET的下拉选择框
        self.src_ct_combo = QComboBox()
        self.src_pt_combo = QComboBox()
        # 设置水平宽度策略
        self.src_ct_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.src_pt_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        
        # 添加标签和下拉框
        buttons_layout.addWidget(QLabel("源CT:"), 2, 0)
        buttons_layout.addWidget(self.src_ct_combo, 2, 1)
        buttons_layout.addWidget(QLabel("源PET:"), 3, 0)
        buttons_layout.addWidget(self.src_pt_combo, 3, 1)
        
        # 添加目标CT和DVF文件的下拉选择框
        self.tgt_ct_combo = QComboBox()
        self.dvf_file_combo = QComboBox()
        self.tgt_ct_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.dvf_file_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        
        buttons_layout.addWidget(QLabel("目标CT:"), 4, 0)
        buttons_layout.addWidget(self.tgt_ct_combo, 4, 1)
        buttons_layout.addWidget(QLabel("DVF文件:"), 5, 0)
        buttons_layout.addWidget(self.dvf_file_combo, 5, 1)
        
        # 添加输出路径行
        self.output_dir_label = QLabel("输出目录: [未设置]")
        self.btn_select_output = QPushButton("选择输出目录")
        self.btn_select_output.clicked.connect(self.select_output_directory)
        buttons_layout.addWidget(self.output_dir_label, 6, 0)
        buttons_layout.addWidget(self.btn_select_output, 6, 1)
        
        # 应用DVF按钮
        self.btn_apply_dvf = QPushButton("应用 DVF 到 PET")
        self.btn_apply_dvf.setEnabled(False) # 初始禁用，直到选择了所有必要文件
        self.btn_apply_dvf.clicked.connect(self.apply_dvf_to_pet)
        buttons_layout.addWidget(self.btn_apply_dvf, 7, 0, 1, 2)
        
        content_layout.addWidget(buttons_widget)
        
        # 添加进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        content_layout.addWidget(self.progress_bar)
        
        # 状态信息标签
        self.dvf_pet_status_label = QLabel("状态: 请选择数据根目录")
        content_layout.addWidget(self.dvf_pet_status_label)
        
        # 添加日志显示区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        content_layout.addWidget(self.log_text)
        
        layout.addWidget(content_widget) # 将内容区域添加到主布局
        self.tab_widget.addTab(self.dvf_pet_tab, "DVF应用器")
        
        # 存储数据目录路径
        self.data_root_path = None
        self.images_path = None
        self.dvf_path = None
        self.output_dir = None
        
        # 初始化DVF应用器
        self.dvf_applier = DVFApplier()
        # 连接信号
        self.dvf_applier.progress_updated.connect(self.update_dvf_progress)
        self.dvf_applier.process_finished.connect(self.on_dvf_process_finished)
        
    def select_data_root(self):
        """选择数据根目录"""
        # 获取当前工作目录，尝试定位到 data/dvf_applyer/cwk
        current_dir = os.getcwd()
        base_data_path = os.path.join(current_dir, 'data', 'dvf_applyer', 'cwk')
        
        if not os.path.exists(base_data_path):
            base_data_path = current_dir # 如果特定路径不存在，则退回到当前目录
            
        # 选择数据根目录
        data_root = QFileDialog.getExistingDirectory(
            self,
            "选择数据根目录",
            base_data_path,
            QFileDialog.ShowDirsOnly
        )
        
        if not data_root:
            self.dvf_pet_status_label.setText("状态: 取消选择数据根目录")
            return
            
        self.data_root_path = data_root
        self.data_root_label.setText(f"数据根目录: {data_root}")
        
        # 查找 images 和 dvf 子目录
        self.images_path = os.path.join(data_root, 'images')
        self.dvf_path = os.path.join(data_root, 'dvf')
        
        if not os.path.exists(self.images_path):
            self.dvf_pet_status_label.setText(f"错误: 在 {data_root} 中未找到 images 目录")
            return
            
        if not os.path.exists(self.dvf_path):
            self.dvf_pet_status_label.setText(f"错误: 在 {data_root} 中未找到 dvf 目录")
            return
            
        # 扫描并解析目录结构
        self.scan_and_parse_directories()
        
    def select_output_directory(self):
        """选择输出目录"""
        # 使用之前选择的数据根目录作为起点，或者当前目录
        start_dir = self.data_root_path if self.data_root_path else os.getcwd()
        
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if output_dir:
            self.output_dir = output_dir
            self.output_dir_label.setText(f"输出目录: {output_dir}")
            self.log_message(f"已选择输出目录: {output_dir}")
            # 如果其他所有必要字段都已选择，则启用应用按钮
            self.check_enable_apply_button()

    def log_message(self, message: str):
        """向日志文本框添加消息"""
        self.log_text.append(message)
        # 滚动到底部
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        
    def update_dvf_progress(self, progress: int, message: str):
        """更新DVF应用进度"""
        self.progress_bar.setValue(progress)
        self.dvf_pet_status_label.setText(f"状态: {message}")
        self.log_message(f"[进度 {progress}%] {message}")
        
    def on_dvf_process_finished(self, success: bool, message: str):
        """DVF应用过程完成回调"""
        if success:
            self.log_message(f"✅ 成功: {message}")
            self.dvf_pet_status_label.setText(f"状态: 成功 - {message}")
        else:
            self.log_message(f"❌ 错误: {message}")
            self.dvf_pet_status_label.setText(f"状态: 失败 - {message}")
        
        # 重新启用应用按钮
        self.btn_apply_dvf.setEnabled(True)
        
    def check_enable_apply_button(self):
        """检查是否应该启用应用按钮"""
        if (self.src_ct_combo.count() > 0 and 
            self.src_pt_combo.count() > 0 and 
            self.tgt_ct_combo.count() > 0 and 
            self.dvf_file_combo.count() > 0 and
            self.output_dir is not None):
            self.btn_apply_dvf.setEnabled(True)
        else:
            self.btn_apply_dvf.setEnabled(False)
            
    def scan_and_parse_directories(self):
        """扫描并解析选择的目录结构"""
        # 清空现有的选项
        self.src_ct_combo.clear()
        self.src_pt_combo.clear()
        self.tgt_ct_combo.clear()
        self.dvf_file_combo.clear()
        
        # 查找 images 子目录中的 CT 和 PET 目录
        try:
            subdirs = [d for d in os.listdir(self.images_path) if os.path.isdir(os.path.join(self.images_path, d))]
            
            ct_dirs = [d for d in subdirs if 'CT' in d.upper()]
            pt_dirs = [d for d in subdirs if 'PT' in d.upper()]
            
            # 将找到的目录添加到下拉框
            self.src_ct_combo.addItems(ct_dirs)
            self.src_pt_combo.addItems(pt_dirs)
            self.tgt_ct_combo.addItems(ct_dirs)
            
            # 查找 dvf 目录中的 DVF 文件
            dvf_files = []
            for ext in ['.mhd', '.raw', '.dcm']:
                files = glob.glob(os.path.join(self.dvf_path, f'*DVF*{ext}'))
                dvf_files.extend([os.path.basename(f) for f in files])
            
            self.dvf_file_combo.addItems(dvf_files)
            
            # 设置默认选项 - 将week4相关的目录设为默认源
            self.set_default_selections(ct_dirs, pt_dirs)
            
            # 设置默认输出目录为 output
            self.setup_default_output_directory()
            
            # 更新状态
            status_msg = f"找到 {len(ct_dirs)} 个CT目录, {len(pt_dirs)} 个PET目录, {len(dvf_files)} 个DVF文件"
            self.dvf_pet_status_label.setText(f"状态: {status_msg}")
            self.log_message(status_msg)
            
            # 检查是否应该启用应用按钮
            self.check_enable_apply_button()
            
        except Exception as e:
            self.dvf_pet_status_label.setText(f"错误: 扫描目录时出错: {str(e)}")
            self.log_message(f"扫描目录出错: {str(e)}")
            logging.error(f"扫描目录结构时出错: {e}", exc_info=True)
            
    def set_default_selections(self, ct_dirs, pt_dirs):
        """设置默认选择的目录"""
        # 查找包含 "week4" 的源CT目录（源CT是week4）
        week4_ct = next((d for d in ct_dirs if 'week4' in d.lower()), None)
        if week4_ct:
            self.src_ct_combo.setCurrentText(week4_ct)
            self.log_message(f"默认源CT设置为: {week4_ct}")
        
        # 查找包含 "week4" 的源PET目录（源PET是week4）
        week4_pt = next((d for d in pt_dirs if 'week4' in d.lower()), None)
        if week4_pt:
            self.src_pt_combo.setCurrentText(week4_pt)
            self.log_message(f"默认源PET设置为: {week4_pt}")
            
        # 目标CT不是week4，优先选择week0
        week0_ct = next((d for d in ct_dirs if 'week0' in d.lower()), None)
        if week0_ct:
            self.tgt_ct_combo.setCurrentText(week0_ct)
            self.log_message(f"默认目标CT设置为: {week0_ct}")
        else:
            # 如果没有week0，选择任何非week4的CT
            non_week4_ct = next((d for d in ct_dirs if 'week4' not in d.lower()), None)
            if non_week4_ct:
                self.tgt_ct_combo.setCurrentText(non_week4_ct)
                self.log_message(f"默认目标CT设置为: {non_week4_ct}")
            
    def setup_default_output_directory(self):
        """设置默认输出目录为output"""
        # 创建output目录
        if self.data_root_path:
            output_dir = os.path.join(self.data_root_path, 'output')
            if not os.path.exists(output_dir):
                try:
                    os.makedirs(output_dir)
                    self.log_message(f"创建默认输出目录: {output_dir}")
                except Exception as e:
                    self.log_message(f"无法创建输出目录: {e}")
                    return
                    
            # 设置为当前输出目录
            self.output_dir = output_dir
            self.output_dir_label.setText(f"输出目录: {output_dir}")
            self.log_message(f"默认输出目录设置为: {output_dir}")
            
    def apply_dvf_to_pet(self):
        """应用DVF到PET"""
        try:
            # 禁用应用按钮，防止重复点击
            self.btn_apply_dvf.setEnabled(False)
            
            # 获取用户选择的值
            src_ct = self.src_ct_combo.currentText()
            src_pet = self.src_pt_combo.currentText()
            tgt_ct = self.tgt_ct_combo.currentText()
            dvf_file = self.dvf_file_combo.currentText()
            
            # 检查是否都已选择
            if not (src_ct and src_pet and tgt_ct and dvf_file and self.output_dir):
                self.log_message("错误: 请选择所有必要的目录和文件")
                self.btn_apply_dvf.setEnabled(True)
                return
                
            # 构建完整路径
            src_ct_path = os.path.join(self.images_path, src_ct)
            src_pet_path = os.path.join(self.images_path, src_pet)
            tgt_ct_path = os.path.join(self.images_path, tgt_ct)
            dvf_file_path = os.path.join(self.dvf_path, dvf_file)
            
            # 记录信息
            self.log_message("======== 开始应用DVF到PET ========")
            self.log_message(f"源CT目录: {src_ct_path}")
            self.log_message(f"源PET目录: {src_pet_path}")
            self.log_message(f"目标CT目录: {tgt_ct_path}")
            self.log_message(f"DVF文件: {dvf_file_path}")
            self.log_message(f"输出目录: {self.output_dir}")
            
            # 更新状态
            self.dvf_pet_status_label.setText(f"状态: 准备将 DVF 从 {src_ct} 应用到 {src_pet}")
            self.statusBar.showMessage(f"正在处理: 源CT={src_ct}, 源PET={src_pet}, 目标CT={tgt_ct}, DVF={dvf_file}")
            
            # 创建一个线程来运行处理过程
            import threading
            
            def process_thread():
                try:
                    # 调用DVF应用器处理
                    success, message, warped_pet = self.dvf_applier.process_directory(
                        src_ct_path, src_pet_path, tgt_ct_path, dvf_file_path
                    )
                    
                    if success and warped_pet is not None:
                        # 保存结果
                        output_file = self.dvf_applier.save_image(
                            warped_pet,
                            self.output_dir,
                            f"warped_pet_{src_pet.replace(' ', '_')}_to_{tgt_ct.replace(' ', '_')}"
                        )
                        # 发送处理完成信号
                        self.dvf_applier.process_finished.emit(True, f"已保存到 {output_file}")
                    else:
                        # 处理失败
                        self.dvf_applier.process_finished.emit(False, message)
                        
                except Exception as e:
                    # 处理异常
                    import traceback
                    error_msg = f"应用DVF时出错: {str(e)}"
                    self.log_message(error_msg)
                    self.log_message(traceback.format_exc())
                    self.dvf_applier.process_finished.emit(False, error_msg)
            
            # 启动处理线程
            thread = threading.Thread(target=process_thread)
            thread.daemon = True  # 设置为守护线程，这样当主程序退出时它会自动终止
            thread.start()
            
        except Exception as e:
            # 处理UI层面的异常
            error_msg = f"准备应用DVF时出错: {str(e)}"
            self.dvf_pet_status_label.setText(f"错误: {error_msg}")
            self.log_message(error_msg)
            self.btn_apply_dvf.setEnabled(True)
            logging.error(error_msg, exc_info=True)

    def open_files_for_dvf_pet_application(self):
        """
        为了保持兼容性而保留的方法，实际上不再使用。
        现在使用 select_data_root 代替。
        """
        pass
        
    def open_file(self):
        """打开文件"""
        # TODO: 实现文件打开功能
        pass
        
    def show_about(self):
        """显示关于对话框"""
        # TODO: 实现关于对话框
        pass

    def add_image_rigid_mover_tab(self):
        """添加图像刚体位移标签页"""
        self.rigid_mover_tab = QWidget()
        layout = QVBoxLayout(self.rigid_mover_tab)
        layout.setAlignment(Qt.AlignTop)  # 内容顶部对齐
        
        # 创建一个容器QWidget用于主要控件
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_widget.setMaximumWidth(900)  # 调整宽度以适应内容
        
        # 创建一个水平分割器，左侧为控制面板，右侧为预览区域
        splitter = QSplitter(Qt.Horizontal)
        content_layout.addWidget(splitter)
        
        # === 左侧：控制面板 ===
        control_panel = QWidget()
        control_layout = QVBoxLayout(control_panel)
        
        # 1. 数据加载部分
        data_group = QGroupBox("数据加载")
        data_layout = QVBoxLayout(data_group)
        
        # 1.1 固定图像（Fixed）加载
        fixed_widget = QWidget()
        fixed_layout = QGridLayout(fixed_widget)
        
        btn_load_fixed = QPushButton("加载固定图像目录")
        btn_load_fixed.clicked.connect(self.load_fixed_directory)
        fixed_layout.addWidget(btn_load_fixed, 0, 0, 1, 2)
        
        self.fixed_dir_label = QLabel("固定图像目录: 未选择")
        fixed_layout.addWidget(self.fixed_dir_label, 1, 0, 1, 2)
        
        # 修改固定图像信息标签，允许显示多行文本
        self.fixed_info_label = QLabel("未加载固定图像")
        self.fixed_info_label.setMinimumHeight(40)  # 设置最小高度
        self.fixed_info_label.setWordWrap(True)  # 允许自动换行
        fixed_layout.addWidget(self.fixed_info_label, 2, 0, 1, 2)
        
        data_layout.addWidget(fixed_widget)
        
        # 1.2 移动图像（Moving）加载
        moving_widget = QWidget()
        moving_layout = QGridLayout(moving_widget)
        
        btn_load_moving = QPushButton("加载移动图像目录")
        btn_load_moving.clicked.connect(self.load_moving_directory)
        moving_layout.addWidget(btn_load_moving, 0, 0, 1, 2)
        
        self.moving_dir_label = QLabel("移动图像目录: 未选择")
        moving_layout.addWidget(self.moving_dir_label, 1, 0, 1, 2)
        
        # 修改移动图像信息标签，允许显示多行文本
        self.moving_info_label = QLabel("未加载移动图像")
        self.moving_info_label.setMinimumHeight(40)  # 设置最小高度
        self.moving_info_label.setWordWrap(True)  # 允许自动换行
        moving_layout.addWidget(self.moving_info_label, 2, 0, 1, 2)
        
        data_layout.addWidget(moving_widget)
        
        control_layout.addWidget(data_group)
        
        # 2. 变换参数设置
        transform_group = QGroupBox("变换参数")
        transform_layout = QFormLayout(transform_group)
        
        # 2.1 平移参数 (Translation)
        self.tx_spin = QDoubleSpinBox()
        self.tx_spin.setRange(-500, 500)
        self.tx_spin.setSingleStep(1.0)
        self.tx_spin.setSuffix(" mm")
        transform_layout.addRow("X平移:", self.tx_spin)
        
        self.ty_spin = QDoubleSpinBox()
        self.ty_spin.setRange(-500, 500)
        self.ty_spin.setSingleStep(1.0)
        self.ty_spin.setSuffix(" mm")
        transform_layout.addRow("Y平移:", self.ty_spin)
        
        self.tz_spin = QDoubleSpinBox()
        self.tz_spin.setRange(-2000, 2000)  # 修改范围为-2000~2000mm，支持更大的平移值
        self.tz_spin.setSingleStep(1.0)
        self.tz_spin.setSuffix(" mm")
        transform_layout.addRow("Z平移:", self.tz_spin)
        
        # 2.2 旋转参数 (Rotation)
        self.rx_spin = QDoubleSpinBox()
        self.rx_spin.setRange(-180, 180)
        self.rx_spin.setSingleStep(1.0)
        self.rx_spin.setSuffix(" 度")
        transform_layout.addRow("X旋转:", self.rx_spin)
        
        self.ry_spin = QDoubleSpinBox()
        self.ry_spin.setRange(-180, 180)
        self.ry_spin.setSingleStep(1.0)
        self.ry_spin.setSuffix(" 度")
        transform_layout.addRow("Y旋转:", self.ry_spin)
        
        self.rz_spin = QDoubleSpinBox()
        self.rz_spin.setRange(-180, 180)
        self.rz_spin.setSingleStep(1.0)
        self.rz_spin.setSuffix(" 度")
        transform_layout.addRow("Z旋转:", self.rz_spin)
        
        control_layout.addWidget(transform_group)
        
        # 3. 输出设置
        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout(output_group)
        
        # 输出目录选择
        output_dir_widget = QWidget()
        output_dir_layout = QHBoxLayout(output_dir_widget)
        
        self.output_dir_label = QLabel("输出目录: [未设置]")
        output_dir_layout.addWidget(self.output_dir_label)
        
        btn_select_output = QPushButton("选择输出目录")
        btn_select_output.clicked.connect(self.select_rigid_mover_output_directory)
        output_dir_layout.addWidget(btn_select_output)
        
        output_layout.addWidget(output_dir_widget)
        
        # 输出选项
        self.output_image_checkbox = QCheckBox("输出变换后的图像")
        self.output_image_checkbox.setChecked(True)
        output_layout.addWidget(self.output_image_checkbox)
        
        self.output_rtss_checkbox = QCheckBox("输出变换后的RTSS")
        self.output_rtss_checkbox.setChecked(True)
        output_layout.addWidget(self.output_rtss_checkbox)
        
        control_layout.addWidget(output_group)
        
        # 添加"根据轮廓质心计算变换参数"按钮
        self.btn_calculate_from_centroids = QPushButton("根据轮廓质心计算变换参数")
        self.btn_calculate_from_centroids.setEnabled(False)  # 初始禁用
        self.btn_calculate_from_centroids.clicked.connect(self.calculate_transform_from_centroids)
        control_layout.addWidget(self.btn_calculate_from_centroids)
        
        # 4. 执行按钮
        self.btn_perform_transform = QPushButton("执行刚体变换")
        self.btn_perform_transform.setEnabled(False)  # 初始禁用
        self.btn_perform_transform.clicked.connect(self.perform_rigid_transform)
        control_layout.addWidget(self.btn_perform_transform)
        
        # 5. 进度条
        self.rigid_mover_progress_bar = QProgressBar()
        self.rigid_mover_progress_bar.setRange(0, 100)
        self.rigid_mover_progress_bar.setValue(0)
        control_layout.addWidget(self.rigid_mover_progress_bar)
        
        # 6. 状态标签
        self.rigid_mover_status_label = QLabel("状态: 请加载图像数据")
        control_layout.addWidget(self.rigid_mover_status_label)
        
        # 7. 日志显示区域
        self.rigid_mover_log_text = QTextEdit()
        self.rigid_mover_log_text.setReadOnly(True)
        self.rigid_mover_log_text.setMinimumHeight(150)
        control_layout.addWidget(self.rigid_mover_log_text)
        
        # === 右侧：预览区域（待实现） ===
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        
        preview_label = QLabel("图像预览区域 (待实现)")
        preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(preview_label)
        
        # 添加左右面板到分割器
        splitter.addWidget(control_panel)
        splitter.addWidget(preview_panel)
        splitter.setSizes([400, 500])  # 设置初始宽度比例
        
        layout.addWidget(content_widget)
        
        # 将标签页添加到标签页控件
        self.tab_widget.addTab(self.rigid_mover_tab, "刚体位移")
        
        # 初始化刚体位移器
        self.rigid_mover = ImageRigidMover()
        # 连接信号
        self.rigid_mover.progress_updated.connect(self.update_rigid_mover_progress)
        self.rigid_mover.process_finished.connect(self.on_rigid_mover_process_finished)
        self.rigid_mover.image_loaded.connect(self.on_rigid_mover_image_loaded)
        
        # 存储数据目录和输出目录路径
        self.rigid_mover_fixed_dir = None
        self.rigid_mover_moving_dir = None
        self.rigid_mover_output_dir = None
        
    def load_fixed_directory(self):
        """加载固定图像目录"""
        # 选择数据根目录
        current_dir = os.getcwd()
        fixed_dir = QFileDialog.getExistingDirectory(
            self,
            "选择固定图像目录",
            current_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if not fixed_dir:
            self.rigid_mover_status_label.setText("状态: 取消选择固定图像目录")
            return
            
        self.rigid_mover_fixed_dir = fixed_dir
        self.fixed_dir_label.setText(f"固定图像目录: {fixed_dir}")
        
        # 加载目录中的图像
        self.rigid_mover_log_message(f"加载固定图像目录: {fixed_dir}")
        success, message, data = self.rigid_mover.load_directory(fixed_dir, is_fixed=True)
        
        if success:
            self.rigid_mover_status_label.setText(f"状态: 已加载固定图像")
            self.check_enable_transform_button()
        else:
            self.rigid_mover_status_label.setText(f"状态: 加载固定图像失败 - {message}")
            
    def load_moving_directory(self):
        """加载移动图像目录"""
        # 选择数据根目录
        current_dir = os.getcwd() if self.rigid_mover_fixed_dir is None else self.rigid_mover_fixed_dir
        moving_dir = QFileDialog.getExistingDirectory(
            self,
            "选择移动图像目录",
            current_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if not moving_dir:
            self.rigid_mover_status_label.setText("状态: 取消选择移动图像目录")
            return
            
        self.rigid_mover_moving_dir = moving_dir
        self.moving_dir_label.setText(f"移动图像目录: {moving_dir}")
        
        # 加载目录中的图像
        self.rigid_mover_log_message(f"加载移动图像目录: {moving_dir}")
        success, message, data = self.rigid_mover.load_directory(moving_dir, is_fixed=False)
        
        if success:
            self.rigid_mover_status_label.setText(f"状态: 已加载移动图像")
            self.check_enable_transform_button()
        else:
            self.rigid_mover_status_label.setText(f"状态: 加载移动图像失败 - {message}")
    
    def select_rigid_mover_output_directory(self):
        """选择刚体位移输出目录"""
        # 使用之前选择的数据目录作为起点，或者当前目录
        start_dir = (self.rigid_mover_fixed_dir or self.rigid_mover_moving_dir 
                    or os.getcwd())
        
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if output_dir:
            self.rigid_mover_output_dir = output_dir
            self.rigid_mover.output_dir = output_dir  # 同时设置到rigid_mover对象中
            self.output_dir_label.setText(f"输出目录: {output_dir}")
            self.rigid_mover_log_message(f"已选择输出目录: {output_dir}")
            # 检查是否应该启用变换按钮
            self.check_enable_transform_button()
            
    def check_enable_transform_button(self):
        """检查是否应该启用刚体变换按钮和质心计算按钮"""
        # 检查是否启用变换按钮
        if (self.rigid_mover.fixed_data['loaded'] and 
            self.rigid_mover.moving_data['loaded'] and 
            self.rigid_mover_output_dir is not None):
            self.btn_perform_transform.setEnabled(True)
        else:
            self.btn_perform_transform.setEnabled(False)
            
        # 检查是否启用质心计算按钮
        # 需要固定和移动图像都已加载，并且都有RTSS
        has_fixed_rtss = (self.rigid_mover.fixed_data['loaded'] and 
                          self.rigid_mover.fixed_data['rtss'] is not None)
        has_moving_rtss = (self.rigid_mover.moving_data['loaded'] and 
                           self.rigid_mover.moving_data['rtss'] is not None)
                           
        if has_fixed_rtss and has_moving_rtss:
            self.btn_calculate_from_centroids.setEnabled(True)
        else:
            self.btn_calculate_from_centroids.setEnabled(False)
            
    def rigid_mover_log_message(self, message: str):
        """向刚体位移日志文本框添加消息"""
        self.rigid_mover_log_text.append(message)
        # 滚动到底部
        self.rigid_mover_log_text.verticalScrollBar().setValue(
            self.rigid_mover_log_text.verticalScrollBar().maximum()
        )
        
    def update_rigid_mover_progress(self, progress: int, message: str):
        """更新刚体位移进度"""
        self.rigid_mover_progress_bar.setValue(progress)
        self.rigid_mover_status_label.setText(f"状态: {message}")
        self.rigid_mover_log_message(f"[进度 {progress}%] {message}")
        
    def on_rigid_mover_process_finished(self, success: bool, message: str):
        """刚体位移过程完成回调"""
        if success:
            self.rigid_mover_log_message(f"✅ 成功: {message}")
            self.rigid_mover_status_label.setText(f"状态: 成功 - {message}")
        else:
            self.rigid_mover_log_message(f"❌ 错误: {message}")
            self.rigid_mover_status_label.setText(f"状态: 失败 - {message}")
        
        # 重新启用变换按钮
        self.btn_perform_transform.setEnabled(True)
        
    def on_rigid_mover_image_loaded(self, data_dict: dict):
        """刚体位移图像加载完成回调"""
        # 根据是固定还是移动图像更新相应的信息标签
        is_fixed = data_dict.get('is_fixed', True)
        info_label = self.fixed_info_label if is_fixed else self.moving_info_label
        
        if data_dict.get('loaded', False):
            image_info = data_dict.get('image_info', {})
            modality = image_info.get('modality', '未知')
            size = image_info.get('size', (0, 0, 0))
            spacing = image_info.get('spacing', (0, 0, 0))
            dicom_count = image_info.get('file_count', 0)  # DICOM图像文件数
            file_count = image_info.get('actual_file_count', 0)  # 目录中的实际文件总数
            has_rtss = data_dict.get('rtss') is not None
            rtss_info = f", RTSS: {self.rigid_mover._count_rtss_contours(data_dict.get('rtss'))}个轮廓" if has_rtss else ""
            
            # 显示更详细的信息
            info_text = (f"模态: {modality}, 尺寸: {size}, "
                        f"间距: {[round(s, 2) for s in spacing]}mm\n"
                        f"目录文件数: {file_count}, DICOM文件数: {dicom_count}{rtss_info}")
            info_label.setText(info_text)
        else:
            info_label.setText(f"未加载{'固定' if is_fixed else '移动'}图像")
        
    def perform_rigid_transform(self):
        """执行刚体变换"""
        if not (self.rigid_mover.fixed_data['loaded'] and 
                self.rigid_mover.moving_data['loaded']):
            self.rigid_mover_log_message("错误: 请先加载固定和移动图像")
            return
            
        if self.rigid_mover_output_dir is None:
            self.rigid_mover_log_message("错误: 请先选择输出目录")
            return
            
        # 禁用按钮，防止重复点击
        self.btn_perform_transform.setEnabled(False)
        
        # 获取用户设置的变换参数
        tx = self.tx_spin.value()
        ty = self.ty_spin.value()
        tz = self.tz_spin.value()
        rx = self.rx_spin.value()
        ry = self.ry_spin.value()
        rz = self.rz_spin.value()
        
        # 设置变换参数
        self.rigid_mover.set_transform_parameters(tx, ty, tz, rx, ry, rz)
        
        # 设置输出目录
        self.rigid_mover.output_dir = self.rigid_mover_output_dir
        
        # 记录变换信息
        self.rigid_mover_log_message("======== 开始刚体变换 ========")
        self.rigid_mover_log_message(f"平移参数: TX={tx}mm, TY={ty}mm, TZ={tz}mm")
        self.rigid_mover_log_message(f"旋转参数: RX={rx}度, RY={ry}度, RZ={rz}度")
        self.rigid_mover_log_message(f"输出目录: {self.rigid_mover_output_dir}")
        
        # 获取输出选项
        output_image = self.output_image_checkbox.isChecked()
        output_rtss = self.output_rtss_checkbox.isChecked()
        
        # 更新状态
        self.rigid_mover_status_label.setText("状态: 准备执行刚体变换...")
        
        # 创建线程执行变换，避免阻塞UI
        import threading
        
        def process_thread():
            try:
                # 执行刚体变换
                success, message = self.rigid_mover.perform_rigid_transform(
                    self.rigid_mover_output_dir,
                    output_image=output_image,
                    output_rtss=output_rtss
                )
                
                # 发送完成信号
                self.rigid_mover.process_finished.emit(success, message)
                
            except Exception as e:
                import traceback
                error_msg = f"执行刚体变换时出错: {str(e)}"
                self.rigid_mover_log_message(error_msg)
                self.rigid_mover_log_message(traceback.format_exc())
                self.rigid_mover.process_finished.emit(False, error_msg)
        
        # 启动处理线程
        thread = threading.Thread(target=process_thread)
        thread.daemon = True
        thread.start()

    def calculate_transform_from_centroids(self):
        """根据RTSS轮廓质心计算变换参数"""
        self.rigid_mover_log_message("正在计算轮廓质心并估算变换参数...")
        self.rigid_mover_status_label.setText("状态: 正在计算轮廓质心...")
        
        # 计算质心并获取变换参数
        success, message, transform_params = self.rigid_mover.calculate_transform_from_centroids()
        
        if success:
            # 更新GUI上的变换参数
            self.tx_spin.setValue(transform_params['tx'])
            self.ty_spin.setValue(transform_params['ty'])
            self.tz_spin.setValue(transform_params['tz'])
            self.rx_spin.setValue(transform_params['rx'])
            self.ry_spin.setValue(transform_params['ry'])
            self.rz_spin.setValue(transform_params['rz'])
            
            # 更新状态和日志
            self.rigid_mover_log_message(f"✅ 成功: {message}")
            self.rigid_mover_status_label.setText(f"状态: {message}")
        else:
            # 报告错误
            self.rigid_mover_log_message(f"❌ 错误: {message}")
            self.rigid_mover_status_label.setText(f"状态: 失败 - {message}") 

    def add_correlation_analyzer_tab(self):
        """添加相关性分析标签页"""
        self.correlation_tab = QWidget()
        layout = QVBoxLayout(self.correlation_tab)
        layout.setAlignment(Qt.AlignTop)  # 内容顶部对齐
        
        # 创建一个容器QWidget用于按钮和标签，并设置最大宽度
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_widget.setMaximumWidth(800)  # 调整宽度以适应更多内容
        
        # 创建PET1和PET2加载区域
        image_group = QGroupBox("步骤1: 加载PET图像和RTSS文件")
        image_layout = QGridLayout(image_group)
        
        # PET1选择按钮和标签
        btn_load_pet1 = QPushButton("选择第一个PET图像目录")
        btn_load_pet1.clicked.connect(self.load_pet1_directory)
        self.pet1_label = QLabel("PET1: 未选择")
        image_layout.addWidget(btn_load_pet1, 0, 0)
        image_layout.addWidget(self.pet1_label, 0, 1)
        
        # PET2选择按钮和标签
        btn_load_pet2 = QPushButton("选择第二个PET图像目录")
        btn_load_pet2.clicked.connect(self.load_pet2_directory)
        self.pet2_label = QLabel("PET2: 未选择")
        image_layout.addWidget(btn_load_pet2, 1, 0)
        image_layout.addWidget(self.pet2_label, 1, 1)
        
        # 可选：手动加载RTSS文件（如果在PET目录中未找到）
        btn_load_rtss = QPushButton("手动加载RTSS文件 (可选)")
        btn_load_rtss.clicked.connect(self.load_correlation_rtss_file)
        self.rtss_label = QLabel("RTSS: 未选择")
        image_layout.addWidget(btn_load_rtss, 2, 0)
        image_layout.addWidget(self.rtss_label, 2, 1)
        
        # 添加图像组
        content_layout.addWidget(image_group)
        
        # 创建ROI选择和分析区域
        analysis_group = QGroupBox("步骤2: 选择ROI并分析相关性")
        analysis_layout = QFormLayout(analysis_group)
        
        # ROI选择下拉框
        self.roi_combo = QComboBox()
        self.roi_combo.setEnabled(False)  # 初始禁用，直到加载RTSS
        analysis_layout.addRow("选择ROI:", self.roi_combo)
        
        # 输出目录选择
        self.correlation_output_dir_label = QLabel("输出目录: [未设置]")
        btn_select_correlation_output = QPushButton("选择输出目录")
        btn_select_correlation_output.clicked.connect(self.select_correlation_output_directory)
        analysis_layout.addRow(self.correlation_output_dir_label, btn_select_correlation_output)
        
        # 分析按钮
        self.btn_analyze_correlation = QPushButton("分析相关性")
        self.btn_analyze_correlation.setEnabled(False)  # 初始禁用
        self.btn_analyze_correlation.clicked.connect(self.perform_correlation_analysis)
        analysis_layout.addRow("", self.btn_analyze_correlation)
        
        # 添加分析组
        content_layout.addWidget(analysis_group)
        
        # 添加进度条
        self.correlation_progress_bar = QProgressBar()
        self.correlation_progress_bar.setRange(0, 100)
        self.correlation_progress_bar.setValue(0)
        content_layout.addWidget(self.correlation_progress_bar)
        
        # 状态信息标签
        self.correlation_status_label = QLabel("状态: 请加载PET图像和RTSS文件")
        content_layout.addWidget(self.correlation_status_label)
        
        # 添加日志显示区域
        self.correlation_log_text = QTextEdit()
        self.correlation_log_text.setReadOnly(True)
        self.correlation_log_text.setMinimumHeight(200)
        content_layout.addWidget(self.correlation_log_text)
        
        # 将内容区域添加到主布局
        layout.addWidget(content_widget)
        self.tab_widget.addTab(self.correlation_tab, "相关性分析")
        
        # 初始化相关性分析器
        self.correlation_analyzer = CorrelationAnalyzer()
        
        # 连接信号
        self.correlation_analyzer.progress_updated.connect(self.update_correlation_progress)
        self.correlation_analyzer.process_finished.connect(self.on_correlation_process_finished)
        self.correlation_analyzer.image_loaded.connect(self.on_correlation_image_loaded)
        
        # 存储数据目录路径
        self.pet1_dir = None
        self.pet2_dir = None
        self.correlation_output_dir = None
    
    def load_pet1_directory(self):
        """选择PET1图像目录"""
        # 获取当前工作目录
        current_dir = os.getcwd()
        
        # 选择PET1目录
        pet1_dir = QFileDialog.getExistingDirectory(
            self,
            "选择第一个PET图像目录",
            current_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if not pet1_dir:
            self.correlation_status_label.setText("状态: 取消选择PET1目录")
            return
            
        self.pet1_dir = pet1_dir
        self.pet1_label.setText(f"PET1: {pet1_dir}")
        
        # 加载PET1图像
        success, message, _ = self.correlation_analyzer.load_pet_directory(pet1_dir, is_pet1=True)
        if success:
            self.correlation_log_message(f"成功加载PET1: {message}")
            self.correlation_status_label.setText(f"状态: {message}")
        else:
            self.correlation_log_message(f"加载PET1失败: {message}")
            self.correlation_status_label.setText(f"状态: 加载PET1失败")
        
        # 检查是否可以启用分析按钮
        self.check_enable_correlation_button()
    
    def load_pet2_directory(self):
        """选择PET2图像目录"""
        # 获取当前工作目录或已选择的PET1目录的父目录
        start_dir = os.path.dirname(self.pet1_dir) if self.pet1_dir else os.getcwd()
        
        # 选择PET2目录
        pet2_dir = QFileDialog.getExistingDirectory(
            self,
            "选择第二个PET图像目录",
            start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if not pet2_dir:
            self.correlation_status_label.setText("状态: 取消选择PET2目录")
            return
            
        self.pet2_dir = pet2_dir
        self.pet2_label.setText(f"PET2: {pet2_dir}")
        
        # 加载PET2图像
        success, message, _ = self.correlation_analyzer.load_pet_directory(pet2_dir, is_pet1=False)
        if success:
            self.correlation_log_message(f"成功加载PET2: {message}")
            self.correlation_status_label.setText(f"状态: {message}")
        else:
            self.correlation_log_message(f"加载PET2失败: {message}")
            self.correlation_status_label.setText(f"状态: 加载PET2失败")
        
        # 检查是否可以启用分析按钮
        self.check_enable_correlation_button()
    
    def load_correlation_rtss_file(self):
        """手动加载RTSS文件"""
        # 获取当前工作目录或已选择的PET目录
        start_dir = self.pet1_dir if self.pet1_dir else os.getcwd()
        
        # 选择RTSS文件
        rtss_file, _ = QFileDialog.getOpenFileName(
            self,
            "选择RTSS文件",
            start_dir,
            "DICOM文件 (*.dcm);;所有文件 (*.*)"
        )
        
        if not rtss_file:
            self.correlation_status_label.setText("状态: 取消选择RTSS文件")
            return
            
        # 加载RTSS文件
        success, message = self.correlation_analyzer.load_rtss_file(rtss_file)
        if success:
            self.rtss_label.setText(f"RTSS: {os.path.basename(rtss_file)}")
            self.correlation_log_message(f"成功加载RTSS: {message}")
            self.correlation_status_label.setText(f"状态: {message}")
            
            # 更新ROI下拉框
            self.update_roi_combo()
        else:
            self.correlation_log_message(f"加载RTSS失败: {message}")
            self.correlation_status_label.setText(f"状态: 加载RTSS失败")
        
        # 检查是否可以启用分析按钮
        self.check_enable_correlation_button()
    
    def update_roi_combo(self):
        """更新ROI下拉框"""
        self.roi_combo.clear()
        roi_names = self.correlation_analyzer.get_roi_names()
        
        if roi_names:
            self.roi_combo.addItems(roi_names)
            self.roi_combo.setEnabled(True)
            self.correlation_log_message(f"可用ROI: {', '.join(roi_names)}")
        else:
            self.roi_combo.setEnabled(False)
            self.correlation_log_message("未找到可用的ROI")
    
    def select_correlation_output_directory(self):
        """选择相关性分析输出目录"""
        # 使用之前选择的数据目录作为起点，或者当前目录
        start_dir = self.pet1_dir if self.pet1_dir else os.getcwd()
        
        # 添加默认的output子目录
        default_output_dir = os.path.join(start_dir, 'correlation_output')
        
        # 选择输出目录
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "选择输出目录",
            default_output_dir if os.path.exists(os.path.dirname(default_output_dir)) else start_dir,
            QFileDialog.ShowDirsOnly
        )
        
        if not output_dir:
            return
            
        # 更新输出目录
        self.correlation_output_dir = output_dir
        self.correlation_output_dir_label.setText(f"输出目录: {output_dir}")
        self.correlation_log_message(f"已设置输出目录: {output_dir}")
        
        # 检查是否可以启用分析按钮
        self.check_enable_correlation_button()
    
    def check_enable_correlation_button(self):
        """检查是否可以启用相关性分析按钮"""
        can_enable = (
            self.correlation_analyzer.pet1_data['loaded'] and
            self.correlation_analyzer.pet2_data['loaded'] and
            self.correlation_analyzer.rtss_data['loaded'] and
            self.correlation_output_dir is not None and
            self.roi_combo.currentText() != ""
        )
        
        self.btn_analyze_correlation.setEnabled(can_enable)
        
        if can_enable:
            self.correlation_status_label.setText("状态: 准备就绪，可以开始分析")
        else:
            missing = []
            if not self.correlation_analyzer.pet1_data['loaded']:
                missing.append("PET1")
            if not self.correlation_analyzer.pet2_data['loaded']:
                missing.append("PET2")
            if not self.correlation_analyzer.rtss_data['loaded']:
                missing.append("RTSS")
            if self.correlation_output_dir is None:
                missing.append("输出目录")
            if self.roi_combo.currentText() == "":
                missing.append("ROI")
                
            if missing:
                self.correlation_status_label.setText(f"状态: 缺少 {', '.join(missing)}")
    
    def perform_correlation_analysis(self):
        """执行相关性分析"""
        if not self.btn_analyze_correlation.isEnabled():
            return
            
        # 获取选中的ROI名称
        roi_name = self.roi_combo.currentText()
        if not roi_name:
            self.correlation_log_message("错误: 未选择ROI")
            return
            
        # 禁用分析按钮，防止重复点击
        self.btn_analyze_correlation.setEnabled(False)
        self.correlation_status_label.setText(f"状态: 正在分析ROI '{roi_name}'的相关性...")
        
        # 执行相关性分析
        success, message = self.correlation_analyzer.analyze_correlation(roi_name, self.correlation_output_dir)
        
        # 重新启用分析按钮
        self.btn_analyze_correlation.setEnabled(True)
        
        # 更新状态
        if success:
            self.correlation_status_label.setText(f"状态: 分析完成")
            self.correlation_log_message(f"分析成功: {message}")
        else:
            self.correlation_status_label.setText(f"状态: 分析失败")
            self.correlation_log_message(f"分析失败: {message}")
    
    def correlation_log_message(self, message: str):
        """在相关性分析日志中添加消息"""
        self.correlation_log_text.append(message)
        # 滚动到底部
        self.correlation_log_text.verticalScrollBar().setValue(
            self.correlation_log_text.verticalScrollBar().maximum()
        )
    
    def update_correlation_progress(self, progress: int, message: str):
        """更新相关性分析进度条"""
        self.correlation_progress_bar.setValue(progress)
        self.correlation_status_label.setText(f"状态: {message}")
        self.correlation_log_message(message)
    
    def on_correlation_process_finished(self, success: bool, message: str):
        """相关性分析过程完成的回调"""
        if success:
            self.correlation_log_message(f"分析完成: {message}")
            self.correlation_status_label.setText("状态: 分析完成")
        else:
            self.correlation_log_message(f"分析失败: {message}")
            self.correlation_status_label.setText("状态: 分析失败")
            
        # 重新启用分析按钮
        self.btn_analyze_correlation.setEnabled(True)
    
    def on_correlation_image_loaded(self, data_dict: dict):
        """当相关性分析模块加载图像时的回调"""
        is_pet1 = data_dict.get('is_pet1', True)
        pet_label = "PET1" if is_pet1 else "PET2"
        
        # 更新状态
        self.correlation_log_message(f"已加载{pet_label}图像: 尺寸={data_dict['image_info']['size']}, "
                                   f"模态={data_dict['image_info']['modality']}")
        
        # 检查并更新ROI下拉框
        if self.correlation_analyzer.rtss_data['loaded']:
            self.update_roi_combo()
            
        # 检查是否可以启用分析按钮
        self.check_enable_correlation_button()
        
        # 如果尚未设置输出目录，则设置默认输出目录
        if not self.correlation_output_dir:
            self.setup_correlation_default_output_directory()
    
    def setup_correlation_default_output_directory(self):
        """设置默认的相关性分析输出目录"""
        if self.pet1_dir:
            default_output_dir = os.path.join(os.path.dirname(self.pet1_dir), 'correlation_output')
            try:
                os.makedirs(default_output_dir, exist_ok=True)
                self.correlation_output_dir = default_output_dir
                self.correlation_output_dir_label.setText(f"输出目录: {default_output_dir}")
                self.correlation_log_message(f"已设置默认输出目录: {default_output_dir}")
            except Exception as e:
                self.correlation_log_message(f"无法创建默认输出目录: {e}") 

    def add_drm_converter_tab(self):
        """添加DRM转换器标签页"""
        drm_converter_gui = DRMConverterGUI()
        self.tab_widget.addTab(drm_converter_gui, "DRM转换器") 