#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import SimpleITK as sitk
import pydicom
from typing import Tuple, List, Dict, Optional, Union
from PyQt5.QtCore import QObject, pyqtSignal
from scipy.stats import pearsonr, spearmanr

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
            'image': None,          # 第一个PET图像
            'image_files': [],      # 图像文件路径列表
            'image_info': {},       # 图像元信息
            'loaded': False         # 是否已加载
        }
        
        self.pet2_data = {
            'image': None,          # 第二个PET图像
            'image_files': [],      # 图像文件路径列表
            'image_info': {},       # 图像元信息
            'loaded': False         # 是否已加载
        }
        
        # RTSS数据
        self.rtss_data = {
            'rtss': None,           # 结构集
            'rtss_file': None,      # 结构集文件路径
            'loaded': False         # 是否已加载
        }
        
        # 分析结果
        self.results = {
            'roi_name': None,       # 分析的ROI名称
            'voxel_count': 0,       # ROI内体素数量
            'pet1_values': None,    # PET1中ROI内的像素值
            'pet2_values': None,    # PET2中ROI内的像素值
            'pearson_r': None,      # Pearson相关系数
            'pearson_p': None,      # Pearson p值
            'spearman_r': None,     # Spearman相关系数
            'spearman_p': None,     # Spearman p值
        }
        
        # 输出目录
        self.output_dir = None
    
    def load_pet_directory(self, directory: str, is_pet1: bool = True) -> Tuple[bool, str, Dict]:
        """
        加载目录中的PET DICOM图像
        
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
            data_dict['image'] = None
            data_dict['image_files'] = []
            data_dict['image_info'] = {}
            data_dict['loaded'] = False
            
            # 递归查找目录中的所有文件（添加递归选项，确保检查子目录）
            dicom_candidates = []
            
            # 首先尝试仅在当前目录中搜索
            current_dir_files = [os.path.join(directory, f) for f in os.listdir(directory) 
                                if os.path.isfile(os.path.join(directory, f))]
            self.logger.info(f"当前目录中找到 {len(current_dir_files)} 个文件")
            dicom_candidates.extend(current_dir_files)
            
            # 如果当前目录文件太少，尝试使用glob进行通配符搜索
            if len(current_dir_files) < 5:  # 假设至少需要5个文件才构成有效序列
                self.logger.info("当前目录文件过少，尝试使用通配符搜索")
                for ext in ['.dcm', '.DCM', '*']:
                    pattern = os.path.join(directory, f"**/*{ext}")
                    found_files = glob.glob(pattern, recursive=True)
                    self.logger.info(f"使用pattern '{pattern}' 找到 {len(found_files)} 个文件")
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
            self.progress_updated.emit(10, f"找到 {total_files} 个文件，正在识别DICOM文件")
            
            # 对找到的文件进行分类
            image_files = []
            rtss_file = None
            
            # 读取每个文件查看其SOPClassUID和Modality
            valid_files = 0
            invalid_files = 0
            
            for i, file_path in enumerate(dicom_candidates):
                try:
                    # 更新进度
                    if i % max(1, total_files // 20) == 0:  # 最多更新20次进度
                        progress = 10 + int(40 * i / total_files)
                        self.progress_updated.emit(progress, f"分析DICOM文件 {i+1}/{total_files}...")
                    
                    # 尝试读取DICOM文件，设置更宽松的选项
                    try:
                        dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                        valid_files += 1
                    except Exception as read_error:
                        self.logger.debug(f"无法读取文件 {file_path}: {read_error}")
                        invalid_files += 1
                        continue
                    
                    # 检查是否为RTSS - 宽松判断，使用多种可能的条件
                    is_rtss = False
                    if hasattr(dcm, 'SOPClassUID') and dcm.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3':
                        is_rtss = True
                    elif hasattr(dcm, 'Modality') and dcm.Modality == 'RTSTRUCT':
                        is_rtss = True
                    elif hasattr(dcm, 'Manufacturer') and 'STRUCTURE' in str(getattr(dcm, 'Manufacturer', '')).upper():
                        is_rtss = True
                        
                    if is_rtss and rtss_file is None:  # 只使用找到的第一个RTSS
                        rtss_file = file_path
                        self.logger.info(f"找到RTSS文件: {file_path}")
                        continue
                    
                    # 检查是否为PET图像 - 宽松判断
                    is_pet = False
                    if hasattr(dcm, 'Modality') and dcm.Modality == 'PT':
                        is_pet = True
                    elif hasattr(dcm, 'SeriesDescription') and 'PET' in str(getattr(dcm, 'SeriesDescription', '')).upper():
                        is_pet = True
                    
                    if is_pet:
                        image_files.append(file_path)
                        
                except Exception as e:
                    self.logger.debug(f"处理文件 {file_path} 时出错: {e}")
                    invalid_files += 1
                    continue
            
            # 更新数据字典
            data_dict['image_files'] = image_files
            
            # 如果找到了RTSS文件，保存到rtss_data中
            if rtss_file and not self.rtss_data['loaded']:
                self.rtss_data['rtss_file'] = rtss_file
                try:
                    self.rtss_data['rtss'] = pydicom.dcmread(rtss_file)
                    self.rtss_data['loaded'] = True
                    contour_count = self._count_rtss_contours(self.rtss_data['rtss'])
                    self.logger.info(f"成功加载RTSS，包含 {contour_count} 个轮廓")
                except Exception as e:
                    self.logger.warning(f"加载RTSS时出错: {e}")
            
            # 记录有效的DICOM图像文件数
            dicom_image_count = len(image_files)
            self.logger.info(f"统计：总文件数 {total_files}, 有效DICOM文件 {valid_files}, 无效文件 {invalid_files}")
            self.logger.info(f"识别出 {dicom_image_count} 个有效的PET图像文件" + (f", 1个RTSS文件" if rtss_file else ""))
            
            if dicom_image_count == 0:
                msg = f"在目录 {directory} 中未找到有效的PET图像文件"
                self.logger.warning(msg)
                return False, msg, data_dict
            
            # 加载图像文件
            self.progress_updated.emit(50, f"加载{pet_label}图像序列，共{dicom_image_count}个文件...")
            try:
                # 按文件名排序，确保图像序列正确
                image_files.sort()
                
                # 使用SimpleITK读取图像序列
                reader = sitk.ImageSeriesReader()
                reader.SetFileNames(image_files)
                
                self.logger.info(f"正在执行SimpleITK读取，文件数量：{len(image_files)}")
                image = reader.Execute()
                data_dict['image'] = image
                
                # 提取图像信息
                data_dict['image_info'] = {
                    'size': image.GetSize(),
                    'spacing': image.GetSpacing(),
                    'origin': image.GetOrigin(),
                    'direction': image.GetDirection(),
                    'file_count': dicom_image_count,
                    'modality': self._get_image_modality(image_files[0])
                }
                
                self.logger.info(f"成功加载{pet_label}图像, 尺寸={image.GetSize()}, 间距={image.GetSpacing()}")
                data_dict['loaded'] = True
            except Exception as e:
                msg = f"加载{pet_label}图像序列时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg, data_dict
            
            # 更新加载状态
            if data_dict['image'] is not None:
                self.progress_updated.emit(100, f"成功加载{pet_label}图像")
                
                # 发送图像加载完成信号
                data_to_emit = data_dict.copy()
                data_to_emit['is_pet1'] = is_pet1  # 添加is_pet1标志
                self.image_loaded.emit(data_to_emit)
                
                return True, f"成功加载{pet_label}图像，尺寸={image.GetSize()}", data_dict
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
            self.rtss_data['rtss_file'] = rtss_file
            self.rtss_data['rtss'] = pydicom.dcmread(rtss_file)
            self.rtss_data['loaded'] = True
            
            contour_count = self._count_rtss_contours(self.rtss_data['rtss'])
            self.logger.info(f"成功加载RTSS，包含 {contour_count} 个轮廓")
            self.progress_updated.emit(100, f"成功加载RTSS, 包含 {contour_count} 个轮廓")
            
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
        if not self.rtss_data['loaded']:
            return []
        
        roi_names = []
        try:
            rtss = self.rtss_data['rtss']
            # 获取ROI名称
            for roi in rtss.StructureSetROISequence:
                roi_names.append(roi.ROIName)
        except Exception as e:
            self.logger.error(f"获取ROI名称时出错: {e}", exc_info=True)
        
        return roi_names
    
    def analyze_correlation(self, roi_name: str, output_dir: str) -> Tuple[bool, str]:
        """
        分析指定ROI区域内两个PET图像的相关性
        
        Args:
            roi_name: ROI名称
            output_dir: 输出目录
            
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        if not self.pet1_data['loaded'] or not self.pet2_data['loaded']:
            return False, "请先加载两个PET图像"
        
        if not self.rtss_data['loaded']:
            return False, "请先加载RTSS文件"
        
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            self.progress_updated.emit(0, f"开始分析ROI '{roi_name}'的相关性...")
            self.results['roi_name'] = roi_name
            
            # 检查两个PET图像的尺寸是否一致
            pet1_size = self.pet1_data['image'].GetSize()
            pet2_size = self.pet2_data['image'].GetSize()
            
            if pet1_size != pet2_size:
                msg = f"两个PET图像尺寸不一致: PET1={pet1_size}, PET2={pet2_size}"
                self.logger.error(msg)
                return False, msg
            
            self.logger.info(f"两个PET图像尺寸一致: {pet1_size}，开始生成ROI掩码")
            
            # 1. 获取ROI轮廓的掩码
            self.progress_updated.emit(10, "生成ROI掩码...")
            mask = self._get_roi_mask(roi_name)
            if mask is None:
                return False, f"未能找到名为 '{roi_name}' 的ROI或生成掩码失败"
            
            # 检查掩码是否为空
            if np.sum(mask) == 0:
                return False, f"ROI '{roi_name}' 生成的掩码为空，无法分析"
                
            mask_count = np.sum(mask)
            mask_shape = mask.shape
            self.logger.info(f"成功生成掩码，掩码内点数: {mask_count}, 掩码形状: {mask_shape}")
            
            # 2. 提取两个PET图像上ROI内的像素值
            self.progress_updated.emit(30, "提取ROI内的PET1像素值...")
            try:
                pet1_array = sitk.GetArrayFromImage(self.pet1_data['image'])
                self.logger.info(f"PET1像素值范围: [{np.min(pet1_array)}, {np.max(pet1_array)}]，形状: {pet1_array.shape}")
                pet1_values = pet1_array[mask]
                self.logger.info(f"提取出 {len(pet1_values)} 个PET1像素值，范围: [{np.min(pet1_values)}, {np.max(pet1_values)}]")
            except Exception as e:
                msg = f"提取PET1像素值时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg
            
            self.progress_updated.emit(50, "提取ROI内的PET2像素值...")
            try:
                pet2_array = sitk.GetArrayFromImage(self.pet2_data['image'])
                self.logger.info(f"PET2像素值范围: [{np.min(pet2_array)}, {np.max(pet2_array)}]，形状: {pet2_array.shape}")
                pet2_values = pet2_array[mask]
                self.logger.info(f"提取出 {len(pet2_values)} 个PET2像素值，范围: [{np.min(pet2_values)}, {np.max(pet2_values)}]")
            except Exception as e:
                msg = f"提取PET2像素值时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg
            
            # 确保值的长度匹配
            if len(pet1_values) != len(pet2_values):
                msg = f"PET1和PET2中ROI内的像素数量不匹配: PET1={len(pet1_values)}, PET2={len(pet2_values)}"
                self.logger.error(msg)
                return False, msg
            
            # 将提取的值保存到结果中
            self.results['voxel_count'] = len(pet1_values)
            self.results['pet1_values'] = pet1_values
            self.results['pet2_values'] = pet2_values
            
            # 3. 检查数据是否有效
            # 检查是否存在无效值(NaN/Inf)
            invalid_pet1 = np.isnan(pet1_values).any() or np.isinf(pet1_values).any()
            invalid_pet2 = np.isnan(pet2_values).any() or np.isinf(pet2_values).any()
            
            if invalid_pet1 or invalid_pet2:
                self.logger.warning(f"数据中存在无效值: PET1_NaN={np.isnan(pet1_values).sum()}, PET1_Inf={np.isinf(pet1_values).sum()}, "
                                  f"PET2_NaN={np.isnan(pet2_values).sum()}, PET2_Inf={np.isinf(pet2_values).sum()}")
                                  
                # 移除无效值
                valid_mask = ~(np.isnan(pet1_values) | np.isinf(pet1_values) | np.isnan(pet2_values) | np.isinf(pet2_values))
                pet1_values = pet1_values[valid_mask]
                pet2_values = pet2_values[valid_mask]
                self.logger.info(f"移除无效值后剩余 {len(pet1_values)} 个有效数据点")
                
                # 更新结果中的值
                self.results['voxel_count'] = len(pet1_values)
                self.results['pet1_values'] = pet1_values
                self.results['pet2_values'] = pet2_values
            
            # 4. 计算相关系数
            self.progress_updated.emit(70, "计算相关系数...")
            if len(pet1_values) > 5:  # 需要足够多的点才能计算可靠的相关性
                try:
                    # Pearson相关系数
                    pearson_r, pearson_p = pearsonr(pet1_values, pet2_values)
                    self.results['pearson_r'] = pearson_r
                    self.results['pearson_p'] = pearson_p
                    
                    # Spearman相关系数
                    spearman_r, spearman_p = spearmanr(pet1_values, pet2_values)
                    self.results['spearman_r'] = spearman_r
                    self.results['spearman_p'] = spearman_p
                    
                    self.logger.info(f"Pearson相关系数: r={pearson_r:.4f}, p={pearson_p:.4f}")
                    self.logger.info(f"Spearman相关系数: r={spearman_r:.4f}, p={spearman_p:.4f}")
                    
                    # 如果r为NaN，尝试计算数据统计信息以帮助诊断
                    if np.isnan(pearson_r) or np.isnan(spearman_r):
                        self.logger.warning("相关系数计算结果为NaN，检查数据分布...")
                        pet1_std = np.std(pet1_values)
                        pet2_std = np.std(pet2_values)
                        self.logger.warning(f"数据统计: PET1标准差={pet1_std}, PET2标准差={pet2_std}")
                        
                        # 如果标准差为0，说明数据没有变化
                        if pet1_std == 0 or pet2_std == 0:
                            self.logger.error("数据没有变化，无法计算相关性")
                            return False, "图像数据没有变化，无法计算相关性"
                except Exception as e:
                    msg = f"计算相关系数时出错: {e}"
                    self.logger.error(msg, exc_info=True)
                    return False, msg
            else:
                self.logger.warning(f"ROI中的体素数量太少 ({len(pet1_values)}), 无法计算可靠的相关性")
                return False, f"ROI '{roi_name}' 中的体素数量太少({len(pet1_values)}), 需要至少5个点才能计算可靠的相关性"
            
            # 5. 保存数据到CSV
            self.progress_updated.emit(80, "保存数据到CSV...")
            try:
                csv_path = self._save_to_csv(roi_name, pet1_values, pet2_values, output_dir)
                self.logger.info(f"成功保存数据到CSV: {csv_path}")
            except Exception as e:
                msg = f"保存CSV时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg
            
            # 6. 绘制散点图
            self.progress_updated.emit(90, "生成散点图...")
            try:
                plot_path = self._create_scatter_plot(roi_name, pet1_values, pet2_values, output_dir)
                self.logger.info(f"成功生成散点图: {plot_path}")
            except Exception as e:
                msg = f"生成散点图时出错: {e}"
                self.logger.error(msg, exc_info=True)
                return False, msg
            
            self.progress_updated.emit(100, "分析完成")
            
            message = (f"成功分析ROI '{roi_name}'的相关性:\n"
                      f"- Pearson r: {pearson_r:.4f} (p={pearson_p:.4f})\n"
                      f"- Spearman r: {spearman_r:.4f} (p={spearman_p:.4f})\n"
                      f"- 体素数量: {len(pet1_values)}\n"
                      f"- 已保存CSV到: {csv_path}\n"
                      f"- 已保存散点图到: {plot_path}")
            
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
            return dcm.Modality if hasattr(dcm, 'Modality') else 'Unknown'
        except:
            return 'Unknown'
    
    def _count_rtss_contours(self, rtss_data) -> int:
        """计算RTSS中的轮廓数量"""
        try:
            return len(rtss_data.StructureSetROISequence)
        except:
            return 0
    
    def _get_roi_mask(self, roi_name: str) -> Optional[np.ndarray]:
        """
        生成指定ROI的二值掩码
        
        Args:
            roi_name: ROI名称
            
        Returns:
            Optional[np.ndarray]: 如果成功，返回二值掩码；否则返回None
        """
        try:
            rtss = self.rtss_data['rtss']
            pet1_image = self.pet1_data['image']
            
            # 输出更多调试信息
            self.logger.info(f"生成ROI '{roi_name}' 的掩码，图像尺寸: {pet1_image.GetSize()}")
            
            # 查找ROI ID
            roi_id = None
            available_rois = []
            for roi in rtss.StructureSetROISequence:
                available_rois.append(roi.ROIName)
                if roi.ROIName == roi_name:
                    roi_id = roi.ROINumber
                    break
                    
            if roi_id is None:
                self.logger.warning(f"未找到名为 '{roi_name}' 的ROI，可用ROI: {', '.join(available_rois)}")
                return None
            
            # 查找对应的轮廓数据
            contour_data = None
            for roi_contour in rtss.ROIContourSequence:
                if roi_contour.ReferencedROINumber == roi_id:
                    contour_data = roi_contour
                    break
            
            if contour_data is None:
                self.logger.warning(f"未找到ROI '{roi_name}' 的轮廓数据")
                return None
                
            if not hasattr(contour_data, 'ContourSequence'):
                self.logger.warning(f"ROI '{roi_name}' 没有ContourSequence属性")
                return None
                
            contour_count = len(contour_data.ContourSequence)
            self.logger.info(f"找到 {contour_count} 个轮廓点集")
            
            # 创建一个与PET图像相同尺寸的空掩码
            pet1_size = pet1_image.GetSize()
            mask_array = np.zeros(shape=(pet1_size[2], pet1_size[1], pet1_size[0]), dtype=np.bool_)
            
            # 用来将DICOM患者坐标转换为图像索引
            pet1_direction = pet1_image.GetDirection()
            pet1_origin = pet1_image.GetOrigin()
            pet1_spacing = pet1_image.GetSpacing()
            
            # 记录一些统计信息用于调试
            total_contours = len(contour_data.ContourSequence)
            filled_slices = set()
            total_points = 0
            
            # 处理每个轮廓
            for contour_idx, contour in enumerate(contour_data.ContourSequence):
                if not hasattr(contour, 'ContourData'):
                    self.logger.warning(f"轮廓 #{contour_idx} 没有ContourData属性")
                    continue
                    
                if len(contour.ContourData) < 6:  # 至少需要两个点 (x,y,z) 的坐标
                    self.logger.warning(f"轮廓 #{contour_idx} 点数不足: {len(contour.ContourData)}")
                    continue
                
                contour_data_array = np.array(contour.ContourData).reshape(-1, 3)
                point_count = contour_data_array.shape[0]
                total_points += point_count
                
                self.logger.debug(f"处理轮廓 #{contour_idx+1}/{total_contours}，包含 {point_count} 个点")
                
                # 将轮廓点转换为图像索引
                indices = []
                for point in contour_data_array:
                    # 计算图像索引 (四舍五入到最近的整数)
                    idx = [
                        int(round((point[0] - pet1_origin[0]) / pet1_spacing[0])),
                        int(round((point[1] - pet1_origin[1]) / pet1_spacing[1])),
                        int(round((point[2] - pet1_origin[2]) / pet1_spacing[2]))
                    ]
                    indices.append(idx)
                
                # 填充轮廓内部的点
                # 注意：这是一个简化的方法，不保证完全精确
                # 对于每个z平面上的轮廓，使用多边形填充算法
                if len(indices) > 2:  # 确保至少有3个点构成一个轮廓
                    # 提取z平面索引
                    z_idx = indices[0][2]
                    filled_slices.add(z_idx)
                    
                    if 0 <= z_idx < pet1_size[2]:  # 确保在图像范围内
                        # 提取当前平面上的x,y坐标
                        polygon = np.array([[idx[0], idx[1]] for idx in indices])
                        # 确定边界框
                        min_x, min_y = np.min(polygon, axis=0)
                        max_x, max_y = np.max(polygon, axis=0)
                        
                        # 遍历边界框中的每个像素
                        for x in range(max(0, min_x), min(pet1_size[0], max_x + 1)):
                            for y in range(max(0, min_y), min(pet1_size[1], max_y + 1)):
                                # 如果点在轮廓内，设置掩码为1
                                if self._point_in_polygon(x, y, polygon):
                                    mask_array[z_idx, y, x] = True
            
            # 输出掩码统计信息
            mask_points = np.sum(mask_array)
            self.logger.info(f"掩码生成统计: 总轮廓数={total_contours}, 填充切片数={len(filled_slices)}, "
                           f"总轮廓点数={total_points}, 掩码内点数={mask_points}")
            
            if mask_points == 0:
                self.logger.warning("生成的掩码为空，未填充任何像素")
                return None
                
            return mask_array
                    
        except Exception as e:
            self.logger.error(f"生成ROI掩码时出错: {e}", exc_info=True)
            return None
    
    def _point_in_polygon(self, x: int, y: int, polygon: np.ndarray) -> bool:
        """
        判断点是否在多边形内部（射线法）
        
        Args:
            x, y: 点坐标
            polygon: 多边形顶点坐标数组，形状为(n,2)
            
        Returns:
            bool: 如果点在多边形内部，返回True；否则返回False
        """
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            x_intersect = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= x_intersect:
                            inside = not inside
            p1x, p1y = p2x, p2y
            
        return inside
    
    def _save_to_csv(self, roi_name: str, pet1_values: np.ndarray, pet2_values: np.ndarray, output_dir: str) -> str:
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
            safe_roi_name = ''.join(c if c.isalnum() else '_' for c in roi_name)
            
            # 创建DataFrame
            self.logger.info(f"创建CSV数据表，数据点数量: {len(pet1_values)}")
            df = pd.DataFrame({
                'PET1': pet1_values,
                'PET2': pet2_values
            })
            
            # 计算一些基本统计信息，记录到日志中
            stats = df.describe()
            self.logger.info(f"数据统计信息:\n{stats}")
            
            # 保存到CSV
            csv_filename = f"{safe_roi_name}_correlation.csv"
            csv_path = os.path.join(output_dir, csv_filename)
            
            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 保存CSV
            df.to_csv(csv_path, index=False)
            
            self.logger.info(f"已保存数据到CSV文件: {csv_path}, 文件大小: {os.path.getsize(csv_path)/1024:.2f} KB")
            return csv_path
            
        except Exception as e:
            self.logger.error(f"保存CSV时出错: {e}", exc_info=True)
            raise
    
    def _create_scatter_plot(self, roi_name: str, pet1_values: np.ndarray, pet2_values: np.ndarray, output_dir: str) -> str:
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
            safe_roi_name = ''.join(c if c.isalnum() else '_' for c in roi_name)
            
            # 创建图像
            plt.figure(figsize=(10, 8))
            
            # 绘制散点图
            self.logger.info(f"创建散点图，数据点数量: {len(pet1_values)}")
            plt.scatter(pet1_values, pet2_values, alpha=0.5)
            
            # 确保pearson_r和spearman_r是有效的
            pearson_r = self.results.get('pearson_r')
            pearson_p = self.results.get('pearson_p')
            spearman_r = self.results.get('spearman_r')
            spearman_p = self.results.get('spearman_p')
            
            # 检查是否有效，如果无效则重新计算
            if pearson_r is None or spearman_r is None or np.isnan(pearson_r) or np.isnan(spearman_r):
                self.logger.warning("散点图创建时发现相关系数无效，重新计算...")
                try:
                    pearson_r, pearson_p = pearsonr(pet1_values, pet2_values)
                    spearman_r, spearman_p = spearmanr(pet1_values, pet2_values)
                except Exception as e:
                    self.logger.error(f"重新计算相关系数时出错: {e}")
                    pearson_r = pearson_p = spearman_r = spearman_p = float('nan')
            
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
            pearson_r_str = f"{pearson_r:.4f}" if not np.isnan(pearson_r) else "无效"
            pearson_p_str = f"{pearson_p:.4f}" if not np.isnan(pearson_p) else "无效"
            spearman_r_str = f"{spearman_r:.4f}" if not np.isnan(spearman_r) else "无效"
            spearman_p_str = f"{spearman_p:.4f}" if not np.isnan(spearman_p) else "无效"
            
            # 添加标签和标题
            plt.xlabel('PET1像素值')
            plt.ylabel('PET2像素值')
            plt.title(f'ROI "{roi_name}" 相关性分析\n'
                    f'Pearson r = {pearson_r_str} (p = {pearson_p_str})\n'
                    f'Spearman r = {spearman_r_str} (p = {spearman_p_str})\n'
                    f'体素数量 = {len(pet1_values)}')
            
            # 添加网格线
            plt.grid(True, alpha=0.3)
            
            # 保存图像
            plot_filename = f"{safe_roi_name}_correlation_plot.png"
            plot_path = os.path.join(output_dir, plot_filename)
            
            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)
            
            # 设置更高质量的输出
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.logger.info(f"已保存散点图: {plot_path}, 文件大小: {os.path.getsize(plot_path)/1024:.2f} KB")
            return plot_path
            
        except Exception as e:
            self.logger.error(f"创建散点图时出错: {e}", exc_info=True)
            raise 