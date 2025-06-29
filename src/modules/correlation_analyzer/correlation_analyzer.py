#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import SimpleITK as sitk
import pydicom
from typing import Tuple, List, Dict, Optional, Union
from PyQt5.QtCore import QObject, pyqtSignal
from scipy.stats import pearsonr, spearmanr

# 导入rt-utils库
from rt_utils import RTStructBuilder

def configure_matplotlib_fonts():
    """配置matplotlib字体，解决中文和特殊字符显示问题"""
    try:
        import platform
        import warnings

        # 根据操作系统选择合适的中文字体
        if platform.system() == "Windows":
            # Windows系统优先使用微软雅黑
            font_list = [
                "Microsoft YaHei",
                "SimHei",
                "Arial Unicode MS",
                "DejaVu Sans",
                "sans-serif",
            ]
        elif platform.system() == "Darwin":  # macOS
            font_list = [
                "Arial Unicode MS",
                "PingFang SC",
                "Helvetica",
                "DejaVu Sans",
                "sans-serif",
            ]
        else:  # Linux
            font_list = [
                "WenQuanYi Micro Hei",
                "DejaVu Sans",
                "Liberation Sans",
                "sans-serif",
            ]

        matplotlib.rcParams["font.sans-serif"] = font_list
        # 解决负号显示问题
        matplotlib.rcParams["axes.unicode_minus"] = False
        # 设置字体回退机制
        matplotlib.rcParams["font.family"] = "sans-serif"
        # 设置DPI以提高清晰度
        matplotlib.rcParams["figure.dpi"] = 100
        matplotlib.rcParams["savefig.dpi"] = 300

        # 禁用字体警告（可选）
        warnings.filterwarnings("ignore", category=UserWarning,
                              message=".*Glyph.*missing from font.*")

    except Exception as e:
        # 如果字体配置失败，使用最基本的设置
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["axes.unicode_minus"] = False

def safe_format_r_squared(r_value):
    """安全格式化R平方值，避免字体问题"""
    return f"R-squared={r_value**2:.3f}"

# 初始化字体配置
configure_matplotlib_fonts()


