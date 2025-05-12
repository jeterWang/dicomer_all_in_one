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
            
            # 加载图像文件
            if image_files:
                self.progress_updated.emit(50, "加载DICOM图像序列...")
                try:
                    reader = sitk.ImageSeriesReader()
                    reader.SetFileNames(image_files)
                    image = reader.Execute()
                    data_dict['images'] = [image]  # 将图像添加到列表
                    
                    # 提取图像信息，确保file_count是实际的图像文件数量
                    data_dict['image_info'] = {
                        'size': image.GetSize(),
                        'spacing': image.GetSpacing(),
                        'origin': image.GetOrigin(),
                        'direction': image.GetDirection(),
                        'file_count': dicom_image_count,  # 有效DICOM图像文件数
                        'actual_file_count': actual_file_count,  # 目录中的实际文件总数
                        'modality': self._get_image_modality(image_files[0])
                    }
                    
                    self.logger.info(f"成功加载图像, 尺寸={image.GetSize()}")
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
                
                # 获取移动图像
                moving_image = self.moving_data['images'][0]
                
                # 创建刚体变换
                transform = self._create_rigid_transform(tx, ty, tz, rx, ry, rz)
                
                # 应用变换到图像
                transformed_image = self._apply_transform_to_image(moving_image, transform)
                
                # 保存变换后的图像
                self.progress_updated.emit(40, "正在保存变换后的图像...")
                
                # 保存DICOM格式的图像
                save_success, output_path = self._save_image_as_dicom(
                    transformed_image, 
                    output_dir, 
                    "transformed_image"
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
    
    def _create_rigid_transform(self, tx, ty, tz, rx, ry, rz) -> sitk.Transform:
        """
        创建刚体变换
        
        Args:
            tx, ty, tz: 平移参数（毫米）
            rx, ry, rz: 旋转参数（度）
            
        Returns:
            sitk.Transform: SimpleITK变换对象
        """
        # 创建3D刚体变换
        transform = sitk.Euler3DTransform()
        
        # 设置平移参数（毫米）
        transform.SetTranslation((float(tx), float(ty), float(tz)))
        
        # 设置旋转参数（弧度）
        # SimpleITK需要弧度，所以要将度转换为弧度
        rx_rad = float(rx) * np.pi / 180.0
        ry_rad = float(ry) * np.pi / 180.0
        rz_rad = float(rz) * np.pi / 180.0
        
        # 设置旋转中心为图像中心
        transform.SetRotation(rx_rad, ry_rad, rz_rad)
        
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
        应用刚体变换到RTSS结构集
        
        Args:
            rtss_data: RTSS DICOM数据
            tx, ty, tz: 平移参数（毫米）
            rx, ry, rz: 旋转参数（度）
            
        Returns:
            pydicom.Dataset: 变换后的RTSS数据
        """
        # 创建一个RTSS的副本
        transformed_rtss = rtss_data.copy()
        
        # 定义变换函数
        def transform_point(point):
            # 提取点坐标
            x, y, z = point
            
            # 应用旋转（首先计算旋转矩阵）
            # 将度转换为弧度
            rx_rad = rx * np.pi / 180.0
            ry_rad = ry * np.pi / 180.0
            rz_rad = rz * np.pi / 180.0
            
            # 计算旋转矩阵（这里使用ZYX欧拉角顺序）
            # 绕X轴旋转
            cx, sx = np.cos(rx_rad), np.sin(rx_rad)
            Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
            
            # 绕Y轴旋转
            cy, sy = np.cos(ry_rad), np.sin(ry_rad)
            Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            
            # 绕Z轴旋转
            cz, sz = np.cos(rz_rad), np.sin(rz_rad)
            Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
            
            # 组合旋转矩阵（ZYX顺序）
            R = Rx @ Ry @ Rz
            
            # 将点转换为numpy数组
            p = np.array([x, y, z])
            
            # 应用旋转
            p_rotated = R @ p
            
            # 应用平移
            p_transformed = p_rotated + np.array([tx, ty, tz])
            
            return p_transformed
        
        # 如果没有轮廓序列，直接返回
        if not hasattr(transformed_rtss, 'ROIContourSequence'):
            return transformed_rtss
            
        # 遍历所有ROI轮廓
        for roi_contour in transformed_rtss.ROIContourSequence:
            if not hasattr(roi_contour, 'ContourSequence'):
                continue
                
            # 遍历每个轮廓的每个切片
            for contour in roi_contour.ContourSequence:
                if not hasattr(contour, 'ContourData') or contour.ContourData is None:
                    continue
                    
                # 获取轮廓点（每3个数值为一个点的x,y,z坐标）
                contour_data = contour.ContourData
                num_points = len(contour_data) // 3
                
                # 变换每个点
                transformed_points = []
                for i in range(num_points):
                    x = float(contour_data[i*3])
                    y = float(contour_data[i*3 + 1])
                    z = float(contour_data[i*3 + 2])
                    
                    # 应用变换
                    x_new, y_new, z_new = transform_point((x, y, z))
                    
                    # 添加变换后的点
                    transformed_points.extend([x_new, y_new, z_new])
                
                # 更新轮廓数据
                contour.ContourData = transformed_points
        
        return transformed_rtss
    
    def _save_image_as_dicom(self, image: sitk.Image, output_dir: str, base_name: str) -> Tuple[bool, str]:
        """
        将图像保存为DICOM格式
        
        Args:
            image: 要保存的图像
            output_dir: 输出目录
            base_name: 基础文件名
            
        Returns:
            Tuple[bool, str]: (成功标志, 输出路径或错误消息)
        """
        try:
            # 确保输出目录存在
            image_output_dir = os.path.join(output_dir, base_name)
            if not os.path.exists(image_output_dir):
                os.makedirs(image_output_dir)
                
            # 获取图像信息
            image_array = sitk.GetArrayFromImage(image)
            size = image.GetSize()
            spacing = image.GetSpacing()
            origin = image.GetOrigin()
            direction = image.GetDirection()
            
            # 为PET图像设置默认的位深度
            bits_allocated = 16
            bits_stored = 16
            high_bit = 15
            
            # 计算图像的窗位窗宽
            min_val = np.min(image_array)
            max_val = np.max(image_array)
            window_center = (max_val + min_val) / 2
            window_width = max_val - min_val
            
            # 准备DICOM元数据
            import pydicom
            from pydicom.dataset import FileDataset, FileMetaDataset
            from datetime import datetime
            
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
            
            # 为每个切片创建和保存DICOM文件
            num_slices = image_array.shape[0]
            for i in range(num_slices):
                # 更新进度
                if num_slices > 10 and i % (num_slices // 10) == 0:
                    self.progress_updated.emit(40 + int(i * 20 / num_slices), f"正在保存图像切片 {i+1}/{num_slices}...")
                
                # 创建文件名
                output_file = os.path.join(image_output_dir, f"slice_{i:04d}.dcm")
                
                # 创建文件元信息
                file_meta = FileMetaDataset()
                file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.2'  # CT图像存储
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
                ds.StudyDescription = "Rigid Transform Study"
                ds.SeriesDescription = "Rigid Transformed Image"
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
                ds.Modality = "CT"  # 默认为CT
                ds.ImageType = ["DERIVED", "SECONDARY", "TRANSFORMED"]
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
                
                # 设置缩放参数
                ds.RescaleSlope = 1.0
                ds.RescaleIntercept = 0.0
                
                # 根据图像数据类型，设置像素数据
                slice_data = image_array[i].astype(np.uint16)  # 使用16位无符号整数
                ds.PixelData = slice_data.tobytes()
                
                # 保存DICOM文件
                ds.save_as(output_file, write_like_original=False)
            
            self.logger.info(f"已成功将图像保存为DICOM序列，共 {num_slices} 个切片，保存到 {image_output_dir}")
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
            rtss_data.save_as(output_file)
            
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
                
            # 计算平移差异
            tx = fixed_centroid[0] - moving_centroid[0]
            ty = fixed_centroid[1] - moving_centroid[1]
            tz = fixed_centroid[2] - moving_centroid[2]
            
            # 目前我们只计算平移，不计算旋转
            # 旋转需要更复杂的计算，通常需要点云配准算法来完成
            transform_params = {
                'tx': tx,
                'ty': ty,
                'tz': tz,
                'rx': 0.0,
                'ry': 0.0,
                'rz': 0.0
            }
            
            # 更新变换参数
            self.set_transform_parameters(tx, ty, tz, 0, 0, 0)
            
            # 记录并返回结果
            self.logger.info(f"根据质心差异计算得到变换参数: 平移=({tx}, {ty}, {tz})mm")
            return True, f"已根据质心差异计算变换参数: 平移=({tx:.2f}, {ty:.2f}, {tz:.2f})mm", transform_params
            
        except Exception as e:
            msg = f"计算变换参数时出错: {e}"
            self.logger.error(msg, exc_info=True)
            return False, msg, {} 