#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import numpy as np
import pydicom
import SimpleITK as sitk
from rt_utils import RTStructBuilder
from typing import Optional, List
from src.debug_utils import  send_to_external_napari
import tempfile # 导入 tempfile
import shutil   # 导入 shutil 用于文件复制和目录删除

# 配置日志
logger = logging.getLogger(__name__)

# ===> Helper function to copy DICOM series excluding RTSS <===
def _copy_dicom_series_to_temp(original_dir: str, temp_dir: str, exclude_file: Optional[str] = None):
    """
    Copies .dcm files from original_dir to temp_dir, optionally excluding one file.
    Returns True if successful, False otherwise.
    """
    try:
        os.makedirs(temp_dir, exist_ok=True)
        copied_count = 0
        exclude_filename = os.path.basename(exclude_file) if exclude_file else None
        logger.info(f"Copying DICOM series from {original_dir} to {temp_dir}, excluding {exclude_filename}")

        for filename in os.listdir(original_dir):
            if filename.lower().endswith('.dcm'):
                if exclude_filename and filename == exclude_filename:
                    logger.debug(f"  Skipping excluded file: {filename}")
                    continue # 跳过要排除的 RTSS 文件

                source_path = os.path.join(original_dir, filename)
                dest_path = os.path.join(temp_dir, filename)
                # 确认是文件而不是目录 (尽管 .dcm 通常是文件)
                if os.path.isfile(source_path):
                    shutil.copy2(source_path, dest_path) # copy2 保留元数据
                    copied_count += 1

        logger.info(f"  Copied {copied_count} .dcm files.")
        if copied_count == 0:
             logger.warning(f"  Warning: No .dcm files were copied from {original_dir}.")
             # 根据需要决定是否是错误
             # return False
        return True
    except Exception as e:
        logger.error(f"Error copying files from {original_dir} to {temp_dir}: {e}", exc_info=True)
        return False

def resample_mask_to_ct_geometry(
    mask_np: np.ndarray,
    pt_ref_image: sitk.Image,
    ct_ref_image: sitk.Image) -> Optional[sitk.Image]:
    """
    将基于 PT 几何的 NumPy 掩码重采样到 CT 几何空间。

    Args:
        mask_np: 从 PT RTStruct 提取的 NumPy 掩码数组 (rt_utils 可能返回 y,x,z 顺序)。
        pt_ref_image: PT DICOM 系列加载的 SimpleITK 图像，作为原始掩码的几何参考。
        ct_ref_image: CT DICOM 系列加载的 SimpleITK 图像，作为目标几何参考。

    Returns:
        重采样后的 SimpleITK 图像掩码，如果出错则返回 None。
    """
    try:
        # 确认输入 mask_np 的维度
        if mask_np.ndim != 3:
            logger.error(f"输入掩码维度不是 3 (shape: {mask_np.shape})，无法处理。")
            return None
        logger.debug(f"输入 NumPy 掩码形状 (来自 rt_utils): {mask_np.shape}")

        # !!! 关键：转置 NumPy 数组以匹配 SimpleITK 的 (z, y, x) 约定 !!!
        # 假设 rt_utils 返回 (y, x, z)，需要转置为 (z, y, x)
        mask_np_transposed = mask_np.transpose((2, 0, 1))
        logger.debug(f"转置后的 NumPy 掩码形状 (用于 SITK): {mask_np_transposed.shape}")

        # 将转置后的 NumPy 数组转换为 SimpleITK 图像
        mask_sitk = sitk.GetImageFromArray(mask_np_transposed.astype(np.uint8))
        logger.debug(f"从转置后数组创建的 SITK 图像大小 (x,y,z): {mask_sitk.GetSize()}")

        # 检查转换后的 SITK 图像尺寸是否与原始参考图像尺寸匹配 (理论上应该匹配，因为转置是为了这个)
        if mask_sitk.GetSize() != pt_ref_image.GetSize():
             logger.warning(f"警告：转置后创建的 SITK 掩码尺寸 {mask_sitk.GetSize()} 与 PT 参考图像尺寸 {pt_ref_image.GetSize()} 不匹配！后续重采样可能出错。")
             # 尽管尺寸不匹配，但仍然尝试应用几何信息并继续，看重采样器是否能处理
             # 或者直接返回 None?
             # return None

        # 手动设置几何信息 (从原始 PT 参考图像获取)
        mask_sitk.SetOrigin(pt_ref_image.GetOrigin())
        mask_sitk.SetSpacing(pt_ref_image.GetSpacing())
        mask_sitk.SetDirection(pt_ref_image.GetDirection())
        logger.info("手动设置掩码几何信息 (Origin, Spacing, Direction) 完成。")

        # 创建重采样器
        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(ct_ref_image) # 设置目标几何来自于 CT 图像
        resampler.SetInterpolator(sitk.sitkNearestNeighbor) # 二值掩码必须用最近邻插值
        resampler.SetOutputPixelType(mask_sitk.GetPixelID()) # 保持像素类型一致
        resampler.SetTransform(sitk.Transform()) # 假设 PT 和 CT 在同一坐标系，仅需匹配几何
        resampler.SetDefaultPixelValue(0) # 背景像素值

        resampled_mask_sitk = resampler.Execute(mask_sitk)
        logger.info("掩码重采样成功。")
        return resampled_mask_sitk

    except Exception as e:
        logger.error(f"重采样掩码时出错: {e}", exc_info=True)
        return None

