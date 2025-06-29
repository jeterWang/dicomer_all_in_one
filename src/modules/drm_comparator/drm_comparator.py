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

    def apply_transformations(self) -> Tuple[bool, str]:
        """
        Applies the loaded rigid and deformation transformations to the NIfTI image.
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

            return True, "Transformations applied successfully."
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
