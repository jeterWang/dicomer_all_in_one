import os
import logging
import numpy as np
import nibabel as nib
import pydicom
from pathlib import Path
from typing import List, Dict, Any, Optional
import SimpleITK as sitk
from datetime import datetime


class DRMConverter:
    """DRM转换器：将NII.gz文件转换为DICOM series格式"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def read_nii_file(self, nii_path: str) -> tuple:
        """
        读取NII.gz文件
        
        Args:
            nii_path: NII.gz文件路径
            
        Returns:
            tuple: (image_data, affine_matrix, header)
        """
        try:
            self.logger.info(f"开始读取NII文件: {nii_path}")
            nii_img = nib.load(nii_path)
            
            # 获取基本信息
            self.logger.info(f"NII文件加载成功，准备读取数据...")
            image_data = nii_img.get_fdata()
            affine = nii_img.affine
            header = nii_img.header
            
            self.logger.info(f"成功读取NII文件: {nii_path}")
            self.logger.info(f"图像尺寸: {image_data.shape}")
            self.logger.info(f"数据类型: {image_data.dtype}")
            self.logger.info(f"数据范围: {image_data.min():.6f} 到 {image_data.max():.6f}")
            self.logger.info(f"内存使用: {image_data.nbytes / 1024 / 1024:.2f} MB")
            
            # 检查数据有效性
            if image_data.size == 0:
                raise ValueError("NII文件包含空数据")
                
            return image_data, affine, header
            
        except Exception as e:
            self.logger.error(f"读取NII文件失败: {e}")
            raise
    
    def read_ct_dicom_template(self, ct_folder_path: str) -> Dict[str, Any]:
        """
        读取CT DICOM文件作为模板，获取头文件信息
        
        Args:
            ct_folder_path: CT DICOM文件夹路径
            
        Returns:
            Dict: DICOM模板信息
        """
        try:
            self.logger.info(f"开始读取CT模板目录: {ct_folder_path}")
            
            if not os.path.exists(ct_folder_path):
                raise ValueError(f"CT目录不存在: {ct_folder_path}")
            
            # 先获取文件列表
            all_files = os.listdir(ct_folder_path)
            ct_files = [f for f in all_files if f.endswith('.dcm')]
            
            if not ct_files:
                raise ValueError(f"在{ct_folder_path}中未找到DICOM文件")
            
            self.logger.info(f"找到{len(ct_files)}个DICOM文件")
            
            # 读取第一个DICOM文件作为模板
            template_path = os.path.join(ct_folder_path, ct_files[0])
            self.logger.info(f"读取模板文件: {os.path.basename(template_path)}")
            
            try:
                template_ds = pydicom.dcmread(template_path)
                self.logger.info(f"模板文件读取成功")
            except Exception as e:
                self.logger.error(f"读取模板文件失败: {e}")
                raise
            
            # 分批读取DICOM文件获取z坐标信息，避免内存问题
            dicom_info = []
            self.logger.info("开始分析DICOM文件的位置信息...")
            
            batch_size = 50  # 每批处理50个文件
            processed_count = 0
            
            for i in range(0, len(ct_files), batch_size):
                batch_files = ct_files[i:i + batch_size]
                
                for j, dcm_file in enumerate(batch_files):
                    try:
                        dcm_path = os.path.join(ct_folder_path, dcm_file)
                        
                        # 只读取必要的标签，节省内存
                        ds = pydicom.dcmread(dcm_path, stop_before_pixels=True)
                        
                        if hasattr(ds, 'ImagePositionPatient'):
                            z_pos = float(ds.ImagePositionPatient[2])
                            dicom_info.append({
                                'filename': dcm_file,
                                'z_position': z_pos,
                                'instance_number': int(ds.InstanceNumber) if hasattr(ds, 'InstanceNumber') else 0
                            })
                        
                        processed_count += 1
                        
                        # 每50个文件报告一次进度
                        if processed_count % 50 == 0:
                            self.logger.info(f"已处理 {processed_count}/{len(ct_files)} 个DICOM文件")
                            
                    except Exception as e:
                        self.logger.warning(f"跳过无效的DICOM文件 {dcm_file}: {e}")
                        continue
                
                # 每批处理后清理内存
                if i > 0:  # 第一批不需要清理
                    import gc
                    gc.collect()
            
            if not dicom_info:
                raise ValueError(f"在{ct_folder_path}中未找到有效的DICOM文件")
            
            # 按z坐标排序
            self.logger.info("排序DICOM切片...")
            dicom_info.sort(key=lambda x: x['z_position'])
            
            self.logger.info(f"成功读取CT模板: {os.path.basename(template_path)}")
            self.logger.info(f"有效DICOM切片数: {len(dicom_info)}")
            
            if dicom_info:
                z_range = dicom_info[-1]['z_position'] - dicom_info[0]['z_position']
                self.logger.info(f"Z轴范围: {dicom_info[0]['z_position']:.3f} 到 {dicom_info[-1]['z_position']:.3f} (总计 {z_range:.3f}mm)")
            
            return {
                'template': template_ds,
                'dicom_info': dicom_info,
                'ct_folder_path': ct_folder_path
            }
            
        except Exception as e:
            self.logger.error(f"读取CT DICOM模板失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            raise
    
    def create_series_uids(self, template_ds: pydicom.Dataset) -> Dict[str, str]:
        """
        创建新的series相关的UID，确保所有切片属于同一个series
        
        Args:
            template_ds: 模板DICOM数据集
            
        Returns:
            Dict: 包含各种UID的字典
        """
        # 生成新的UID
        new_series_instance_uid = pydicom.uid.generate_uid()
        new_study_instance_uid = template_ds.StudyInstanceUID if hasattr(template_ds, 'StudyInstanceUID') else pydicom.uid.generate_uid()
        new_frame_of_reference_uid = template_ds.FrameOfReferenceUID if hasattr(template_ds, 'FrameOfReferenceUID') else pydicom.uid.generate_uid()
        
        return {
            'series_instance_uid': new_series_instance_uid,
            'study_instance_uid': new_study_instance_uid,
            'frame_of_reference_uid': new_frame_of_reference_uid
        }
    
    def create_dicom_header(self, template_ds: pydicom.Dataset, 
                          slice_index: int, total_slices: int,
                          drm_data_slice: np.ndarray,
                          z_position: float,
                          series_uids: Dict[str, str]) -> pydicom.Dataset:
        """
        基于模板创建新的DICOM头文件
        
        Args:
            template_ds: 模板DICOM数据集
            slice_index: 当前切片索引
            total_slices: 总切片数
            drm_data_slice: DRM数据切片
            z_position: Z轴位置
            series_uids: series相关的UID字典
            
        Returns:
            pydicom.Dataset: 新的DICOM数据集
        """
        # 创建新的数据集
        new_ds = pydicom.Dataset()
        
        # 复制基本信息（排除像素数据和file_meta相关的元素）
        exclude_tags = [
            pydicom.tag.Tag('7fe0', '0010'),  # 像素数据
            pydicom.tag.Tag('0002', '0000'),  # File Meta Information Group Length
            pydicom.tag.Tag('0002', '0001'),  # File Meta Information Version
            pydicom.tag.Tag('0002', '0002'),  # Media Storage SOP Class UID
            pydicom.tag.Tag('0002', '0003'),  # Media Storage SOP Instance UID
            pydicom.tag.Tag('0002', '0010'),  # Transfer Syntax UID
            pydicom.tag.Tag('0002', '0012'),  # Implementation Class UID
            pydicom.tag.Tag('0002', '0013'),  # Implementation Version Name
            pydicom.tag.Tag('0020', '000e'),  # SeriesInstanceUID
            pydicom.tag.Tag('0020', '000d'),  # StudyInstanceUID  
            pydicom.tag.Tag('0020', '0052'),  # FrameOfReferenceUID
            pydicom.tag.Tag('0020', '0011'),  # SeriesNumber
            pydicom.tag.Tag('0020', '0013'),  # InstanceNumber
            pydicom.tag.Tag('0020', '1041'),  # SliceLocation
            pydicom.tag.Tag('0020', '0032'),  # ImagePositionPatient
            pydicom.tag.Tag('0008', '0018'),  # SOPInstanceUID
            pydicom.tag.Tag('0008', '103e'),  # SeriesDescription
        ]
        
        for element in template_ds:
            if element.tag not in exclude_tags:
                new_ds[element.tag] = element
        
        # 创建file_meta信息
        file_meta = pydicom.FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"  # CT Image Storage
        file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
        file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
        file_meta.ImplementationVersionName = "PYDICOM " + pydicom.__version__
        file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
        
        new_ds.file_meta = file_meta
        
        # 设置关键的series和study信息 - 这是确保文件被识别为一个series的关键
        new_ds.StudyInstanceUID = series_uids['study_instance_uid']
        new_ds.SeriesInstanceUID = series_uids['series_instance_uid']
        new_ds.FrameOfReferenceUID = series_uids['frame_of_reference_uid']
        
        # 更新特定字段
        new_ds.Modality = "MR"
        new_ds.SeriesDescription = "OGSE"
        new_ds.SeriesNumber = str(int(template_ds.SeriesNumber) + 1000) if hasattr(template_ds, 'SeriesNumber') else "1000"
        new_ds.InstanceNumber = str(slice_index + 1)
        new_ds.SliceLocation = f"{z_position:.3f}"
        
        # 更新图像位置 - 确保每个切片有正确的空间位置
        if hasattr(template_ds, 'ImagePositionPatient'):
            new_position = list(template_ds.ImagePositionPatient)
            new_position[2] = z_position  # 更新Z坐标
            new_ds.ImagePositionPatient = [f"{float(x):.3f}" for x in new_position]
        
        # 确保图像方向信息正确
        if hasattr(template_ds, 'ImageOrientationPatient'):
            new_ds.ImageOrientationPatient = template_ds.ImageOrientationPatient
        
        # 更新像素数据相关信息
        new_ds.Rows, new_ds.Columns = drm_data_slice.shape
        
        # 设置像素数据类型 - 简化精度处理，确保DICOM查看器正确显示
        if drm_data_slice.dtype == np.float32 or drm_data_slice.dtype == np.float64:
            # 获取数据范围
            data_min, data_max = np.min(drm_data_slice), np.max(drm_data_slice)
            self.logger.info(f"DRM数据范围: {data_min:.6f} 到 {data_max:.6f}")
            
            if data_max > data_min:
                # 简化处理：将0-10范围的数据缩放到0-4095范围（12位），保持两位小数精度
                # 这样可以确保DICOM查看器正确显示
                scale_factor = 100.0  # 保留两位小数 
                scaled_data = (drm_data_slice * scale_factor).astype(np.uint16)
                
                # 限制最大值防止溢出
                scaled_data = np.clip(scaled_data, 0, 4095)
                
                # 设置简单的rescale参数
                slope = 1.0 / scale_factor  # 0.01
                intercept = 0.0
                
                self.logger.info(f"缩放后范围: {np.min(scaled_data)} 到 {np.max(scaled_data)}")
                self.logger.info(f"Rescale Slope: {slope:.4f}, Intercept: {intercept:.4f}")
            else:
                # 如果所有值相同
                scaled_data = np.zeros_like(drm_data_slice, dtype=np.uint16)
                slope = 0.01
                intercept = data_min
            
            new_ds.BitsAllocated = 16
            new_ds.BitsStored = 12  # 使用12位存储
            new_ds.HighBit = 11
            new_ds.PixelRepresentation = 0  # 无符号
            new_ds.SamplesPerPixel = 1
            new_ds.PhotometricInterpretation = "MONOCHROME2"
            
            # 设置简化的缩放参数
            new_ds.RescaleSlope = f"{slope:.4f}"
            new_ds.RescaleIntercept = f"{intercept:.4f}"
            new_ds.RescaleType = "US"  # 指定rescale类型
            
            # 设置合适的窗宽窗位，帮助DICOM查看器正确显示
            window_center = (np.max(scaled_data) + np.min(scaled_data)) / 2
            window_width = np.max(scaled_data) - np.min(scaled_data)
            if window_width == 0:
                window_width = 1000
            
            new_ds.WindowCenter = str(int(window_center))
            new_ds.WindowWidth = str(int(window_width))
            
        else:
            # 如果数据已经是整数类型
            scaled_data = drm_data_slice.astype(np.uint16)
            new_ds.BitsAllocated = 16
            new_ds.BitsStored = 16
            new_ds.HighBit = 15
            new_ds.PixelRepresentation = 0
            new_ds.SamplesPerPixel = 1
            new_ds.PhotometricInterpretation = "MONOCHROME2"
            new_ds.RescaleSlope = "1.0"
            new_ds.RescaleIntercept = "0.0"
        
        # 设置像素数据
        new_ds.PixelData = scaled_data.tobytes()
        
        # 更新其他必要字段
        new_ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        new_ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.128"
        
        # 更新时间戳
        now = datetime.now()
        new_ds.ContentDate = now.strftime('%Y%m%d')
        new_ds.ContentTime = now.strftime('%H%M%S.%f')[:-3]
        new_ds.InstanceCreationDate = new_ds.ContentDate
        new_ds.InstanceCreationTime = new_ds.ContentTime
        
        # 确保像素间距信息正确
        if hasattr(template_ds, 'PixelSpacing'):
            new_ds.PixelSpacing = template_ds.PixelSpacing
        
        if hasattr(template_ds, 'SliceThickness'):
            new_ds.SliceThickness = template_ds.SliceThickness
        
        return new_ds
    
    def convert_nii_to_dicom_series(self, nii_path: str, ct_folder_path: str, 
                                  output_folder: str) -> bool:
        """
        将NII.gz文件转换为DICOM series
        
        Args:
            nii_path: NII.gz文件路径
            ct_folder_path: CT DICOM文件夹路径（用作模板）
            output_folder: 输出文件夹路径
            
        Returns:
            bool: 转换是否成功
        """
        drm_data = None
        ct_template_info = None
        
        try:
            self.logger.info("开始DRM到DICOM转换...")
            
            # 1. 读取NII文件
            self.logger.info("步骤 1/7: 读取NII文件...")
            drm_data, affine, nii_header = self.read_nii_file(nii_path)
            
            # 添加内存清理
            import gc
            gc.collect()
            
            # 2. 读取CT模板
            self.logger.info("步骤 2/7: 读取CT模板...")
            ct_template_info = self.read_ct_dicom_template(ct_folder_path)
            template_ds = ct_template_info['template']
            dicom_info = ct_template_info['dicom_info']
            
            # 再次清理内存
            gc.collect()
            
            # 3. 创建series相关的UID
            self.logger.info("步骤 3/7: 创建DICOM标识符...")
            series_uids = self.create_series_uids(template_ds)
            self.logger.info(f"新的Series UID: {series_uids['series_instance_uid']}")
            
            # 4. 创建输出目录
            self.logger.info("步骤 4/7: 创建输出目录...")
            Path(output_folder).mkdir(parents=True, exist_ok=True)
            
            # 5. 获取DRM数据的切片数
            self.logger.info("步骤 5/7: 分析数据维度...")
            if len(drm_data.shape) == 3:
                num_slices = drm_data.shape[2]  # 假设z轴是第三个维度
            else:
                raise ValueError(f"DRM数据维度不正确: {drm_data.shape}")
            
            self.logger.info(f"DRM数据切片数: {num_slices}")
            self.logger.info(f"CT模板切片数: {len(dicom_info)}")
            
            # 6. 计算空间信息 - 仅用NIfTI的affine矩阵，采用yx排列+180度旋转
            self.logger.info("步骤 6/7: 计算空间坐标（仅用NIfTI affine，yx排列+180度旋转）...")
            affine_used = affine.copy()
            affine_used[:, [0, 1]] = affine_used[:, [1, 0]]
            pixel_spacing = [
                float(np.linalg.norm(affine_used[0:3, 0])),
                float(np.linalg.norm(affine_used[0:3, 1]))
            ]
            slice_thickness = float(np.linalg.norm(affine_used[0:3, 2]))
            orientation = np.concatenate([
                affine_used[0:3, 0] / pixel_spacing[0],
                affine_used[0:3, 1] / pixel_spacing[1]
            ])
            self.logger.info(f"像素间距: {pixel_spacing}")
            self.logger.info(f"切片厚度: {slice_thickness}")
            self.logger.info(f"图像方向: {orientation}")
            image_positions = []
            for k in range(num_slices):
                pos = affine_used @ np.array([0, 0, k, 1])
                image_positions.append(pos[:3])
            self.logger.info(f"Z轴范围: {min(image_positions, key=lambda x: x[2])[2]:.3f} 到 {max(image_positions, key=lambda x: x[2])[2]:.3f}")
            # 7. 转换每个切片
            self.logger.info("开始转换切片...")
            Path(output_folder).mkdir(parents=True, exist_ok=True)
            for i in range(num_slices):
                try:
                    drm_slice = drm_data[:, :, i]
                    drm_slice = np.rot90(drm_slice, 2)  # 180度旋转
                    image_position = image_positions[i]
                    dicom_ds = self.create_dicom_header(
                        template_ds, i, num_slices, drm_slice, image_position[2], series_uids
                    )
                    dicom_ds.PixelSpacing = [f"{x:.6f}" for x in pixel_spacing]
                    dicom_ds.SliceThickness = f"{slice_thickness:.6f}"
                    dicom_ds.ImageOrientationPatient = [f"{x:.6f}" for x in orientation]
                    dicom_ds.ImagePositionPatient = [f"{x:.6f}" for x in image_position]
                    output_filename = f"DRM_{i+1:04d}.dcm"
                    output_path = os.path.join(output_folder, output_filename)
                    dicom_ds.save_as(output_path, enforce_file_format=True)
                except Exception as e:
                    self.logger.error(f"转换第{i+1}个切片失败: {e}")
                    continue
            
            # self.logger.info(f"转换完成！成功: {success_count}, 失败: {failed_count}")
            self.logger.info(f"输出目录: {output_folder}")
            self.logger.info(f"Series UID: {series_uids['series_instance_uid']}")
            
            # return success_count > 0 and failed_count == 0
            return True
            
        except Exception as e:
            self.logger.error(f"DRM到DICOM转换失败: {e}")
            import traceback
            self.logger.error(f"详细错误: {traceback.format_exc()}")
            return False
        finally:
            # 最终清理内存
            try:
                if 'drm_data' in locals() and drm_data is not None:
                    del drm_data
                if 'ct_template_info' in locals() and ct_template_info is not None:
                    del ct_template_info
                import gc
                gc.collect()
                self.logger.info("内存清理完成")
            except:
                pass
    
    def convert_drm_folder(self, drm_folder_path: str, output_base_folder: str) -> bool:
        """
        转换整个DRM文件夹
        
        Args:
            drm_folder_path: DRM文件夹路径（如FAPI_DRM）
            output_base_folder: 输出基础文件夹路径
            
        Returns:
            bool: 转换是否成功
        """
        try:
            self.logger.info(f"开始处理DRM文件夹: {drm_folder_path}")
            
            # 查找DRM.nii.gz文件
            nii_file = None
            for filename in os.listdir(drm_folder_path):
                if filename.lower().endswith('.nii.gz') and 'drm' in filename.lower():
                    nii_file = os.path.join(drm_folder_path, filename)
                    break
            
            if not nii_file:
                raise ValueError(f"在{drm_folder_path}中未找到DRM.nii.gz文件")
            
            # 查找CT文件夹
            ct_folder = None
            for item in os.listdir(drm_folder_path):
                item_path = os.path.join(drm_folder_path, item)
                if os.path.isdir(item_path) and 'CT' in item:
                    ct_folder = item_path
                    break
            
            if not ct_folder:
                raise ValueError(f"在{drm_folder_path}中未找到CT文件夹")
            
            # 创建输出文件夹
            folder_name = os.path.basename(drm_folder_path)
            output_folder = os.path.join(output_base_folder, f"{folder_name}_DRM_DICOM")
            
            # 执行转换
            return self.convert_nii_to_dicom_series(nii_file, ct_folder, output_folder)
            
        except Exception as e:
            self.logger.error(f"处理DRM文件夹失败: {e}")
            return False 