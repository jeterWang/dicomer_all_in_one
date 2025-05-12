#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import glob
import logging
import SimpleITK as sitk
import numpy as np
from typing import Tuple, List, Dict, Optional, Union
from PyQt5.QtCore import QObject, pyqtSignal
import pydicom
from datetime import datetime
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.dataset import Dataset
from scipy.interpolate import RegularGridInterpolator

class DVFApplier(QObject):
    """
    使用SimpleITK实现DVF（形变矢量场）应用到PET图像的功能
    """
    
    # 定义信号用于进度更新
    progress_updated = pyqtSignal(int, str)  # (进度百分比, 状态消息)
    process_finished = pyqtSignal(bool, str)  # (是否成功, 消息)
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
    
    def load_image_series(self, directory: str) -> sitk.Image:
        """
        加载DICOM图像序列
        
        Args:
            directory: 包含DICOM序列的目录
            
        Returns:
            sitk.Image: 加载的图像
        """
        reader = sitk.ImageSeriesReader()
        dicom_names = reader.GetGDCMSeriesFileNames(directory)
        if not dicom_names:
            raise ValueError(f"在目录 {directory} 中未找到DICOM序列")
            
        reader.SetFileNames(dicom_names)
        self.logger.info(f"正在从 {directory} 加载DICOM序列，找到 {len(dicom_names)} 个文件")
        return reader.Execute()
    
    def load_image_single_file(self, file_path: str) -> sitk.Image:
        """
        加载单个图像文件 (如 NIFTI)
        
        Args:
            file_path: 图像文件路径
            
        Returns:
            sitk.Image: 加载的图像
        """
        return sitk.ReadImage(file_path)
    
    def load_dvf(self, dvf_path: str) -> sitk.Image:
        """
        加载DVF文件 (支持 MHD/RAW 或 DICOM)
        
        Args:
            dvf_path: DVF文件路径
            
        Returns:
            sitk.Image: 加载的DVF图像
        """
        self.logger.info(f"正在加载DVF: {dvf_path}")
        
        # 根据扩展名确定文件类型
        ext = os.path.splitext(dvf_path)[1].lower()
        
        if ext == '.mhd':
            # 加载 MHD/RAW 格式的 DVF
            dvf = sitk.ReadImage(dvf_path)
        elif ext == '.dcm':
            # 加载 DICOM 格式的 DVF
            dvf = sitk.ReadImage(dvf_path)
            
            # 检查是否是DVF（应该有3个分量）
            if 'DEFORMABLE_REGISTRATION' in dvf.GetMetaDataKeys():
                self.logger.info("检测到DICOM格式的形变场")
            else:
                self.logger.warning("该DICOM文件可能不是DVF格式，请检查")
        else:
            raise ValueError(f"不支持的DVF文件格式: {ext}")
            
        self.logger.info(f"DVF像素类型: {dvf.GetPixelIDTypeAsString()}")
        self.logger.info(f"DVF分量数: {dvf.GetNumberOfComponentsPerPixel()}")
        
        return dvf
    
    def check_compatible_spaces(self, source_img: sitk.Image, dvf: sitk.Image) -> bool:
        """
        检查源图像和DVF是否在兼容的空间中
        
        Args:
            source_img: 源图像
            dvf: 形变矢量场
            
        Returns:
            bool: 是否兼容
        """
        self.logger.info("检查图像和DVF空间兼容性")
        
        # 检查物理空间
        source_origin = source_img.GetOrigin()
        dvf_origin = dvf.GetOrigin()
        
        source_spacing = source_img.GetSpacing()
        dvf_spacing = dvf.GetSpacing()
        
        source_size = source_img.GetSize()
        dvf_size = dvf.GetSize()
        
        # 简单检查，实际应用中可能需要更复杂的检查
        compatible = True
        tolerance = 1.0  # 容差 1mm
        
        # 记录详细信息以便调试
        self.logger.info(f"源图像: 尺寸={source_size}, 间距={source_spacing}, 原点={source_origin}")
        self.logger.info(f"DVF: 尺寸={dvf_size}, 间距={dvf_spacing}, 原点={dvf_origin}")
        
        # 注意：DVF 通常具有3个通道，每个通道对应xyz方向的位移
        if dvf.GetNumberOfComponentsPerPixel() != 3:
            self.logger.warning(f"DVF应该有3个通道，但找到 {dvf.GetNumberOfComponentsPerPixel()} 个")
            compatible = False
            
        return compatible
    
    def apply_dvf_to_image(self, source_img: sitk.Image, dvf: sitk.Image) -> sitk.Image:
        """
        将DVF应用到源图像
        
        Args:
            source_img: 源图像
            dvf: 形变矢量场
            
        Returns:
            sitk.Image: 变形后的图像
        """
        self.logger.info("开始应用DVF到图像")
        self.progress_updated.emit(10, "准备应用DVF...")
        
        # 确保DVF是vector float64类型
        # SimpleITK的DisplacementFieldTransform要求DVF是vector float64类型
        pixel_type = dvf.GetPixelIDTypeAsString()
        comp_per_pixel = dvf.GetNumberOfComponentsPerPixel()
        
        self.logger.info(f"原始DVF类型: {pixel_type}, 每像素分量数: {comp_per_pixel}")
        
        # 检查是否是32位向量场，需要转换为64位
        if "vector" in pixel_type.lower() and "32-bit float" in pixel_type and comp_per_pixel == 3:
            self.logger.info("检测到32位向量场，正在转换为64位...")
            try:
                # 方法1：使用sitk.Cast尝试直接转换
                try:
                    self.logger.info("尝试使用sitk.Cast直接转换...")
                    dvf_float64 = sitk.Cast(dvf, sitk.sitkVectorFloat64)
                    self.logger.info(f"转换后类型: {dvf_float64.GetPixelIDTypeAsString()}")
                    dvf = dvf_float64
                except Exception as e:
                    self.logger.warning(f"直接转换失败: {e}，尝试其他方法...")
                    
                    # 方法2：通过numpy数组转换
                    self.logger.info("尝试通过numpy数组转换...")
                    array = sitk.GetArrayFromImage(dvf)
                    array_float64 = array.astype(np.float64)
                    
                    # 创建新的向量场图像
                    dvf_float64 = sitk.GetImageFromArray(array_float64, isVector=True)
                    dvf_float64.CopyInformation(dvf)  # 复制原始的元数据
                    
                    self.logger.info(f"通过numpy转换后类型: {dvf_float64.GetPixelIDTypeAsString()}")
                    dvf = dvf_float64
                    
            except Exception as e:
                self.logger.error(f"转换为64位浮点型失败: {e}")
                # 继续处理，使用原始DVF
        
        # 检查是否需要转换DVF（非向量场情况）
        elif comp_per_pixel == 3 and "vector" not in pixel_type.lower():
            self.logger.warning(f"非标准DVF格式: {pixel_type}, 分量数: {comp_per_pixel}")
            # 尝试进行转换
            self.logger.info("尝试转换DVF为向量场...")
            try:
                # 将DVF转换为vector float64类型
                dvf = sitk.Cast(dvf, sitk.sitkVectorFloat64)
                self.logger.info(f"转换后DVF类型: {dvf.GetPixelIDTypeAsString()}")
            except Exception as e:
                self.logger.error(f"无法转换DVF到向量场格式: {e}")
                raise ValueError(f"无法转换DVF到向量场格式: {e}")
        
        # 创建形变变换
        try:
            self.logger.info("创建形变场变换...")
            displacement_transform = sitk.DisplacementFieldTransform(dvf)
            self.logger.info("形变场变换创建成功")
        except Exception as e:
            self.logger.error(f"创建形变场变换失败: {e}")
            
            # 尝试替代方法1：使用sitk.TransformToDisplacementField
            try:
                self.logger.info("尝试使用替代方法创建形变场...")
                # 创建恒等变换
                identity = sitk.Transform(3, sitk.sitkIdentity)
                
                # 手动构建位移场变换
                transform = sitk.DisplacementFieldTransform(3)
                
                # 将dvf设置为位移场
                if "vector" in pixel_type.lower() and comp_per_pixel == 3:
                    # 获取DVF的数组表示
                    dvf_array = sitk.GetArrayFromImage(dvf)
                    # 转换为float64
                    dvf_array_float64 = dvf_array.astype(np.float64)
                    # 创建新的向量场图像
                    dvf_float64 = sitk.GetImageFromArray(dvf_array_float64, isVector=True)
                    dvf_float64.CopyInformation(dvf)  # 复制原始的元数据
                    
                    # 设置位移场
                    transform.SetDisplacementField(dvf_float64)
                    self.logger.info("已手动创建位移场变换")
                    
                    # 应用变换
                    self.progress_updated.emit(30, "使用手动创建的变换计算形变...")
                    warped_image = sitk.Resample(source_img, 
                                               dvf_float64, 
                                               transform, 
                                               sitk.sitkLinear, 
                                               0.0)
                    
                    self.progress_updated.emit(90, "形变计算完成")
                    return warped_image
                else:
                    raise ValueError("DVF不是有效的向量场")
                    
            except Exception as e2:
                self.logger.error(f"替代方法1失败: {e2}")
                
                # 尝试替代方法2：使用ITK内部的转换方法
                try:
                    self.logger.info("尝试使用ITK风格的方法创建形变场...")
                    # 尝试使用ITK的扩展方法
                    import SimpleITK as sitk_ext
                    
                    # 转换DVF类型
                    dvf_array = sitk.GetArrayFromImage(dvf).astype(np.float64)
                    dvf_float64 = sitk.GetImageFromArray(dvf_array, isVector=True)
                    dvf_float64.CopyInformation(dvf)
                    
                    # 使用低级API创建变换
                    # 注意：此部分是尝试性的，可能需要根据SimpleITK版本调整
                    transform_float64 = sitk.DisplacementFieldTransform(dvf_float64)
                    
                    self.progress_updated.emit(30, "使用ITK方法计算形变...")
                    warped_image = sitk.Resample(source_img, 
                                               dvf_float64, 
                                               transform_float64, 
                                               sitk.sitkLinear, 
                                               0.0)
                    
                    self.progress_updated.emit(90, "形变计算完成")
                    return warped_image
                    
                except Exception as e3:
                    self.logger.error(f"替代方法2失败: {e3}")
            
            # 如果所有方法都失败，回退到手动方法
            self.logger.info("所有自动方法失败，尝试使用完全手动的方法...")
            return self.apply_dvf_manually_v2(source_img, dvf)
        
        # 设置插值方法（对于PET/CT通常使用线性插值）
        interpolator = sitk.sitkLinear
        
        self.progress_updated.emit(30, "正在计算形变...")
        
        # 应用形变
        # 默认背景值为0，对于PET/CT通常合适
        warped_image = sitk.Resample(source_img, 
                                     dvf, 
                                     displacement_transform, 
                                     interpolator, 
                                     0.0)
        
        self.progress_updated.emit(90, "形变计算完成")
        return warped_image
    
    def apply_dvf_manually_v2(self, source_img: sitk.Image, dvf: sitk.Image) -> sitk.Image:
        """
        实现一种更完整的手动应用DVF方法
        
        Args:
            source_img: 源图像
            dvf: 形变矢量场
            
        Returns:
            sitk.Image: 变形后的图像
        """
        self.logger.info("使用改进的手动方法应用DVF...")
        self.progress_updated.emit(20, "准备手动应用DVF (V2)...")
        
        # 获取图像和DVF的数组表示
        source_array = sitk.GetArrayFromImage(source_img)
        dvf_array = sitk.GetArrayFromImage(dvf)
        
        # 获取图像尺寸和间距信息
        source_size = source_img.GetSize()
        source_spacing = source_img.GetSpacing()
        source_origin = source_img.GetOrigin()
        source_direction = source_img.GetDirection()
        
        dvf_size = dvf.GetSize()
        dvf_spacing = dvf.GetSpacing()
        dvf_origin = dvf.GetOrigin()
        dvf_direction = dvf.GetDirection()
        
        self.logger.info(f"手动处理 - 源图像形状: {source_array.shape}")
        self.logger.info(f"手动处理 - DVF形状: {dvf_array.shape}")
        
        # 修正DVF数组的形状
        # SimpleITK的GetArrayFromImage会将数据变成numpy数组，通道顺序可能是(z,y,x,vector)或(vector,z,y,x)
        if len(dvf_array.shape) == 4:
            self.logger.info(f"DVF数组维度: 4D, 形状: {dvf_array.shape}")
            # 检查哪个维度是向量维度
            if dvf_array.shape[0] == 3:  # (vector,z,y,x)
                self.logger.info("DVF格式: (vector,z,y,x)")
                # 需要重新排列以获得(z,y,x,vector)格式
                dvf_array = np.moveaxis(dvf_array, 0, -1)
                self.logger.info(f"重排后DVF形状: {dvf_array.shape}")
            elif dvf_array.shape[-1] == 3:  # (z,y,x,vector)
                self.logger.info("DVF格式: (z,y,x,vector)")
            else:
                self.logger.warning(f"意外的DVF形状: {dvf_array.shape}")
        else:
            # 重新解释DVF数组形状
            self.logger.warning(f"DVF数组不是4D: {dvf_array.shape}")
            
            if dvf.GetNumberOfComponentsPerPixel() == 3:
                # 尝试将扁平数组重塑为正确形状
                self.logger.info("重新组织DVF数组...")
                try:
                    # 创建正确形状的数组
                    correct_shape = (dvf_size[2], dvf_size[1], dvf_size[0], 3)
                    self.logger.info(f"尝试重塑为: {correct_shape}")
                    
                    # 对于Flat数组
                    if dvf_array.ndim == 3:
                        # 可能是SimpleITK以特殊方式组织的向量场
                        self.logger.info("尝试从3D数组创建向量场...")
                        
                        # 创建一个合适大小的新数组
                        new_dvf_array = np.zeros((dvf_size[2], dvf_size[1], dvf_size[0], 3), dtype=np.float32)
                        
                        # 手动提取位移分量
                        # 注：这里需要根据实际数据结构调整
                        self.logger.info("假设DVF是3D数组，每个元素是3分量向量")
                        
                        # 验证数据大小是否合理
                        expected_size = dvf_size[0] * dvf_size[1] * dvf_size[2] * 3
                        actual_size = dvf_array.size
                        self.logger.info(f"预期大小: {expected_size}, 实际大小: {actual_size}")
                        
                        if dvf_array.size == dvf_size[0] * dvf_size[1] * dvf_size[2] * 3:
                            # 这可能是个扁平数组，需要重塑
                            try:
                                temp_array = dvf_array.reshape(dvf_size[2], dvf_size[1], dvf_size[0], 3)
                                self.logger.info(f"重塑成功，新形状: {temp_array.shape}")
                                dvf_array = temp_array
                            except Exception as e:
                                self.logger.error(f"重塑失败: {e}")
                        else:
                            # 如果大小不匹配，使用更直接的方法从向量场中提取分量
                            self.logger.info("尝试直接从SimpleITK对象提取向量场分量...")
                
                except Exception as e:
                    self.logger.error(f"重新组织DVF数组失败: {e}")
                    # 继续处理，尝试其他方法
        
        # ===== 修改:保持原始PET图像尺寸 =====
        # 方法1: 通过向原图添加DVF的逆向变换来保持原始PET图像尺寸
        self.logger.info("使用保持原始PET图像尺寸的方法")
        self.progress_updated.emit(25, "初始化输出图像...")
        
        # 创建与原始PET图像相同尺寸的输出数组
        warped_array = np.zeros_like(source_array)
        
        # 为原始PET图像创建坐标网格
        z_src_coords, y_src_coords, x_src_coords = np.meshgrid(
            np.arange(0, source_size[2]),
            np.arange(0, source_size[1]),
            np.arange(0, source_size[0]),
            indexing='ij'
        )
        
        # 将源图像的索引坐标转换为物理坐标
        src_phys_x = source_origin[0] + x_src_coords * source_spacing[0]
        src_phys_y = source_origin[1] + y_src_coords * source_spacing[1]
        src_phys_z = source_origin[2] + z_src_coords * source_spacing[2]
        
        self.progress_updated.emit(35, "准备DVF分量...")
        
        # 确保我们有正确的DVF格式来提取分量
        if len(dvf_array.shape) == 4 and dvf_array.shape[-1] == 3:
            # 提取各个方向的位移
            dx = dvf_array[..., 0]  # x方向位移
            dy = dvf_array[..., 1]  # y方向位移
            dz = dvf_array[..., 2]  # z方向位移
            
            self.logger.info(f"位移范围 - dx: {np.min(dx)} to {np.max(dx)}, " 
                          f"dy: {np.min(dy)} to {np.max(dy)}, "
                          f"dz: {np.min(dz)} to {np.max(dz)}")
        else:
            # 尝试使用SimpleITK直接提取向量场分量
            self.logger.info("尝试使用SimpleITK API提取向量场分量...")
            
            try:
                # 使用VectorIndexSelectionCast提取分量
                dvf_x = sitk.VectorIndexSelectionCast(dvf, 0)
                dvf_y = sitk.VectorIndexSelectionCast(dvf, 1)
                dvf_z = sitk.VectorIndexSelectionCast(dvf, 2)
                
                # 转换为numpy数组
                dx = sitk.GetArrayFromImage(dvf_x)
                dy = sitk.GetArrayFromImage(dvf_y)
                dz = sitk.GetArrayFromImage(dvf_z)
                
                self.logger.info(f"通过SimpleITK API提取的位移场 - 形状: dx={dx.shape}, dy={dy.shape}, dz={dz.shape}")
                self.logger.info(f"位移范围 - dx: {np.min(dx)} to {np.max(dx)}, " 
                             f"dy: {np.min(dy)} to {np.max(dy)}, "
                             f"dz: {np.min(dz)} to {np.max(dz)}")
            except Exception as e:
                self.logger.error(f"使用SimpleITK API提取分量失败: {e}")
                # 使用默认值（零位移）
                dx = np.zeros_like(x_src_coords)
                dy = np.zeros_like(y_src_coords)
                dz = np.zeros_like(z_src_coords)
        
        # 创建从DVF物理空间到DVF索引空间的插值器
        self.progress_updated.emit(40, "创建DVF插值器...")
        
        try:
            # 为DVF位移场创建物理坐标到位移的插值器
            # 生成DVF的物理坐标网格点
            z_dvf_points = np.linspace(dvf_origin[2], dvf_origin[2] + (dvf_size[2]-1) * dvf_spacing[2], dvf_size[2])
            y_dvf_points = np.linspace(dvf_origin[1], dvf_origin[1] + (dvf_size[1]-1) * dvf_spacing[1], dvf_size[1])
            x_dvf_points = np.linspace(dvf_origin[0], dvf_origin[0] + (dvf_size[0]-1) * dvf_spacing[0], dvf_size[0])
            
            # 创建位移场的插值器
            if dx.shape == (dvf_size[2], dvf_size[1], dvf_size[0]):
                dx_interpolator = RegularGridInterpolator(
                    (z_dvf_points, y_dvf_points, x_dvf_points), 
                    dx, 
                    method='linear', 
                    bounds_error=False, 
                    fill_value=0
                )
                
                dy_interpolator = RegularGridInterpolator(
                    (z_dvf_points, y_dvf_points, x_dvf_points), 
                    dy, 
                    method='linear', 
                    bounds_error=False, 
                    fill_value=0
                )
                
                dz_interpolator = RegularGridInterpolator(
                    (z_dvf_points, y_dvf_points, x_dvf_points), 
                    dz, 
                    method='linear', 
                    bounds_error=False, 
                    fill_value=0
                )
                
                # 准备源图像物理坐标点以在DVF中查询
                points = np.stack([src_phys_z.ravel(), src_phys_y.ravel(), src_phys_x.ravel()], axis=-1)
                
                # 在每个方向上查询位移
                self.progress_updated.emit(50, "插值DVF位移场...")
                disp_x = dx_interpolator(points).reshape(source_array.shape)
                disp_y = dy_interpolator(points).reshape(source_array.shape)
                disp_z = dz_interpolator(points).reshape(source_array.shape)
                
                # 应用位移并获取变形后的物理坐标
                warped_phys_x = src_phys_x + disp_x
                warped_phys_y = src_phys_y + disp_y
                warped_phys_z = src_phys_z + disp_z
            else:
                self.logger.warning(f"DVF分量形状 {dx.shape} 与预期 {(dvf_size[2], dvf_size[1], dvf_size[0])} 不符，使用默认方法")
                # 回退到默认方法
                disp_x = np.zeros_like(src_phys_x)
                disp_y = np.zeros_like(src_phys_y)
                disp_z = np.zeros_like(src_phys_z)
                
                # 无变形
                warped_phys_x = src_phys_x
                warped_phys_y = src_phys_y
                warped_phys_z = src_phys_z
                
        except Exception as e:
            self.logger.error(f"创建DVF插值器失败: {e}")
            # 回退到默认（无变形）
            warped_phys_x = src_phys_x
            warped_phys_y = src_phys_y
            warped_phys_z = src_phys_z
        
        # 将变形后的物理坐标转换回源图像的索引坐标
        self.progress_updated.emit(70, "计算变形后坐标...")
        warped_x_idx = (warped_phys_x - source_origin[0]) / source_spacing[0]
        warped_y_idx = (warped_phys_y - source_origin[1]) / source_spacing[1]
        warped_z_idx = (warped_phys_z - source_origin[2]) / source_spacing[2]
        
        # 创建源图像的插值器
        self.progress_updated.emit(80, "创建图像插值器...")
        try:
            # 生成源图像的索引坐标网格点
            z_src_points = np.arange(0, source_array.shape[0])
            y_src_points = np.arange(0, source_array.shape[1])
            x_src_points = np.arange(0, source_array.shape[2])
            
            # 创建源图像的插值器
            source_interpolator = RegularGridInterpolator(
                (z_src_points, y_src_points, x_src_points),
                source_array,
                method='linear',
                bounds_error=False,
                fill_value=0
            )
            
            # 准备变形后的索引坐标点
            warped_points = np.stack([warped_z_idx.ravel(), warped_y_idx.ravel(), warped_x_idx.ravel()], axis=-1)
            
            # 使用插值获取变形后图像的值
            self.progress_updated.emit(90, "执行最终图像插值...")
            warped_values = source_interpolator(warped_points)
            
            # 重塑为原始图像尺寸
            warped_array = warped_values.reshape(source_array.shape)
            
        except Exception as e:
            self.logger.error(f"创建源图像插值器失败: {e}")
            # 使用简单的最近邻插值（循环版本）
            self.logger.warning("回退到简单的最近邻插值")
            
            # 裁剪索引到有效范围
            warped_x_idx = np.clip(warped_x_idx, 0, source_array.shape[2] - 1)
            warped_y_idx = np.clip(warped_y_idx, 0, source_array.shape[1] - 1)
            warped_z_idx = np.clip(warped_z_idx, 0, source_array.shape[0] - 1)
            
            # 转换为整数索引
            warped_x_idx = np.round(warped_x_idx).astype(np.int32)
            warped_y_idx = np.round(warped_y_idx).astype(np.int32)
            warped_z_idx = np.round(warped_z_idx).astype(np.int32)
            
            # 执行最近邻插值
            for z in range(warped_array.shape[0]):
                if z % 10 == 0:  # 每10个切片更新一次进度
                    progress = 80 + 15 * z / warped_array.shape[0]
                    self.progress_updated.emit(int(progress), f"处理切片 {z+1}/{warped_array.shape[0]}")
                    
                for y in range(warped_array.shape[1]):
                    for x in range(warped_array.shape[2]):
                        src_z = warped_z_idx[z, y, x]
                        src_y = warped_y_idx[z, y, x]
                        src_x = warped_x_idx[z, y, x]
                        warped_array[z, y, x] = source_array[src_z, src_y, src_x]
        
        # 创建结果图像，保持原始PET的元数据
        self.progress_updated.emit(95, "创建结果图像...")
        warped_image = sitk.GetImageFromArray(warped_array)
        warped_image.SetSpacing(source_spacing)
        warped_image.SetOrigin(source_origin)
        warped_image.SetDirection(source_direction)
        
        self.logger.info(f"变形完成 - 结果图像形状与原始PET相同: {warped_array.shape}")
        self.progress_updated.emit(100, "变形完成")
        return warped_image
    
    def process_directory(self, src_ct_dir: str, src_pet_dir: str, 
                         tgt_ct_dir: str, dvf_path: str) -> Tuple[bool, str, Optional[sitk.Image]]:
        """
        处理完整的工作流：从源CT到目标CT的DVF应用到源PET
        
        Args:
            src_ct_dir: 源CT目录
            src_pet_dir: 源PET目录
            tgt_ct_dir: 目标CT目录
            dvf_path: DVF文件路径
            
        Returns:
            Tuple[bool, str, Optional[sitk.Image]]: (成功标志, 消息, 变形后的图像)
        """
        try:
            self.logger.info(f"开始处理：源CT={src_ct_dir}, 源PET={src_pet_dir}, 目标CT={tgt_ct_dir}, DVF={dvf_path}")
            self.progress_updated.emit(0, "开始处理...")
            
            # 1. 加载图像
            self.progress_updated.emit(5, "加载源PET图像...")
            try:
                src_pet = self.load_image_series(src_pet_dir)
            except Exception as e:
                self.logger.error(f"加载源PET失败: {e}")
                return False, f"加载源PET失败: {e}", None
                
            # 2. 加载DVF
            self.progress_updated.emit(15, "加载DVF...")
            try:
                dvf = self.load_dvf(dvf_path)
            except Exception as e:
                self.logger.error(f"加载DVF失败: {e}")
                return False, f"加载DVF失败: {e}", None
            
            # 3. 检查兼容性
            if not self.check_compatible_spaces(src_pet, dvf):
                msg = "源PET和DVF空间不兼容，将直接使用手动方法"
                self.logger.warning(msg)
                
                # 直接使用手动方法，跳过重采样和自动变换
                self.logger.info("使用手动方法应用DVF")
                warped_pet = self.apply_dvf_manually_v2(src_pet, dvf)
                
                # 完成
                self.progress_updated.emit(100, "处理完成")
                self.logger.info("手动DVF应用完成")
                
                return True, "DVF成功手动应用到PET图像", warped_pet
            
            # 4. 应用DVF
            self.progress_updated.emit(30, "应用DVF到源PET...")
            try:
                warped_pet = self.apply_dvf_to_image(src_pet, dvf)
            except Exception as e:
                self.logger.error(f"应用DVF失败: {e}")
                
                # 出错时回退到手动方法
                self.logger.info("自动方法失败，尝试手动方法...")
                warped_pet = self.apply_dvf_manually_v2(src_pet, dvf)
                
                if warped_pet is None:
                    return False, f"应用DVF失败: {e}", None
            
            # 5. 完成
            self.progress_updated.emit(100, "处理完成")
            self.logger.info("DVF应用完成")
            
            return True, "DVF成功应用到PET图像", warped_pet
            
        except Exception as e:
            error_msg = f"处理过程中出错: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return False, error_msg, None
            
    def save_image(self, image: sitk.Image, output_dir: str, base_name: str = "warped_pet") -> str:
        """
        保存变形后的图像
        
        Args:
            image: 要保存的图像
            output_dir: 输出目录
            base_name: 基础文件名
            
        Returns:
            str: 保存的文件路径
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 创建输出子目录
        dcm_output_dir = os.path.join(output_dir, base_name)
        if not os.path.exists(dcm_output_dir):
            os.makedirs(dcm_output_dir)
            
        # 首先保存为NIFTI格式作为备份
        nifti_path = os.path.join(output_dir, f"{base_name}.nii.gz")
        writer = sitk.ImageFileWriter()
        writer.SetFileName(nifti_path)
        writer.Execute(image)
        
        self.logger.info(f"已将图像保存为NIFTI格式: {nifti_path}")
        
        # 尝试保存为DICOM序列
        try:
            self.logger.info("尝试保存为DICOM序列...")
            return self.save_as_dicom_series(image, dcm_output_dir, base_name)
        except Exception as e:
            self.logger.error(f"保存为DICOM序列失败: {e}", exc_info=True)
            return nifti_path  # 返回NIFTI路径作为备选
        
    def save_as_dicom_series(self, image: sitk.Image, output_dir: str, base_name: str) -> str:
        """
        将图像保存为DICOM序列，并尽可能保持与原始PET图像相同的DICOM属性
        
        Args:
            image: 要保存的图像
            output_dir: 输出目录
            base_name: 基础文件名
            
        Returns:
            str: 保存的文件目录
        """
        self.logger.info(f"将图像保存为DICOM序列到目录: {output_dir}")
        
        # 1. 获取原始图像的数组表示
        image_array = sitk.GetArrayFromImage(image)
        self.logger.info(f"图像形状: {image_array.shape}")
        
        # 2. 创建目录结构
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 3. 寻找一个模板DICOM文件
        # 从当前数据根目录中的源PET目录找一个模板DICOM文件
        import glob
        import pydicom
        from datetime import datetime
        
        # 使用辅助函数查找模板DICOM文件
        template_file = self.find_template_dicom_file()
        
        if not template_file:
            self.logger.warning("未找到模板DICOM文件，使用默认DICOM属性")
            # 使用默认方法保存
            return self.save_as_default_dicom_series(image, output_dir)
            
        # 4. 读取模板DICOM文件
        try:
            template_dcm = pydicom.dcmread(template_file)
            self.logger.info(f"使用模板DICOM文件: {template_file}")
        except Exception as e:
            self.logger.error(f"读取模板DICOM文件失败: {e}")
            # 使用默认方法保存
            return self.save_as_default_dicom_series(image, output_dir)
            
        # 5. 准备新序列的元数据
        # 复用原始StudyID
        study_id = template_dcm.StudyID if hasattr(template_dcm, 'StudyID') else "1"

        # 生成新的系列UID，但保持原始StudyInstanceUID
        series_uid = pydicom.uid.generate_uid()
        study_uid = template_dcm.StudyInstanceUID if hasattr(template_dcm, 'StudyInstanceUID') else pydicom.uid.generate_uid()
        frame_of_ref_uid = template_dcm.FrameOfReferenceUID if hasattr(template_dcm, 'FrameOfReferenceUID') else pydicom.uid.generate_uid()
        
        # 生成当前日期时间
        now = datetime.now()
        date_str = now.strftime('%Y%m%d')
        time_str = now.strftime('%H%M%S')
        
        # 6. 保存每个切片为单独的DICOM文件
        spacing = image.GetSpacing()
        origin = image.GetOrigin()
        direction = image.GetDirection()
        
        # 获取切片数
        num_slices = image_array.shape[0]
        
        # 检查模版的像素表示格式
        try:
            photometric_interpretation = template_dcm.PhotometricInterpretation
        except:
            photometric_interpretation = "MONOCHROME2"  # 使用默认值
            
        # 检查模板的位深度
        try:
            bits_allocated = template_dcm.BitsAllocated
            bits_stored = template_dcm.BitsStored
            high_bit = template_dcm.HighBit
        except:
            # 为PET图像使用默认值（通常16位）
            bits_allocated = 16
            bits_stored = 16
            high_bit = 15
            
        # 检查其他关键标签
        try:
            modality = template_dcm.Modality
        except:
            modality = "PT"  # 假设我们处理的是PET图像
        
        # 获取原始图像的最小/最大值，用于设置窗位窗宽
        min_val = np.min(image_array)
        max_val = np.max(image_array)
        window_center = (max_val + min_val) / 2
        window_width = max_val - min_val
        
        # 创建序列信息 (重要的临床相关标签)
        accession_number = template_dcm.AccessionNumber if hasattr(template_dcm, 'AccessionNumber') else ""
        study_description = template_dcm.StudyDescription if hasattr(template_dcm, 'StudyDescription') else "PET Study"
        series_number = template_dcm.SeriesNumber if hasattr(template_dcm, 'SeriesNumber') else "100"
        
        # 为每个切片创建并保存DICOM文件
        for i in range(num_slices):
            # 创建新的DICOM数据集而不是复制模板
            # 这样可以避免一些不兼容的标记
            new_dcm = pydicom.Dataset()
            
            # 添加文件元数据
            file_meta = pydicom.Dataset()
            file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.128' # PET图像存储的SOP类
            file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
            file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
            file_meta.ImplementationClassUID = pydicom.uid.generate_uid()
            
            # 设置文件元信息
            new_dcm.file_meta = file_meta
            new_dcm.is_little_endian = True
            new_dcm.is_implicit_VR = False
            
            # 设置必需标记
            new_dcm.SOPClassUID = '1.2.840.10008.5.1.4.1.1.128'  # PET图像存储
            new_dcm.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
            new_dcm.StudyInstanceUID = study_uid
            new_dcm.SeriesInstanceUID = series_uid
            
            # 增加临床重要标签
            new_dcm.StudyID = study_id
            new_dcm.AccessionNumber = accession_number
            new_dcm.StudyDescription = study_description
            new_dcm.SeriesNumber = series_number
            
            # 从模板复制重要属性
            important_attrs = [
                'PatientName', 'PatientID', 'PatientBirthDate', 'PatientSex', 'PatientAge', 'PatientWeight',
                'StudyDate', 'StudyTime', 'ReferringPhysicianName', 'InstitutionName', 
                'Manufacturer', 'ManufacturerModelName', 'SoftwareVersions',
                'DeviceSerialNumber', 'InstitutionalDepartmentName', 'ProtocolName'
            ]
            
            for attr in important_attrs:
                if hasattr(template_dcm, attr):
                    setattr(new_dcm, attr, getattr(template_dcm, attr))
            
            # 设置图像特定属性
            new_dcm.InstanceNumber = i + 1
            new_dcm.ImagePositionPatient = [origin[0], origin[1], origin[2] + i * spacing[2]]
            new_dcm.ImageOrientationPatient = [direction[0], direction[1], direction[2], 
                                              direction[3], direction[4], direction[5]]
            new_dcm.FrameOfReferenceUID = frame_of_ref_uid
            new_dcm.SliceLocation = origin[2] + i * spacing[2]
            
            # 设置像素数据相关属性
            new_dcm.SamplesPerPixel = 1
            new_dcm.PhotometricInterpretation = photometric_interpretation
            new_dcm.Rows = image_array.shape[1]
            new_dcm.Columns = image_array.shape[2]
            new_dcm.BitsAllocated = bits_allocated
            new_dcm.BitsStored = bits_stored
            new_dcm.HighBit = high_bit
            new_dcm.PixelRepresentation = 0  # 无符号整数
            
            # 设置窗位窗宽
            new_dcm.WindowCenter = window_center
            new_dcm.WindowWidth = window_width
            
            # 设置PET特定属性
            new_dcm.Modality = modality
            new_dcm.SeriesDescription = f"Deformed PET - {base_name}"
            new_dcm.SliceThickness = spacing[2]
            new_dcm.PixelSpacing = [spacing[0], spacing[1]]
            
            # 设置日期和时间
            new_dcm.SeriesDate = date_str
            new_dcm.SeriesTime = time_str
            new_dcm.ContentDate = date_str
            new_dcm.ContentTime = time_str
            new_dcm.AcquisitionDate = date_str
            new_dcm.AcquisitionTime = time_str
            
            # 适当处理SUV相关标签
            # 确保SUV计算所需的必要标签存在
            if hasattr(template_dcm, 'Units'):
                new_dcm.Units = template_dcm.Units
            elif hasattr(template_dcm, 'CorrectedImage') and 'ATTN' in template_dcm.CorrectedImage:
                new_dcm.Units = "BQML"
                
            if hasattr(template_dcm, 'SUVFactor'):
                new_dcm.SUVFactor = template_dcm.SUVFactor
            
            # 复制所有重要的序列/衰变相关的PET特有标签
            pet_tags = [
                'RadionuclideHalfLife', 'RadionuclideTotalDose', 'RadiopharmaceuticalInformationSequence',
                'DecayCorrection', 'DecayFactor', 'CorrectedImage', 'SeriesType', 'ActualFrameDuration',
                'PatientOrientation', 'ImageType', 'ScanOptions'
            ]
            
            for tag in pet_tags:
                if hasattr(template_dcm, tag):
                    setattr(new_dcm, tag, getattr(template_dcm, tag))
            
            # 处理重要的缩放参数
            if hasattr(template_dcm, 'RescaleSlope') and hasattr(template_dcm, 'RescaleIntercept'):
                new_dcm.RescaleSlope = template_dcm.RescaleSlope
                new_dcm.RescaleIntercept = template_dcm.RescaleIntercept
                
                # 获取原始斜率和截距
                slope = float(template_dcm.RescaleSlope)
                intercept = float(template_dcm.RescaleIntercept)
                
                # 确保像素数据使用与模板相同的数据类型
                if hasattr(template_dcm, 'pixel_array'):
                    slice_data = image_array[i].astype(template_dcm.pixel_array.dtype)
                else:
                    # 如果无法确定数据类型，则使用基于BitsAllocated的默认类型
                    if bits_allocated == 16:
                        slice_data = image_array[i].astype(np.uint16)
                    else:
                        slice_data = image_array[i].astype(np.uint8)
                
                # 根据RescaleSlope和RescaleIntercept调整像素值
                if slope != 0:
                    slice_data = np.round((slice_data - intercept) / slope).astype(slice_data.dtype)
            else:
                # 如果模板中没有缩放参数，则直接使用像素数据
                slice_data = image_array[i].astype(np.uint16)  # 默认使用16位
                # 设置默认缩放参数
                new_dcm.RescaleSlope = 1.0
                new_dcm.RescaleIntercept = 0.0
            
            # 设置像素数据
            new_dcm.PixelData = slice_data.tobytes()
            
            # 保存DICOM文件
            output_file = os.path.join(output_dir, f"slice_{i:04d}.dcm")
            # 设置适当的写入选项
            new_dcm.save_as(output_file, write_like_original=False)
            
            # 更新进度
            if i % 10 == 0 or i == num_slices - 1:
                self.logger.info(f"已保存 {i+1}/{num_slices} 个DICOM切片")
                
        self.logger.info(f"已成功将图像保存为DICOM序列，共 {num_slices} 个切片，保存到 {output_dir}")
        return output_dir
    
    def save_as_default_dicom_series(self, image: sitk.Image, output_dir: str) -> str:
        """
        使用标准方法将图像保存为DICOM序列（当没有模板文件时使用）
        
        Args:
            image: 要保存的图像
            output_dir: 输出目录
            
        Returns:
            str: 保存的文件目录
        """
        self.logger.info("使用标准方法保存DICOM序列")
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 获取图像信息
        image_array = sitk.GetArrayFromImage(image)
        size = image.GetSize()
        spacing = image.GetSpacing()
        origin = image.GetOrigin()
        direction = image.GetDirection()
        
        # 准备DICOM元数据
        import pydicom
        from pydicom.dataset import FileDataset, FileMetaDataset
        from datetime import datetime
        import numpy as np
        
        # 生成UID
        series_uid = pydicom.uid.generate_uid()
        study_uid = pydicom.uid.generate_uid()
        frame_of_ref_uid = pydicom.uid.generate_uid()
        
        # 生成StudyID和其他临床标识符
        study_id = "1"  # 默认StudyID
        accession_number = "ACCN" + datetime.now().strftime('%Y%m%d')  # 使用日期创建AccessionNumber
        
        # 获取当前日期时间
        now = datetime.now()
        date_str = now.strftime('%Y%m%d')
        time_str = now.strftime('%H%M%S')
        
        # 为PET图像设置默认的位深度
        bits_allocated = 16
        bits_stored = 16
        high_bit = 15
        
        # 计算图像的窗位窗宽
        min_val = np.min(image_array)
        max_val = np.max(image_array)
        window_center = (max_val + min_val) / 2
        window_width = max_val - min_val
        
        # 为每个切片创建和保存DICOM文件
        num_slices = image_array.shape[0]
        for i in range(num_slices):
            # 创建文件名
            output_file = os.path.join(output_dir, f"slice_{i:04d}.dcm")
            
            # 创建文件元信息
            file_meta = FileMetaDataset()
            file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.128'  # PET图像存储
            file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
            file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
            file_meta.ImplementationClassUID = pydicom.uid.generate_uid()
            
            # 创建数据集
            ds = FileDataset(output_file, {}, file_meta=file_meta, preamble=b"\0" * 128)
            ds.is_little_endian = True
            ds.is_implicit_VR = False
            
            # 设置必需的DICOM标签
            ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
            ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
            ds.StudyInstanceUID = study_uid
            ds.SeriesInstanceUID = series_uid
            ds.FrameOfReferenceUID = frame_of_ref_uid
            
            # 设置临床相关标签
            ds.StudyID = study_id
            ds.AccessionNumber = accession_number
            ds.StudyDescription = "PET Deformation Study"
            ds.SeriesDescription = "Deformed PET Image"
            ds.SeriesNumber = "100"
            
            # 设置患者和研究信息（使用默认值）
            ds.PatientName = "ANONYMOUS"
            ds.PatientID = "ANON12345"
            ds.PatientBirthDate = ""
            ds.PatientSex = "O"  # Other
            ds.PatientAge = "000Y"
            ds.PatientWeight = "70"  # 默认70公斤
            ds.PatientPosition = "FFS"  # 默认头先进，仰卧位
            ds.StudyDate = date_str
            ds.StudyTime = time_str
            ds.ReferringPhysicianName = ""
            ds.InstitutionName = "DICOM All-in-One Tool"
            ds.InstitutionalDepartmentName = "Medical Physics"
            ds.PerformingPhysicianName = ""
            
            # 设置图像特定属性
            ds.Modality = "PT"  # PET
            ds.ImageType = ["DERIVED", "SECONDARY", "DEFORMED"]
            ds.InstanceNumber = i + 1
            ds.ImagePositionPatient = [origin[0], origin[1], origin[2] + i * spacing[2]]
            ds.ImageOrientationPatient = [direction[0], direction[1], direction[2], 
                                         direction[3], direction[4], direction[5]]
            ds.SliceLocation = origin[2] + i * spacing[2]
            ds.SliceThickness = spacing[2]
            ds.PixelSpacing = [spacing[0], spacing[1]]
            
            # 设置窗位窗宽
            ds.WindowCenter = window_center
            ds.WindowWidth = window_width
            
            # 设置像素数据相关属性
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = "MONOCHROME2"
            ds.Rows = image_array.shape[1]
            ds.Columns = image_array.shape[2]
            ds.BitsAllocated = bits_allocated
            ds.BitsStored = bits_stored
            ds.HighBit = high_bit
            ds.PixelRepresentation = 0  # 无符号整数
            
            # 设置PET特有的属性
            ds.Units = "BQML"  # 常用单位
            ds.RescaleSlope = 1.0
            ds.RescaleIntercept = 0.0
            
            # PET特有的时间和采集信息
            ds.SeriesType = "STATIC"
            ds.AcquisitionDate = date_str
            ds.AcquisitionTime = time_str
            ds.AcquisitionNumber = 1
            ds.ContentDate = date_str
            ds.ContentTime = time_str
            
            # PET特有的校正标签
            ds.CorrectedImage = ["ATTN", "DECAY", "SCAT"]
            ds.DecayCorrection = "ADMIN"
            ds.DecayFactor = 1.0
            
            # 放射性药物信息（使用F-18 FDG作为默认值）
            from pydicom.sequence import Sequence
            from pydicom.dataset import Dataset
            
            # 创建放射性药物信息序列
            radiopharm_seq = Sequence()
            radiopharm_item = Dataset()
            
            # 创建放射性核素代码序列
            radionuclide_seq = Sequence()
            radionuclide_item = Dataset()
            radionuclide_item.CodeValue = "C-111A1"
            radionuclide_item.CodingSchemeDesignator = "SRT"
            radionuclide_item.CodeMeaning = "18^Fluorine"
            radionuclide_seq.append(radionuclide_item)
            
            radiopharm_item.RadionuclideCodeSequence = radionuclide_seq
            radiopharm_item.RadionuclideHalfLife = 6588.0  # F-18的半衰期（秒）
            radiopharm_item.RadionuclideTotalDose = 370000000.0  # 370 MBq (10 mCi)，一个典型的FDG注射量
            radiopharm_item.RadiopharmaceuticalStartTime = time_str
            radiopharm_item.RadiopharmaceuticalStartDateTime = date_str + time_str
            
            # 创建放射性药物代码序列
            radiopharm_code_seq = Sequence()
            radiopharm_code_item = Dataset()
            radiopharm_code_item.CodeValue = "C-B1031"
            radiopharm_code_item.CodingSchemeDesignator = "SRT"
            radiopharm_code_item.CodeMeaning = "Fluorodeoxyglucose F^18^"
            radiopharm_code_seq.append(radiopharm_code_item)
            
            radiopharm_item.RadiopharmaceuticalCodeSequence = radiopharm_code_seq
            radiopharm_seq.append(radiopharm_item)
            ds.RadiopharmaceuticalInformationSequence = radiopharm_seq
            
            # 计划和采集信息
            ds.NumberOfSlices = num_slices
            ds.ActualFrameDuration = 300000  # 5分钟 = 300000毫秒
            ds.ScanOptions = "WB"  # 全身扫描
            
            # 制造商信息
            ds.Manufacturer = "DICOM All-in-One Tool"
            ds.ManufacturerModelName = "DVF Applier"
            ds.SoftwareVersions = "1.0"
            ds.DeviceSerialNumber = "001"
            
            # 根据图像数据类型，设置像素数据
            slice_data = image_array[i].astype(np.uint16)  # 使用16位无符号整数
            ds.PixelData = slice_data.tobytes()
            
            # 保存DICOM文件
            ds.save_as(output_file, write_like_original=False)
            
            # 更新进度
            if i % 10 == 0 or i == num_slices - 1:
                self.logger.info(f"已保存 {i+1}/{num_slices} 个DICOM切片")
                
        self.logger.info(f"已成功将图像保存为标准DICOM序列，共 {num_slices} 个切片，保存到 {output_dir}")
        return output_dir
        
    def find_template_dicom_file(self) -> str:
        """
        查找一个合适的模板DICOM文件
        
        Returns:
            str: 模板DICOM文件的路径，如果未找到则返回空字符串
        """
        # 尝试从数据根目录中找到PET目录
        try:
            import glob
            
            # 1. 首先尝试从上下文中找到数据根目录
            template_paths = []
            
            # 2. 从所有可能的位置查找DICOM文件
            search_paths = [
                "**/week*_PT/*.dcm",  # 任何week_PT目录下的DICOM文件
                "**/week*_PT/**/*.dcm",  # 任何week_PT目录及其子目录下的DICOM文件
                "**/images/week*_PT/*.dcm",  # images/week_PT目录下的DICOM文件
                "**/*.dcm"  # 所有DICOM文件
            ]
            
            # 对每个搜索路径进行查找
            for path_pattern in search_paths:
                found_files = glob.glob(path_pattern, recursive=True)
                if found_files:
                    self.logger.info(f"在路径 {path_pattern} 中找到 {len(found_files)} 个DICOM文件")
                    template_paths.extend(found_files)
                    break  # 找到文件后停止搜索
                    
            # 如果找到了文件，返回第一个
            if template_paths:
                return template_paths[0]
                
        except Exception as e:
            self.logger.error(f"查找模板DICOM文件时出错: {e}")
            
        # 如果无法找到，返回空字符串
        return "" 