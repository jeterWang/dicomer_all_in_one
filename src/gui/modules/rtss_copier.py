import os
import json
import logging
import sys # 需要导入 sys 才能在 select_folder 中使用
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QFileDialog, QTextEdit, QMessageBox, QApplication, QGroupBox, QFormLayout, QDoubleSpinBox, QLabel, QHBoxLayout)
from PyQt5.QtCore import Qt
# 导入 pydicom 和自定义的 dicom 工具
import pydicom
from src.core.dicom_utils import read_dicom_file
from typing import Optional, Dict
from collections import Counter
# 导入 RTSS 复制功能
from src.core.rtstruct_utils import copy_rtss_between_series, copy_rtss_with_transform
# 导入 SimpleITK 用于创建变换
import SimpleITK as sitk
import math # 用于角度弧度转换

# --- 实现 RTSS 扫描函数 ---
# MAX_RTSS_FILE_SIZE_BYTES = 1 * 1024 * 1024 # 不再使用固定阈值

def scan_patient_folder(base_folder: str) -> Optional[Dict[str, Dict[str, Optional[str]]]]:
    """
    扫描指定的患者图像文件夹，查找 week0/4 下的 CT/PT 子目录中的 RTSS 文件。
    通过分析目录内文件大小的分布来识别潜在的 RTSS 文件（尺寸通常与其他文件不同），
    然后确认 DICOM Modality。

    Args:
        base_folder: 患者图像数据的基础文件夹路径 (例如 '.../images')。

    Returns:
        一个字典，包含找到的 RTSS 文件路径。
        如果找不到任何 RTSS 文件或结构不符合预期，则返回 None。
    """
    scan_results: Dict[str, Dict[str, Optional[str]]] = {
        'week0': {'CT_RTSS': None, 'PT_RTSS': None},
        'week4': {'CT_RTSS': None, 'PT_RTSS': None}
    }
    weeks = ['week0', 'week4']
    modalities = ['CT', 'PT']
    found_any = False

    logging.info(f"开始扫描文件夹: {base_folder}")

    for week in weeks:
        for modality in modalities:
            week_modality_dirname = f"{week}_{modality}"
            week_modality_folder = os.path.join(base_folder, week_modality_dirname)
            rtss_key = f"{modality}_RTSS"

            if not os.path.isdir(week_modality_folder):
                logging.warning(f"未找到目录: {week_modality_folder}")
                continue

            logging.info(f"正在扫描: {week_modality_folder}")
            files_with_sizes = []
            try:
                for filename in os.listdir(week_modality_folder):
                    file_path = os.path.join(week_modality_folder, filename)
                    if os.path.isfile(file_path) and filename.lower().endswith('.dcm'):
                        try:
                            size = os.path.getsize(file_path)
                            files_with_sizes.append((file_path, size))
                        except FileNotFoundError:
                            logging.warning(f"获取大小时找不到文件（可能已被删除）: {file_path}")
                        except OSError as e:
                             logging.error(f"获取文件大小失败: {file_path}, Error: {e}")

            except OSError as e:
                logging.error(f"无法列出目录内容: {week_modality_folder}, Error: {e}")
                continue # 跳过这个有问题的目录

            if not files_with_sizes:
                logging.warning(f"目录 {week_modality_folder} 中没有找到 .dcm 文件。")
                continue

            # 分析文件大小分布
            size_counts = Counter(size for _, size in files_with_sizes)
            
            # 可能性 1：只有一个文件，直接检查它是不是 RTSS
            if len(files_with_sizes) == 1:
                potential_rtss_paths = [files_with_sizes[0][0]]
                logging.info(f"目录 {week_modality_folder} 中只有一个 dcm 文件，将其视为潜在 RTSS。")
            # 可能性 2：多个文件，找出大小独特的（频率最低的）
            elif len(size_counts) > 1: # 必须有至少两种大小才能区分
                # 找出频率最低的大小
                min_freq = min(size_counts.values())
                candidate_sizes = {size for size, count in size_counts.items() if count == min_freq}
                # 如果最低频率的大小有多个，或者最低频率不是1（可能都是切片，没有RTSS），需要更复杂的逻辑
                # 简化：优先选择频率为1的大小作为候选
                if 1 in size_counts.values():
                     candidate_sizes = {size for size, count in size_counts.items() if count == 1}
                     logging.info(f"在 {week_modality_folder} 中找到大小频率为 1 的文件，可能是 RTSS。候选大小: {candidate_sizes}")
                else:
                     # 如果没有频率为1的大小，可能没有RTSS，或者RTSS大小和某些切片一样？
                     # 或者取最不常见的大小（即使频率>1）？这里我们采取保守策略：假设没有明显不同的RTSS
                     logging.warning(f"在 {week_modality_folder} 中未找到大小频率为 1 的文件，无法明确识别 RTSS。文件大小分布: {size_counts}")
                     candidate_sizes = set()

                potential_rtss_paths = [fp for fp, size in files_with_sizes if size in candidate_sizes]
            # 可能性 3：所有文件大小都一样
            else:
                logging.info(f"目录 {week_modality_folder} 中所有 .dcm 文件大小相同 ({size_counts})，可能没有 RTSS 文件。")
                potential_rtss_paths = []

            # 验证候选文件
            rtss_found_in_modality = False
            for candidate_path in potential_rtss_paths:
                try:
                    ds = pydicom.dcmread(candidate_path, stop_before_pixels=True, force=True)
                    if hasattr(ds, 'Modality') and ds.Modality == 'RTSTRUCT':
                        logging.info(f"确认找到 RTSS 文件: {candidate_path}")
                        if scan_results[week][rtss_key] is not None:
                            logging.warning(f"在 {week_modality_folder} 中找到多个 RTSS 文件，将使用第一个确认的: {scan_results[week][rtss_key]}")
                        else:
                            scan_results[week][rtss_key] = candidate_path
                            found_any = True
                            rtss_found_in_modality = True
                            # break # 如果确定只有一个RTSS，找到就可以停止检查该目录的其他候选
                    # else: # 不需要记录不是RTSTRUCT的候选，因为它们本来就是根据大小猜测的
                    #    logging.debug(f"候选文件 {os.path.basename(candidate_path)} Modality ({getattr(ds, 'Modality', 'N/A')}) 不是 RTSTRUCT。")
                except pydicom.errors.InvalidDicomError:
                     logging.warning(f"候选文件无效 DICOM: {candidate_path}")
                except Exception as e:
                    logging.error(f"读取候选 RTSS 文件 {candidate_path} 时出错: {e}", exc_info=True)

            if not rtss_found_in_modality and potential_rtss_paths:
                logging.warning(f"在 {week_modality_folder} 中找到大小独特的候选文件，但它们都不是 RTSTRUCT。")
            elif not rtss_found_in_modality:
                 logging.warning(f"在 {week_modality_folder} 中未找到符合条件的 RTSS 文件。")

    if not found_any:
        logging.warning(f"在 {base_folder} 的子目录中未找到任何确认的 RTSS 文件。")
        return None # 或者返回空的 scan_results 字典，取决于后续如何处理

    logging.info(f"扫描完成: {scan_results}")
    return scan_results
