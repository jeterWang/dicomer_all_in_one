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

    def load_nifti(self, file_path: str) -> bool:
        """Loads a NIfTI file, preserving its original data type."""
        try:
            self.nifti_image = sitk.ReadImage(file_path, sitk.sitkFloat64)
            print(f"Successfully loaded NIfTI image: {file_path}")
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
            if reg_ds.SOPClassUID != '1.2.840.10008.5.1.4.1.1.66.1': # Registration SOP Class
                 print(f"Warning: The provided file may not be a DICOM REG file. SOPClassUID: {reg_ds.SOPClassUID}")

            # Navigate to the transformation matrix
            # This file has multiple registration items, the actual transform is in the second one.
            reg_seq = reg_ds.RegistrationSequence[1]
            matrix_reg_seq = reg_seq.MatrixRegistrationSequence[0]
            matrix_seq = matrix_reg_seq.MatrixSequence[0]
            
            # Correctly access the matrix by its tag (3006,00C6)
            matrix_data = matrix_seq[0x3006, 0x00C6].value
            matrix = np.array(matrix_data, dtype=float).reshape((4, 4))

            rotation_matrix = matrix[0:3, 0:3]
            translation_vector = matrix[0:3, 3]
            
            # --- DEBUG: Print the transformation details ---
            print("-" * 20)
            print("DICOM REG Transformation Details:")
            print(f"  - Translation (x, y, z): {translation_vector.tolist()}")
            print(f"  - Rotation Matrix:\n{rotation_matrix}")
            print("-" * 20)
            # --- END DEBUG ---

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
        Loads a Deformation Vector Field (DVF) from a DICOM DVF file.
        """
        try:
            dvf_ds = pydicom.dcmread(dvf_file_path)
            if dvf_ds.SOPClassUID != '1.2.840.10008.5.1.4.1.1.66.4': # Deformable Spatial Registration SOP Class
                print(f"Warning: The provided file may not be a DICOM DVF file. SOPClassUID: {dvf_ds.SOPClassUID}")

            pixel_data = dvf_ds.pixel_array.astype(np.float64)
            pixel_data = np.transpose(pixel_data, (2, 1, 0, 3))
            dvf_image = sitk.GetImageFromArray(pixel_data, isVector=True)
            
            dvf_image.SetSpacing([dvf_ds.PixelSpacing[1], dvf_ds.PixelSpacing[0], dvf_ds.SliceThickness])
            dvf_image.SetOrigin(dvf_ds.ImagePositionPatient)
            
            orientation = dvf_ds.ImageOrientationPatient
            direction = [orientation[0], orientation[1], orientation[2],
                         orientation[3], orientation[4], orientation[5],
                         0, 0, 1]
            dvf_image.SetDirection(direction)

            self.dvf_transform = sitk.DisplacementFieldTransform(dvf_image)
            self.reference_image_for_dvf = sitk.Image(dvf_image.GetSize(), sitk.sitkUInt8)
            self.reference_image_for_dvf.CopyInformation(dvf_image)

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
        if self.reference_image_for_dvf is None:
            return False, "DVF reference grid is not available."

        try:
            resampler = sitk.ResampleImageFilter()
            resampler.SetReferenceImage(self.reference_image_for_dvf)
            resampler.SetInterpolator(sitk.sitkLinear)
            resampler.SetTransform(self.rigid_transform)
            resampler.SetOutputPixelType(self.nifti_image.GetPixelID())
            
            self.rigid_transformed_image = resampler.Execute(self.nifti_image)
            print("Successfully applied rigid transformation.")

            warp_filter = sitk.WarpImageFilter()
            warp_filter.SetInterpolator(sitk.sitkLinear)
            warp_filter.SetOutputParameterization(sitk.WarpImageFilter.Displacement)
            warp_filter.SetOutputPixelType(self.nifti_image.GetPixelID())
            warp_filter.SetDisplacementField(self.dvf_transform.GetDisplacementField())

            self.final_transformed_image = warp_filter.Execute(self.rigid_transformed_image)
            print("Successfully applied deformation field.")
            
            return True, "Transformations applied successfully."
        except Exception as e:
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
            return True, f"Successfully applied rigid transform and saved to {output_path}"
        except Exception as e:
            return False, f"An error occurred during rigid transformation: {e}"