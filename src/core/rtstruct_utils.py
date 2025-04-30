#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import numpy as np
import pydicom
import SimpleITK as sitk
from rt_utils import RTStructBuilder
from typing import Optional, List, Tuple
from src.debug_utils import  send_to_external_napari
import tempfile # 导入 tempfile
import shutil   # 导入 shutil 用于文件复制和目录删除
import math # 新增导入

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

def apply_transform_to_mask(
    mask_image: sitk.Image,
    reference_image: sitk.Image,
    transform: sitk.Transform,
    default_value: int = 0) -> Optional[sitk.Image]:
    """
    Applies a given SimpleITK transform to a mask image.

    Args:
        mask_image: The input mask image (already in the reference space grid potentially).
        reference_image: The image defining the output grid (size, spacing, origin, direction).
        transform: The SimpleITK transform to apply.
        default_value: Pixel value for points outside the transformed mask.

    Returns:
        The transformed mask image, or None if an error occurs.
    """
    try:
        resampler = sitk.ResampleImageFilter()
        resampler.SetReferenceImage(reference_image)
        resampler.SetInterpolator(sitk.sitkNearestNeighbor) # Crucial for masks
        resampler.SetOutputPixelType(mask_image.GetPixelID())
        resampler.SetTransform(transform) # Apply the provided transform
        resampler.SetDefaultPixelValue(default_value)

        transformed_mask = resampler.Execute(mask_image)
        logger.info("成功应用变换到掩码。")
        return transformed_mask
    except Exception as e:
        logger.error(f"应用变换到掩码时出错: {e}", exc_info=True)
        return None