# --- 结束扫描函数 ---

class RTSSCopier(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_folder = None
        self.scan_results = None
        self.default_dir = self.calculate_default_dir()
        # 初始化变换输入框字典，方便访问
        self.transform_inputs = {}
        self.init_ui()

    def calculate_default_dir(self):
        """计算文件对话框的默认起始目录 (项目根目录下的 data 文件夹)"""
        try:
            # 获取当前文件所在的目录的上三级目录（src/gui/modules -> src/gui -> src -> project_root）
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_dir = os.path.join(project_root, 'data')
            if os.path.isdir(data_dir):
                logging.info(f"找到默认数据目录: {data_dir}")
                return data_dir
            else:
                logging.warning(f"未找到默认数据目录: {data_dir}，将使用用户主目录。")
                return os.path.expanduser("~")
        except Exception as e:
            logging.error(f"计算默认目录时出错: {e}", exc_info=True)
            return os.path.expanduser("~")

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. 选择文件夹按钮
        self.select_folder_button = QPushButton("选择患者文件夹 (包含 week0/4 CT/PT)")
        self.select_folder_button.clicked.connect(self.select_folder)
        layout.addWidget(self.select_folder_button)

        # 2. 显示扫描结果的文本区域
        self.result_display = QTextEdit()
        self.result_display.setReadOnly(True)
        self.result_display.setPlaceholderText("扫描结果将显示在此处...")
        layout.addWidget(self.result_display)

        # 3. PT -> CT 复制按钮组
        pt_ct_group = QGroupBox("PT -> CT 复制")
        pt_ct_layout = QHBoxLayout()
        pt_ct_group.setLayout(pt_ct_layout)

        self.copy_button_w0 = QPushButton("复制 W0 PT->CT")
        self.copy_button_w0.clicked.connect(self.copy_week0_pt_to_ct)
        self.copy_button_w0.setEnabled(False)
        pt_ct_layout.addWidget(self.copy_button_w0)

        self.copy_button_w4 = QPushButton("复制 W4 PT->CT")
        self.copy_button_w4.clicked.connect(self.copy_week4_pt_to_ct)
        self.copy_button_w4.setEnabled(False)
        pt_ct_layout.addWidget(self.copy_button_w4)
        layout.addWidget(pt_ct_group)

        # 4. W0 PT -> W4 PT (带变换) 复制组
        w0w4_tx_group = QGroupBox("Week0 PT -> Week4 PT (带变换)")
        w0w4_tx_layout = QFormLayout()
        w0w4_tx_group.setLayout(w0w4_tx_layout)

        # --- 变换参数输入 ---
        # 旋转中心 (Cx, Cy, Cz)
        center_layout = QHBoxLayout()
        self.transform_inputs['Cx'] = QDoubleSpinBox(); self.transform_inputs['Cx'].setRange(-10000, 10000); self.transform_inputs['Cx'].setDecimals(3)
        self.transform_inputs['Cy'] = QDoubleSpinBox(); self.transform_inputs['Cy'].setRange(-10000, 10000); self.transform_inputs['Cy'].setDecimals(3)
        self.transform_inputs['Cz'] = QDoubleSpinBox(); self.transform_inputs['Cz'].setRange(-10000, 10000); self.transform_inputs['Cz'].setDecimals(3)
        center_layout.addWidget(QLabel("Cx:")); center_layout.addWidget(self.transform_inputs['Cx'])
        center_layout.addWidget(QLabel(" Cy:")); center_layout.addWidget(self.transform_inputs['Cy'])
        center_layout.addWidget(QLabel(" Cz:")); center_layout.addWidget(self.transform_inputs['Cz'])
        w0w4_tx_layout.addRow("旋转中心:", center_layout)

        # 旋转角度 (Rx, Ry, Rz) - 单位：度
        rotation_layout = QHBoxLayout()
        self.transform_inputs['Rx'] = QDoubleSpinBox(); self.transform_inputs['Rx'].setRange(-360, 360); self.transform_inputs['Rx'].setDecimals(3)
        self.transform_inputs['Ry'] = QDoubleSpinBox(); self.transform_inputs['Ry'].setRange(-360, 360); self.transform_inputs['Ry'].setDecimals(3)
        self.transform_inputs['Rz'] = QDoubleSpinBox(); self.transform_inputs['Rz'].setRange(-360, 360); self.transform_inputs['Rz'].setDecimals(3)
        rotation_layout.addWidget(QLabel("Rx (°):")); rotation_layout.addWidget(self.transform_inputs['Rx'])
        rotation_layout.addWidget(QLabel(" Ry (°):")); rotation_layout.addWidget(self.transform_inputs['Ry'])
        rotation_layout.addWidget(QLabel(" Rz (°):")); rotation_layout.addWidget(self.transform_inputs['Rz'])
        w0w4_tx_layout.addRow("旋转角度:", rotation_layout)

        # 平移向量 (Tx, Ty, Tz)
        translation_layout = QHBoxLayout()
        self.transform_inputs['Tx'] = QDoubleSpinBox(); self.transform_inputs['Tx'].setRange(-10000, 10000); self.transform_inputs['Tx'].setDecimals(3)
        self.transform_inputs['Ty'] = QDoubleSpinBox(); self.transform_inputs['Ty'].setRange(-10000, 10000); self.transform_inputs['Ty'].setDecimals(3)
        self.transform_inputs['Tz'] = QDoubleSpinBox(); self.transform_inputs['Tz'].setRange(-10000, 10000); self.transform_inputs['Tz'].setDecimals(3)
        translation_layout.addWidget(QLabel("Tx:")); translation_layout.addWidget(self.transform_inputs['Tx'])
        translation_layout.addWidget(QLabel(" Ty:")); translation_layout.addWidget(self.transform_inputs['Ty'])
        translation_layout.addWidget(QLabel(" Tz:")); translation_layout.addWidget(self.transform_inputs['Tz'])
        w0w4_tx_layout.addRow("平移向量:", translation_layout)

        # 执行按钮
        self.copy_button_w0w4_tx = QPushButton("执行 W0 PT -> W4 PT (带变换) 复制")
        self.copy_button_w0w4_tx.clicked.connect(self.copy_w0pt_to_w4pt_with_transform)
        self.copy_button_w0w4_tx.setEnabled(False) # 初始禁用
        w0w4_tx_layout.addRow(self.copy_button_w0w4_tx)

        layout.addWidget(w0w4_tx_group)
        layout.addStretch(1) # 添加弹性空间到底部
        self.setLayout(layout)

    def select_folder(self):
        """打开文件夹选择对话框并触发扫描"""
        # 如果用户已经选择过文件夹(self.base_folder)，则以此为起点，否则使用计算好的默认目录
        start_dir = self.base_folder if self.base_folder else self.default_dir
        folder = QFileDialog.getExistingDirectory(self, "选择患者文件夹", start_dir)
        if folder:
            self.base_folder = folder
            self.select_folder_button.setText(f"已选择: {os.path.basename(folder)}")
            self.result_display.setPlaceholderText(f"正在扫描 {self.base_folder}...")
            QApplication.processEvents() # 处理事件以更新UI

            try:
                # 调用 scan_patient_folder (可能是真的，也可能是假的)
                self.scan_results = scan_patient_folder(self.base_folder)
                if self.scan_results:
                    # 格式化结果以便显示
                    display_text = json.dumps(self.scan_results, indent=4, ensure_ascii=False)
                    self.result_display.setText(display_text)
                    logging.info(f"文件夹 {self.base_folder} 扫描完成。")
                    # 检查是否可以启用复制按钮
                    self.update_copy_buttons_state()
                # 如果 scan_results 是 None (可能是导入失败时的假函数返回的)
                elif self.scan_results is None:
                    # 区分是加载失败还是扫描未找到
                    # 注意：下面的 'rtss_copier' not in sys.modules 检查可能不再准确反映问题
                    # 我们需要根据 scan_patient_folder 的返回值来判断
                    # logging 中的信息会更准确
                    self.result_display.setText(f"在 {self.base_folder} 中未找到预期的 RT Structure Set 文件，或者文件夹结构不符合 week0/4 -> CT/PT 的预期。请检查日志。")
                    logging.warning(f"scan_patient_folder 返回 None，可能未找到 RTSS 文件或结构错误。")
                    # 扫描失败或未找到文件，禁用按钮
                    self.copy_button_w0.setEnabled(False)
                    self.copy_button_w4.setEnabled(False)
                else:
                    # 扫描成功但未找到预期文件/文件夹
                    self.result_display.setText(f"在 {self.base_folder} 中未找到预期的子文件夹或扫描时出错。请检查日志或控制台输出。")
                    logging.warning(f"在 {self.base_folder} 中未找到预期的子文件夹或扫描时出错。")
                    # 扫描失败或未找到文件，禁用按钮
                    self.copy_button_w0.setEnabled(False)
                    self.copy_button_w4.setEnabled(False)
            except Exception as e:
                self.result_display.setText(f"处理文件夹 {self.base_folder} 时发生错误: {e}")
                logging.error(f"处理文件夹 {self.base_folder} 时发生错误: {e}", exc_info=True)
                QMessageBox.critical(self, "处理错误", f"处理时发生意外错误: {e}")
                # 扫描失败或未找到文件，禁用按钮
                self.copy_button_w0.setEnabled(False)
                self.copy_button_w4.setEnabled(False)
        else:
            # 用户取消选择，保留占位符文本，不清空已选择的文件夹(如果之前选过)
             if not self.base_folder:
                 self.result_display.setPlaceholderText("未选择文件夹。")
                 # 用户取消选择时也应禁用复制按钮
                 self.copy_button_w0.setEnabled(False)
                 self.copy_button_w4.setEnabled(False)

    def update_copy_buttons_state(self):
        """根据扫描结果更新所有复制按钮的启用状态"""
        w0_pt_ct_enabled = False
        w4_pt_ct_enabled = False
        w0pt_w4pt_tx_enabled = False # 新按钮的状态

        if self.scan_results and self.base_folder:
            week0 = self.scan_results.get('week0')
            week4 = self.scan_results.get('week4')
            w0_pt_dir = os.path.join(self.base_folder, 'week0_PT')
            w0_ct_dir = os.path.join(self.base_folder, 'week0_CT')
            w4_pt_dir = os.path.join(self.base_folder, 'week4_PT')
            w4_ct_dir = os.path.join(self.base_folder, 'week4_CT')

            # Check Week 0 PT -> CT
            if week0 and week0.get('PT_RTSS') and os.path.isdir(w0_pt_dir) and os.path.isdir(w0_ct_dir):
                w0_pt_ct_enabled = True

            # Check Week 4 PT -> CT
            if week4 and week4.get('PT_RTSS') and os.path.isdir(w4_pt_dir) and os.path.isdir(w4_ct_dir):
                w4_pt_ct_enabled = True

            # Check Week 0 PT -> Week 4 PT (Transform)
            if week0 and week0.get('PT_RTSS') and os.path.isdir(w0_pt_dir) and os.path.isdir(w4_pt_dir):
                 w0pt_w4pt_tx_enabled = True

        self.copy_button_w0.setEnabled(w0_pt_ct_enabled)
        self.copy_button_w4.setEnabled(w4_pt_ct_enabled)
        self.copy_button_w0w4_tx.setEnabled(w0pt_w4pt_tx_enabled) # 设置新按钮状态

        logging.info(f"更新复制按钮状态: W0PT->CT={w0_pt_ct_enabled}, W4PT->CT={w4_pt_ct_enabled}, W0PT->W4PT_TX={w0pt_w4pt_tx_enabled}")

    def copy_week0_pt_to_ct(self):
        """执行将 Week0 PT RTSS 复制并适配到 Week0 CT 的操作"""
        if not self.scan_results or not self.base_folder:
            QMessageBox.warning(self, "错误", "请先选择有效的患者文件夹并成功扫描。")
            return

        week0_results = self.scan_results.get('week0')
        if not week0_results:
            QMessageBox.warning(self, "错误", "扫描结果中缺少 Week0 的信息。")
            return

        pt_rtss_path = week0_results.get('PT_RTSS')
        if not pt_rtss_path:
            QMessageBox.warning(self, "缺少文件", "未在 Week0 PT 目录中找到 RTStruct 文件。")
            return

        # 构建源和目标系列目录路径
        pt_series_dir = os.path.join(self.base_folder, 'week0_PT')
        ct_series_dir = os.path.join(self.base_folder, 'week0_CT')

        # 再次检查目录是否存在
        if not os.path.isdir(pt_series_dir):
            QMessageBox.critical(self, "目录错误", f"找不到 Week0 PT 目录: {pt_series_dir}")
            return
        if not os.path.isdir(ct_series_dir):
            QMessageBox.critical(self, "目录错误", f"找不到 Week0 CT 目录: {ct_series_dir}")
            return

        # 定义输出文件名
        output_filename = f"RS.{os.path.basename(ct_series_dir)}_from_PT.dcm" # 例如 RS.week0_CT_from_PT.dcm
        output_rtss_path = os.path.join(ct_series_dir, output_filename)

        # 提示用户确认
        reply = QMessageBox.question(self,
                                     "确认操作",
                                     f"将从以下文件复制 ROI:\n{pt_rtss_path}\n\n" 
                                     f"适配到以下 CT 系列:\n{ct_series_dir}\n\n" 
                                     f"并保存为:\n{output_rtss_path}\n\n是否继续？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            logging.info("用户确认复制操作，开始执行...")
            QApplication.setOverrideCursor(Qt.WaitCursor) # 显示等待光标
            self.copy_button_w0.setEnabled(False) # 禁用按钮防止重复点击
            self.result_display.append("\n正在复制和重采样 RTStruct...") # 更新文本区域状态
            QApplication.processEvents() # 强制 UI 更新

            try:
                success = copy_rtss_between_series(
                    source_rtss_path=pt_rtss_path,
                    source_series_dir=pt_series_dir,
                    target_series_dir=ct_series_dir,
                    output_rtss_path=output_rtss_path
                )

                if success:
                    QMessageBox.information(self, "成功", f"RTStruct 已成功复制并保存到:\n{output_rtss_path}")
                    self.result_display.append("复制操作成功完成。")
                    # 可以考虑重新扫描文件夹以更新显示？
                    # self.select_folder() # 或者只更新文本显示
                else:
                    QMessageBox.critical(self, "失败", "复制 RTStruct 时发生错误。请检查日志获取详细信息。")
                    self.result_display.append("复制操作失败。请检查日志。")

            except Exception as e:
                # 捕获核心函数可能未捕获的意外异常
                logging.error(f"调用 copy_rtss_between_series 时发生意外错误: {e}", exc_info=True)
                QMessageBox.critical(self, "严重错误", f"执行复制时发生意外错误: {e}")
                self.result_display.append(f"复制操作因意外错误而中止: {e}")
            finally:
                QApplication.restoreOverrideCursor() # 恢复光标
                # 不论成功失败，重新评估按钮状态
                self.update_copy_buttons_state()
        else:
            logging.info("用户取消了复制操作。")

    def copy_week4_pt_to_ct(self):
        """执行将 Week4 PT RTSS 复制并适配到 Week4 CT 的操作"""
        if not self.scan_results or not self.base_folder:
            QMessageBox.warning(self, "错误", "请先选择有效的患者文件夹并成功扫描。")
            return

        week4_results = self.scan_results.get('week4')
        if not week4_results:
            QMessageBox.warning(self, "错误", "扫描结果中缺少 Week4 的信息。")
            return

        pt_rtss_path = week4_results.get('PT_RTSS')
        if not pt_rtss_path:
            QMessageBox.warning(self, "缺少文件", "未在 Week4 PT 目录中找到 RTStruct 文件。")
            return

        # 构建源和目标系列目录路径
        pt_series_dir = os.path.join(self.base_folder, 'week4_PT')
        ct_series_dir = os.path.join(self.base_folder, 'week4_CT')

        # 再次检查目录是否存在
        if not os.path.isdir(pt_series_dir):
            QMessageBox.critical(self, "目录错误", f"找不到 Week4 PT 目录: {pt_series_dir}")
            return
        if not os.path.isdir(ct_series_dir):
            QMessageBox.critical(self, "目录错误", f"找不到 Week4 CT 目录: {ct_series_dir}")
            return

        # 定义输出文件名
        output_filename = f"RS.{os.path.basename(ct_series_dir)}_from_PT.dcm" # 例如 RS.week4_CT_from_PT.dcm
        output_rtss_path = os.path.join(ct_series_dir, output_filename)

        # 提示用户确认
        reply = QMessageBox.question(self,
                                     "确认操作",
                                     f"将从以下文件复制 ROI:\n{pt_rtss_path}\n\n" 
                                     f"适配到以下 CT 系列:\n{ct_series_dir}\n\n" 
                                     f"并保存为:\n{output_rtss_path}\n\n是否继续？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            logging.info("用户确认 Week4 复制操作，开始执行...")
            QApplication.setOverrideCursor(Qt.WaitCursor) # 显示等待光标
            self.copy_button_w4.setEnabled(False) # 禁用按钮防止重复点击
            self.result_display.append("\n正在复制和重采样 Week4 RTStruct...") # 更新文本区域状态
            QApplication.processEvents() # 强制 UI 更新

            try:
                success = copy_rtss_between_series(
                    source_rtss_path=pt_rtss_path,
                    source_series_dir=pt_series_dir,
                    target_series_dir=ct_series_dir,
                    output_rtss_path=output_rtss_path
                )

                if success:
                    QMessageBox.information(self, "成功", f"Week4 RTStruct 已成功复制并保存到:\n{output_rtss_path}")
                    self.result_display.append("Week4 复制操作成功完成。")
                else:
                    QMessageBox.critical(self, "失败", "复制 Week4 RTStruct 时发生错误。请检查日志获取详细信息。")
                    self.result_display.append("Week4 复制操作失败。请检查日志。")

            except Exception as e:
                logging.error(f"调用 Week4 copy_rtss_between_series 时发生意外错误: {e}", exc_info=True)
                QMessageBox.critical(self, "严重错误", f"执行 Week4 复制时发生意外错误: {e}")
                self.result_display.append(f"Week4 复制操作因意外错误而中止: {e}")
            finally:
                QApplication.restoreOverrideCursor() # 恢复光标
                # 不论成功失败，重新评估按钮状态
                self.update_copy_buttons_state()
        else:
            logging.info("用户取消了 Week4 复制操作。")

    def copy_w0pt_to_w4pt_with_transform(self):
        """执行将 Week0 PT RTSS 复制并应用变换到 Week4 PT 的操作"""
        if not self.scan_results or not self.base_folder:
            QMessageBox.warning(self, "错误", "请先选择有效的患者文件夹并成功扫描。")
            return

        week0_results = self.scan_results.get('week0')
        week4_results = self.scan_results.get('week4') # 需要 Week4 信息来确认目录

        if not week0_results or not week4_results: # 确保 week0 和 week4 都有扫描结果
            QMessageBox.warning(self, "错误", "扫描结果中缺少 Week0 或 Week4 的信息。")
            return

        source_rtss_path = week0_results.get('PT_RTSS')
        if not source_rtss_path:
            QMessageBox.warning(self, "缺少文件", "未在 Week0 PT 目录中找到 RTStruct 文件。")
            return

        # 构建源和目标系列目录路径 (目标是 W4 PT)
        # 源 RTSS 路径已知，但 target_image_series_dir 是 W4 PT 目录
        target_series_dir = os.path.join(self.base_folder, 'week4_PT')

        # 检查目录是否存在
        source_series_dir_check = os.path.dirname(source_rtss_path) # 源 RTSS 所在的目录 (应该是 week0_PT)
        if not os.path.isdir(source_series_dir_check):
            QMessageBox.critical(self, "目录错误", f"找不到源 RTSS 所在的目录: {source_series_dir_check}")
            return
        if not os.path.isdir(target_series_dir):
            QMessageBox.critical(self, "目录错误", f"找不到目标 Week4 PT 目录: {target_series_dir}")
            return

        # --- 获取变换参数 --- 
        try:
            cx = self.transform_inputs['Cx'].value()
            cy = self.transform_inputs['Cy'].value()
            cz = self.transform_inputs['Cz'].value()
            center = (cx, cy, cz)

            rx_deg = self.transform_inputs['Rx'].value()
            ry_deg = self.transform_inputs['Ry'].value()
            rz_deg = self.transform_inputs['Rz'].value()
            rotation_deg = (rx_deg, ry_deg, rz_deg) # 保持角度为度，核心函数会处理转换

            tx = self.transform_inputs['Tx'].value()
            ty = self.transform_inputs['Ty'].value()
            tz = self.transform_inputs['Tz'].value()
            translation = (tx, ty, tz)

            logging.info("从 GUI 获取变换参数成功:")
            logging.info(f"  Center: {center}")
            logging.info(f"  Rotation (deg): {rotation_deg}")
            logging.info(f"  Translation: {translation}")

        except KeyError as e:
             QMessageBox.critical(self, "内部错误", f"无法获取变换参数输入框: {e}")
             return
        except Exception as e:
             QMessageBox.critical(self, "参数错误", f"读取变换参数时出错: {e}")
             return
        # --- 参数获取结束 ---

        # 定义输出文件名和路径 (将在 target_series_dir 中创建)
        output_filename = f"RS.{os.path.basename(target_series_dir)}_from_W0PT_Tx.dcm" # 例如 RS.week4_PT_from_W0PT_Tx.dcm
        # 输出目录直接使用目标系列目录
        output_dir = target_series_dir
        # 完整的最终输出路径 (由核心函数内部处理复制到此位置)
        final_output_path = os.path.join(output_dir, output_filename)

        # 提示用户确认
        reply = QMessageBox.question(self,
                                     "确认操作 (带变换)",
                                     f"将从 Week0 PT RTSS 复制 ROI:\n{source_rtss_path}\n\n" 
                                     f"适配到 Week4 PT 系列:\n{target_series_dir}\n\n" 
                                     f"并应用以下刚性变换:\n"
                                     f"Center: ({cx:.2f}, {cy:.2f}, {cz:.2f})\n"
                                     f"Rotation (°): ({rx_deg:.2f}, {ry_deg:.2f}, {rz_deg:.2f})\n"
                                     f"Translation: ({tx:.2f}, {ty:.2f}, {tz:.2f})\n\n"
                                     f"保存为:\n{final_output_path}\n\n是否继续？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            logging.info("用户确认 W0->W4 PT (带变换) 复制操作，开始执行...")
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.copy_button_w0w4_tx.setEnabled(False)
            self.result_display.append("\n正在执行 Week0 PT -> Week4 PT (带变换) 复制...")
            QApplication.processEvents()

            try:
                # *** 调用核心函数 ***
                # 注意：我们不再需要传递 source_series_dir，核心函数会从 source_rtss_path 推断
                # 也不需要传递 output_rtss_path，而是传递 output_dir 和 new_rtss_filename
                copy_rtss_with_transform(
                    source_rtss_path=source_rtss_path,
                    target_image_series_dir=target_series_dir,
                    output_dir=output_dir, # 目标系列目录作为输出目录
                    rotation_center=center,
                    rotation_angles_deg=rotation_deg, # 传递度数
                    translation=translation,
                    # roi_name="PTV", # 可以省略，核心函数会尝试处理所有ROI
                    new_rtss_filename=output_filename
                )
                # 注意：copy_rtss_with_transform 抛出异常表示失败，不返回布尔值

                # 如果代码执行到这里，表示没有抛出异常，即成功
                QMessageBox.information(self, "成功", f"W0->W4 PT (带变换) RTStruct 已成功复制并保存到:\n{final_output_path}")
                self.result_display.append("W0->W4 PT (带变换) 复制操作成功完成。")
                # 可以在成功后重新扫描以刷新状态，但可能不是必须的
                # self.select_folder() # 触发重新扫描

            except FileNotFoundError as fnf_e:
                 logging.error(f"复制 W0->W4 PT 时文件/目录未找到: {fnf_e}", exc_info=True)
                 QMessageBox.critical(self, "文件错误", f"文件或目录未找到: {fnf_e}")
                 self.result_display.append(f"复制操作失败：文件或目录未找到 - {fnf_e}")
            except Exception as e:
                # 捕获核心函数抛出的所有其他异常
                logging.error(f"调用 W0->W4 PT (带变换) copy 函数时发生意外错误: {e}", exc_info=True)
                QMessageBox.critical(self, "严重错误", f"执行 W0->W4 PT (带变换) 复制时发生错误: {e}")
                self.result_display.append(f"W0->W4 PT (带变换) 复制操作因错误而中止: {e}")
            finally:
                QApplication.restoreOverrideCursor()
                # 重新评估按钮状态（即使失败也可能需要）
                self.update_copy_buttons_state()
        else:
            logging.info("用户取消了 W0->W4 PT (带变换) 复制操作。")

# 为了能独立运行测试（如果需要）
if __name__ == '__main__':
    # 配置基础日志记录
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)

    app = QApplication(sys.argv)
    copier_widget = RTSSCopier()
    copier_widget.show()
    sys.exit(app.exec_()) 