def copy_rtss_between_series(
    source_rtss_path: str,
    source_series_dir: str,
    target_series_dir: str,
    output_rtss_path: str) -> bool:
    """
    将 RTStruct 从源 DICOM 系列复制并适配到目标 DICOM 系列。

    Args:
        source_rtss_path: 源 RTStruct 文件路径 (例如 PT 的 RTSS)。
        source_series_dir: 源 RTStruct 引用的 DICOM 系列文件夹路径 (例如 PT 系列)。
        target_series_dir: 目标 DICOM 系列文件夹路径 (例如 CT 系列)。
        output_rtss_path: 新生成的 RTStruct 文件保存路径。

    Returns:
        如果成功复制并保存，返回 True，否则返回 False。
    """
    logger.info(f"开始处理 RTSS 复制: {source_rtss_path} -> {output_rtss_path}")
    logger.info(f"源系列: {source_series_dir}, 目标系列: {target_series_dir}")

    if not os.path.exists(source_rtss_path):
        logger.error(f"源 RTStruct 文件不存在: {source_rtss_path}")
        return False
    if not os.path.isdir(source_series_dir):
        logger.error(f"源 DICOM 系列文件夹不存在: {source_series_dir}")
        return False
    if not os.path.isdir(target_series_dir):
        logger.error(f"目标 DICOM 系列文件夹不存在: {target_series_dir}")
        return False

    # ===> 创建临时目录并在 finally 中确保清理 <===
    temp_root_dir = None # 初始化
    try:
        temp_root_dir = tempfile.mkdtemp(prefix="rtss_copy_")
        logger.info(f"创建临时工作目录: {temp_root_dir}")
        temp_source_series_dir = os.path.join(temp_root_dir, "source_series")
        temp_target_series_dir = os.path.join(temp_root_dir, "target_series")

        # ===> 复制文件到临时目录 <===
        logger.info("准备临时源系列...")
        if not _copy_dicom_series_to_temp(source_series_dir, temp_source_series_dir, exclude_file=source_rtss_path):
            raise RuntimeError(f"无法复制源系列文件到临时目录 {temp_source_series_dir}")

        logger.info("准备临时目标系列...")
        if not _copy_dicom_series_to_temp(target_series_dir, temp_target_series_dir):
            # 目标系列可能没有 RTSS，所以不排除文件
            raise RuntimeError(f"无法复制目标系列文件到临时目录 {temp_target_series_dir}")

        # ===> 使用临时目录路径进行后续操作 <===
        effective_source_series_dir = temp_source_series_dir
        effective_target_series_dir = temp_target_series_dir

        # 1. 加载源 RTStruct (RTSS路径不变) 和其引用的图像系列 (使用临时目录)
        source_rtstruct = RTStructBuilder.create_from(
            dicom_series_path=effective_source_series_dir, # <-- 使用临时目录
            rt_struct_path=source_rtss_path
        )
        logger.info("成功加载源 RTStruct 和临时系列。")

        # 使用 SimpleITK 加载源和目标图像系列 (从临时目录)
        logger.info("使用 SimpleITK 加载临时源和目标图像系列...")
        reader = sitk.ImageSeriesReader()

        source_dicom_names = reader.GetGDCMSeriesFileNames(effective_source_series_dir) # <-- 使用临时目录
        if not source_dicom_names:
            # 之前 _copy_dicom_series_to_temp 中应该已经警告过了
            logger.error(f"在临时源目录 {effective_source_series_dir} 中找不到 DICOM 文件。")
            return False
        reader.SetFileNames(source_dicom_names)
        source_image_ref = reader.Execute()
        logger.info(f"成功加载临时源系列图像: {effective_source_series_dir}")
        logger.info(f"源 PT 图像 (source_image_ref) 大小: {source_image_ref.GetSize()}")

        target_dicom_names = reader.GetGDCMSeriesFileNames(effective_target_series_dir) # <-- 使用临时目录
        if not target_dicom_names:
            logger.error(f"在临时目标目录 {effective_target_series_dir} 中找不到 DICOM 文件。")
            return False
        reader.SetFileNames(target_dicom_names)
        target_image_ref = reader.Execute()
        logger.info(f"成功加载临时目标系列图像: {effective_target_series_dir}")
        logger.info(f"目标 CT 图像 (target_image_ref) 大小: {target_image_ref.GetSize()}")

        # 2. 创建新的 RTStructBuilder，引用目标系列 (使用临时目录)
        new_rtstruct = RTStructBuilder.create_new(dicom_series_path=effective_target_series_dir) # <-- 使用临时目录
        logger.info("创建新的 RTStructBuilder，引用临时目标系列。")

        # ===> 重新确保 Napari 调试导入和变量定义 <===
        try:
            from src.debug_utils import send_to_external_napari
            napari_debug_available = True
        except ImportError:
            napari_debug_available = False
            logger.warning("Napari 调试工具 (send_to_external_napari) 未找到，跳过可视化调试。")

        # 3. 遍历源 RTStruct 中的 ROI
        roi_names = source_rtstruct.get_roi_names()
        if not roi_names:
            logger.warning(f"源 RTStruct 文件 {source_rtss_path} 中没有找到 ROI。")
            # 仍然可以创建一个空的 RTStruct 文件，或者返回 False？
            # 决定返回 True，因为过程没出错，只是没内容可复制
            # return True # 或者 False? 看需求

        logger.info(f"找到 ROI: {roi_names}")
        process_success = True
        for roi_name in roi_names:
            logger.info(f"处理 ROI: {roi_name}")
            try:
                # 3.1 获取源 ROI 掩码 (基于源图像几何)
                source_mask_np = source_rtstruct.get_roi_mask_by_name(roi_name)
                logger.debug(f"获取 ROI '{roi_name}' 的 NumPy 掩码，形状: {source_mask_np.shape}")
                if source_mask_np.ndim != 3:
                     logger.error(f"ROI '{roi_name}' 的源掩码维度不是 3 (shape: {source_mask_np.shape})，无法处理。")
                     process_success = False
                     continue

                # 创建临时 SimpleITK 图像以检查尺寸
                temp_mask_sitk = sitk.GetImageFromArray(source_mask_np.astype(np.uint8))
                logger.debug(f"从源掩码创建的临时 SITK 图像大小: {temp_mask_sitk.GetSize()}")

                # ===> 清理调试代码：移除发送不同转置和暂停 <===
                # if napari_debug_available:
                #     ...
                # ===> 调试代码结束 <===

                # 3.2 重采样掩码到目标几何
                # resample_mask_to_ct_geometry 函数内部会执行正确的转置 transpose((2, 0, 1))
                resampled_mask_sitk = resample_mask_to_ct_geometry(
                    source_mask_np, source_image_ref, target_image_ref
                )

                if resampled_mask_sitk is None:
                    logger.error(f"ROI '{roi_name}' 的掩码重采样失败，跳过此 ROI。")
                    process_success = False # 标记整个过程部分失败
                    continue
                logger.debug(f"重采样后的 SITK 掩码 (resampled_mask_sitk) 大小: {resampled_mask_sitk.GetSize()}")

                # 将重采样后的 SimpleITK 图像转回 NumPy 数组以添加到新的 RTStruct
                resampled_mask_np = sitk.GetArrayFromImage(resampled_mask_sitk).astype(bool)
                logger.debug(f"重采样后的 NumPy 掩码 (resampled_mask_np) 形状: {resampled_mask_np.shape}")

                # 3.3 获取原始颜色 (如果需要)
                # color = source_rtstruct.get_roi_color_by_name(roi_name) # rt_utils 似乎没有直接获取颜色的方法？需要检查
                # 临时使用默认颜色或随机颜色
                # TODO: 查找如何从 pydicom Dataset 获取原始颜色
                try:
                    # 尝试从原始 RTStruct Dataset 获取颜色
                    original_ds = pydicom.dcmread(source_rtss_path, force=True)
                    color = [255, 0, 0] # 默认红色
                    for item in original_ds.StructureSetROISequence:
                        if item.ROIName == roi_name:
                            # 在 ROI Contour Sequence 或 RT ROI Observations Sequence 中找颜色?
                            # 检查 ROIContourSequence -> ContourSequence -> ContourData ? (不太可能)
                            # 检查 RTROIObservationsSequence -> ROIDisplayColor?
                            # pydicom 的结构比较复杂，这里暂时简化
                            # 需要更可靠的方法来获取原始颜色
                            # 查找 RTROIObservationsSequence
                            obs_seq = original_ds.get("RTROIObservationsSequence", [])
                            for obs_item in obs_seq:
                                # 通过 ReferencedROINumber 链接 StructureSetROISequence
                                ref_roi_number = obs_item.get("ReferencedROINumber")
                                roi_number_struct_set = item.get("ROINumber")
                                if ref_roi_number is not None and roi_number_struct_set is not None and ref_roi_number == roi_number_struct_set:
                                    found_color = obs_item.get("ROIDisplayColor")
                                    if found_color:
                                        # 颜色是 DICOM 多值字符串 'R\G\B'
                                        color = [int(c) for c in found_color]
                                        logger.info(f"找到 ROI '{roi_name}' 的原始颜色: {color}")
                                        break # 找到颜色就跳出内部循环
                            break # 找到 ROI Name 对应的 Item 就跳出外部循环
                except Exception as color_e:
                     logger.warning(f"无法获取 ROI '{roi_name}' 的原始颜色: {color_e}，将使用默认红色。")
                     color = [255, 0, 0]

                # 3.4 添加重采样后的 ROI 到新 RTStruct
                # new_rtstruct.add_roi(
                #     mask=resampled_mask_np,
                #     color=color, # 使用获取到的或默认的颜色
                #     name=roi_name
                # )                
                new_rtstruct.add_roi(
                    mask=resampled_mask_np.transpose((1, 2, 0)),
                    color=color, # 使用获取到的或默认的颜色
                    name=roi_name
                )
                logger.info(f"成功添加重采样后的 ROI '{roi_name}' 到新 RTStruct。")

            except Exception as roi_e:
                logger.error(f"处理 ROI '{roi_name}' 时发生错误: {roi_e}", exc_info=True)
                process_success = False # 标记整个过程部分失败


        # 4. 保存新的 RTStruct 文件
        if process_success or not roi_names:
            # --- 先保存到临时目录 ---
            temp_output_filename = os.path.basename(output_rtss_path)
            temp_output_rtss_path = os.path.join(effective_target_series_dir, temp_output_filename)
            logger.info(f"尝试将新的 RTStruct 保存到临时路径: {temp_output_rtss_path}")
            new_rtstruct.save(temp_output_rtss_path)
            logger.info("成功保存到临时路径。")

            # --- 再从临时目录拷贝到最终目标目录 ---
            # 确保 *原始* 输出目录存在
            output_dir = os.path.dirname(output_rtss_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                logger.info(f"创建最终输出目录: {output_dir}")

            logger.info(f"将临时 RTStruct 文件从 {temp_output_rtss_path} 拷贝到最终路径 {output_rtss_path}")
            shutil.copy2(temp_output_rtss_path, output_rtss_path) # copy2 保留元数据
            logger.info(f"成功拷贝到最终路径。")

            # 清理临时目录时会自动删除 temp_output_rtss_path
            return process_success and bool(roi_names)
        else:
             logger.error("由于处理 ROI 时发生错误，未保存新的 RTStruct 文件。")
             return False

    except ImportError:
         logger.error("缺少必要的库。请确保已安装 rt_utils, SimpleITK, pydicom, numpy。")
         return False
    except Exception as e:
        logger.error(f"复制 RTStruct 时发生意外错误: {e}", exc_info=True)
        return False
    finally:
        # ===> 清理临时目录 <===
        if temp_root_dir and os.path.exists(temp_root_dir):
            try:
                logger.info(f"开始清理临时目录: {temp_root_dir}")
                shutil.rmtree(temp_root_dir)
                logger.info("临时目录清理完成。")
            except Exception as cleanup_e:
                logger.error(f"清理临时目录 {temp_root_dir} 时出错: {cleanup_e}", exc_info=True)

# 可以在这里添加一些测试代码
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    logger.info("测试 rtstruct_utils 模块...")

    # --- 定义测试用的路径 (需要替换为实际存在的测试数据路径) ---
    # base_test_dir = 'path/to/your/test_data/patient_folder'
    base_test_dir = 'C:/Users/elekta/Desktop/jiteng/code/dicomer_all_in_one/data/rtss_copier/123890hf/images' # 使用你的示例路径
    pt_rtss_path = os.path.join(base_test_dir, 'week0_PT', 'RS.week0_PT.dcm') # 假设的 PT RTSS 文件名
    pt_series_dir = os.path.join(base_test_dir, 'week0_PT')
    ct_series_dir = os.path.join(base_test_dir, 'week0_CT')
    output_rtss_path = os.path.join(base_test_dir, 'week0_CT', 'RS.week0_CT_from_PT.dcm') # 新生成的文件名

    # --- 运行测试 ---
    # 注意：你需要确保上述路径和文件真实存在且包含有效数据才能成功运行测试
    if not os.path.exists(pt_rtss_path):
         logger.warning(f"测试所需的 PT RTSS 文件不存在: {pt_rtss_path}")
         logger.warning("请修改 __main__ 中的路径指向有效的测试数据，或创建虚拟数据。")
    elif not os.path.isdir(pt_series_dir) or not os.listdir(pt_series_dir):
         logger.warning(f"测试所需的 PT 系列目录不存在或为空: {pt_series_dir}")
    elif not os.path.isdir(ct_series_dir) or not os.listdir(ct_series_dir):
         logger.warning(f"测试所需的 CT 系列目录不存在或为空: {ct_series_dir}")
    else:
        logger.info("找到测试数据路径，尝试执行复制...")
        success = copy_rtss_between_series(
            pt_rtss_path,
            pt_series_dir,
            ct_series_dir,
            output_rtss_path
        )

        if success:
            logger.info("测试复制操作成功完成！")
            # 可以在这里添加代码来加载并检查生成的 RTSS 文件
        else:
            logger.error("测试复制操作失败。") 