def copy_rtss_between_series_with_transform(
    source_rtss_path: str,
    source_series_dir: str,
    target_series_dir: str,
    output_rtss_path: str,
    rigid_transform: sitk.Transform) -> bool:
    """
    将 RTStruct 从源系列复制、适配到目标系列，并应用一个额外的刚性变换。

    Args:
        source_rtss_path: 源 RTStruct 文件路径 (e.g., week0_PT RTSS).
        source_series_dir: 源 RTStruct 引用的 DICOM 系列文件夹 (e.g., week0_PT).
        target_series_dir: 目标 DICOM 系列文件夹 (e.g., week4_PT).
        output_rtss_path: 新生成的 RTStruct 文件保存路径。
        rigid_transform: 应用于重采样后掩码的 SimpleITK.Transform 对象。

    Returns:
        True if successful, False otherwise.
    """
    logger.info(f"开始处理 RTSS 复制 (带变换): {source_rtss_path} -> {output_rtss_path}")
    logger.info(f"源系列: {source_series_dir}, 目标系列: {target_series_dir}")

    # --- 输入检查 (与之前类似) ---
    if not os.path.exists(source_rtss_path):
        logger.error(f"源 RTStruct 文件不存在: {source_rtss_path}")
        return False
    if not os.path.isdir(source_series_dir):
        logger.error(f"源 DICOM 系列文件夹不存在: {source_series_dir}")
        return False
    if not os.path.isdir(target_series_dir):
        logger.error(f"目标 DICOM 系列文件夹不存在: {target_series_dir}")
        return False
    if not isinstance(rigid_transform, sitk.Transform):
         logger.error("提供的变换不是有效的 SimpleITK.Transform 对象。")
         return False

    temp_root_dir = None
    try:
        # ===> 创建和准备临时目录 (与之前相同) <===
        temp_root_dir = tempfile.mkdtemp(prefix="rtss_copy_tx_")
        logger.info(f"创建临时工作目录: {temp_root_dir}")
        temp_source_series_dir = os.path.join(temp_root_dir, "source_series")
        temp_target_series_dir = os.path.join(temp_root_dir, "target_series")

        logger.info("准备临时源系列...")
        if not _copy_dicom_series_to_temp(source_series_dir, temp_source_series_dir, exclude_file=source_rtss_path):
            raise RuntimeError(f"无法复制源系列文件到临时目录 {temp_source_series_dir}")

        logger.info("准备临时目标系列...")
        if not _copy_dicom_series_to_temp(target_series_dir, temp_target_series_dir):
            raise RuntimeError(f"无法复制目标系列文件到临时目录 {temp_target_series_dir}")

        effective_source_series_dir = temp_source_series_dir
        effective_target_series_dir = temp_target_series_dir

        # ===> 加载数据 (与之前类似，使用临时目录) <===
        source_rtstruct = RTStructBuilder.create_from(
            dicom_series_path=effective_source_series_dir,
            rt_struct_path=source_rtss_path
        )
        logger.info("成功加载源 RTStruct 和临时系列。")

        logger.info("使用 SimpleITK 加载临时源和目标图像系列...")
        reader = sitk.ImageSeriesReader()
        source_dicom_names = reader.GetGDCMSeriesFileNames(effective_source_series_dir)
        if not source_dicom_names: return False
        reader.SetFileNames(source_dicom_names)
        source_image_ref = reader.Execute()
        logger.info(f"成功加载临时源系列图像: {effective_source_series_dir}")

        target_dicom_names = reader.GetGDCMSeriesFileNames(effective_target_series_dir)
        if not target_dicom_names: return False
        reader.SetFileNames(target_dicom_names)
        target_image_ref = reader.Execute()
        logger.info(f"成功加载临时目标系列图像: {effective_target_series_dir}")

        # ===> 创建新的 RTStructBuilder (与之前类似) <===
        new_rtstruct = RTStructBuilder.create_new(dicom_series_path=effective_target_series_dir)
        logger.info("创建新的 RTStructBuilder，引用临时目标系列。")

        # ===> 处理 ROI (主要区别在这里) <===
        roi_names = source_rtstruct.get_roi_names()
        logger.info(f"找到 ROI: {roi_names}")
        process_success = True
        for roi_name in roi_names:
            logger.info(f"处理 ROI: {roi_name}")
            try:
                # 1. 获取源 ROI 掩码 (NumPy)
                source_mask_np = source_rtstruct.get_roi_mask_by_name(roi_name)
                if source_mask_np.ndim != 3: continue # Basic check

                # 2. 重采样到目标空间 (得到 SITK 掩码)
                # resample_mask_to_ct_geometry 内部处理了轴转置和设置几何信息
                resampled_mask_sitk = resample_mask_to_ct_geometry(
                    source_mask_np, source_image_ref, target_image_ref
                )
                if resampled_mask_sitk is None:
                    logger.error(f"ROI '{roi_name}' 重采样到目标空间失败，跳过。")
                    process_success = False; continue
                logger.info(f"ROI '{roi_name}' 已重采样到目标空间。")

                # 3. 应用刚性变换 (使用辅助函数)
                transformed_mask_sitk = apply_transform_to_mask(
                    mask_image=resampled_mask_sitk,
                    reference_image=target_image_ref, # 输出网格基于目标图像
                    transform=rigid_transform
                )
                if transformed_mask_sitk is None:
                    logger.error(f"ROI '{roi_name}' 应用变换失败，跳过。")
                    process_success = False; continue
                logger.info(f"ROI '{roi_name}' 已应用变换。")

                # 4. 将最终变换后的掩码转回 NumPy
                final_mask_np = sitk.GetArrayFromImage(transformed_mask_sitk).astype(bool)

                # 5. 获取颜色 (与之前类似)
                try:
                    original_ds = pydicom.dcmread(source_rtss_path, force=True)
                    color = [255, 0, 0] # Default
                    for item in original_ds.StructureSetROISequence:
                        if item.ROIName == roi_name:
                            obs_seq = original_ds.get("RTROIObservationsSequence", [])
                            for obs_item in obs_seq:
                                ref_roi_number = obs_item.get("ReferencedROINumber")
                                roi_number_struct_set = item.get("ROINumber")
                                if ref_roi_number is not None and roi_number_struct_set is not None and ref_roi_number == roi_number_struct_set:
                                    found_color = obs_item.get("ROIDisplayColor")
                                    if found_color: color = [int(c) for c in found_color]; break
                            break
                    logger.info(f"找到 ROI '{roi_name}' 颜色: {color}")
                except Exception as color_e:
                    logger.warning(f"无法获取 ROI '{roi_name}' 颜色: {color_e}，使用默认红色。")
                    color = [255, 0, 0]

                # 6. 添加变换后的 ROI 到新 RTStruct
                # 注意 rt_utils 的 add_roi 可能需要特定轴顺序的 mask，需要确认！
                # 从之前的调试看，add_roi 似乎期望 (z, y, x) 对应的 NumPy 数组
                # sitk.GetArrayFromImage 返回的就是 (z, y, x)，所以 final_mask_np 应该是正确的
                logger.debug(f"准备添加变换后的掩码到 rt_utils, 形状: {final_mask_np.shape}")
                new_rtstruct.add_roi(
                    mask=final_mask_np,
                    color=color,
                    name=roi_name
                )
                logger.info(f"成功添加变换后的 ROI '{roi_name}' 到新 RTStruct。")

            except Exception as roi_e:
                logger.error(f"处理 ROI '{roi_name}' 时发生错误: {roi_e}", exc_info=True)
                process_success = False

        # ===> 保存逻辑 (与之前类似，保存到原始目标路径) <===
        if process_success or not roi_names:
            temp_output_filename = os.path.basename(output_rtss_path)
            temp_output_rtss_path = os.path.join(effective_target_series_dir, temp_output_filename)
            logger.info(f"尝试将新的 RTStruct 保存到临时路径: {temp_output_rtss_path}")
            new_rtstruct.save(temp_output_rtss_path)
            logger.info("成功保存到临时路径。")

            output_dir = os.path.dirname(output_rtss_path)
            if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir)
            logger.info(f"将临时 RTStruct 文件从 {temp_output_rtss_path} 拷贝到最终路径 {output_rtss_path}")
            shutil.copy2(temp_output_rtss_path, output_rtss_path)
            logger.info(f"成功拷贝到最终路径。")
            return process_success and bool(roi_names)
        else:
            logger.error("由于处理 ROI 时发生错误，未保存新的 RTStruct 文件。")
            return False

    except ImportError:
         logger.error("缺少必要的库。")
         return False
    except Exception as e:
        logger.error(f"复制 RTStruct (带变换) 时发生意外错误: {e}", exc_info=True)
        return False
    finally:
        # ===> 清理临时目录 (与之前相同) <===
        if temp_root_dir and os.path.exists(temp_root_dir):
            try:
                logger.info(f"开始清理临时目录: {temp_root_dir}")
                shutil.rmtree(temp_root_dir)
                logger.info("临时目录清理完成。")
            except Exception as cleanup_e:
                logger.error(f"清理临时目录 {temp_root_dir} 时出错: {cleanup_e}", exc_info=True)

