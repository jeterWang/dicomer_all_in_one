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
from pydicom.dataset import FileDataset, FileMetaDataset
from datetime import datetime

# 忽略pydicom的弃用警告
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*FileDataset.is_little_endian.*")
warnings.filterwarnings("ignore", message=".*FileDataset.is_implicit_VR.*")
warnings.filterwarnings("ignore", message=".*write_like_original.*")

class ImageRigidMover(QObject):
    """
    实现医学图像的刚体位移配准
    支持DICOM图像和结构集(RTSS)的同步变换
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
        self.fixed_data = {
            'images': [],           # 存储固定图像
            'rtss': None,           # 存储固定图像的结构集
            'image_files': [],      # 图像文件路径列表
            'rtss_file': None,      # 结构集文件路径
            'image_info': {},       # 图像元信息
            'loaded': False         # 是否已加载
        }
        
        self.moving_data = {
            'images': [],           # 存储移动图像
            'rtss': None,           # 存储移动图像的结构集
            'image_files': [],      # 图像文件路径列表
            'rtss_file': None,      # 结构集文件路径
            'image_info': {},       # 图像元信息
            'loaded': False         # 是否已加载
        }
        
        # 变换参数
        self.transform_params = {
            'tx': 0.0,  # x方向平移（mm）
            'ty': 0.0,  # y方向平移（mm）
            'tz': 0.0,  # z方向平移（mm）
            'rx': 0.0,  # x轴旋转（度）
            'ry': 0.0,  # y轴旋转（度）
            'rz': 0.0,  # z轴旋转（度）
        }
        
        # 输出目录
        self.output_dir = None
    
    def get_true_origin_from_slices(self, dicom_files):
        """
        通过遍历所有DICOM切片，获取真实的origin
        按照DICOM的方向，找到z坐标最小的切片作为origin
        
        Args:
            dicom_files: DICOM文件路径列表
            
        Returns:
            Tuple[float, float, float]: 真实的origin坐标 (x, y, z)
        """
        try:
            self.logger.info(f"开始分析 {len(dicom_files)} 个DICOM切片以确定真实origin")
            print(f"开始分析 {len(dicom_files)} 个DICOM切片以确定真实origin")
            
            # 读取所有切片的ImagePositionPatient和其他空间信息
            slice_data = []
            
            for file_path in dicom_files:
                try:
                    dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                    if hasattr(dcm, 'ImagePositionPatient') and hasattr(dcm, 'ImageOrientationPatient'):
                        position = dcm.ImagePositionPatient
                        orientation = dcm.ImageOrientationPatient
                        
                        # 提取位置和方向信息
                        pos = [float(position[0]), float(position[1]), float(position[2])]
                        orient = [float(o) for o in orientation]
                        
                        # 保存信息
                        slice_data.append({
                            'file': file_path,
                            'position': pos,
                            'orientation': orient,
                            'instance_number': int(getattr(dcm, 'InstanceNumber', 0))
                        })
                except Exception as e:
                    self.logger.warning(f"读取DICOM文件 {file_path} 时出错: {e}")
                    continue
            
            if not slice_data:
                self.logger.warning("没有找到有效的DICOM切片空间信息")
                return None
                
            # 检查是否所有切片的方向都相同
            first_orientation = slice_data[0]['orientation']
            all_same_orientation = all(
                np.allclose(s['orientation'], first_orientation, rtol=1e-5, atol=1e-5) 
                for s in slice_data
            )
            
            if not all_same_orientation:
                self.logger.warning("警告：不是所有切片都具有相同的方向信息")
                print("警告：不是所有切片都具有相同的方向信息，将使用第一个切片的方向")
            
            # 根据方向计算z轴向量
            # ImageOrientationPatient存储为[row_x, row_y, row_z, col_x, col_y, col_z]
            row_vec = np.array(first_orientation[:3])
            col_vec = np.array(first_orientation[3:])
            
            # z轴向量是行向量和列向量的叉积
            z_vec = np.cross(row_vec, col_vec)
            
            # 归一化
            z_vec = z_vec / np.linalg.norm(z_vec)
            
            self.logger.info(f"计算得到的z轴方向向量: {z_vec}")
            print(f"计算得到的z轴方向向量: {z_vec}")
            
            # 计算每个切片位置在z轴上的投影
            for slice_info in slice_data:
                pos = np.array(slice_info['position'])
                # 计算位置在z轴上的标量投影
                z_proj = np.dot(pos, z_vec)
                slice_info['z_projection'] = z_proj
            
            # 打印所有切片的z投影，帮助调试
            print("\n切片Z轴投影值:")
            for i, s in enumerate(slice_data[:min(5, len(slice_data))]):
                print(f"切片 {i+1}/{len(slice_data)}: 位置={s['position']}, Z投影={s['z_projection']:.2f}")
            if len(slice_data) > 5:
                print(f"... 共有 {len(slice_data)} 个切片")
            
            # 按z轴投影排序
            slice_data.sort(key=lambda x: x['z_projection'])
            
            # 选择z轴投影最小的切片作为origin
            min_z_slice = slice_data[0]
            
            true_origin = min_z_slice['position']
            
            self.logger.info(f"找到的真实origin（来自z轴投影最小的切片）: {true_origin}")
            print(f"找到的真实origin: ({true_origin[0]:.2f}, {true_origin[1]:.2f}, {true_origin[2]:.2f})")
            print(f"来自文件: {os.path.basename(min_z_slice['file'])}")
            print(f"实例编号: {min_z_slice['instance_number']}")
            
            return true_origin
            
        except Exception as e:
            self.logger.error(f"获取切片真实origin时出错: {e}", exc_info=True)
            print(f"获取切片真实origin时出错: {e}")
            return None
    
    def load_directory(self, directory: str, is_fixed: bool = True) -> Tuple[bool, str, Dict]:
        """
        加载目录中的DICOM图像和结构集
        
        Args:
            directory: 包含DICOM序列的目录
            is_fixed: 是否作为固定图像加载，否则作为移动图像
            
        Returns:
            Tuple[bool, str, Dict]: (成功标志, 消息, 数据字典)
        """
        try:
            self.logger.info(f"正在加载目录: {directory}, 作为{'固定' if is_fixed else '移动'}图像")
            self.progress_updated.emit(0, f"开始加载{'固定' if is_fixed else '移动'}图像...")
            
            # 确定是加载到fixed还是moving
            data_dict = self.fixed_data if is_fixed else self.moving_data
            
            # 重置数据
            data_dict['images'] = []
            data_dict['rtss'] = None
            data_dict['image_files'] = []
            data_dict['rtss_file'] = None
            data_dict['image_info'] = {}
            data_dict['loaded'] = False
            
            # 直接列出目录中的所有文件，不进行递归
            try:
                directory_contents = os.listdir(directory)
                # 只保留文件，排除目录
                file_names = [f for f in directory_contents if os.path.isfile(os.path.join(directory, f))]
                # 计算目录中的实际文件数
                actual_file_count = len(file_names)
                # 转换为完整路径
                dicom_candidates = [os.path.join(directory, f) for f in file_names]
            except Exception as e:
                self.logger.warning(f"列出目录内容时出错: {e}")
                dicom_candidates = []
                actual_file_count = 0
            
            # 如果没有找到文件，尝试使用glob搜索
            if not dicom_candidates:
                self.logger.info(f"尝试使用glob模式搜索DICOM文件")
                for ext in ['.dcm', '.DCM', '']:
                    pattern = os.path.join(directory, f"*{ext}")
                    dicom_candidates.extend(glob.glob(pattern))
                # 过滤掉目录
                dicom_candidates = [f for f in dicom_candidates if os.path.isfile(f)]
                actual_file_count = len(dicom_candidates)
            
            if not dicom_candidates:
                msg = f"目录 {directory} 中未找到文件"
                self.logger.warning(msg)
                return False, msg, data_dict
                
            self.logger.info(f"在目录 {directory} 中找到 {actual_file_count} 个文件")
            self.progress_updated.emit(10, f"找到 {actual_file_count} 个文件")
            
            # 对找到的文件进行分类
            image_files = []
            rtss_file = None
            
            # 读取每个文件查看其SOPClassUID
            for i, file_path in enumerate(dicom_candidates):
                try:
                    # 更新进度
                    if i % 10 == 0:
                        progress = 10 + int(40 * i / len(dicom_candidates))
                        self.progress_updated.emit(progress, f"分析DICOM文件 {i+1}/{len(dicom_candidates)}...")
                    
                    dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                    
                    # 检查是否为RTSS
                    if hasattr(dcm, 'SOPClassUID') and dcm.SOPClassUID == '1.2.840.10008.5.1.4.1.1.481.3':
                        rtss_file = file_path
                        self.logger.info(f"找到RTSS文件: {file_path}")
                    # 检查是否为医学图像(CT/MR/PT)
                    elif hasattr(dcm, 'Modality') and dcm.Modality in ['CT', 'MR', 'PT']:
                        image_files.append(file_path)
                except Exception as e:
                    # 可能不是DICOM文件，忽略
                    continue
            
            # 更新数据字典
            data_dict['image_files'] = image_files
            data_dict['rtss_file'] = rtss_file
            
            # 记录有效的DICOM图像文件数
            dicom_image_count = len(image_files)
            self.logger.info(f"识别出 {dicom_image_count} 个有效的DICOM图像文件和 {1 if rtss_file else 0} 个RTSS文件")
            
            # 从DICOM切片获取真实origin
            true_origin = None
            if image_files:
                # 从所有DICOM切片获取真实origin
                self.progress_updated.emit(45, "计算DICOM序列的真实origin...")
                true_origin = self.get_true_origin_from_slices(image_files)
            
            # 加载图像文件
            if image_files:
                self.progress_updated.emit(50, "加载DICOM图像序列...")
                try:
                    reader = sitk.ImageSeriesReader()
                    reader.SetFileNames(image_files)
                    image = reader.Execute()
                    
                    # 获取SimpleITK读取的原始origin
                    sitk_origin = image.GetOrigin()
                    self.logger.info(f"SimpleITK读取的原始origin: {sitk_origin}")
                    print(f"SimpleITK读取的原始origin: {sitk_origin}")
                    
                    # 如果成功获取到了真实origin，使用它替换SimpleITK的origin
                    if true_origin:
                        self.logger.info(f"使用从DICOM切片计算的真实origin替换SimpleITK的origin")
                        print(f"替换origin: 从 {sitk_origin} 到 {true_origin}")
                        
                        # 创建一个新的图像，复制原始图像的数据和属性，但使用真实origin
                        # 获取原始图像数据
                        image_array = sitk.GetArrayFromImage(image)
                        
                        # 创建新图像
                        new_image = sitk.GetImageFromArray(image_array)
                        new_image.SetSpacing(image.GetSpacing())
                        new_image.SetDirection(image.GetDirection())
                        new_image.SetOrigin(true_origin)
                        
                        # 保存替换了origin的图像
                        data_dict['images'] = [new_image]
                        data_dict['true_origin'] = true_origin
                    else:
                        # 如果无法获取真实origin，使用SimpleITK的origin
                        self.logger.warning("无法获取真实origin，使用SimpleITK读取的origin")
                        data_dict['images'] = [image]
                        data_dict['true_origin'] = sitk_origin
                    
                    # 提取图像信息，确保file_count是实际的图像文件数量
                    data_dict['image_info'] = {
                        'size': image.GetSize(),
                        'spacing': image.GetSpacing(),
                        'origin': true_origin if true_origin else image.GetOrigin(),
                        'sitk_origin': image.GetOrigin(),  # 保存SimpleITK读取的原始origin
                        'direction': image.GetDirection(),
                        'file_count': dicom_image_count,  # 有效DICOM图像文件数
                        'actual_file_count': actual_file_count,  # 目录中的实际文件总数
                        'modality': self._get_image_modality(image_files[0])
                    }
                    
                    self.logger.info(f"成功加载图像, 尺寸={image.GetSize()}, origin={data_dict['image_info']['origin']}")
                except Exception as e:
                    msg = f"加载图像序列时出错: {e}"
                    self.logger.error(msg)
                    return False, msg, data_dict
            else:
                self.logger.warning("未找到图像文件")
            
            # 如果有RTSS，加载结构集
            if rtss_file:
                self.progress_updated.emit(80, "加载RTSS结构集...")
                try:
                    rtss_data = pydicom.dcmread(rtss_file)
                    data_dict['rtss'] = rtss_data
                    self.logger.info(f"成功加载RTSS，包含 {self._count_rtss_contours(rtss_data)} 个轮廓")
                except Exception as e:
                    self.logger.warning(f"加载RTSS时出错: {e}")
                    # 继续处理，因为可以只有图像没有结构集
            
            # 更新加载状态
            if data_dict['images']:
                data_dict['loaded'] = True
                self.progress_updated.emit(100, f"成功加载{'固定' if is_fixed else '移动'}图像")
                self.logger.info(f"成功加载{'固定' if is_fixed else '移动'}图像数据")
                
                # 发送图像加载完成信号
                data_to_emit = data_dict.copy()
                data_to_emit['is_fixed'] = is_fixed  # 添加is_fixed标志
                self.image_loaded.emit(data_to_emit)
                
                return True, "成功加载图像数据", data_dict
            else:
                msg = "未能成功加载图像数据"
                self.logger.warning(msg)
                return False, msg, data_dict
                
        except Exception as e:
            msg = f"加载目录 {directory} 时出错: {e}"
            self.logger.error(msg, exc_info=True)
            return False, msg, {}
    
    def _get_image_modality(self, dicom_file: str) -> str:
        """获取DICOM图像的模态类型"""
        try:
            dcm = pydicom.dcmread(dicom_file, force=True, stop_before_pixels=True)
            return dcm.Modality if hasattr(dcm, 'Modality') else "未知"
        except:
            return "未知"
            
    def _count_rtss_contours(self, rtss_data) -> int:
        """统计RTSS中的轮廓数量"""
        try:
            if hasattr(rtss_data, 'ROIContourSequence'):
                return len(rtss_data.ROIContourSequence)
            return 0
        except:
            return 0
            
    def get_data_summary(self, is_fixed: bool = True) -> Dict:
        """
        获取加载数据的摘要信息，用于GUI显示
        
        Args:
            is_fixed: 是否获取固定图像的摘要
            
        Returns:
            Dict: 数据摘要
        """
        data_dict = self.fixed_data if is_fixed else self.moving_data
        
        if not data_dict['loaded']:
            return {
                'loaded': False,
                'message': '未加载数据'
            }
            
        image_info = data_dict['image_info']
        
        summary = {
            'loaded': True,
            'modality': image_info.get('modality', '未知'),
            'size': image_info.get('size', (0, 0, 0)),
            'spacing': image_info.get('spacing', (0, 0, 0)),
            'slice_count': image_info.get('size', (0, 0, 0))[2],
            'file_count': image_info.get('file_count', 0),
            'has_rtss': data_dict['rtss'] is not None,
            'rtss_contour_count': self._count_rtss_contours(data_dict['rtss']) if data_dict['rtss'] else 0
        }
        
        return summary
        
    def set_transform_parameters(self, tx=0.0, ty=0.0, tz=0.0, rx=0.0, ry=0.0, rz=0.0):
        """
        设置变换参数
        
        Args:
            tx: x方向平移（mm）
            ty: y方向平移（mm）
            tz: z方向平移（mm）
            rx: x轴旋转（度）
            ry: y轴旋转（度）
            rz: z轴旋转（度）
        """
        self.transform_params = {
            'tx': float(tx),
            'ty': float(ty),
            'tz': float(tz),
            'rx': float(rx),
            'ry': float(ry),
            'rz': float(rz),
        }
        self.logger.info(f"设置变换参数: 平移=({tx}, {ty}, {tz})mm, 旋转=({rx}, {ry}, {rz})度")
    
    def perform_rigid_registration(self):
        """
        执行刚体配准，使用预设的参数将移动图像配准到固定图像
        
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        try:
            # 检查是否有输出目录
            if not hasattr(self, 'output_dir') or not self.output_dir:
                return False, "未设置输出目录，请先选择输出目录"
                
            # 获取输出选项
            output_image = True
            output_rtss = True
            
            # 执行刚体变换
            success, message = self.perform_rigid_transform(
                self.output_dir,
                output_image=output_image,
                output_rtss=output_rtss
            )
            
            return success, message
            
        except Exception as e:
            error_msg = f"执行刚体配准时出错: {e}"
            self.logger.error(error_msg, exc_info=True)
            return False, error_msg
        
    def print_debug_info(self, fixed_image, moving_image, tx, ty, tz):
        """将关键的空间信息直接打印到控制台，避免警告消息干扰"""
        print("\n\n========== 图像空间信息详细比较 ==========")
        fixed_origin = fixed_image.GetOrigin()
        moving_origin = moving_image.GetOrigin()
        
        print("--- 基本空间信息 ---")
        print(f"Fixed图像: origin=({fixed_origin[0]:.2f}, {fixed_origin[1]:.2f}, {fixed_origin[2]:.2f}), spacing={fixed_image.GetSpacing()}, size={fixed_image.GetSize()}")
        print(f"Moving图像: origin=({moving_origin[0]:.2f}, {moving_origin[1]:.2f}, {moving_origin[2]:.2f}), spacing={moving_image.GetSpacing()}, size={moving_image.GetSize()}")
        
        print("\n--- 空间差异 ---")
        origin_diff = (
            fixed_origin[0] - moving_origin[0],
            fixed_origin[1] - moving_origin[1],
            fixed_origin[2] - moving_origin[2]
        )
        print(f"原点差异(Fixed - Moving): ({origin_diff[0]:.2f}, {origin_diff[1]:.2f}, {origin_diff[2]:.2f}) mm")
        
        print("\n--- 计算的平移参数 ---")
        print(f"平移参数: tx={tx:.2f}, ty={ty:.2f}, tz={tz:.2f} mm")
        
        expected_new_origin = (
            moving_origin[0] + tx, 
            moving_origin[1] + ty, 
            moving_origin[2] + tz
        )
        
        print("\n--- 预期结果 ---")
        print(f"平移后预期新origin: ({expected_new_origin[0]:.2f}, {expected_new_origin[1]:.2f}, {expected_new_origin[2]:.2f})")
        
        expected_diff = (
            expected_new_origin[0] - fixed_origin[0],
            expected_new_origin[1] - fixed_origin[1],
            expected_new_origin[2] - fixed_origin[2]
        )
        print(f"与Fixed的origin预期差异: ({expected_diff[0]:.2f}, {expected_diff[1]:.2f}, {expected_diff[2]:.2f}) mm")
        
        # 检查Z轴差异是否特别大
        if abs(origin_diff[2]) > 500 or abs(tz) > 500:
            print("\n!!! 警告：Z轴差异非常大，可能需要特别关注 !!!")
            print(f"Z轴原点差异: {origin_diff[2]:.2f} mm")
            print(f"Z轴平移参数: {tz:.2f} mm")
            print("确保GUI的Z轴平移范围足够大（±2000mm）以容纳这个差异")
        
        print("=======================================\n")
        
    def perform_rigid_transform(self, output_dir: str, output_image=True, output_rtss=True) -> Tuple[bool, str]:
        """
        执行刚体变换，并将结果保存到指定目录
        
        Args:
            output_dir: 输出目录路径
            output_image: 是否输出变换后的图像
            output_rtss: 是否输出变换后的RTSS
            
        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        try:
            # 检查是否已加载数据
            if not (self.fixed_data['loaded'] and self.moving_data['loaded']):
                return False, "请先加载固定和移动图像数据"
                
            # 检查输出目录
            if not output_dir:
                return False, "请指定输出目录"
                
            # 确保输出目录存在
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            # 记录开始执行
            self.logger.info(f"开始执行刚体变换，参数: TX={self.transform_params['tx']}, TY={self.transform_params['ty']}, TZ={self.transform_params['tz']}, RX={self.transform_params['rx']}, RY={self.transform_params['ry']}, RZ={self.transform_params['rz']}")
            self.progress_updated.emit(5, "正在准备刚体变换...")
            
            # 提取参数
            tx = self.transform_params['tx']
            ty = self.transform_params['ty']
            tz = self.transform_params['tz']
            rx = self.transform_params['rx']
            ry = self.transform_params['ry']
            rz = self.transform_params['rz']
            
            # 准备用于存储结果的变量
            transformed_image = None
            transformed_rtss = None
            
            # 执行图像变换
            if output_image and self.moving_data['images']:
                self.progress_updated.emit(10, "正在执行图像刚体变换...")
                
                # 获取移动图像和固定图像
                moving_image = self.moving_data['images'][0]
                fixed_image = self.fixed_data['images'][0]
                
                # 获取真实origin（如果有）
                moving_true_origin = self.moving_data.get('true_origin')
                fixed_true_origin = self.fixed_data.get('true_origin')
                
                # 使用控制台打印DEBUG信息，避免被警告覆盖
                print("\n===== 执行刚体变换 =====")
                print(f"Moving图像原点: {moving_image.GetOrigin()}")
                if moving_true_origin:
                    print(f"Moving真实原点: {moving_true_origin}")
                print(f"Fixed图像原点: {fixed_image.GetOrigin()}")
                if fixed_true_origin:
                    print(f"Fixed真实原点: {fixed_true_origin}")
                print(f"变换参数: 平移=({tx}, {ty}, {tz})mm")
                
                # 创建平移变换对象
                print("\n===== 创建平移变换 =====")
                transform = self._create_rigid_transform(tx, ty, tz, rx, ry, rz)
                print(f"变换参数: {transform.GetParameters()}")
                
                # 重采样到fixed图像空间
                self.progress_updated.emit(30, "重采样到固定图像空间...")
                print("===== 开始重采样 =====")
                resampler = sitk.ResampleImageFilter()
                resampler.SetReferenceImage(fixed_image)  # 使用fixed_image的尺寸和间距
                resampler.SetInterpolator(sitk.sitkLinear)
                resampler.SetDefaultPixelValue(0)
                resampler.SetTransform(transform)
                
                transformed_image = resampler.Execute(moving_image)
                
                # 打印重采样后信息
                print("===== 重采样完成 =====")
                print(f"重采样后图像: origin={transformed_image.GetOrigin()}, spacing={transformed_image.GetSpacing()}, size={transformed_image.GetSize()}")
                print(f"与Fixed对比: origin差异={np.array(transformed_image.GetOrigin()) - np.array(fixed_image.GetOrigin())}")
                
                # 检查图像内容
                img_array = sitk.GetArrayFromImage(transformed_image)
                non_zero = np.count_nonzero(img_array)
                total_pixels = img_array.size
                print(f"图像内容: 非零像素占比 {non_zero/total_pixels*100:.2f}%")
                print(f"像素值范围: [{np.min(img_array)}, {np.max(img_array)}]")
                
                # 保存变换后的图像
                self.progress_updated.emit(40, "正在保存变换后的图像...")
                
                # 保存DICOM格式的图像
                save_success, output_path = self._save_image_as_dicom(
                    transformed_image, 
                    output_dir, 
                    "transformed_image",
                    self.moving_data['image_files'][0]
                )
                
                if not save_success:
                    self.logger.warning(f"保存图像失败: {output_path}")
                else:
                    self.logger.info(f"已保存变换后的图像到: {output_path}")
            
            # 执行RTSS变换
            if output_rtss and self.moving_data['rtss'] is not None:
                self.progress_updated.emit(60, "正在执行RTSS刚体变换...")
                
                # 获取移动RTSS
                moving_rtss = self.moving_data['rtss']
                
                # 变换RTSS
                transformed_rtss = self._transform_rtss(moving_rtss, tx, ty, tz, rx, ry, rz)
                
                # 保存变换后的RTSS
                self.progress_updated.emit(80, "正在保存变换后的RTSS...")
                
                # 保存DICOM格式的RTSS
                rtss_success, rtss_path = self._save_rtss_as_dicom(
                    transformed_rtss, 
                    output_dir, 
                    "transformed_rtss"
                )
                
                if not rtss_success:
                    self.logger.warning(f"保存RTSS失败: {rtss_path}")
                else:
                    self.logger.info(f"已保存变换后的RTSS到: {rtss_path}")
            
            # 记录成功完成
            self.progress_updated.emit(100, "刚体变换完成!")
            return True, f"成功完成刚体变换，结果已保存到 {output_dir}"
            
        except Exception as e:
            error_msg = f"执行刚体变换时出错: {e}"
            self.logger.error(error_msg, exc_info=True)
            self.progress_updated.emit(0, f"错误: {error_msg}")
            return False, error_msg
    
    def _create_rigid_transform(self, tx, ty, tz, rx, ry, rz):
        """
        创建只做平移的3D变换（不做旋转）
        Args:
            tx, ty, tz: 平移参数（毫米）
            rx, ry, rz: 保留参数，不使用
        Returns:
            sitk.Transform: SimpleITK平移变换对象
        """
        transform = sitk.TranslationTransform(3)
        transform.SetOffset((float(tx), float(ty), float(tz)))
        return transform
    
    def _apply_transform_to_image(self, image: sitk.Image, transform: sitk.Transform) -> sitk.Image:
        """
        将变换应用到图像
        
        Args:
            image: 输入图像
            transform: 变换对象
            
        Returns:
            sitk.Image: 变换后的图像
        """
        # 设置插值器
        interpolator = sitk.sitkLinear
        
        # 设置默认像素值
        default_pixel_value = 0
        
        # 获取图像信息
        size = image.GetSize()
        spacing = image.GetSpacing()
        origin = image.GetOrigin()
        direction = image.GetDirection()
        
        # 应用变换
        transformed_image = sitk.Resample(
            image, 
            size, 
            transform, 
            interpolator, 
            origin, 
            spacing, 
            direction, 
            default_pixel_value
        )
        
        return transformed_image
    
    def _transform_rtss(self, rtss_data, tx, ty, tz, rx, ry, rz) -> pydicom.Dataset:
        """
        应用平移变换到RTSS结构集（不做旋转）
        Args:
            rtss_data: RTSS DICOM数据
            tx, ty, tz: 平移参数（毫米）
            rx, ry, rz: 保留参数，不使用
        Returns:
            pydicom.Dataset: 变换后的RTSS数据
        """
        transformed_rtss = rtss_data.copy()
        def transform_point(point):
            x, y, z = point
            return (x + tx, y + ty, z + tz)
        if not hasattr(transformed_rtss, 'ROIContourSequence'):
            return transformed_rtss
        for roi_contour in transformed_rtss.ROIContourSequence:
            if not hasattr(roi_contour, 'ContourSequence'):
                continue
            for contour in roi_contour.ContourSequence:
                if not hasattr(contour, 'ContourData') or contour.ContourData is None:
                    continue
                contour_data = contour.ContourData
                num_points = len(contour_data) // 3
                transformed_points = []
                for i in range(num_points):
                    x = float(contour_data[i*3])
                    y = float(contour_data[i*3 + 1])
                    z = float(contour_data[i*3 + 2])
                    x_new, y_new, z_new = transform_point((x, y, z))
                    transformed_points.extend([x_new, y_new, z_new])
                contour.ContourData = transformed_points
        return transformed_rtss
    
    def _save_image_as_dicom(self, image: sitk.Image, output_dir: str, base_name: str, reference_dicom_file: str) -> Tuple[bool, str]:
        """
        将图像保存为DICOM格式，只继承第一个参考DICOM的全局关键信息，重建像素和空间信息。
        保证所有图像切片属于同一序列，能被DICOM查看器作为一个序列加载。
        使用正确的origin计算每个切片的ImagePositionPatient。
        """
        try:
            image_output_dir = os.path.join(output_dir, base_name)
            if not os.path.exists(image_output_dir):
                os.makedirs(image_output_dir)
                
            image_array = sitk.GetArrayFromImage(image)
            size = image.GetSize()
            spacing = image.GetSpacing()
            origin = image.GetOrigin()
            direction = image.GetDirection()
            num_slices = image_array.shape[0]

            # 读取第一个参考DICOM，提取全局信息
            ref_dcm = pydicom.dcmread(reference_dicom_file, force=True)
            
            # 记录原始模态信息
            original_modality = ref_dcm.get('Modality', 'CT')
            self.logger.info(f"原始图像模态: {original_modality}")
            print(f"原始图像模态: {original_modality}")
            
            # 打印origin信息用于调试
            print(f"\n===== 保存DICOM图像 =====")
            print(f"图像origin: {origin}")
            print(f"方向矩阵: {direction}")
            print(f"切片数量: {num_slices}")

            # 要保留的全局关键标签列表
            # 确保包含所有序列相关标签
            global_tags = [
                'PatientName', 'PatientID', 'PatientBirthDate', 'PatientSex',
                'StudyInstanceUID', 'StudyDate', 'StudyTime', 'StudyID',
                'AccessionNumber', 'ReferringPhysicianName', 
                'StationName', 'StudyDescription', 'InstitutionName'
            ]
            
            # 生成一个新的Series UID 和 Frame of Reference UID，所有切片共用
            new_series_uid = pydicom.uid.generate_uid()
            new_frame_of_reference_uid = pydicom.uid.generate_uid()
            series_number = getattr(ref_dcm, 'SeriesNumber', 1000)
            series_description = f"Transformed_{getattr(ref_dcm, 'SeriesDescription', base_name)}"
            
            # 确定Modality和SOPClassUID
            modality = original_modality
            if modality == 'PT' or 'PET' in str(getattr(ref_dcm, 'SeriesDescription', '')).upper():
                sop_class_uid = '1.2.840.10008.5.1.4.1.1.128'  # PET Image Storage
                modality = 'PT'  # 确保使用标准模态代码
            elif modality == 'CT':
                sop_class_uid = '1.2.840.10008.5.1.4.1.1.2'  # CT Image Storage
            else:
                sop_class_uid = '1.2.840.10008.5.1.4.1.1.2'  # 默认为CT Image Storage
                
            self.logger.info(f"使用模态: {modality}, SOPClassUID: {sop_class_uid}")
            print(f"使用模态: {modality}, SOPClassUID: {sop_class_uid}")
            print(f"新序列UID: {new_series_uid}")
            print(f"新帧参考UID: {new_frame_of_reference_uid}")
                
            # 以升序命名文件，确保DICOM浏览器能正确排序
            # 使用统一的命名前缀，许多PACS系统依赖这种命名约定识别序列
            file_prefix = "IM"  # 标准DICOM命名前缀
            
            # 计算所有切片的ImagePositionPatient，并按Z位置排序
            slice_positions = []
            for i in range(num_slices):
                position = self.compute_image_position(origin, direction, i, spacing)
                # 仅使用Z坐标进行排序
                slice_positions.append((i, position, position[2]))
                if i < 3 or i >= num_slices - 3:
                    print(f"切片 {i}: 位置={position}")
            
            # 按Z位置排序，确保切片按解剖位置排序
            slice_positions.sort(key=lambda x: x[2])
            slice_order = [idx for idx, _, _ in slice_positions]
            is_ascending = slice_positions[0][2] < slice_positions[-1][2]
            
            self.logger.info(f"保存DICOM序列，切片数: {num_slices}，顺序方向: {'升序' if is_ascending else '降序'}")
            print(f"切片顺序方向: {'升序' if is_ascending else '降序'}")
            
            # 保存每个切片
            for slice_idx, (original_idx, position, _) in enumerate(slice_positions):
                # 创建新的DICOM对象
                dcm = pydicom.Dataset()
                
                # 复制全局标签
                for tag in global_tags:
                    if hasattr(ref_dcm, tag):
                        setattr(dcm, tag, getattr(ref_dcm, tag))
                
                # 设置序列相关信息 - 所有切片必须共享这些值
                dcm.SeriesInstanceUID = new_series_uid
                dcm.SeriesDescription = series_description
                dcm.SeriesNumber = series_number
                dcm.SeriesDate = getattr(ref_dcm, 'SeriesDate', getattr(ref_dcm, 'StudyDate', ''))
                dcm.SeriesTime = getattr(ref_dcm, 'SeriesTime', getattr(ref_dcm, 'StudyTime', ''))
                
                # 设置模态信息
                dcm.Modality = modality
                
                # 设置SOPClassUID和MediaStorageSOPClassUID
                dcm.SOPClassUID = sop_class_uid
                
                # 设置file_meta信息
                dcm.file_meta = pydicom.Dataset()
                dcm.file_meta.MediaStorageSOPClassUID = sop_class_uid
                dcm.SOPInstanceUID = pydicom.uid.generate_uid()
                dcm.file_meta.MediaStorageSOPInstanceUID = dcm.SOPInstanceUID
                dcm.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
                dcm.file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
                
                # 设置FrameOfReferenceUID - 所有切片必须共享此值
                dcm.FrameOfReferenceUID = new_frame_of_reference_uid
                
                # 设置图像类型
                dcm.ImageType = ["DERIVED", "SECONDARY"]
                
                # 设置图像空间信息
                dcm.Rows = size[1]
                dcm.Columns = size[0]
                dcm.PixelSpacing = [spacing[1], spacing[0]]
                dcm.SliceThickness = spacing[2]
                dcm.SpacingBetweenSlices = spacing[2]
                
                # 使用预先计算的位置信息
                dcm.ImagePositionPatient = [float(v) for v in position]
                
                # 设置图像方向
                image_orientation = [direction[0], direction[3], direction[6], direction[1], direction[4], direction[7]]
                dcm.ImageOrientationPatient = [float(v) for v in image_orientation]
                
                # 设置切片位置
                dcm.SliceLocation = float(position[2])
                
                # 设置实例编号 - 按切片顺序递增，从1开始
                dcm.InstanceNumber = slice_idx + 1
                
                # 设置切片数据
                slice_data = image_array[original_idx, :, :]
                
                # 根据需要调整数据类型
                pixels_min = np.min(slice_data)
                pixels_max = np.max(slice_data)
                
                # 设置窗宽窗位
                if hasattr(ref_dcm, 'WindowCenter') and hasattr(ref_dcm, 'WindowWidth'):
                    dcm.WindowCenter = ref_dcm.WindowCenter
                    dcm.WindowWidth = ref_dcm.WindowWidth
                else:
                    dcm.WindowCenter = (pixels_max + pixels_min) // 2
                    dcm.WindowWidth = pixels_max - pixels_min
                
                # 如果图像数据范围较小，可以使用16位整数
                if pixels_min >= -32768 and pixels_max <= 32767:
                    # 使用16位有符号整数
                    slice_data = slice_data.astype(np.int16)
                    dcm.BitsAllocated = 16
                    dcm.BitsStored = 16
                    dcm.HighBit = 15
                    dcm.PixelRepresentation = 1  # 有符号整数
                else:
                    # 否则使用32位浮点数，需要转换为DICOM支持的格式
                    # 找到合适的缩放比例
                    if pixels_min != pixels_max:
                        rescale_slope = (pixels_max - pixels_min) / 65534
                        rescale_intercept = pixels_min
                        # 使用缩放来适应16位范围
                        rescaled_data = (slice_data - rescale_intercept) / rescale_slope
                        # 四舍五入并限制在合理范围内
                        slice_data = np.clip(np.round(rescaled_data), 0, 65535).astype(np.uint16)
                        dcm.RescaleSlope = float(rescale_slope)
                        dcm.RescaleIntercept = float(rescale_intercept)
                    else:
                        # 如果所有像素值相同
                        slice_data = np.zeros_like(slice_data, dtype=np.uint16)
                        dcm.RescaleSlope = 1.0
                        dcm.RescaleIntercept = pixels_min
                    
                    dcm.BitsAllocated = 16
                    dcm.BitsStored = 16
                    dcm.HighBit = 15
                    dcm.PixelRepresentation = 0  # 无符号整数
                
                # 设置像素数据
                dcm.SamplesPerPixel = 1
                dcm.PhotometricInterpretation = "MONOCHROME2"
                dcm.PixelData = slice_data.tobytes()
                
                # 使用标准的DICOM文件命名约定，确保切片能正确排序
                output_file = os.path.join(image_output_dir, f"{file_prefix}{slice_idx+1:04d}.dcm")
                dcm.save_as(output_file)
                
                # 打印前几个和最后几个切片的信息
                if slice_idx < 3 or slice_idx >= num_slices - 3:
                    print(f"保存切片 {slice_idx+1}/{num_slices}: 位置={position}, 文件={os.path.basename(output_file)}")
            
            self.logger.info(f"成功将图像保存为DICOM序列，共 {num_slices} 个切片，保存到 {image_output_dir}")
            print(f"成功将图像保存为DICOM序列，共 {num_slices} 个切片，保存到 {image_output_dir}")
            print(f"所有切片共享同一SeriesInstanceUID: {new_series_uid}")
            return True, image_output_dir
            
        except Exception as e:
            error_msg = f"保存DICOM图像时出错: {e}"
            self.logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def _save_rtss_as_dicom(self, rtss_data, output_dir: str, base_name: str) -> Tuple[bool, str]:
        """
        将RTSS保存为DICOM文件
        
        Args:
            rtss_data: RTSS DICOM数据
            output_dir: 输出目录
            base_name: 基础文件名
            
        Returns:
            Tuple[bool, str]: (成功标志, 输出路径或错误消息)
        """
        try:
            # 确保输出目录存在
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            # 创建输出文件路径
            output_file = os.path.join(output_dir, f"{base_name}.dcm")
            
            # 保存RTSS文件
            rtss_data.save_as(output_file, enforce_file_format=False)
            
            self.logger.info(f"已成功保存RTSS文件到: {output_file}")
            return True, output_file
            
        except Exception as e:
            error_msg = f"保存RTSS文件时出错: {e}"
            self.logger.error(error_msg, exc_info=True)
            return False, error_msg
        
    def calculate_centroid_from_rtss(self, rtss_data) -> Union[Tuple[float, float, float], None]:
        """
        计算RTSS中所有轮廓的质心
        
        Args:
            rtss_data: RTSS DICOM数据
            
        Returns:
            Tuple[float, float, float]: 质心坐标 (x, y, z) 或 None (如果计算失败)
        """
        try:
            if not rtss_data or not hasattr(rtss_data, 'ROIContourSequence'):
                self.logger.warning("RTSS数据不存在或没有轮廓序列")
                return None
                
            # 所有轮廓点的列表
            all_points = []
            
            # 遍历所有ROI轮廓
            for roi_contour in rtss_data.ROIContourSequence:
                if not hasattr(roi_contour, 'ContourSequence'):
                    continue
                    
                # 遍历每个轮廓的每个切片
                for contour in roi_contour.ContourSequence:
                    if not hasattr(contour, 'ContourData') or contour.ContourData is None:
                        continue
                        
                    # 获取轮廓点（每3个数值为一个点的x,y,z坐标）
                    contour_data = contour.ContourData
                    num_points = len(contour_data) // 3
                    
                    for i in range(num_points):
                        x = float(contour_data[i*3])
                        y = float(contour_data[i*3 + 1])
                        z = float(contour_data[i*3 + 2])
                        all_points.append((x, y, z))
            
            if not all_points:
                self.logger.warning("未找到有效的轮廓点")
                return None
                
            # 计算质心
            centroid_x = sum(p[0] for p in all_points) / len(all_points)
            centroid_y = sum(p[1] for p in all_points) / len(all_points)
            centroid_z = sum(p[2] for p in all_points) / len(all_points)
            
            self.logger.info(f"计算得到质心坐标: ({centroid_x}, {centroid_y}, {centroid_z})")
            return (centroid_x, centroid_y, centroid_z)
            
        except Exception as e:
            self.logger.error(f"计算质心时出错: {e}", exc_info=True)
            return None
            
    def calculate_transform_from_centroids(self) -> Tuple[bool, str, Dict]:
        """
        根据固定和移动RTSS的质心差异，计算刚体变换参数
        注意：平移应该是把moving图像变换到fixed图像位置
        
        Returns:
            Tuple[bool, str, Dict]: (成功标志, 消息, 变换参数字典)
        """
        try:
            # 检查是否已加载数据
            if not (self.fixed_data['loaded'] and self.moving_data['loaded']):
                return False, "请先加载固定和移动图像数据", {}
                
            # 检查是否有RTSS
            if not (self.fixed_data['rtss'] and self.moving_data['rtss']):
                return False, "固定和移动图像数据必须都包含RTSS", {}
                
            # 计算固定图像的RTSS质心
            fixed_centroid = self.calculate_centroid_from_rtss(self.fixed_data['rtss'])
            if fixed_centroid is None:
                return False, "无法计算固定图像RTSS的质心", {}
                
            # 计算移动图像的RTSS质心
            moving_centroid = self.calculate_centroid_from_rtss(self.moving_data['rtss'])
            if moving_centroid is None:
                return False, "无法计算移动图像RTSS的质心", {}
                
            # 获取固定和移动图像的原点
            fixed_image = self.fixed_data['images'][0]
            moving_image = self.moving_data['images'][0]
            fixed_origin = fixed_image.GetOrigin()
            moving_origin = moving_image.GetOrigin()
            
            # 详细打印原始值
            print("\n【图像原点】")
            print(f"Fixed图像原点: X={fixed_origin[0]:.2f}, Y={fixed_origin[1]:.2f}, Z={fixed_origin[2]:.2f}")
            print(f"Moving图像原点: X={moving_origin[0]:.2f}, Y={moving_origin[1]:.2f}, Z={moving_origin[2]:.2f}")
            print(f"!!! Z轴值: Fixed Z={fixed_origin[2]:.2f}, Moving Z={moving_origin[2]:.2f}")
            
            print("\n【轮廓质心】")
            print(f"Fixed轮廓质心: X={fixed_centroid[0]:.2f}, Y={fixed_centroid[1]:.2f}, Z={fixed_centroid[2]:.2f}")
            print(f"Moving轮廓质心: X={moving_centroid[0]:.2f}, Y={moving_centroid[1]:.2f}, Z={moving_centroid[2]:.2f}")
            
            # 计算将Moving图像变换到Fixed图像需要的参数
            # 原点差异 (Moving需要向哪个方向移动才能让原点对齐)
            # 正确方向: Fixed - Moving (表示Moving需要增加多少才能等于Fixed)
            origin_diff_x = fixed_origin[0] - moving_origin[0]
            origin_diff_y = fixed_origin[1] - moving_origin[1] 
            origin_diff_z = fixed_origin[2] - moving_origin[2]  # Z轴可能有很大的差异
            
            print("\n【原点差异】(Fixed - Moving)")
            print(f"X轴原点差异: {origin_diff_x:.2f}mm")
            print(f"Y轴原点差异: {origin_diff_y:.2f}mm")
            print(f"Z轴原点差异: {origin_diff_z:.2f}mm")
            
            # 质心差异 (将Moving轮廓配准到Fixed轮廓的平移量)
            centroid_diff_x = fixed_centroid[0] - moving_centroid[0]
            centroid_diff_y = fixed_centroid[1] - moving_centroid[1]
            centroid_diff_z = fixed_centroid[2] - moving_centroid[2]
            
            print("\n【质心差异】")
            print(f"X轴质心差异: {centroid_diff_x:.2f}mm")
            print(f"Y轴质心差异: {centroid_diff_y:.2f}mm")
            print(f"Z轴质心差异: {centroid_diff_z:.2f}mm")
            
            # 计算总平移量
            tx = centroid_diff_x + origin_diff_x
            ty = centroid_diff_y + origin_diff_y
            tz = centroid_diff_z + origin_diff_z
            
            print("\n【平移计算】")
            print(f"X平移 = 质心差异({centroid_diff_x:.2f}) + 原点差异({origin_diff_x:.2f}) = {tx:.2f}mm")
            print(f"Y平移 = 质心差异({centroid_diff_y:.2f}) + 原点差异({origin_diff_y:.2f}) = {ty:.2f}mm")
            print(f"Z平移 = 质心差异({centroid_diff_z:.2f}) + 原点差异({origin_diff_z:.2f}) = {tz:.2f}mm")
            
            # 检查大偏移并警告
            if abs(origin_diff_z) > 500 or abs(tz) > 500:
                print(f"\n!!! 警告: Z轴有大幅偏移 !!!")
                print(f"Z轴移动: {tz:.2f}mm (从{moving_origin[2]:.2f}移动到约{moving_origin[2]+tz:.2f})")
                print(f"这将使Moving Z轴从{moving_origin[2]:.2f}变为{moving_origin[2]+tz:.2f}，而Fixed Z轴是{fixed_origin[2]:.2f}")
                print(f"确保GUI的Z轴平移范围设置为±2000mm")
            
            # 计算移动后的预期结果
            predicted_new_origin = (
                moving_origin[0] + tx,
                moving_origin[1] + ty,
                moving_origin[2] + tz
            )
            
            print("\n【预测结果检验】")
            print(f"移动后的预期原点: ({predicted_new_origin[0]:.2f}, {predicted_new_origin[1]:.2f}, {predicted_new_origin[2]:.2f})")
            print(f"Fixed目标原点: ({fixed_origin[0]:.2f}, {fixed_origin[1]:.2f}, {fixed_origin[2]:.2f})")
            print(f"与Fixed原点的偏差: ({predicted_new_origin[0]-fixed_origin[0]:.2f}, {predicted_new_origin[1]-fixed_origin[1]:.2f}, {predicted_new_origin[2]-fixed_origin[2]:.2f})")
            
            # 配置变换参数
            rx, ry, rz = 0.0, 0.0, 0.0  # 默认不旋转
            transform_params = {
                'tx': tx, 'ty': ty, 'tz': tz,
                'rx': rx, 'ry': ry, 'rz': rz
            }
            
            # 更新变换参数
            self.set_transform_parameters(tx, ty, tz, rx, ry, rz)
            
            # 记录并返回结果
            self.logger.info(f"计算得到变换参数: 平移=({tx:.2f}, {ty:.2f}, {tz:.2f})mm")
            return True, f"已计算变换参数: 平移=({tx:.2f}, {ty:.2f}, {tz:.2f})mm", transform_params
            
        except Exception as e:
            error_msg = f"计算变换参数时出错: {e}"
            self.logger.error(error_msg, exc_info=True)
            return False, error_msg, {}

    def compute_image_position(self, origin, direction, slice_number, spacing):
        """
        计算DICOM切片的ImagePositionPatient值
        
        Args:
            origin: 图像原点坐标
            direction: 图像方向余弦矩阵
            slice_number: 切片索引
            spacing: 图像间距
            
        Returns:
            List[float]: 切片的ImagePositionPatient值
        """
        # 将方向矩阵转换为3x3数组
        direction_mat = np.array(direction).reshape(3, 3)
        
        # 计算Z方向的单位向量
        # 方向矩阵的第三列表示Z方向
        z_unit = np.array([direction_mat[0, 2], direction_mat[1, 2], direction_mat[2, 2]])
        
        # 归一化Z方向向量（确保是单位向量）
        z_norm = np.linalg.norm(z_unit)
        if z_norm > 0:
            z_unit = z_unit / z_norm
        
        # 计算当前切片的偏移量
        offset = slice_number * spacing[2] * z_unit
        
        # 计算最终位置
        position = np.array(origin) + offset
        
        return position.tolist()