class CorrelationAnalyzer(QObject):
    """
    分析两个PET图像在相同ROI区域内的像素值相关性
    支持:
    1. 提取相同ROI内的像素值
    2. 计算相关系数 (Pearson和Spearman)
    3. 生成散点图
    4. 保存数据到CSV文件
    """

    # 定义信号用于进度更新
    progress_updated = pyqtSignal(int, str)  # (进度百分比, 状态消息)
    process_finished = pyqtSignal(bool, str)  # (是否成功, 消息)
    image_loaded = pyqtSignal(dict)  # 图像加载完成信号，携带图像信息

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

        # 存储加载的图像和结构集
        self.pet1_data = {
            "image": None,  # 第一个PET图像
            "image_files": [],  # 图像文件路径列表
            "image_info": {},  # 图像元信息
            "loaded": False,  # 是否已加载
        }

        self.pet2_data = {
            "image": None,  # 第二个PET图像
            "image_files": [],  # 图像文件路径列表
            "image_info": {},  # 图像元信息
            "loaded": False,  # 是否已加载
        }

        # RTSS数据
        self.rtss_data = {
            "rtss": None,  # 结构集
            "rtss_file": None,  # 结构集文件路径
            "loaded": False,  # 是否已加载
        }

        # NIfTI数据存储
        self.nifti1_data = {
            "image": None,  # 第一个NIfTI图像
            "file_path": None,  # 文件路径
            "loaded": False,  # 是否已加载
        }

        self.nifti2_data = {
            "image": None,  # 第二个NIfTI图像
            "file_path": None,  # 文件路径
            "loaded": False,  # 是否已加载
        }

        # 分析结果
        self.results = {
            "roi_name": None,  # 分析的ROI名称
            "voxel_count": 0,  # ROI内体素数量
            "pet1_values": None,  # PET1中ROI内的像素值
            "pet2_values": None,  # PET2中ROI内的像素值
            "pearson_r": None,  # Pearson相关系数
            "pearson_p": None,  # Pearson p值
            "spearman_r": None,  # Spearman相关系数
            "spearman_p": None,  # Spearman p值
            "analysis_type": None,  # 'dicom_roi' 或 'nifti_mask'
            "mask_option": None,  # 掩码选项
            "nifti1_file": None,  # 第一个NIfTI文件名
            "nifti2_file": None,  # 第二个NIfTI文件名
        }

        # 掩码选项
        self.MASK_OPTIONS = {
            "non_zero_first": "第一个图像的所有非零像素",
            "non_zero_both": "两个图像都非零的像素",
            "positive_first": "第一个图像的所有正值像素",
            "threshold_first": "第一个图像超过阈值的像素(>0.1)",
        }

        # 输出目录
        self.output_dir = None

        # 自定义选项
        self.custom_options = {
            'chart_title': None,
            'x_label': None,
            'y_label': None,
            'output_prefix': None
        }

    def load_pet_directory(
        self, directory: str, is_pet1: bool = True
    ) -> Tuple[bool, str, Dict]:
        """
        加载目录中的PET DICOM图像
        根据切片的ImagePositionPatient对图像文件进行排序，强制按Z值从小到大排序

        Args:
            directory: 包含DICOM序列的目录
            is_pet1: 是否作为第一个PET图像加载，否则作为第二个PET图像

        Returns:
            Tuple[bool, str, Dict]: (成功标志, 消息, 数据字典)
        """
        try:
            pet_label = "PET1" if is_pet1 else "PET2"
            self.logger.info(f"正在加载目录: {directory}, 作为{pet_label}")
            self.progress_updated.emit(0, f"开始加载{pet_label}图像...")

            # 确定是加载到pet1还是pet2
            data_dict = self.pet1_data if is_pet1 else self.pet2_data

            # 重置数据
            data_dict["image"] = None
            data_dict["image_files"] = []
            data_dict["image_info"] = {}
            data_dict["loaded"] = False

            # 递归查找目录中的所有文件（添加递归选项，确保检查子目录）
            dicom_candidates = []

            # 首先尝试仅在当前目录中搜索
            current_dir_files = [
                os.path.join(directory, f)
                for f in os.listdir(directory)
                if os.path.isfile(os.path.join(directory, f))
            ]
            self.logger.info(f"当前目录中找到 {len(current_dir_files)} 个文件")
            dicom_candidates.extend(current_dir_files)

            # 如果当前目录文件太少，尝试使用glob进行通配符搜索
            if len(current_dir_files) < 5:  # 假设至少需要5个文件才构成有效序列
                self.logger.info("当前目录文件过少，尝试使用通配符搜索")
                for ext in [".dcm", ".DCM", "*"]:
                    pattern = os.path.join(directory, f"**/*{ext}")
                    found_files = glob.glob(pattern, recursive=True)
                    self.logger.info(
                        f"使用pattern '{pattern}' 找到 {len(found_files)} 个文件"
                    )
                    dicom_candidates.extend(found_files)

            # 使用集合去重
            dicom_candidates = list(set(dicom_candidates))

            # 过滤掉目录
            dicom_candidates = [f for f in dicom_candidates if os.path.isfile(f)]

            total_files = len(dicom_candidates)
            if total_files == 0:
                msg = f"目录 {directory} 中未找到任何文件"
                self.logger.warning(msg)
                return False, msg, data_dict

            self.logger.info(f"在目录 {directory} 中找到 {total_files} 个待检测文件")
            self.progress_updated.emit(
                10, f"找到 {total_files} 个文件，正在识别DICOM文件"
            )

            # 对找到的文件进行分类
            image_files = []
            rtss_file = None

            # 读取每个文件查看其SOPClassUID和Modality
            valid_files = 0
            invalid_files = 0

            # 用于存储DICOM切片信息
            slices_info = []

            for i, file_path in enumerate(dicom_candidates):
                try:
                    # 更新进度
                    if i % max(1, total_files // 20) == 0:  # 最多更新20次进度
                        progress = 10 + int(40 * i / total_files)
                        self.progress_updated.emit(
                            progress, f"分析DICOM文件 {i+1}/{total_files}..."
                        )

                    # 尝试读取DICOM文件，设置更宽松的选项
                    try:
                        dcm = pydicom.dcmread(
                            file_path, force=True, stop_before_pixels=True
                        )
                        valid_files += 1
                    except Exception as read_error:
                        self.logger.debug(f"无法读取文件 {file_path}: {read_error}")
                        invalid_files += 1
                        continue

                    # 检查是否为RTSS - 宽松判断，使用多种可能的条件
                    is_rtss = False
                    if (
                        hasattr(dcm, "SOPClassUID")
                        and dcm.SOPClassUID == "1.2.840.10008.5.1.4.1.1.481.3"
                    ):
                        is_rtss = True
                    elif hasattr(dcm, "Modality") and dcm.Modality == "RTSTRUCT":
                        is_rtss = True
                    elif (
                        hasattr(dcm, "Manufacturer")
                        and "STRUCTURE" in str(getattr(dcm, "Manufacturer", "")).upper()
                    ):
                        is_rtss = True

                    if is_rtss and rtss_file is None:  # 只使用找到的第一个RTSS
                        rtss_file = file_path
                        self.logger.info(f"找到RTSS文件: {file_path}")
                        continue

                    # 检查是否为PET图像 - 更加宽松的判断
                    is_pet = False
                    # 基于模态判断
                    if hasattr(dcm, "Modality") and dcm.Modality == "PT":
                        is_pet = True
                        self.logger.debug(f"通过Modality=PT识别为PET图像: {file_path}")
                    # 基于序列描述判断
                    elif (
                        hasattr(dcm, "SeriesDescription")
                        and "PET" in str(getattr(dcm, "SeriesDescription", "")).upper()
                    ):
                        is_pet = True
                        self.logger.debug(
                            f"通过SeriesDescription包含PET识别为PET图像: {file_path}"
                        )
                    # 基于序列名称判断
                    elif (
                        hasattr(dcm, "SeriesDescription")
                        and "FDG" in str(getattr(dcm, "SeriesDescription", "")).upper()
                    ):
                        is_pet = True
                        self.logger.debug(
                            f"通过SeriesDescription包含FDG识别为PET图像: {file_path}"
                        )
                    # 基于研究描述判断
                    elif (
                        hasattr(dcm, "StudyDescription")
                        and "PET" in str(getattr(dcm, "StudyDescription", "")).upper()
                    ):
                        is_pet = True
                        self.logger.debug(
                            f"通过StudyDescription包含PET识别为PET图像: {file_path}"
                        )
                    # 基于文件路径判断
                    elif (
                        "PET" in file_path.upper()
                        or "PT" in os.path.basename(os.path.dirname(file_path)).upper()
                    ):
                        is_pet = True
                        self.logger.debug(
                            f"通过文件路径包含PET/PT识别为PET图像: {file_path}"
                        )

                    # 如果是PET图像，添加到列表并保存位置信息
                    if is_pet:
                        # 获取ImagePositionPatient信息，用于后续排序
                        position = None
                        try:
                            if hasattr(dcm, "ImagePositionPatient"):
                                position = tuple(
                                    float(p) for p in dcm.ImagePositionPatient
                                )
                                # 将切片信息添加到列表
                                z_position = position[2] if len(position) > 2 else 0
                                instance_number = int(getattr(dcm, "InstanceNumber", 0))
                                slice_info = {
                                    "file_path": file_path,
                                    "position": position,
                                    "z_position": z_position,
                                    "instance_number": instance_number,
                                }
                                slices_info.append(slice_info)
                                image_files.append(file_path)
                            else:
                                # 即使没有位置信息，也添加到图像文件列表
                                image_files.append(file_path)
                                self.logger.warning(
                                    f"图像文件 {file_path} 没有ImagePositionPatient信息"
                                )
                        except Exception as position_error:
                            # 忽略位置获取错误，仍然加入图像列表
                            image_files.append(file_path)
                            self.logger.warning(
                                f"获取位置信息时出错 {file_path}: {position_error}"
                            )

                        if len(image_files) < 5:  # 只显示前几个找到的文件，避免日志过长
                            self.logger.info(
                                f"识别为PET图像: {file_path}"
                                + (f", 位置: {position}" if position else "")
                            )
                        elif len(image_files) == 5:
                            self.logger.info("找到更多PET图像...")

                except Exception as e:
                    self.logger.debug(f"处理文件 {file_path} 时出错: {e}")
                    invalid_files += 1
                    continue

            # 如果有位置信息，按Z坐标从小到大排序切片
            if slices_info:
                self.logger.info(
                    f"根据ImagePositionPatient的Z值对 {len(slices_info)} 个切片进行排序"
                )

                # 检查Z坐标的最小值和最大值
                z_values = [info["z_position"] for info in slices_info]
                min_z = min(z_values)
                max_z = max(z_values)

                # 输出最小和最大Z值，用于调试
                self.logger.info(f"Z坐标范围: [{min_z}, {max_z}]")

                # 始终按Z坐标从小到大排序，不管原始DICOM的顺序如何
                slices_info.sort(key=lambda x: x["z_position"])

                # 输出排序结果信息
                self.logger.info(f"切片已按Z坐标从小到大排序")
                self.logger.info(
                    f"排序后的第一个切片Z坐标: {slices_info[0]['z_position']}"
                )
                self.logger.info(
                    f"排序后的最后一个切片Z坐标: {slices_info[-1]['z_position']}"
                )

                # 输出InstanceNumber信息用于调试
                instance_numbers = [
                    info["instance_number"]
                    for info in slices_info
                    if info["instance_number"] > 0
                ]
                if instance_numbers:
                    first_instance = slices_info[0]["instance_number"]
                    last_instance = slices_info[-1]["instance_number"]
                    self.logger.info(
                        f"从小到大排序后: 第一个切片的InstanceNumber: {first_instance}, 最后一个切片的InstanceNumber: {last_instance}"
                    )

                # 更新图像文件列表，按排序后的顺序
                image_files = [info["file_path"] for info in slices_info]
            else:
                self.logger.warning("没有找到切片位置信息，无法按Z坐标排序")

            # 更新数据字典
            data_dict["image_files"] = image_files

            # 如果找到了RTSS文件，保存到rtss_data中
            if rtss_file and not self.rtss_data["loaded"]:
                self.rtss_data["rtss_file"] = rtss_file
                try:
                    self.rtss_data["rtss"] = pydicom.dcmread(rtss_file)
                    self.rtss_data["loaded"] = True
                    contour_count = self._count_rtss_contours(self.rtss_data["rtss"])
                    self.logger.info(f"成功加载RTSS，包含 {contour_count} 个轮廓")
                except Exception as e:
                    self.logger.warning(f"加载RTSS时出错: {e}")

            # 记录有效的DICOM图像文件数
            dicom_image_count = len(image_files)
            self.logger.info(
                f"统计：总文件数 {total_files}, 有效DICOM文件 {valid_files}, 无效文件 {invalid_files}"
            )
            self.logger.info(
                f"识别出 {dicom_image_count} 个有效的PET图像文件"
                + (f", 1个RTSS文件" if rtss_file else "")
            )

            if dicom_image_count == 0:
                msg = f"在目录 {directory} 中未找到有效的PET图像文件"
                self.logger.warning(msg)
                return False, msg, data_dict

            # 加载图像文件
            self.progress_updated.emit(
                50, f"加载{pet_label}图像序列，共{dicom_image_count}个文件..."
            )
            try:
                # 使用SimpleITK读取图像序列
                reader = sitk.ImageSeriesReader()
                reader.SetFileNames(image_files)

                self.logger.info(f"正在执行SimpleITK读取，文件数量：{len(image_files)}")
                image = reader.Execute()
                data_dict["image"] = image

                # 提取图像信息
                data_dict["image_info"] = {
                    "size": image.GetSize(),
                    "spacing": image.GetSpacing(),
                    "origin": image.GetOrigin(),
                    "direction": image.GetDirection(),
                    "file_count": dicom_image_count,
                    "modality": self._get_image_modality(image_files[0]),
                }

                self.logger.info(
                    f"成功加载{pet_label}图像, 尺寸={image.GetSize()}, 间距={image.GetSpacing()}, 原点={image.GetOrigin()}"
                )
                data_dict["loaded"] = True
            except Exception as e:
                msg = f"加载{pet_label}图像序列时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg, data_dict

            # 更新加载状态
            if data_dict["image"] is not None:
                self.progress_updated.emit(100, f"成功加载{pet_label}图像")

                # 发送图像加载完成信号
                data_to_emit = data_dict.copy()
                data_to_emit["is_pet1"] = is_pet1  # 添加is_pet1标志
                self.image_loaded.emit(data_to_emit)

                return (
                    True,
                    f"成功加载{pet_label}图像，尺寸={image.GetSize()}",
                    data_dict,
                )
            else:
                return False, f"未能加载{pet_label}图像", data_dict

        except Exception as e:
            msg = f"加载{pet_label}目录时出错: {e}"
            self.logger.error(msg, exc_info=True)
            return False, msg, data_dict

    def load_rtss_file(self, rtss_file: str) -> Tuple[bool, str]:
        """
        加载RTSS文件

        Args:
            rtss_file: RTSS文件路径

        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        try:
            self.logger.info(f"加载RTSS文件: {rtss_file}")
            self.progress_updated.emit(0, "加载RTSS文件...")

            # 加载RTSS文件
            self.rtss_data["rtss_file"] = rtss_file
            self.rtss_data["rtss"] = pydicom.dcmread(rtss_file)
            self.rtss_data["loaded"] = True

            contour_count = self._count_rtss_contours(self.rtss_data["rtss"])
            self.logger.info(f"成功加载RTSS，包含 {contour_count} 个轮廓")
            self.progress_updated.emit(
                100, f"成功加载RTSS, 包含 {contour_count} 个轮廓"
            )

            return True, f"成功加载RTSS, 包含 {contour_count} 个轮廓"
        except Exception as e:
            msg = f"加载RTSS文件时出错: {e}"
            self.logger.error(msg, exc_info=True)
            return False, msg

    def get_roi_names(self) -> List[str]:
        """
        获取RTSS中所有ROI的名称

        Returns:
            List[str]: ROI名称列表
        """
        if not self.rtss_data["loaded"]:
            return []

        roi_names = []
        try:
            rtss = self.rtss_data["rtss"]
            # 获取ROI名称
            for roi in rtss.StructureSetROISequence:
                roi_names.append(roi.ROIName)
        except Exception as e:
            self.logger.error(f"获取ROI名称时出错: {e}", exc_info=True)

        return roi_names

    def analyze_correlation(self, roi_name: str, output_dir: str) -> Tuple[bool, str]:
        """
        分析指定ROI区域内两个PET图像的相关性
        如果找不到指定名称的ROI，会尝试使用第一个可用的ROI

        Args:
            roi_name: ROI名称（如果不存在，将使用第一个可用的ROI）
            output_dir: 输出目录

        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        if not self.pet1_data["loaded"] or not self.pet2_data["loaded"]:
            return False, "请先加载两个PET图像"

        if not self.rtss_data["loaded"]:
            return False, "请先加载RTSS文件"

        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        try:
            self.progress_updated.emit(0, f"开始分析ROI '{roi_name}'的相关性...")

            # 初始化结果中的ROI名称为请求的名称
            self.results["roi_name"] = roi_name

            # 检查两个PET图像的尺寸是否一致
            pet1_size = self.pet1_data["image"].GetSize()
            pet2_size = self.pet2_data["image"].GetSize()

            if pet1_size != pet2_size:
                msg = f"两个PET图像尺寸不一致: PET1={pet1_size}, PET2={pet2_size}"
                self.logger.error(msg)
                return False, msg

            # 检查两个PET图像的原点和方向
            pet1_origin = self.pet1_data["image"].GetOrigin()
            pet2_origin = self.pet2_data["image"].GetOrigin()
            pet1_direction = self.pet1_data["image"].GetDirection()
            pet2_direction = self.pet2_data["image"].GetDirection()

            self.logger.info(f"PET1原点: {pet1_origin}, 方向矩阵: {pet1_direction}")
            self.logger.info(f"PET2原点: {pet2_origin}, 方向矩阵: {pet2_direction}")

            # 判断是否存在反向情况
            # 如果Z轴原点的差异很大，可能表示反向加载
            z_origin_diff = abs(pet1_origin[2] - pet2_origin[2])
            self.logger.info(f"Z轴原点差异: {z_origin_diff} mm")

            # 检查Z轴是否反向
            pet1_z_vector = (pet1_direction[2], pet1_direction[5], pet1_direction[8])
            pet2_z_vector = (pet2_direction[2], pet2_direction[5], pet2_direction[8])
            z_direction_diff = sum(
                abs(pet1_z_vector[i] - pet2_z_vector[i]) for i in range(3)
            )
            self.logger.info(f"Z轴方向向量差异: {z_direction_diff}")

            is_reversed = False
            if (
                z_origin_diff > 10 or z_direction_diff > 0.1
            ):  # 如果Z原点差异大或Z方向向量差异明显
                self.logger.warning("检测到PET2可能与PET1反向加载")
                is_reversed = True
                self.progress_updated.emit(5, "检测到图像可能反向加载，将进行调整")

            self.logger.info(f"两个PET图像尺寸一致: {pet1_size}，开始生成ROI掩码")

            # 1. 获取ROI轮廓的掩码
            self.progress_updated.emit(10, "生成ROI掩码...")
            mask = self._get_roi_mask(roi_name)
            if mask is None:
                return False, f"未能找到可用的ROI或生成掩码失败"

            # 检查掩码是否为空
            if np.sum(mask) == 0:
                actual_roi_name = self.results["roi_name"]  # 在_get_roi_mask中已更新
                return False, f"ROI '{actual_roi_name}' 生成的掩码为空，无法分析"

            # 获取实际使用的ROI名称（可能是第一个可用的ROI）
            actual_roi_name = self.results["roi_name"]
            if actual_roi_name != roi_name:
                self.logger.info(
                    f"使用替代ROI '{actual_roi_name}' 而非请求的 '{roi_name}'"
                )
                self.progress_updated.emit(15, f"使用ROI '{actual_roi_name}'")

            mask_count = np.sum(mask)
            mask_shape = mask.shape
            self.logger.info(
                f"成功生成掩码，掩码内点数: {mask_count}, 掩码形状: {mask_shape}"
            )

            # 2. 提取两个PET图像上ROI内的像素值
            self.progress_updated.emit(
                30, f"提取ROI '{actual_roi_name}' 内的PET1像素值..."
            )
            try:
                pet1_array = sitk.GetArrayFromImage(self.pet1_data["image"])
                self.logger.info(
                    f"PET1像素值范围: [{np.min(pet1_array)}, {np.max(pet1_array)}]，形状: {pet1_array.shape}"
                )
                pet1_values = pet1_array[mask]
                self.logger.info(
                    f"提取出 {len(pet1_values)} 个PET1像素值，范围: [{np.min(pet1_values)}, {np.max(pet1_values)}]"
                )
            except Exception as e:
                msg = f"提取PET1像素值时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg

            self.progress_updated.emit(
                50, f"提取ROI '{actual_roi_name}' 内的PET2像素值..."
            )
            try:
                pet2_array = sitk.GetArrayFromImage(self.pet2_data["image"])
                self.logger.info(
                    f"PET2像素值范围: [{np.min(pet2_array)}, {np.max(pet2_array)}]，形状: {pet2_array.shape}"
                )

                # 如果检测到反向加载，需要翻转PET2数组
                if is_reversed:
                    self.logger.info("正在翻转PET2数组以匹配PET1方向...")

                    # 因为DICOM按照Z坐标从小到大排序，所以只需翻转Z轴
                    pet2_array = pet2_array[::-1, :, :]
                    self.logger.info(f"PET2数组已沿Z轴翻转，新形状: {pet2_array.shape}")

                # 应用掩码提取像素值
                pet2_values = pet2_array[mask]
                self.logger.info(
                    f"提取出 {len(pet2_values)} 个PET2像素值，范围: [{np.min(pet2_values)}, {np.max(pet2_values)}]"
                )
            except Exception as e:
                msg = f"提取PET2像素值时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg

            # 确保值的长度匹配
            if len(pet1_values) != len(pet2_values):
                # 如果反向翻转后仍然不匹配，尝试创建和应用新掩码
                self.logger.warning(
                    f"PET1和PET2中ROI内的像素数量不匹配: PET1={len(pet1_values)}, PET2={len(pet2_values)}"
                )
                self.logger.info("尝试创建新掩码解决不匹配问题...")

                # 创建PET1掩码的副本
                pet1_mask = np.zeros_like(pet1_array, dtype=bool)
                pet1_mask[mask] = True

                # 为PET2创建新掩码
                pet2_mask = None

                # 尝试不同的掩码转换方式
                if is_reversed:
                    # 如果已反转Z轴，但仍不匹配，可能需要额外的调整
                    pet2_mask = pet1_mask[::-1, :, :]  # 沿Z轴翻转掩码
                    self.logger.info("尝试沿Z轴翻转掩码")
                else:
                    # 尝试其他轴的翻转
                    masks_to_try = [
                        ("原始掩码", pet1_mask),
                        ("X轴翻转", pet1_mask[:, :, ::-1]),
                        ("Y轴翻转", pet1_mask[:, ::-1, :]),
                        ("Z轴翻转", pet1_mask[::-1, :, :]),
                        ("XY翻转", pet1_mask[:, ::-1, ::-1]),
                        ("XZ翻转", pet1_mask[::-1, :, ::-1]),
                        ("YZ翻转", pet1_mask[::-1, ::-1, :]),
                        ("XYZ翻转", pet1_mask[::-1, ::-1, ::-1]),
                    ]

                    # 测试每种掩码，找到最接近期望数量的
                    best_mask = None
                    best_count_diff = float("inf")

                    for mask_name, mask_to_try in masks_to_try:
                        count = np.sum(mask_to_try)
                        count_diff = abs(count - mask_count)
                        self.logger.info(
                            f"掩码 {mask_name}: 点数 = {count}, 与原始差异 = {count_diff}"
                        )

                        if count_diff < best_count_diff:
                            best_count_diff = count_diff
                            best_mask = mask_to_try
                            self.logger.info(f"找到更好的掩码: {mask_name}")

                    pet2_mask = best_mask

                # 使用新掩码提取像素值
                if pet2_mask is not None:
                    pet1_values = pet1_array[pet1_mask]
                    pet2_values = pet2_array[pet2_mask]

                    self.logger.info(
                        f"使用新掩码后: PET1={len(pet1_values)}个像素, PET2={len(pet2_values)}个像素"
                    )

                    # 再次检查
                    if len(pet1_values) != len(pet2_values):
                        # 如果仍然不匹配，取较小的集合
                        min_length = min(len(pet1_values), len(pet2_values))
                        self.logger.warning(
                            f"仍然不匹配，截取相同长度: {min_length}像素"
                        )
                        pet1_values = pet1_values[:min_length]
                        pet2_values = pet2_values[:min_length]
                else:
                    self.logger.error("未能创建有效的替代掩码")
                    return False, "无法创建有效掩码，PET1和PET2中像素数量不匹配"

            # 将提取的值保存到结果中
            self.results["voxel_count"] = len(pet1_values)
            self.results["pet1_values"] = pet1_values
            self.results["pet2_values"] = pet2_values

            # 3. 检查数据是否有效
            # 检查是否存在无效值(NaN/Inf)
            invalid_pet1 = np.isnan(pet1_values).any() or np.isinf(pet1_values).any()
            invalid_pet2 = np.isnan(pet2_values).any() or np.isinf(pet2_values).any()

            if invalid_pet1 or invalid_pet2:
                self.logger.warning(
                    f"数据中存在无效值: PET1_NaN={np.isnan(pet1_values).sum()}, PET1_Inf={np.isinf(pet1_values).sum()}, "
                    f"PET2_NaN={np.isnan(pet2_values).sum()}, PET2_Inf={np.isinf(pet2_values).sum()}"
                )

                # 移除无效值
                valid_mask = ~(
                    np.isnan(pet1_values)
                    | np.isinf(pet1_values)
                    | np.isnan(pet2_values)
                    | np.isinf(pet2_values)
                )
                pet1_values = pet1_values[valid_mask]
                pet2_values = pet2_values[valid_mask]
                self.logger.info(f"移除无效值后剩余 {len(pet1_values)} 个有效数据点")

                # 更新结果中的值
                self.results["voxel_count"] = len(pet1_values)
                self.results["pet1_values"] = pet1_values
                self.results["pet2_values"] = pet2_values

            # 4. 计算相关系数
            self.progress_updated.emit(70, "计算相关系数...")
            if len(pet1_values) > 5:  # 需要足够多的点才能计算可靠的相关性
                try:
                    # Pearson相关系数
                    pearson_r, pearson_p = pearsonr(pet1_values, pet2_values)
                    self.results["pearson_r"] = pearson_r
                    self.results["pearson_p"] = pearson_p

                    # Spearman相关系数
                    spearman_r, spearman_p = spearmanr(pet1_values, pet2_values)
                    self.results["spearman_r"] = spearman_r
                    self.results["spearman_p"] = spearman_p

                    self.logger.info(
                        f"Pearson相关系数: r={pearson_r:.4f}, p={pearson_p:.4f}"
                    )
                    self.logger.info(
                        f"Spearman相关系数: r={spearman_r:.4f}, p={spearman_p:.4f}"
                    )

                    # 如果r为NaN，尝试计算数据统计信息以帮助诊断
                    if np.isnan(pearson_r) or np.isnan(spearman_r):
                        self.logger.warning("相关系数计算结果为NaN，检查数据分布...")
                        pet1_std = np.std(pet1_values)
                        pet2_std = np.std(pet2_values)
                        self.logger.warning(
                            f"数据统计: PET1标准差={pet1_std}, PET2标准差={pet2_std}"
                        )

                        # 如果标准差为0，说明数据没有变化
                        if pet1_std == 0 or pet2_std == 0:
                            self.logger.error("数据没有变化，无法计算相关性")
                            return False, "图像数据没有变化，无法计算相关性"
                except Exception as e:
                    msg = f"计算相关系数时出错: {e}"
                    self.logger.error(msg, exc_info=True)
                    return False, msg
            else:
                self.logger.warning(
                    f"ROI中的体素数量太少 ({len(pet1_values)}), 无法计算可靠的相关性"
                )
                return (
                    False,
                    f"ROI '{actual_roi_name}' 中的体素数量太少({len(pet1_values)}), 需要至少5个点才能计算可靠的相关性",
                )

            # 5. 保存数据到CSV
            self.progress_updated.emit(80, "保存数据到CSV...")
            try:
                csv_path = self._save_to_csv(
                    actual_roi_name, pet1_values, pet2_values, output_dir
                )
                self.logger.info(f"成功保存数据到CSV: {csv_path}")
            except Exception as e:
                msg = f"保存CSV时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg

            # 6. 绘制散点图
            self.progress_updated.emit(90, "生成散点图...")
            try:
                plot_path = self._create_scatter_plot(
                    actual_roi_name, pet1_values, pet2_values, output_dir
                )
                self.logger.info(f"成功生成散点图: {plot_path}")
            except Exception as e:
                msg = f"生成散点图时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg

            self.progress_updated.emit(100, "分析完成")

            # 格式化p值，确保足够小的p值使用科学计数法
            pearson_p_str = f"{pearson_p:.8f}"
            spearman_p_str = f"{spearman_p:.8f}"
            if pearson_p < 0.00000001:
                pearson_p_str = f"{pearson_p:.3e}"
            if spearman_p < 0.00000001:
                spearman_p_str = f"{spearman_p:.3e}"

            message = (
                f"成功分析ROI '{actual_roi_name}'的相关性:\n"
                f"- Pearson r: {pearson_r:.4f} (p={pearson_p_str})\n"
                f"- Spearman r: {spearman_r:.4f} (p={spearman_p_str})\n"
                f"- 体素数量: {len(pet1_values)}\n"
                f"- 已保存CSV到: {csv_path}\n"
                f"- 已保存散点图到: {plot_path}"
            )

            self.process_finished.emit(True, message)
            return True, message

        except Exception as e:
            msg = f"分析相关性时出错: {e}"
            self.logger.error(msg, exc_info=True)
            self.process_finished.emit(False, msg)
            return False, msg

    def _get_image_modality(self, dicom_file: str) -> str:
        """获取DICOM图像的模态"""
        try:
            dcm = pydicom.dcmread(dicom_file, stop_before_pixels=True)
            return dcm.Modality if hasattr(dcm, "Modality") else "Unknown"
        except:
            return "Unknown"

    def _count_rtss_contours(self, rtss_data) -> int:
        """计算RTSS中的轮廓数量"""
        try:
            return len(rtss_data.StructureSetROISequence)
        except:
            return 0

    def _get_roi_mask(self, roi_name: str) -> Optional[np.ndarray]:
        """
        使用rt-utils库生成指定ROI的二值掩码
        如果找不到指定名称的ROI，会尝试使用第一个可用的ROI

        Args:
            roi_name: ROI名称

        Returns:
            Optional[np.ndarray]: 如果成功，返回二值掩码；否则返回None
        """
        try:
            # 检查必要的数据是否已加载
            if not self.rtss_data["loaded"] or not self.pet1_data["loaded"]:
                self.logger.error("缺少必要的数据：RTSS或PET图像未加载")
                return None

            rtss_file = self.rtss_data["rtss_file"]
            pet_dir = os.path.dirname(self.pet1_data["image_files"][0])

            self.logger.info(f"使用rt-utils生成ROI '{roi_name}' 的掩码")
            self.logger.info(f"RTSS文件: {rtss_file}")
            self.logger.info(f"PET目录: {pet_dir}")

            # 为pet_dir创建一个临时目录，以便rt-utils可以正确加载
            temp_dir = None
            if not os.path.isdir(pet_dir):
                # 如果pet_dir包含单个文件而不是目录，创建临时目录
                temp_dir = os.path.join(os.path.dirname(pet_dir), "temp_dicom_dir")
                os.makedirs(temp_dir, exist_ok=True)
                # 复制所有PET文件到临时目录
                for file_path in self.pet1_data["image_files"]:
                    import shutil

                    shutil.copy(file_path, temp_dir)
                pet_dir = temp_dir
                self.logger.info(f"创建临时目录: {temp_dir}")

            # 使用RTStructBuilder加载RTSS和图像
            try:
                rtstruct = RTStructBuilder.create_from(
                    dicom_series_path=pet_dir, rt_struct_path=rtss_file
                )
                self.logger.info("成功加载RTStructBuilder")
            except Exception as e:
                self.logger.error(f"加载RTStructBuilder失败: {e}")
                # 尝试另一种方法：直接使用第一个图像文件
                rtstruct = RTStructBuilder.create_from(
                    dicom_series_path=self.pet1_data["image_files"][0],
                    rt_struct_path=rtss_file,
                )
                self.logger.info("使用单个文件模式成功加载RTStructBuilder")

            # 获取可用的ROI名称
            available_rois = rtstruct.get_roi_names()
            self.logger.info(f"可用的ROI列表: {available_rois}")

            # 如果指定ROI名称不存在，使用第一个可用的ROI
            selected_roi_name = roi_name
            if roi_name not in available_rois and available_rois:
                selected_roi_name = available_rois[0]
                self.logger.info(
                    f"未找到指定的ROI '{roi_name}'，使用第一个可用的ROI '{selected_roi_name}'"
                )

            # 更新结果中的ROI名称
            self.results["roi_name"] = selected_roi_name

            # 如果没有可用的ROI，返回None
            if not available_rois:
                self.logger.warning("没有可用的ROI")
                return None

            # 获取ROI掩码
            try:
                # 获取3D掩码数组
                mask_3d = rtstruct.get_roi_mask_by_name(selected_roi_name)
                self.logger.info(f"获取到3D掩码，形状: {mask_3d.shape}")

                # 检查掩码是否为空
                mask_points = np.sum(mask_3d)
                self.logger.info(f"掩码内点数: {mask_points}")
                if mask_points == 0:
                    self.logger.warning(f"生成的掩码为空, 未包含任何像素")
                    return None

                # 获取图像方向信息
                pet1_direction = self.pet1_data["image"].GetDirection()
                self.logger.info(f"PET1图像方向: {pet1_direction}")

                # rt-utils返回的掩码形状通常是[Y, X, Z]，但需要确保与SimpleITK图像匹配
                pet1_shape = self.pet1_data["image"].GetSize()  # (X, Y, Z)
                expected_shape = (
                    pet1_shape[2],
                    pet1_shape[1],
                    pet1_shape[0],
                )  # (Z, Y, X)

                self.logger.info(f"期望的掩码形状: {expected_shape}")
                self.logger.info(f"实际掩码形状: {mask_3d.shape}")

                # 检查主对角线方向的符号，这影响了坐标系的方向
                main_diag_signs = [
                    np.sign(pet1_direction[0]),
                    np.sign(pet1_direction[4]),
                    np.sign(pet1_direction[8]),
                ]
                self.logger.info(f"主对角线方向符号: {main_diag_signs}")

                # 如果形状不匹配，尝试转置和翻转
                if mask_3d.shape != expected_shape:
                    self.logger.warning(
                        f"掩码形状 {mask_3d.shape} 与期望形状 {expected_shape} 不匹配，尝试调整"
                    )

                    # 尝试不同的转置方式
                    if mask_3d.shape == (
                        pet1_shape[1],
                        pet1_shape[0],
                        pet1_shape[2],
                    ):  # (Y, X, Z)
                        self.logger.info("检测到掩码形状为(Y, X, Z)，转置为(Z, Y, X)")
                        mask_3d = mask_3d.transpose(2, 0, 1)  # (Z, Y, X)
                    elif mask_3d.shape == (
                        pet1_shape[0],
                        pet1_shape[1],
                        pet1_shape[2],
                    ):  # (X, Y, Z)
                        self.logger.info("检测到掩码形状为(X, Y, Z)，转置为(Z, Y, X)")
                        mask_3d = mask_3d.transpose(2, 1, 0)  # (Z, Y, X)
                    elif mask_3d.shape == (
                        pet1_shape[2],
                        pet1_shape[0],
                        pet1_shape[1],
                    ):  # (Z, X, Y)
                        self.logger.info("检测到掩码形状为(Z, X, Y)，转置为(Z, Y, X)")
                        mask_3d = mask_3d.transpose(0, 2, 1)  # (Z, Y, X)

                    # 如果主对角线有负值，可能需要翻转某些轴
                    if main_diag_signs[0] < 0:  # X轴反向
                        self.logger.info("X轴方向为负，翻转X轴")
                        mask_3d = mask_3d[:, :, ::-1]
                    if main_diag_signs[1] < 0:  # Y轴反向
                        self.logger.info("Y轴方向为负，翻转Y轴")
                        mask_3d = mask_3d[:, ::-1, :]
                    if main_diag_signs[2] < 0:  # Z轴反向
                        self.logger.info("Z轴方向为负，翻转Z轴")
                        mask_3d = mask_3d[::-1, :, :]

                    self.logger.info(f"调整后的掩码形状: {mask_3d.shape}")

                # 最后检查一次点数
                adjusted_points = np.sum(mask_3d)
                if adjusted_points != mask_points:
                    self.logger.warning(
                        f"调整后的掩码点数({adjusted_points})与原始点数({mask_points})不一致，这可能是正常的"
                    )

                return mask_3d.astype(np.bool_)

            except Exception as mask_error:
                self.logger.error(f"获取ROI掩码时错误: {mask_error}")
                return None

        except Exception as e:
            self.logger.error(f"生成ROI掩码时出错: {e}", exc_info=True)
            return None
        finally:
            # 清理临时目录
            if temp_dir and os.path.exists(temp_dir):
                import shutil

                try:
                    shutil.rmtree(temp_dir)
                    self.logger.info(f"已删除临时目录: {temp_dir}")
                except:
                    self.logger.warning(f"无法删除临时目录: {temp_dir}")

    def _save_to_csv(
        self,
        roi_name: str,
        pet1_values: np.ndarray,
        pet2_values: np.ndarray,
        output_dir: str,
    ) -> str:
        """
        将像素值数据保存到CSV文件

        Args:
            roi_name: ROI名称
            pet1_values: PET1图像中的像素值
            pet2_values: PET2图像中的像素值
            output_dir: 输出目录

        Returns:
            str: CSV文件路径
        """
        try:
            # 清理ROI名称，避免文件名中的特殊字符
            safe_roi_name = "".join(c if c.isalnum() else "_" for c in roi_name)

            # 创建DataFrame
            self.logger.info(f"创建CSV数据表，数据点数量: {len(pet1_values)}")
            df = pd.DataFrame({"PET1": pet1_values, "PET2": pet2_values})

            # 计算一些基本统计信息，记录到日志中
            stats = df.describe()
            self.logger.info(f"数据统计信息:\n{stats}")

            # 保存到CSV - 使用自定义前缀
            if hasattr(self, 'custom_options') and self.custom_options.get('output_prefix'):
                prefix = self.custom_options['output_prefix']
                safe_prefix = "".join(c if c.isalnum() else "_" for c in prefix)
                csv_filename = f"{safe_prefix}_correlation.csv"
            else:
                csv_filename = f"{safe_roi_name}_correlation.csv"
            csv_path = os.path.join(output_dir, csv_filename)

            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)

            # 保存CSV
            df.to_csv(csv_path, index=False)

            self.logger.info(
                f"已保存数据到CSV文件: {csv_path}, 文件大小: {os.path.getsize(csv_path)/1024:.2f} KB"
            )
            return csv_path

        except Exception as e:
            self.logger.error(f"保存CSV时出错: {e}", exc_info=True)
            raise

    def _create_scatter_plot(
        self,
        roi_name: str,
        pet1_values: np.ndarray,
        pet2_values: np.ndarray,
        output_dir: str,
    ) -> str:
        """
        创建散点图，并标注相关系数

        Args:
            roi_name: ROI名称
            pet1_values: PET1图像中的像素值
            pet2_values: PET2图像中的像素值
            output_dir: 输出目录

        Returns:
            str: 图像文件路径
        """
        try:
            # 清理ROI名称，避免文件名中的特殊字符
            safe_roi_name = "".join(c if c.isalnum() else "_" for c in roi_name)

            # 创建图像
            plt.figure(figsize=(10, 8))

            # 绘制散点图
            self.logger.info(f"创建散点图，数据点数量: {len(pet1_values)}")
            plt.scatter(pet1_values, pet2_values, alpha=0.5)

            # 确保pearson_r和spearman_r是有效的
            pearson_r = self.results.get("pearson_r")
            pearson_p = self.results.get("pearson_p")
            spearman_r = self.results.get("spearman_r")
            spearman_p = self.results.get("spearman_p")

            # 检查是否有效，如果无效则重新计算
            if (
                pearson_r is None
                or spearman_r is None
                or np.isnan(pearson_r)
                or np.isnan(spearman_r)
            ):
                self.logger.warning("散点图创建时发现相关系数无效，重新计算...")
                try:
                    pearson_r, pearson_p = pearsonr(pet1_values, pet2_values)
                    spearman_r, spearman_p = spearmanr(pet1_values, pet2_values)
                except Exception as e:
                    self.logger.error(f"重新计算相关系数时出错: {e}")
                    pearson_r = pearson_p = spearman_r = spearman_p = float("nan")

            # 添加回归线
            try:
                z = np.polyfit(pet1_values, pet2_values, 1)
                p = np.poly1d(z)
                x_range = np.linspace(min(pet1_values), max(pet1_values), 100)
                plt.plot(x_range, p(x_range), "r--", alpha=0.8)
                self.logger.info(f"成功添加回归线，斜率: {z[0]:.4f}, 截距: {z[1]:.4f}")
            except Exception as e:
                self.logger.warning(f"添加回归线时出错: {e}")

            # 格式化相关系数，处理NaN情况
            # 增加p值小数位数，确保超小的p值能正确显示
            pearson_r_str = f"{pearson_r:.4f}" if not np.isnan(pearson_r) else "无效"
            pearson_p_str = f"{pearson_p:.8f}" if not np.isnan(pearson_p) else "无效"
            spearman_r_str = f"{spearman_r:.4f}" if not np.isnan(spearman_r) else "无效"
            spearman_p_str = f"{spearman_p:.8f}" if not np.isnan(spearman_p) else "无效"

            # 如果p值太小（科学计数法表示），使用科学计数法格式化
            if pearson_p is not None and pearson_p < 0.00000001:
                pearson_p_str = f"{pearson_p:.3e}"
            if spearman_p is not None and spearman_p < 0.00000001:
                spearman_p_str = f"{spearman_p:.3e}"

            # 添加标签和标题 - 使用自定义选项
            if hasattr(self, 'custom_options') and self.custom_options:
                x_label = self.custom_options.get('x_label') or "PET1像素值"
                y_label = self.custom_options.get('y_label') or "PET2像素值"
                chart_title = self.custom_options.get('chart_title') or f'ROI "{roi_name}" 相关性分析'
            else:
                x_label = "PET1像素值"
                y_label = "PET2像素值"
                chart_title = f'ROI "{roi_name}" 相关性分析'

            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.title(
                f'{chart_title}\n'
                f"Pearson r = {pearson_r_str} (p = {pearson_p_str})\n"
                f"Spearman r = {spearman_r_str} (p = {spearman_p_str})\n"
                f"体素数量 = {len(pet1_values)}"
            )

            # 添加网格线
            plt.grid(True, alpha=0.3)

            # 保存图像 - 使用自定义前缀
            if hasattr(self, 'custom_options') and self.custom_options.get('output_prefix'):
                prefix = self.custom_options['output_prefix']
                safe_prefix = "".join(c if c.isalnum() else "_" for c in prefix)
                plot_filename = f"{safe_prefix}_correlation_plot.png"
            else:
                plot_filename = f"{safe_roi_name}_correlation_plot.png"
            plot_path = os.path.join(output_dir, plot_filename)

            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)

            # 设置更高质量的输出
            plt.savefig(plot_path, dpi=300, bbox_inches="tight")
            plt.close()

            self.logger.info(
                f"已保存散点图: {plot_path}, 文件大小: {os.path.getsize(plot_path)/1024:.2f} KB"
            )
            return plot_path

        except Exception as e:
            self.logger.error(f"创建散点图时出错: {e}", exc_info=True)
            raise

    def load_nifti_file(
        self, file_path: str, is_first: bool = True
    ) -> Tuple[bool, str]:
        """
        加载NIfTI文件

        Args:
            file_path: NIfTI文件路径
            is_first: 是否为第一个文件

        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        try:
            if not os.path.exists(file_path):
                return False, f"文件不存在: {file_path}"

            if not file_path.lower().endswith((".nii", ".nii.gz")):
                return False, f"不是有效的NIfTI文件: {file_path}"

            # 重置数据
            target_data = self.nifti1_data if is_first else self.nifti2_data
            target_data["image"] = None
            target_data["file_path"] = None
            target_data["loaded"] = False

            self.progress_updated.emit(10, f"加载NIfTI文件...")

            # 使用SimpleITK加载图像
            image = sitk.ReadImage(file_path)

            # 保存数据
            target_data["image"] = image
            target_data["file_path"] = file_path
            target_data["loaded"] = True

            label = "第一个" if is_first else "第二个"
            self.logger.info(f"成功加载{label}NIfTI图像: {file_path}")
            self.logger.info(f"图像尺寸: {image.GetSize()}, 间距: {image.GetSpacing()}")

            self.progress_updated.emit(100, f"成功加载{label}NIfTI文件")

            return True, f"成功加载{label}NIfTI文件"

        except Exception as e:
            msg = f"加载NIfTI文件时出错: {e}"
            self.logger.error(msg, exc_info=True)
            return False, msg

    def analyze_nifti_correlation(
        self,
        mask_option: str = "non_zero_first",
        threshold: float = 0.1,
        output_dir: str = None,
    ) -> Tuple[bool, str]:
        """
        分析两个NIfTI文件的相关性

        Args:
            mask_option: 掩码选项 ('non_zero_first', 'non_zero_both', 'positive_first', 'threshold_first')
            threshold: 阈值（仅在mask_option='threshold_first'时使用）
            output_dir: 输出目录

        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        if not self.nifti1_data["loaded"] or not self.nifti2_data["loaded"]:
            return False, "请先加载两个NIfTI文件"

        try:
            self.progress_updated.emit(0, "开始分析NIfTI相关性...")

            # 获取图像数据
            image1 = self.nifti1_data["image"]
            image2 = self.nifti2_data["image"]

            # 检查尺寸是否匹配，如果不匹配则重采样第二个图像到第一个图像的空间
            if image1.GetSize() != image2.GetSize():
                self.logger.warning(
                    f"两个图像尺寸不匹配: {image1.GetSize()} vs {image2.GetSize()}"
                )
                self.progress_updated.emit(15, "图像尺寸不匹配，正在重采样...")

                # 创建重采样器
                resampler = sitk.ResampleImageFilter()
                resampler.SetReferenceImage(image1)  # 以第一个图像为参考
                resampler.SetInterpolator(sitk.sitkLinear)
                resampler.SetDefaultPixelValue(0)

                # 重采样第二个图像
                image2 = resampler.Execute(image2)
                self.logger.info(f"已将第二个图像重采样到尺寸: {image2.GetSize()}")

                # 更新存储的图像
                self.nifti2_data["image"] = image2

            # 转换为numpy数组
            array1 = sitk.GetArrayFromImage(image1)
            array2 = sitk.GetArrayFromImage(image2)

            self.logger.info(f"图像1数值范围: [{np.min(array1)}, {np.max(array1)}]")
            self.logger.info(f"图像2数值范围: [{np.min(array2)}, {np.max(array2)}]")

            # 生成掩码
            self.progress_updated.emit(
                20, f"生成掩码: {self.MASK_OPTIONS[mask_option]}..."
            )
            mask = self._generate_nifti_mask(array1, array2, mask_option, threshold)

            if np.sum(mask) == 0:
                return False, f"掩码为空，无法分析相关性"

            mask_count = np.sum(mask)
            self.logger.info(f"掩码包含 {mask_count} 个像素")

            # 提取像素值
            self.progress_updated.emit(40, "提取像素值...")
            values1 = array1[mask]
            values2 = array2[mask]

            # 移除无效值
            valid_mask = ~(
                np.isnan(values1)
                | np.isinf(values1)
                | np.isnan(values2)
                | np.isinf(values2)
            )
            values1 = values1[valid_mask]
            values2 = values2[valid_mask]

            if len(values1) < 5:
                return False, f"有效像素数量太少 ({len(values1)})，无法计算可靠的相关性"

            # 计算相关系数
            self.progress_updated.emit(60, "计算相关系数...")
            pearson_r, pearson_p = pearsonr(values1, values2)
            spearman_r, spearman_p = spearmanr(values1, values2)

            # 保存结果
            self.results = {
                "roi_name": None,
                "voxel_count": len(values1),
                "pet1_values": values1,
                "pet2_values": values2,
                "pearson_r": pearson_r,
                "pearson_p": pearson_p,
                "spearman_r": spearman_r,
                "spearman_p": spearman_p,
                "analysis_type": "nifti_mask",
                "mask_option": mask_option,
                "nifti1_file": os.path.basename(self.nifti1_data["file_path"]),
                "nifti2_file": os.path.basename(self.nifti2_data["file_path"]),
            }

            self.logger.info(f"Pearson相关系数: r={pearson_r:.4f}, p={pearson_p:.4f}")
            self.logger.info(
                f"Spearman相关系数: r={spearman_r:.4f}, p={spearman_p:.4f}"
            )

            # 保存数据到CSV
            if output_dir:
                self.output_dir = output_dir
                os.makedirs(output_dir, exist_ok=True)

                self.progress_updated.emit(80, "保存数据到CSV...")
                mask_label = self.MASK_OPTIONS[mask_option]
                csv_path = self._save_nifti_csv(
                    values1, values2, mask_label, output_dir
                )

                # 生成散点图
                self.progress_updated.emit(90, "生成散点图...")
                plot_path = self._create_nifti_scatter_plot(
                    values1, values2, mask_label, output_dir
                )

                message = (
                    f"成功分析NIfTI相关性:\n"
                    f"- Pearson r: {pearson_r:.4f} (p={pearson_p:.3e})\n"
                    f"- Spearman r: {spearman_r:.4f} (p={spearman_p:.3e})\n"
                    f"- 有效像素数量: {len(values1)}\n"
                    f"- 掩码类型: {mask_label}\n"
                    f"- 已保存CSV到: {csv_path}\n"
                    f"- 已保存散点图到: {plot_path}"
                )
            else:
                mask_label = self.MASK_OPTIONS[mask_option]
                message = (
                    f"成功分析NIfTI相关性:\n"
                    f"- Pearson r: {pearson_r:.4f} (p={pearson_p:.3e})\n"
                    f"- Spearman r: {spearman_r:.4f} (p={spearman_p:.3e})\n"
                    f"- 有效像素数量: {len(values1)}\n"
                    f"- 掩码类型: {mask_label}"
                )

            self.progress_updated.emit(100, "分析完成")
            self.process_finished.emit(True, message)

            return True, message

        except Exception as e:
            msg = f"分析NIfTI相关性时出错: {e}"
            self.logger.error(msg, exc_info=True)
            return False, msg

    def _generate_nifti_mask(
        self,
        array1: np.ndarray,
        array2: np.ndarray,
        mask_option: str,
        threshold: float = 0.1,
    ) -> np.ndarray:
        """
        生成NIfTI掩码

        Args:
            array1: 第一个图像数组
            array2: 第二个图像数组
            mask_option: 掩码选项
            threshold: 阈值

        Returns:
            np.ndarray: 布尔掩码
        """
        if mask_option == "non_zero_first":
            # 第一个图像的所有非零像素
            mask = array1 != 0
        elif mask_option == "non_zero_both":
            # 两个图像都非零的像素
            mask = (array1 != 0) & (array2 != 0)
        elif mask_option == "positive_first":
            # 第一个图像的所有正值像素
            mask = array1 > 0
        elif mask_option == "threshold_first":
            # 第一个图像超过阈值的像素
            mask = array1 > threshold
        else:
            raise ValueError(f"未知的掩码选项: {mask_option}")

        self.logger.info(f"掩码选项: {mask_option}, 掩码像素数: {np.sum(mask)}")
        return mask

    def _save_nifti_csv(
        self, values1: np.ndarray, values2: np.ndarray, mask_label: str, output_dir: str
    ) -> str:
        """
        保存NIfTI相关性数据到CSV

        Args:
            values1: 第一个图像的像素值
            values2: 第二个图像的像素值
            mask_label: 掩码标签
            output_dir: 输出目录

        Returns:
            str: CSV文件路径
        """
        try:
            from datetime import datetime

            # 创建文件名
            if hasattr(self, 'custom_options') and self.custom_options.get('output_prefix'):
                # 使用自定义前缀
                prefix = self.custom_options['output_prefix']
                safe_prefix = "".join(c if c.isalnum() else "_" for c in prefix)
                safe_mask = "".join(c if c.isalnum() else "_" for c in mask_label)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_filename = f"{safe_prefix}_{safe_mask}_{timestamp}.csv"
            else:
                # 使用默认命名
                file1_name = os.path.splitext(
                    os.path.basename(self.nifti1_data["file_path"])
                )[0]
                file2_name = os.path.splitext(
                    os.path.basename(self.nifti2_data["file_path"])
                )[0]

                # 清理文件名
                safe_file1 = "".join(c if c.isalnum() else "_" for c in file1_name)
                safe_file2 = "".join(c if c.isalnum() else "_" for c in file2_name)
                safe_mask = "".join(c if c.isalnum() else "_" for c in mask_label)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                csv_filename = f"nifti_correlation_{safe_file1}_vs_{safe_file2}_{safe_mask}_{timestamp}.csv"
            csv_path = os.path.join(output_dir, csv_filename)

            # 创建DataFrame
            df = pd.DataFrame({"Image1": values1, "Image2": values2})

            # 添加元数据作为注释
            with open(csv_path, "w") as f:
                f.write(f"# NIfTI图像相关性分析结果\n")
                f.write(f"# 图像1: {self.nifti1_data['file_path']}\n")
                f.write(f"# 图像2: {self.nifti2_data['file_path']}\n")
                f.write(f"# 掩码类型: {mask_label}\n")
                f.write(f"# 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# Pearson r: {self.results['pearson_r']:.6f}\n")
                f.write(f"# Pearson p: {self.results['pearson_p']:.6e}\n")
                f.write(f"# Spearman r: {self.results['spearman_r']:.6f}\n")
                f.write(f"# Spearman p: {self.results['spearman_p']:.6e}\n")
                f.write(f"# 有效像素数量: {len(values1)}\n")
                f.write(f"#\n")

            # 追加数据
            df.to_csv(csv_path, mode="a", index=False)

            self.logger.info(f"已保存NIfTI相关性数据到CSV: {csv_path}")
            return csv_path

        except Exception as e:
            self.logger.error(f"保存NIfTI CSV时出错: {e}", exc_info=True)
            raise

    def _create_nifti_scatter_plot(
        self, values1: np.ndarray, values2: np.ndarray, mask_label: str, output_dir: str
    ) -> str:
        """
        创建NIfTI相关性散点图

        Args:
            values1: 第一个图像的像素值
            values2: 第二个图像的像素值
            mask_label: 掩码标签
            output_dir: 输出目录

        Returns:
            str: 图像文件路径
        """
        try:
            from datetime import datetime

            # 创建文件名
            file1_name = os.path.splitext(
                os.path.basename(self.nifti1_data["file_path"])
            )[0]
            file2_name = os.path.splitext(
                os.path.basename(self.nifti2_data["file_path"])
            )[0]

            if hasattr(self, 'custom_options') and self.custom_options.get('output_prefix'):
                # 使用自定义前缀
                prefix = self.custom_options['output_prefix']
                safe_prefix = "".join(c if c.isalnum() else "_" for c in prefix)
                safe_mask = "".join(c if c.isalnum() else "_" for c in mask_label)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                plot_filename = f"{safe_prefix}_{safe_mask}_{timestamp}.png"
            else:
                # 使用默认命名
                safe_file1 = "".join(c if c.isalnum() else "_" for c in file1_name)
                safe_file2 = "".join(c if c.isalnum() else "_" for c in file2_name)
                safe_mask = "".join(c if c.isalnum() else "_" for c in mask_label)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                plot_filename = f"nifti_correlation_{safe_file1}_vs_{safe_file2}_{safe_mask}_{timestamp}.png"
            plot_path = os.path.join(output_dir, plot_filename)

            # 创建图像
            plt.figure(figsize=(10, 8))

            # 绘制散点图
            plt.scatter(values1, values2, alpha=0.5, s=2)

            # 添加回归线
            try:
                from scipy.stats import linregress

                slope, intercept, r_value, p_value, std_err = linregress(
                    values1, values2
                )
                line_x = np.array([np.min(values1), np.max(values1)])
                line_y = slope * line_x + intercept
                plt.plot(
                    line_x,
                    line_y,
                    "r-",
                    alpha=0.8,
                    linewidth=2,
                    label=safe_format_r_squared(r_value),
                )
                plt.legend()
            except Exception as e:
                self.logger.warning(f"无法添加回归线: {e}")

            # 格式化相关系数显示
            pearson_r = self.results["pearson_r"]
            pearson_p = self.results["pearson_p"]
            spearman_r = self.results["spearman_r"]
            spearman_p = self.results["spearman_p"]

            pearson_r_str = f"{pearson_r:.4f}" if not np.isnan(pearson_r) else "NaN"
            spearman_r_str = f"{spearman_r:.4f}" if not np.isnan(spearman_r) else "NaN"
            pearson_p_str = f"{pearson_p:.3e}" if not np.isnan(pearson_p) else "NaN"
            spearman_p_str = f"{spearman_p:.3e}" if not np.isnan(spearman_p) else "NaN"

            # 添加标签和标题 - 使用自定义选项
            if hasattr(self, 'custom_options') and self.custom_options:
                x_label = self.custom_options.get('x_label') or f"{file1_name} 像素值"
                y_label = self.custom_options.get('y_label') or f"{file2_name} 像素值"
                chart_title = self.custom_options.get('chart_title') or f"NIfTI图像相关性分析"
            else:
                x_label = f"{file1_name} 像素值"
                y_label = f"{file2_name} 像素值"
                chart_title = f"NIfTI图像相关性分析"

            plt.xlabel(x_label)
            plt.ylabel(y_label)
            plt.title(
                f"{chart_title}\n"
                f"掩码: {mask_label}\n"
                f"Pearson r = {pearson_r_str} (p = {pearson_p_str})\n"
                f"Spearman r = {spearman_r_str} (p = {spearman_p_str})\n"
                f"像素数量 = {len(values1)}"
            )

            # 添加网格线
            plt.grid(True, alpha=0.3)

            # 保存图像
            plt.savefig(plot_path, dpi=300, bbox_inches="tight")
            plt.close()

            self.logger.info(f"已保存NIfTI散点图: {plot_path}")
            return plot_path

        except Exception as e:
            self.logger.error(f"创建NIfTI散点图时出错: {e}", exc_info=True)
            raise

    def get_current_results(self) -> Dict:
        """
        获取当前分析结果

        Returns:
            Dict: 包含分析结果的字典
        """
        return self.results.copy()