def resample_mask_to_target_geometry(
    source_mask_sitk: sitk.Image,
    target_ref_image: sitk.Image,
    interpolator: int = sitk.sitkNearestNeighbor,
    transform: Optional[sitk.Transform] = None
) -> np.ndarray:
    """
    Resamples a source SimpleITK mask image to the geometry of a target reference image,
    optionally applying a transformation.

    Args:
        source_mask_sitk: The source mask as a SimpleITK image.
        target_ref_image: The target reference image defining the output geometry.
        interpolator: The interpolator to use (default: nearest neighbor for masks).
        transform: An optional SimpleITK transform to apply during resampling.
                   Note: Resample expects the inverse transform mapping output points to input points.

    Returns:
        The resampled mask as a NumPy array with axes potentially needing transpose for rt_utils.
    """
    logging.info("Starting mask resampling...")
    logging.info(f"Source mask size: {source_mask_sitk.GetSize()}, spacing: {source_mask_sitk.GetSpacing()}, origin: {source_mask_sitk.GetOrigin()}, direction: {source_mask_sitk.GetDirection()}")
    logging.info(f"Target ref size: {target_ref_image.GetSize()}, spacing: {target_ref_image.GetSpacing()}, origin: {target_ref_image.GetOrigin()}, direction: {target_ref_image.GetDirection()}")

    resample_filter = sitk.ResampleImageFilter()
    resample_filter.SetReferenceImage(target_ref_image) # Set size, origin, spacing, direction from target
    resample_filter.SetInterpolator(interpolator)
    resample_filter.SetDefaultPixelValue(0) # Background pixel value for mask

    if transform:
        logging.info(f"Applying transform: {transform.GetName()}")
        # Resample requires the transform mapping points from the output space BACK to the input space
        # If 'transform' maps input -> output, we need its inverse.
        try:
            inverse_transform = transform.GetInverse()
            resample_filter.SetTransform(inverse_transform)
            logging.info("Using inverse transform for resampling.")
        except RuntimeError as e:
            logging.error(f"Could not compute inverse transform: {e}. Using original transform (might be incorrect).")
            # Fallback or raise error? For now, log and proceed cautiously.
            resample_filter.SetTransform(transform)

    else:
         # Set identity transform if no transform is provided explicitly
        resample_filter.SetTransform(sitk.Transform())
        logging.info("No transform provided, using identity transform.")


    resampled_mask_sitk = resample_filter.Execute(source_mask_sitk)
    logging.info(f"Resampled mask size: {resampled_mask_sitk.GetSize()}")

    # Convert SimpleITK image (z, y, x) back to NumPy array
    resampled_mask_np = sitk.GetArrayFromImage(resampled_mask_sitk) # Shape: (z, y, x)

    # rt_utils expects (y, x, z), so transpose is needed
    # Let's confirm this again later if needed. Assuming (z, y, x) -> (y, x, z)
    resampled_mask_np_transposed = resampled_mask_np.transpose((1, 2, 0)) # (y, x, z)
    logging.info(f"Resampling complete. Output NumPy array shape (transposed for rt_utils): {resampled_mask_np_transposed.shape}")


    return resampled_mask_np_transposed

