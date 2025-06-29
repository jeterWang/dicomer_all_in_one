import SimpleITK as sitk
import pydicom
import numpy as np
import os
from typing import Optional, Tuple


class DrmComparator:
    """
    A class to compare a NIfTI mask after applying a rigid transformation
    and a deformation field, both from DICOM sources.
    """

    def __init__(self):
        self.nifti_image: Optional[sitk.Image] = None
        self.rigid_transform: Optional[sitk.AffineTransform] = None
        self.dvf_transform: Optional[sitk.DisplacementFieldTransform] = None
        self.rigid_transformed_image: Optional[sitk.Image] = None
        self.final_transformed_image: Optional[sitk.Image] = None
        self.reference_image_for_dvf: Optional[sitk.Image] = None
        self.target_space_image: Optional[sitk.Image] = None

    def load_nifti(self, file_path: str) -> bool:
        """Loads a NIfTI file, preserving its original data type."""
        try:
            self.nifti_image = sitk.ReadImage(file_path, sitk.sitkFloat64)
            print(f"Successfully loaded NIfTI image: {file_path}")
            print("--- Original NIfTI Image ---")
            print(self.nifti_image)
            print("------------------------------")
            return True
        except Exception as e:
            print(f"Error loading NIfTI file: {e}")
            self.nifti_image = None
            return False

    def load_rigid_transform(self, reg_file_path: str) -> bool:
        """
        Loads a rigid transformation from a DICOM REG file.
        It looks for the Frame of Reference Transformation Matrix.
        """
        try:
            reg_ds = pydicom.dcmread(reg_file_path)
            if (
                reg_ds.SOPClassUID != "1.2.840.10008.5.1.4.1.1.66.1"
            ):  # Registration SOP Class
                print(
                    f"Warning: The provided file may not be a DICOM REG file. SOPClassUID: {reg_ds.SOPClassUID}"
                )

            reg_seq = reg_ds.RegistrationSequence[1]
            matrix_reg_seq = reg_seq.MatrixRegistrationSequence[0]
            matrix_seq = matrix_reg_seq.MatrixSequence[0]

            matrix_data = matrix_seq[0x3006, 0x00C6].value
            matrix = np.array(matrix_data, dtype=float).reshape((4, 4))

            rotation_matrix = matrix[0:3, 0:3]
            translation_vector = matrix[0:3, 3]

            print("-" * 20)
            print("DICOM REG Transformation Details:")
            print(f"  - Translation (x, y, z): {translation_vector.tolist()}")
            print(f"  - Rotation Matrix:\n{rotation_matrix}")
            print("-" * 20)

            transform = sitk.AffineTransform(3)
            transform.SetMatrix(rotation_matrix.flatten().tolist())
            transform.SetTranslation(translation_vector.tolist())

            self.rigid_transform = transform
            print(f"Successfully loaded rigid transform from: {reg_file_path}")
            return True
        except Exception as e:
            print(f"Error loading DICOM REG file: {e}")
            self.rigid_transform = None
            return False

    def load_dvf(self, dvf_file_path: str) -> bool:
        """
        Loads a Deformation Vector Field (DVF) from a DICOM DVF file,
        parsing the DeformableRegistrationGridSequence.
        """
        try:
            dvf_ds = pydicom.dcmread(dvf_file_path)

            # --- DVF File Inspection ---
            print("\n" + "=" * 30)
            print("DVF DICOM Header Inspection Start")
            print(dvf_ds)
            print("DVF DICOM Header Inspection End")
            print("=" * 30 + "\n")
            # --- End Inspection ---

            if not hasattr(dvf_ds, "DeformableRegistrationSequence"):
                print(
                    "Error: 'DeformableRegistrationSequence' not found in the dataset."
                )
                return False

            grid_item = None
            for deform_reg_item in dvf_ds.DeformableRegistrationSequence:
                if hasattr(deform_reg_item, "DeformableRegistrationGridSequence"):
                    grid_item = deform_reg_item.DeformableRegistrationGridSequence[0]
                    break

            if grid_item is None:
                print(
                    "Error: Could not find 'DeformableRegistrationGridSequence' in any item."
                )
                return False

            size = tuple(map(int, grid_item.GridDimensions))
            origin = tuple(map(float, grid_item.ImagePositionPatient))

            # GridResolution provides spacing information. Try to get XYZ spacing from it first.
            grid_resolution = tuple(map(float, grid_item.GridResolution))
            print(f"Grid Resolution (XYZ Spacing): {grid_resolution}")

            if len(grid_resolution) >= 3:
                # GridResolution contains X, Y, Z spacing
                x_spacing = grid_resolution[0]
                y_spacing = grid_resolution[1]
                z_spacing = grid_resolution[2]
                print(
                    f"Using GridResolution for all three axes: X={x_spacing}, Y={y_spacing}, Z={z_spacing}"
                )
            elif len(grid_resolution) >= 2:
                # GridResolution only contains X, Y spacing, need to determine Z
                x_spacing = grid_resolution[0]
                y_spacing = grid_resolution[1]
                z_spacing = 0.0

                if (
                    hasattr(grid_item, "GridFrameOffsetVector")
                    and len(grid_item.GridFrameOffsetVector) > 1
                ):
                    z_spacing = (
                        grid_item.GridFrameOffsetVector[1]
                        - grid_item.GridFrameOffsetVector[0]
                    )
                    print(f"Z spacing from GridFrameOffsetVector: {z_spacing}")
                elif hasattr(dvf_ds, "PerFrameFunctionalGroupsSequence"):
                    # Fallback to another common tag if GridFrameOffsetVector is not available
                    try:
                        slice_dist_item = dvf_ds.PerFrameFunctionalGroupsSequence[
                            0
                        ].PixelMeasuresSequence[0]
                        z_spacing = float(slice_dist_item.SpacingBetweenSlices)
                        print(
                            f"Z spacing from PerFrameFunctionalGroupsSequence: {z_spacing}"
                        )
                    except (AttributeError, IndexError):
                        print(
                            "Warning: Could not determine Z spacing from PerFrameFunctionalGroupsSequence. Defaulting to 1.0"
                        )
                        z_spacing = 1.0
                else:
                    print("Warning: Z-spacing information not found. Defaulting to 1.0")
                    z_spacing = 1.0
            else:
                print(
                    "Error: GridResolution does not contain enough values. Cannot proceed."
                )
                return False

            spacing = (x_spacing, y_spacing, z_spacing)

            vectors_float32 = np.frombuffer(grid_item.VectorGridData, dtype=np.float32)
            vectors_float64 = vectors_float32.astype(np.float64)

            # Separate the components
            dx = (
                vectors_float64[0::3]
                .reshape(size[2], size[1], size[0])
                .transpose(2, 1, 0)
            )
            dy = (
                vectors_float64[1::3]
                .reshape(size[2], size[1], size[0])
                .transpose(2, 1, 0)
            )
            dz = (
                vectors_float64[2::3]
                .reshape(size[2], size[1], size[0])
                .transpose(2, 1, 0)
            )

            # --- DVF Data Inspection ---
            print("\n" + "-" * 20)
            print("DVF Data Inspection Start")
            print(f"  Grid Dimensions: {grid_item.GridDimensions}")
            print(f"  Image Position (Origin): {grid_item.ImagePositionPatient}")
            print(f"  Grid Resolution (XY Spacing): {grid_item.GridResolution}")
            if hasattr(grid_item, "ImageOrientationPatient"):
                print(f"  Image Orientation: {grid_item.ImageOrientationPatient}")

            print("\n  Displacement Vector Statistics (in mm):")
            stats_dx = (dx.min(), dx.max(), dx.mean(), dx.std())
            stats_dy = (dy.min(), dy.max(), dy.mean(), dy.std())
            stats_dz = (dz.min(), dz.max(), dz.mean(), dz.std())
            print(
                f"  - X component (dx): min={stats_dx[0]:.4f}, max={stats_dx[1]:.4f}, mean={stats_dx[2]:.4f}, std={stats_dx[3]:.4f}"
            )
            print(
                f"  - Y component (dy): min={stats_dy[0]:.4f}, max={stats_dy[1]:.4f}, mean={stats_dy[2]:.4f}, std={stats_dy[3]:.4f}"
            )
            print(
                f"  - Z component (dz): min={stats_dz[0]:.4f}, max={stats_dz[1]:.4f}, mean={stats_dz[2]:.4f}, std={stats_dz[3]:.4f}"
            )
            print("DVF Data Inspection End")
            print("-" * 20 + "\n")
            # --- End Inspection ---

            # Create a scalar image for each component
            dx_image = sitk.GetImageFromArray(dx, isVector=False)
            dy_image = sitk.GetImageFromArray(dy, isVector=False)
            dz_image = sitk.GetImageFromArray(dz, isVector=False)

            # Compose them into a vector image
            dvf_image = sitk.Compose(dx_image, dy_image, dz_image)
            dvf_image.SetOrigin(origin)
            dvf_image.SetSpacing(spacing)

            if hasattr(grid_item, "ImageOrientationPatient"):
                direction = grid_item.ImageOrientationPatient
                dvf_image.SetDirection([float(d) for d in direction] + [0.0, 0.0, 1.0])
            else:
                dvf_image.SetDirection([1, 0, 0, 0, 1, 0, 0, 0, 1])

            # Create a scalar reference image that defines the grid for the DVF.
            # This is crucial for ensuring all metadata is correctly handled in 3D.
            self.reference_image_for_dvf = sitk.Image(size, sitk.sitkUInt8)
            self.reference_image_for_dvf.SetOrigin(origin)
            self.reference_image_for_dvf.SetSpacing(spacing)

            direction_matrix = np.identity(3).flatten().tolist()  # Default to identity
            if hasattr(grid_item, "ImageOrientationPatient"):
                iop = [float(v) for v in grid_item.ImageOrientationPatient]
                row1 = iop[0:3]
                row2 = iop[3:6]
                row3 = np.cross(row1, row2)
                direction_matrix = row1 + row2 + list(row3)

            self.reference_image_for_dvf.SetDirection(direction_matrix)
            print("--- DVF Reference Grid Image ---")
            print(self.reference_image_for_dvf)
            print("--------------------------------")

            # Now, create the DVF transform itself.
            self.dvf_transform = sitk.DisplacementFieldTransform(dvf_image)
            self.dvf_transform.SetFixedParameters(
                self.reference_image_for_dvf.GetSize()
                + self.reference_image_for_dvf.GetOrigin()
                + self.reference_image_for_dvf.GetSpacing()
                + self.reference_image_for_dvf.GetDirection()
            )

            print(f"Successfully loaded DVF from: {dvf_file_path}")
            return True
        except Exception as e:
            print(f"Error loading DICOM DVF file: {e}")
            self.dvf_transform = None
            return False

    def apply_transformations_direct_to_target(self, target_image_path: str) -> Tuple[bool, str]:
        """
        直接将变换应用到目标空间，避免中间重采样步骤，减少累积误差。
        这是推荐的方法，因为它只进行一次插值操作。

        Args:
            target_image_path: 目标图像路径，用于定义输出空间

        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        if self.nifti_image is None:
            return False, "NIfTI image not loaded."
        if self.rigid_transform is None:
            return False, "Rigid transform not loaded."
        if self.dvf_transform is None:
            return False, "DVF not loaded."

        try:
            # 加载目标图像定义输出空间
            target_img = sitk.ReadImage(target_image_path)
            print(f"Loaded target space image from: {target_image_path}")

            print("--- Target Space Information ---")
            print(f"Target size: {target_img.GetSize()}")
            print(f"Target spacing: {target_img.GetSpacing()}")
            print(f"Target origin: {target_img.GetOrigin()}")
            print("--------------------------------")

            # 创建复合变换
            composite_transform = sitk.CompositeTransform(3)
            composite_transform.AddTransform(self.rigid_transform)
            composite_transform.AddTransform(self.dvf_transform)
            print("Created composite transform: Rigid + DVF")

            # 直接重采样到目标空间（一步到位，减少误差）
            resampler = sitk.ResampleImageFilter()
            resampler.SetReferenceImage(target_img)  # 使用目标图像定义输出空间
            resampler.SetInterpolator(sitk.sitkLinear)
            resampler.SetTransform(composite_transform)
            resampler.SetOutputPixelType(self.nifti_image.GetPixelID())
            resampler.SetDefaultPixelValue(0.0)

            # 执行变换（一次插值完成所有变换）
            self.target_space_image = resampler.Execute(self.nifti_image)

            print("--- Final Result Information ---")
            print(f"Result size: {self.target_space_image.GetSize()}")
            print(f"Result spacing: {self.target_space_image.GetSpacing()}")
            print(f"Result origin: {self.target_space_image.GetOrigin()}")
            print("--------------------------------")

            print("✓ Successfully applied transformations directly to target space (single interpolation)")

            # 同时生成仅刚体变换的结果用于对比
            resampler_rigid = sitk.ResampleImageFilter()
            resampler_rigid.SetReferenceImage(target_img)  # 也使用目标空间
            resampler_rigid.SetInterpolator(sitk.sitkLinear)
            resampler_rigid.SetTransform(self.rigid_transform)
            resampler_rigid.SetOutputPixelType(self.nifti_image.GetPixelID())
            resampler_rigid.SetDefaultPixelValue(0.0)
            self.rigid_transformed_image = resampler_rigid.Execute(self.nifti_image)
            print("✓ Also generated rigid-only transformation in target space for comparison")

            return True, "Transformations applied directly to target space successfully (optimized single-step method)"

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"An error occurred during direct transformation to target space: {e}"

    def apply_transformations(self, target_image_path: str = None, direct_to_target: bool = True) -> Tuple[bool, str]:
        """
        应用变换，支持两种模式：
        1. 直接到目标空间（推荐）：减少插值误差，提高精度
        2. 传统分步方式：先到DVF空间，再重采样到目标空间

        Args:
            target_image_path: 目标图像路径（direct_to_target=True时必需）
            direct_to_target: 是否直接重采样到目标空间（推荐True）

        Returns:
            Tuple[bool, str]: (成功标志, 消息)
        """
        if direct_to_target and target_image_path:
            print("🚀 Using optimized direct-to-target transformation method")
            return self.apply_transformations_direct_to_target(target_image_path)
        else:
            print("⚠️  Using traditional two-step transformation method")
            return self._apply_transformations_traditional()

    def _apply_transformations_traditional(self) -> Tuple[bool, str]:
        """
        传统的分步变换方法（保留用于调试和对比）
        """
        if self.nifti_image is None:
            return False, "NIfTI image not loaded."
        if self.rigid_transform is None:
            return False, "Rigid transform not loaded."
        if self.dvf_transform is None:
            return False, "DVF not loaded."

        try:
            # Create a composite transform
            composite_transform = sitk.CompositeTransform(3)
            composite_transform.AddTransform(self.rigid_transform)
            composite_transform.AddTransform(self.dvf_transform)

            # Resample the nifti image using the composite transform
            # Use DVF reference image to define the output space (final target space)
            resampler = sitk.ResampleImageFilter()
            if self.reference_image_for_dvf is not None:
                resampler.SetReferenceImage(self.reference_image_for_dvf)
                print("Using DVF reference image for final transformation output space")
            else:
                resampler.SetReferenceImage(self.nifti_image)
                print(
                    "Warning: DVF reference image not available, using original image space"
                )
            resampler.SetInterpolator(sitk.sitkLinear)
            resampler.SetTransform(composite_transform)
            resampler.SetOutputPixelType(self.nifti_image.GetPixelID())
            resampler.SetDefaultPixelValue(0.0)

            self.final_transformed_image = resampler.Execute(self.nifti_image)
            print("Successfully applied composite transformation.")

            # For debugging, also save the rigid-only transformation
            resampler_rigid = sitk.ResampleImageFilter()
            resampler_rigid.SetReferenceImage(self.nifti_image)
            resampler_rigid.SetInterpolator(sitk.sitkLinear)
            resampler_rigid.SetTransform(self.rigid_transform)
            resampler_rigid.SetOutputPixelType(self.nifti_image.GetPixelID())
            resampler_rigid.SetDefaultPixelValue(0.0)
            self.rigid_transformed_image = resampler_rigid.Execute(self.nifti_image)
            print(
                "Successfully generated intermediate rigid-transformed image for comparison."
            )

            return True, "Transformations applied successfully (traditional method)."
        except Exception as e:
            import traceback

            traceback.print_exc()
            return False, f"An error occurred during transformation: {e}"

    def save_image(self, image: sitk.Image, file_path: str) -> bool:
        """Saves a SimpleITK image to a file."""
        try:
            sitk.WriteImage(image, file_path)
            print(f"Image saved to: {file_path}")
            return True
        except Exception as e:
            print(f"Error saving image: {e}")
            return False

    def apply_rigid_transform_only(self, output_path: str) -> Tuple[bool, str]:
        """
        Applies only the loaded rigid transformation to the NIfTI image and saves it.
        """
        if self.nifti_image is None:
            return False, "NIfTI image not loaded."
        if self.rigid_transform is None:
            return False, "Rigid transform not loaded."

        try:
            resampler = sitk.ResampleImageFilter()
            resampler.SetReferenceImage(self.nifti_image)
            resampler.SetInterpolator(sitk.sitkLinear)
            resampler.SetTransform(self.rigid_transform)
            resampler.SetOutputPixelType(self.nifti_image.GetPixelID())

            rigid_only_image = resampler.Execute(self.nifti_image)
            print("Successfully applied rigid transformation.")

            self.save_image(rigid_only_image, output_path)
            return (
                True,
                f"Successfully applied rigid transform and saved to {output_path}",
            )
        except Exception as e:
            return False, f"An error occurred during rigid transformation: {e}"

    def resample_to_target_space(self, target_image_path: str) -> Tuple[bool, str]:
        """
        Resamples the final transformed image to the target space defined by the target image.
        This is the third step in the three-step registration pipeline:
        1. Original -> Rigid transform -> Intermediate space
        2. Intermediate -> DVF transform -> DVF space
        3. DVF space -> Resample -> Target space
        """
        if self.final_transformed_image is None:
            return (
                False,
                "Final transformed image not available. Please run apply_transformations() first.",
            )

        try:
            # Load target image to get target space information
            target_img = sitk.ReadImage(target_image_path)
            print(f"Loaded target space image from: {target_image_path}")

            print("--- Target Space Information ---")
            print(f"Target size: {target_img.GetSize()}")
            print(f"Target spacing: {target_img.GetSpacing()}")
            print(f"Target origin: {target_img.GetOrigin()}")
            print("--------------------------------")

            print("--- Current DVF Space Information ---")
            print(f"DVF size: {self.final_transformed_image.GetSize()}")
            print(f"DVF spacing: {self.final_transformed_image.GetSpacing()}")
            print(f"DVF origin: {self.final_transformed_image.GetOrigin()}")
            print("------------------------------------")

            # Create resampler for target space
            resampler = sitk.ResampleImageFilter()
            resampler.SetReferenceImage(
                target_img
            )  # Use target image to define output space
            resampler.SetInterpolator(sitk.sitkLinear)  # Bilinear interpolation
            resampler.SetTransform(
                sitk.Transform(3, sitk.sitkIdentity)
            )  # Identity transform (no additional deformation)
            resampler.SetOutputPixelType(self.final_transformed_image.GetPixelID())
            resampler.SetDefaultPixelValue(0.0)

            # Execute resampling
            self.target_space_image = resampler.Execute(self.final_transformed_image)

            print("--- Final Target Space Result ---")
            print(f"Final size: {self.target_space_image.GetSize()}")
            print(f"Final spacing: {self.target_space_image.GetSpacing()}")
            print(f"Final origin: {self.target_space_image.GetOrigin()}")
            print("---------------------------------")

            print("Successfully resampled to target space.")
            return (
                True,
                "Successfully resampled final transformed image to target space.",
            )

        except Exception as e:
            import traceback

            traceback.print_exc()
            return False, f"An error occurred during target space resampling: {e}"

    def compare_resampling_methods(self, target_image_path: str, output_dir: str = "comparison_output") -> Tuple[bool, str]:
        """
        比较直接重采样和传统分步重采样的结果差异

        Args:
            target_image_path: 目标图像路径
            output_dir: 输出目录

        Returns:
            Tuple[bool, str]: (成功标志, 比较结果消息)
        """
        try:
            import os
            os.makedirs(output_dir, exist_ok=True)

            print("🔬 开始比较两种重采样方法...")

            # 方法1: 直接重采样到目标空间
            print("\n--- 方法1: 直接重采样到目标空间 ---")
            success1, msg1 = self.apply_transformations_direct_to_target(target_image_path)
            if not success1:
                return False, f"直接重采样失败: {msg1}"

            # 保存直接重采样结果
            direct_result = sitk.Image(self.target_space_image)  # 创建副本
            self.save_image(direct_result, os.path.join(output_dir, "direct_method_result.nii.gz"))

            # 方法2: 传统分步重采样
            print("\n--- 方法2: 传统分步重采样 ---")
            success2, msg2 = self._apply_transformations_traditional()
            if not success2:
                return False, f"传统重采样失败: {msg2}"

            success3, msg3 = self.resample_to_target_space(target_image_path)
            if not success3:
                return False, f"目标空间重采样失败: {msg3}"

            # 保存传统重采样结果
            traditional_result = sitk.Image(self.target_space_image)  # 创建副本
            self.save_image(traditional_result, os.path.join(output_dir, "traditional_method_result.nii.gz"))

            # 计算差异
            print("\n--- 计算两种方法的差异 ---")
            diff_filter = sitk.SubtractImageFilter()
            difference_image = diff_filter.Execute(direct_result, traditional_result)
            self.save_image(difference_image, os.path.join(output_dir, "difference_image.nii.gz"))

            # 统计差异
            stats_filter = sitk.StatisticsImageFilter()
            stats_filter.Execute(difference_image)

            abs_diff_image = sitk.Abs(difference_image)
            stats_filter.Execute(abs_diff_image)

            max_diff = stats_filter.GetMaximum()
            mean_diff = stats_filter.GetMean()
            std_diff = stats_filter.GetSigma()

            # 计算相对差异
            stats_filter.Execute(direct_result)
            max_value = stats_filter.GetMaximum()
            relative_max_diff = (max_diff / max_value * 100) if max_value > 0 else 0

            result_msg = f"""
📊 重采样方法比较结果:
✅ 直接重采样: 成功
✅ 传统重采样: 成功

📈 差异统计:
- 最大绝对差异: {max_diff:.6f}
- 平均绝对差异: {mean_diff:.6f}
- 差异标准差: {std_diff:.6f}
- 最大相对差异: {relative_max_diff:.3f}%

📁 输出文件:
- 直接方法结果: {output_dir}/direct_method_result.nii.gz
- 传统方法结果: {output_dir}/traditional_method_result.nii.gz
- 差异图像: {output_dir}/difference_image.nii.gz

💡 建议: {'直接重采样方法精度更高' if max_diff < mean_diff else '两种方法差异较小'}
            """

            print(result_msg)
            return True, result_msg

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"比较过程中出错: {e}"

    def save_target_space_image(self, output_path: str) -> Tuple[bool, str]:
        """
        Saves the target space resampled image to a file.
        """
        if self.target_space_image is None:
            return (
                False,
                "Target space image not available. Please run resample_to_target_space() first.",
            )

        try:
            self.save_image(self.target_space_image, output_path)
            return True, f"Successfully saved target space image to {output_path}"
        except Exception as e:
            return False, f"An error occurred while saving target space image: {e}"