def copy_rtss_with_transform(
    source_rtss_path: str,
    target_image_series_dir: str,
    output_dir: str,
    rotation_center: Tuple[float, float, float],
    rotation_angles_deg: Tuple[float, float, float],
    translation: Tuple[float, float, float],
    new_rtss_filename: str = "RTSTRUCT_transformed.dcm",
    default_color: List[int] = [255, 0, 0]
) -> None:
    """
    Copies an RTStruct, applies a rigid transformation to *all* its ROI masks, and saves
    it relative to a target image series.

    Args:
        source_rtss_path: Path to the source RTStruct file.
        target_image_series_dir: Path to the directory containing the target DICOM series.
        output_dir: Directory where the new RTStruct file will be saved.
        rotation_center: The center of rotation (x, y, z) in mm.
        rotation_angles_deg: The rotation angles (Euler X, Y, Z) in degrees.
        translation: The translation vector (x, y, z) in mm.
        new_rtss_filename: The filename for the newly created RTStruct file.
        default_color: Default color for ROIs if not found in source.

    Raises:
        FileNotFoundError: If input files/directories are not found.
        RuntimeError: If core operations like series loading or RTStruct building fail.
        Exception: For other unexpected errors during processing.
    """
    logging.info(f"Starting RTSS copy with transform (all ROIs): {source_rtss_path} -> {target_image_series_dir}")
    logging.info(f"Transform params: Center={rotation_center}, Angles={rotation_angles_deg}, Translation={translation}")

    # --- 输入检查 ---
    if not os.path.exists(source_rtss_path):
        raise FileNotFoundError(f"源 RTStruct 文件不存在: {source_rtss_path}")
    # target_image_series_dir 的检查在 copy_dicom_series 中进行

    # 使用临时目录避免加载问题
    temp_target_dir = tempfile.mkdtemp(prefix="target_series_")
    temp_source_dir_for_rtstruct = tempfile.mkdtemp(prefix="source_rtstruct_ref_")
    temp_output_dir = tempfile.mkdtemp(prefix="output_rtss_") # 临时输出目录

    try:
        # --- 1. 准备目标系列 (无RTSS) 到临时目录 ---
        logging.info(f"复制目标系列到临时目录: {temp_target_dir}")
        copy_dicom_series(target_image_series_dir, temp_target_dir, exclude_rtstruct=True)
        if not os.listdir(temp_target_dir):
             raise FileNotFoundError(f"复制后临时目标目录为空: {temp_target_dir} (源: {target_image_series_dir})")
        target_ref_image = load_dicom_series_sitk(temp_target_dir)
        if target_ref_image is None:
             raise RuntimeError(f"无法加载临时目标系列图像: {temp_target_dir}")
        logging.info("目标参考图像已从临时目录加载。")

        # --- 2. 准备源 RTStruct 及其参考系列到临时目录 ---
        source_image_series_dir = os.path.dirname(source_rtss_path)
        logging.info(f"复制源系列(无RTSS)到临时目录: {temp_source_dir_for_rtstruct}")
        copy_dicom_series(source_image_series_dir, temp_source_dir_for_rtstruct, exclude_rtstruct=True)
        if not os.listdir(temp_source_dir_for_rtstruct):
             raise FileNotFoundError(f"复制后临时源系列目录为空: {temp_source_dir_for_rtstruct} (源: {source_image_series_dir})")

        logging.info("复制源 RTStruct 到其临时系列目录...")
        temp_source_rtss_path = os.path.join(temp_source_dir_for_rtstruct, os.path.basename(source_rtss_path))
        shutil.copy2(source_rtss_path, temp_source_rtss_path)

        logging.info(f"使用 rt_utils 加载源 RTStruct 从: {temp_source_dir_for_rtstruct}")
        rtstruct = RTStructBuilder.create_from(
            dicom_series_path=temp_source_dir_for_rtstruct,
            rt_struct_path=temp_source_rtss_path
        )
        source_ref_image = load_dicom_series_sitk(temp_source_dir_for_rtstruct)
        if source_ref_image is None:
            raise RuntimeError(f"无法加载临时源参考图像: {temp_source_dir_for_rtstruct}")
        logging.info("源 RTStruct 和参考图像已加载。")

        # --- 3. 创建变换 ---
        transform = sitk.Euler3DTransform()
        transform.SetCenter(rotation_center)
        rotation_angles_rad = [math.radians(a) for a in rotation_angles_deg]
        transform.SetRotation(rotation_angles_rad[0], rotation_angles_rad[1], rotation_angles_rad[2])
        transform.SetTranslation(translation)
        logging.info(f"已创建 Euler3DTransform: Center={transform.GetCenter()}, Angles(rad)={(transform.GetAngleX(), transform.GetAngleY(), transform.GetAngleZ())}, Translation={transform.GetTranslation()}")

        # --- 4. 创建新的 RTStructBuilder，引用目标系列 ---
        new_rtstruct = RTStructBuilder.create_new(dicom_series_path=temp_target_dir)
        logging.info(f"已创建新的 RTStructBuilder，引用临时目标系列: {temp_target_dir}")

        # --- 5. 遍历、处理和添加所有 ROI --- #
        all_roi_names = rtstruct.get_roi_names()
        logging.info(f"源 RTStruct 中的 ROI: {all_roi_names}")
        if not all_roi_names:
            logging.warning("源 RTStruct 中没有找到任何 ROI。将生成一个空的 RTStruct 文件。")

        process_errors = []
        processed_roi_count = 0
        for roi_name in all_roi_names:
            logging.info(f"--- 开始处理 ROI: {roi_name} ---")
            try:
                # a. 获取源掩码 (NumPy, yxz?)
                source_mask_np = rtstruct.get_roi_mask_by_name(roi_name)
                logging.debug(f"获取源掩码 '{roi_name}' (NumPy): shape={source_mask_np.shape}")

                # b. 转换为 SimpleITK Image (zyx) 并赋予几何信息
                source_mask_np_transposed = source_mask_np.transpose((2, 0, 1))
                # 将布尔类型转换为 uint8，因为 GetImageFromArray 不直接支持 bool
                source_mask_sitk = sitk.GetImageFromArray(source_mask_np_transposed.astype(np.uint8))
                if source_mask_sitk.GetSize() != source_ref_image.GetSize():
                     logging.warning(f"ROI '{roi_name}': SITK 掩码尺寸 {source_mask_sitk.GetSize()} 与源参考图像 {source_ref_image.GetSize()} 不匹配！")
                     # 仍然尝试继续
                source_mask_sitk.CopyInformation(source_ref_image) # 分配几何信息
                logging.debug(f"源掩码 '{roi_name}' 已转为 SITK Image: Size={source_mask_sitk.GetSize()}")

                # c. 重采样和变换 (使用 resample_mask_to_target_geometry)
                # 这个函数内部处理变换的反转和插值等
                resampled_transformed_mask_np_transposed = resample_mask_to_target_geometry(
                    source_mask_sitk=source_mask_sitk,
                    target_ref_image=target_ref_image,
                    transform=transform # 正向变换传递给它
                )
                # 返回的是 numpy array (y, x, z)，可以直接给 rt_utils
                logging.debug(f"重采样和变换后的掩码 '{roi_name}' (NumPy, yxz): shape={resampled_transformed_mask_np_transposed.shape}")

                # d. 确保是布尔类型
                final_mask_np = resampled_transformed_mask_np_transposed.astype(bool)

                # e. 获取颜色
                color = default_color
                try:
                    original_ds = pydicom.dcmread(source_rtss_path, force=True)
                    for item in original_ds.StructureSetROISequence:
                        if item.ROIName == roi_name:
                            roi_number_struct_set = item.get("ROINumber")
                            obs_seq = original_ds.get("RTROIObservationsSequence", [])
                            for obs_item in obs_seq:
                                ref_roi_number = obs_item.get("ReferencedROINumber")
                                if ref_roi_number is not None and roi_number_struct_set is not None and ref_roi_number == roi_number_struct_set:
                                    found_color = obs_item.get("ROIDisplayColor")
                                    if found_color: color = [int(c) for c in found_color]; break
                            break
                    if color == default_color:
                        logging.warning(f"ROI '{roi_name}': 未找到颜色，使用默认 {default_color}")
                    else:
                         logging.info(f"ROI '{roi_name}': 找到颜色 {color}")
                except Exception as color_e:
                    logging.warning(f"ROI '{roi_name}': 获取颜色时出错: {color_e}，使用默认 {default_color}")

                # f. 添加到新的 RTStruct
                new_rtstruct.add_roi(
                    mask=final_mask_np, # 应该是 (y, x, z)
                    color=color,
                    name=roi_name
                )
                logging.info(f"成功添加变换和重采样后的 ROI '{roi_name}'。")
                processed_roi_count += 1

            except Exception as roi_e:
                logging.error(f"处理 ROI '{roi_name}' 时发生错误: {roi_e}", exc_info=True)
                process_errors.append(f"ROI '{roi_name}': {roi_e}")

        # --- 6. 保存新的 RTStruct --- #
        if processed_roi_count == 0 and all_roi_names:
             # 如果有 ROI 但全部处理失败
             error_summary = "\n".join(process_errors)
             raise RuntimeError(f"所有 ROI 处理失败，未保存文件。错误摘要:\n{error_summary}")

        # 保存到临时输出目录
        temp_output_path = os.path.join(temp_output_dir, new_rtss_filename)
        logging.info(f"保存变换后的 RTStruct 到临时路径: {temp_output_path}")
        new_rtstruct.save(temp_output_path)

        # 确保最终输出目录存在 (output_dir 是 target_image_series_dir)
        os.makedirs(output_dir, exist_ok=True)
        final_output_path = os.path.join(output_dir, new_rtss_filename)
        logging.info(f"拷贝变换后的 RTStruct 从 {temp_output_path} 到最终路径: {final_output_path}")
        shutil.copy2(temp_output_path, final_output_path)
        logging.info("RTSS 复制和变换成功完成。")

        if process_errors:
             # 如果有非致命错误，在成功保存后记录警告
             logging.warning(f"RTSS 文件已保存，但处理部分 ROI 时遇到错误: {process_errors}")

    except Exception as e:
        logging.error(f"执行 RTSS 复制与变换时出错: {e}", exc_info=True)
        raise # 将异常重新抛出，由调用者处理
    finally:
        # --- 7. 清理临时目录 --- #
        logging.info(f"清理临时目录: {temp_target_dir}, {temp_source_dir_for_rtstruct}, {temp_output_dir}")
        shutil.rmtree(temp_target_dir, ignore_errors=True)
        shutil.rmtree(temp_source_dir_for_rtstruct, ignore_errors=True)
        shutil.rmtree(temp_output_dir, ignore_errors=True)

# ===> Helper function to load DICOM series using SimpleITK <===
def load_dicom_series_sitk(dicom_dir: str) -> Optional[sitk.Image]:
    """Loads a DICOM series from a directory using SimpleITK."""
    try:
        reader = sitk.ImageSeriesReader()
        dicom_names = reader.GetGDCMSeriesFileNames(dicom_dir)
        if not dicom_names:
            logger.error(f"SimpleITK无法在目录中找到DICOM系列: {dicom_dir}")
            return None
        reader.SetFileNames(dicom_names)
        image = reader.Execute()
        logger.info(f"成功使用SimpleITK加载DICOM系列: {dicom_dir}, 大小: {image.GetSize()}")
        return image
    except Exception as e:
        logger.error(f"使用SimpleITK加载DICOM系列时出错: {dicom_dir}, Error: {e}", exc_info=True)
        return None

# ===> Helper function to copy DICOM series, excluding RTSTRUCT if specified <===
def copy_dicom_series(source_dir: str, dest_dir: str, exclude_rtstruct: bool = False):
    """Copies DICOM files from source_dir to dest_dir, optionally excluding RTSTRUCT."""
    os.makedirs(dest_dir, exist_ok=True)
    copied_count = 0
    skipped_rtss_count = 0
    logger.info(f"开始复制 DICOM 系列: {source_dir} -> {dest_dir}, exclude_rtstruct={exclude_rtstruct}")
    for filename in os.listdir(source_dir):
        source_path = os.path.join(source_dir, filename)
        dest_path = os.path.join(dest_dir, filename)
        if os.path.isfile(source_path) and filename.lower().endswith('.dcm'):
            is_rtstruct = False
            if exclude_rtstruct:
                try:
                    # 只需要读头信息来判断 Modality
                    ds = pydicom.dcmread(source_path, stop_before_pixels=True, force=True)
                    if hasattr(ds, 'Modality') and ds.Modality == 'RTSTRUCT':
                        is_rtstruct = True
                except Exception as e:
                    logger.warning(f"读取文件 {filename} 判断 Modality 时出错: {e}, 假设不是 RTSTRUCT。")

            if is_rtstruct:
                logger.debug(f"  跳过 RTSTRUCT 文件: {filename}")
                skipped_rtss_count += 1
                continue

            shutil.copy2(source_path, dest_path)
            copied_count += 1
    logger.info(f"  复制完成: {copied_count} 个文件已复制, {skipped_rtss_count} 个 RTSTRUCT 文件已跳过。")
    if copied_count == 0 and skipped_rtss_count == 0:
        logger.warning(f"  警告: 没有从 {source_dir} 复制任何 .dcm 文件。")

# ===> The missing copy_rtss_between_series function <===
def copy_rtss_between_series(
    source_rtss_path: str,
    source_series_dir: str,
    target_series_dir: str,
    output_rtss_path: str,
    roi_names_to_copy: Optional[List[str]] = None, # 允许指定要复制的ROI名称列表
    default_color: List[int] = [255, 0, 0] # ROI默认颜色
) -> bool:
    """
    将 RTStruct 从源系列复制并适配(重采样)到目标系列。
    使用临时目录处理图像加载，以避免干扰。

    Args:
        source_rtss_path: 源 RTStruct 文件路径。
        source_series_dir: 源 RTStruct 引用的 DICOM 系列文件夹。
        target_series_dir: 目标 DICOM 系列文件夹。
        output_rtss_path: 新生成的 RTStruct 文件保存路径。
        roi_names_to_copy: (可选) 只复制指定的ROI名称列表。如果为 None，则复制所有 ROI。
        default_color: (可选) 如果无法从源 RTStruct 获取颜色，使用的默认 RGB 颜色。

    Returns:
        True if successful, False otherwise.
    """
    logger.info(f"开始处理 RTSS 复制: {source_rtss_path} -> {output_rtss_path}")
    logger.info(f"源系列: {source_series_dir}, 目标系列: {target_series_dir}")

    # --- 输入检查 ---
    if not os.path.exists(source_rtss_path):
        logger.error(f"源 RTStruct 文件不存在: {source_rtss_path}")
        return False
    if not os.path.isdir(source_series_dir):
        logger.error(f"源 DICOM 系列文件夹不存在: {source_series_dir}")
        return False
    if not os.path.isdir(target_series_dir):
        logger.error(f"目标 DICOM 系列文件夹不存在: {target_series_dir}")
        return False

    temp_root_dir = None
    try:
        # ===> 1. 创建临时目录结构 <===
        temp_root_dir = tempfile.mkdtemp(prefix="rtss_copy_")
        logger.info(f"创建临时工作目录: {temp_root_dir}")

        # 临时目录用于存放不含RTSS的源和目标系列副本
        temp_source_series_dir = os.path.join(temp_root_dir, "source_series")
        temp_target_series_dir = os.path.join(temp_root_dir, "target_series")
        # 临时目录用于保存最终生成的RTSS文件，然后再拷贝出去
        temp_output_dir = os.path.join(temp_root_dir, "output")
        os.makedirs(temp_output_dir, exist_ok=True)

        # ===> 2. 准备临时数据 <===
        # 复制源系列 (排除 RTSS) 到临时目录
        logger.info(f"复制源系列(无RTSS)到临时目录: {temp_source_series_dir}")
        copy_dicom_series(source_series_dir, temp_source_series_dir, exclude_rtstruct=True)

        # 复制目标系列 (排除任何可能存在的 RTSS) 到临时目录
        logger.info(f"复制目标系列(无RTSS)到临时目录: {temp_target_series_dir}")
        copy_dicom_series(target_series_dir, temp_target_series_dir, exclude_rtstruct=True)

        # 检查临时目录中是否有文件
        if not os.listdir(temp_source_series_dir):
            raise FileNotFoundError(f"复制后临时源目录为空: {temp_source_series_dir}")
        if not os.listdir(temp_target_series_dir):
             raise FileNotFoundError(f"复制后临时目标目录为空: {temp_target_series_dir}")

        # --- 临时目录准备完成 --- #

        # ===> 3. 加载数据 <===
        # 使用原始 RTSS 文件路径，但指定 Dicom 路径为临时源目录
        # rt_utils 需要源 RTStruct 文件和其对应的 DICOM 系列（即使是临时的）
        # 为了让 rt_utils 能找到 RTSS 文件，需要将其也复制到临时源目录中
        temp_source_rtss_path = os.path.join(temp_source_series_dir, os.path.basename(source_rtss_path))
        logger.info(f"复制源 RTSS 到临时源目录: {temp_source_rtss_path}")
        shutil.copy2(source_rtss_path, temp_source_rtss_path)

        logger.info(f"使用 rt_utils 加载 RTStruct: DICOM Path='{temp_source_series_dir}', RTStruct Path='{temp_source_rtss_path}'")
        source_rtstruct = RTStructBuilder.create_from(
            dicom_series_path=temp_source_series_dir,
            rt_struct_path=temp_source_rtss_path # 使用复制到临时目录的RTSS路径
        )
        logger.info("成功加载源 RTStruct。")

        # 使用 SimpleITK 加载源和目标图像系列（从临时目录加载）
        logger.info("使用 SimpleITK 加载临时源和目标图像系列...")
        source_image_ref = load_dicom_series_sitk(temp_source_series_dir)
        target_image_ref = load_dicom_series_sitk(temp_target_series_dir)

        if source_image_ref is None:
             raise RuntimeError(f"无法加载临时源系列图像: {temp_source_series_dir}")
        if target_image_ref is None:
             raise RuntimeError(f"无法加载临时目标系列图像: {temp_target_series_dir}")

        # ===> 4. 创建新的 RTStructBuilder <===
        # 新的 RTStruct 应引用目标系列（使用临时目标目录）
        logger.info(f"创建新的 RTStructBuilder，引用临时目标系列: {temp_target_series_dir}")
        new_rtstruct = RTStructBuilder.create_new(dicom_series_path=temp_target_series_dir)

        # ===> 5. 处理和复制 ROI <===
        all_roi_names = source_rtstruct.get_roi_names()
        logger.info(f"源 RTStruct 中的 ROI: {all_roi_names}")
        rois_to_process = roi_names_to_copy if roi_names_to_copy is not None else all_roi_names
        logger.info(f"将要处理的 ROI: {rois_to_process}")

        process_success = True
        processed_roi_count = 0
        for roi_name in rois_to_process:
            if roi_name not in all_roi_names:
                logger.warning(f"请求复制的 ROI '{roi_name}' 在源 RTStruct 中不存在，跳过。")
                continue

            logger.info(f"--- 开始处理 ROI: {roi_name} ---")
            try:
                # 1. 获取源 ROI 掩码 (NumPy, rt_utils 返回 y, x, z)
                source_mask_np = source_rtstruct.get_roi_mask_by_name(roi_name)
                logger.debug(f"获取源掩码 '{roi_name}' (NumPy, yxz?): shape={source_mask_np.shape}, dtype={source_mask_np.dtype}")

                # 2. 重采样掩码到目标几何空间 (使用辅助函数)
                resampled_mask_sitk = resample_mask_to_ct_geometry(
                    mask_np=source_mask_np,
                    pt_ref_image=source_image_ref,
                    ct_ref_image=target_image_ref
                )

                if resampled_mask_sitk is None:
                    logger.error(f"ROI '{roi_name}' 重采样失败，跳过此 ROI。")
                    process_success = False
                    continue

                # 3. 将重采样后的 SimpleITK 图像转换回 NumPy 数组
                # 确认轴顺序！ sitk.GetArrayFromImage 返回 (z, y, x)
                resampled_mask_np = sitk.GetArrayFromImage(resampled_mask_sitk)
                logger.debug(f"重采样后的掩码 '{roi_name}' (NumPy, zyx): shape={resampled_mask_np.shape}, dtype={resampled_mask_np.dtype}")

                # 确保掩码是布尔类型 (重采样可能引入非0/1值)
                resampled_mask_bool = resampled_mask_np.astype(bool)
                logger.debug(f"转换为布尔类型后的掩码 '{roi_name}' (NumPy, zyx): shape={resampled_mask_bool.shape}")

                # 4. 获取 ROI 颜色 (从原始 RTSS 文件)
                color = default_color
                try:
                    original_ds = pydicom.dcmread(source_rtss_path, force=True)
                    for item in original_ds.StructureSetROISequence:
                        if item.ROIName == roi_name:
                            # 查找对应的 RTROIObservationsSequence 条目来获取颜色
                            # 需要匹配 ROINumber
                            roi_number_struct_set = item.get("ROINumber")
                            obs_seq = original_ds.get("RTROIObservationsSequence", [])
                            for obs_item in obs_seq:
                                # ROI Observation Label 通常也等于 ROIName，但颜色在 ROIDisplayColor
                                # ReferencedROINumber 应该等于 StructureSetROISequence 中的 ROINumber
                                ref_roi_number = obs_item.get("ReferencedROINumber")
                                if ref_roi_number is not None and roi_number_struct_set is not None and ref_roi_number == roi_number_struct_set:
                                    found_color = obs_item.get("ROIDisplayColor") # DICOM Standard (0070,0284)
                                    if found_color:
                                        color = [int(c) for c in found_color] # 颜色是字符串列表或整数列表
                                        logger.info(f"找到 ROI '{roi_name}' 颜色: {color}")
                                        break # 找到颜色就退出内层循环
                            break # 找到对应的 ROI 条目就退出外层循环
                    if color == default_color:
                         logger.warning(f"无法在源 RTStruct 中找到 ROI '{roi_name}' 的颜色，使用默认值: {default_color}")
                except Exception as color_e:
                    logger.warning(f"尝试获取 ROI '{roi_name}' 颜色时出错: {color_e}，使用默认值: {default_color}")

                # 5. 添加重采样后的 ROI 到新的 RTStruct
                # !! 关键: rt_utils 的 add_roi 需要什么形状的 mask? !!
                # 根据之前的经验和 rt_utils 文档（通常期望 z 在最后），我们可能需要再次转置
                # 从 (z, y, x) 转回 (y, x, z)? 或者是 (z, y, x) -> (y, x, z) ??
                # 让我们坚持之前的结论：resample_mask_to_ct_geometry 返回的 SITK 图像，GetArrayFromImage(img) 得到 zyx
                # 而 rt_utils.add_roi 期望 yxz 或 zyx? 文档和实验是关键。
                # 假设 rt_utils add_roi 期望 (y, x, z) - 这与我们从 rt_utils get_roi_mask 得到的格式一致
                # 因此，需要将 resampled_mask_bool (z, y, x) 转置为 (y, x, z)
                final_mask_for_rtutils = resampled_mask_bool.transpose((1, 2, 0))
                logger.debug(f"为 rt_utils.add_roi 准备的最终掩码 '{roi_name}' (NumPy, yxz): shape={final_mask_for_rtutils.shape}")

                new_rtstruct.add_roi(
                    mask=final_mask_for_rtutils,
                    color=color,
                    name=roi_name # 可以修改名称，但通常保留原名
                )
                logger.info(f"成功添加重采样后的 ROI '{roi_name}' 到新 RTStruct。")
                processed_roi_count += 1

            except Exception as roi_e:
                logger.error(f"处理 ROI '{roi_name}' 时发生错误: {roi_e}", exc_info=True)
                process_success = False # 标记处理中出现错误，但继续处理其他 ROI

        # ===> 6. 保存新的 RTStruct 文件 <===
        if processed_roi_count > 0: # 只有成功处理了至少一个 ROI 才保存
            # 先保存到临时输出目录
            temp_output_filename = os.path.basename(output_rtss_path)
            temp_output_rtss_path = os.path.join(temp_output_dir, temp_output_filename)
            logger.info(f"尝试将新的 RTStruct 保存到临时路径: {temp_output_rtss_path}")
            new_rtstruct.save(temp_output_rtss_path)
            logger.info(f"成功保存到临时路径: {temp_output_rtss_path}")

            # 确保最终目标目录存在
            final_output_dir = os.path.dirname(output_rtss_path)
            if final_output_dir and not os.path.exists(final_output_dir): os.makedirs(final_output_dir)

            # 从临时目录拷贝到最终目标路径
            logger.info(f"将临时 RTStruct 文件从 {temp_output_rtss_path} 拷贝到最终路径 {output_rtss_path}")
            shutil.copy2(temp_output_rtss_path, output_rtss_path)
            logger.info(f"成功拷贝到最终路径。")
            # 只有当所有请求的ROI都成功处理时，才返回True吗？还是只要至少有一个成功就返回True？
            # 目前逻辑：只要至少处理成功一个ROI且未发生其他致命错误，就返回True
            return process_success # 如果中途有非致命ROI错误，process_success会是False
        elif not rois_to_process: # 如果压根没有要处理的ROI
             logger.warning("没有指定要处理的 ROI，未生成 RTStruct 文件。")
             return False
        else: # 如果有要处理的ROI，但全部失败了
            logger.error("所有请求的 ROI 都处理失败，未生成 RTStruct 文件。")
            return False

    except ImportError as import_err:
         logger.error(f"缺少必要的库: {import_err}", exc_info=True)
         return False
    except FileNotFoundError as fnf_err:
         logger.error(f"处理过程中文件或目录未找到: {fnf_err}", exc_info=True)
         return False
    except Exception as e:
        logger.error(f"复制 RTStruct 时发生意外错误: {e}", exc_info=True)
        return False
    finally:
        # ===> 7. 清理临时目录 <===
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
        # 测试不带变换的复制
        logger.info("--- 测试 copy_rtss_between_series ---")
        success_no_tx = copy_rtss_between_series(
            source_rtss_path=pt_rtss_path,
            source_series_dir=pt_series_dir,
            target_series_dir=ct_series_dir,
            output_rtss_path=output_rtss_path
        )
        if success_no_tx:
            logger.info("测试 copy_rtss_between_series 成功！")
        else:
            logger.error("测试 copy_rtss_between_series 失败。")

        # 测试带变换的复制 (使用身份变换作为示例)
        logger.info("--- 测试 copy_rtss_with_transform (身份变换) ---")
        output_rtss_tx_path = os.path.join(base_test_dir, 'week4_PT', 'RS.week4_PT_from_W0PT_IdentityTx.dcm')
        target_series_tx_dir = os.path.join(base_test_dir, 'week4_PT')
        if not os.path.isdir(target_series_tx_dir):
             logger.warning(f"测试带变换复制所需的目标目录不存在: {target_series_tx_dir}")
        else:
            try:
                copy_rtss_with_transform(
                    source_rtss_path=pt_rtss_path,
                    target_image_series_dir=target_series_tx_dir,
                    output_dir=target_series_tx_dir,
                    rotation_center=(0, 0, 0),
                    rotation_angles_deg=(0, 0, 0),
                    translation=(0, 0, 0),
                    new_rtss_filename=os.path.basename(output_rtss_tx_path)
                )
                logger.info("测试 copy_rtss_with_transform (身份变换) 成功！")
            except Exception as tx_e:
                logger.error(f"测试 copy_rtss_with_transform (身份变换) 失败: {tx_e}", exc_info=True) 