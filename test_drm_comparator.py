import unittest
import os
import SimpleITK as sitk
import numpy as np

# Add the project root to the Python path to allow for absolute imports
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.modules.drm_comparator.drm_comparator import DrmComparator


class TestDrmComparator(unittest.TestCase):

    def setUp(self):
        """Set up the test environment."""
        self.comparator = DrmComparator()
        self.test_data_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "data", "drm_data")
        )
        self.output_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "output", "test_drm_comparator")
        )

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        # Define file paths
        self.nifti_path = os.path.join(self.test_data_dir, "DRM.nii.gz")
        self.reg_path = os.path.join(self.test_data_dir, "moving.dcm")
        self.dvf_path = os.path.join(self.test_data_dir, "deformable.dcm")

    def test_01_file_loading(self):
        """Test the loading of NIfTI, DICOM REG, and DICOM DVF files."""
        # Test NIfTI loading
        self.assertTrue(
            self.comparator.load_nifti(self.nifti_path),
            "NIfTI file should load successfully.",
        )
        self.assertIsInstance(
            self.comparator.nifti_image,
            sitk.Image,
            "Loaded NIfTI should be a SimpleITK Image.",
        )

        # Test DICOM REG loading
        self.assertTrue(
            self.comparator.load_rigid_transform(self.reg_path),
            "DICOM REG file should load successfully.",
        )
        self.assertIsInstance(
            self.comparator.rigid_transform,
            sitk.AffineTransform,
            "Loaded rigid transform should be an AffineTransform.",
        )

        # Test DICOM DVF loading
        self.assertTrue(
            self.comparator.load_dvf(self.dvf_path),
            "DICOM DVF file should load successfully.",
        )
        self.assertIsInstance(
            self.comparator.dvf_transform,
            sitk.DisplacementFieldTransform,
            "Loaded DVF should be a DisplacementFieldTransform.",
        )
        self.assertIsInstance(
            self.comparator.reference_image_for_dvf,
            sitk.Image,
            "DVF reference image should be created.",
        )

    def test_02_transformation_pipeline(self):
        """Test the full transformation pipeline from loading to result."""
        # Step 1: Load all necessary files
        self.comparator.load_nifti(self.nifti_path)
        self.comparator.load_rigid_transform(self.reg_path)
        self.comparator.load_dvf(self.dvf_path)

        # Step 2: Apply transformations
        success, message = self.comparator.apply_transformations()
        self.assertTrue(
            success, f"Transformation pipeline failed with message: {message}"
        )

        # Step 3: Verify the outputs
        self.assertIsNotNone(
            self.comparator.rigid_transformed_image,
            "Rigidly transformed image should not be None.",
        )
        self.assertIsNotNone(
            self.comparator.final_transformed_image,
            "Final deformed image should not be None.",
        )

        # Step 4: Verify metadata of the final image
        # The final image should have the same metadata as the DVF reference grid
        ref_img = self.comparator.reference_image_for_dvf
        final_img = self.comparator.final_transformed_image

        self.assertEqual(
            final_img.GetSize(),
            ref_img.GetSize(),
            "Final image size should match DVF grid size.",
        )
        self.assertTrue(
            np.allclose(final_img.GetOrigin(), ref_img.GetOrigin()),
            "Final image origin should match DVF grid origin.",
        )
        self.assertTrue(
            np.allclose(final_img.GetSpacing(), ref_img.GetSpacing()),
            "Final image spacing should match DVF grid spacing.",
        )
        self.assertTrue(
            np.allclose(final_img.GetDirection(), ref_img.GetDirection()),
            "Final image direction should match DVF grid direction.",
        )

        # Step 5: Save the output files for manual inspection
        rigid_path = os.path.join(self.output_dir, "test_rigid_output.nii.gz")
        final_path = os.path.join(self.output_dir, "test_final_output.nii.gz")
        self.assertTrue(
            self.comparator.save_image(
                self.comparator.rigid_transformed_image, rigid_path
            )
        )
        self.assertTrue(
            self.comparator.save_image(
                self.comparator.final_transformed_image, final_path
            )
        )

    def test_04_output_file_verification(self):
        """Verify that the output NIfTI file is created and has correct metadata."""
        # Step 1: Run the full pipeline to generate the output file
        self.comparator.load_nifti(self.nifti_path)
        self.comparator.load_rigid_transform(self.reg_path)
        self.comparator.load_dvf(self.dvf_path)
        self.comparator.apply_transformations()

        # Step 2: Define the expected output path and save the final image
        final_output_path = os.path.join(
            self.output_dir, "verification_final_output.nii.gz"
        )
        self.assertTrue(
            self.comparator.save_image(
                self.comparator.final_transformed_image, final_output_path
            )
        )

        # Step 3: Check if the file exists
        self.assertTrue(
            os.path.exists(final_output_path), "Final output file should be created."
        )

        # Step 4: Load the saved file and verify its metadata against the reference grid
        saved_image = sitk.ReadImage(final_output_path)
        ref_image = self.comparator.reference_image_for_dvf

        self.assertEqual(
            saved_image.GetSize(),
            ref_image.GetSize(),
            "Saved image size should match DVF grid size.",
        )
        self.assertTrue(
            np.allclose(saved_image.GetOrigin(), ref_image.GetOrigin()),
            "Saved image origin should match DVF grid origin.",
        )
        self.assertTrue(
            np.allclose(saved_image.GetSpacing(), ref_image.GetSpacing()),
            "Saved image spacing should match DVF grid spacing.",
        )
        self.assertTrue(
            np.allclose(saved_image.GetDirection(), ref_image.GetDirection()),
            "Saved image direction should match DVF grid direction.",
        )

    def test_03_error_handling(self):
        """Test error handling for incomplete inputs."""
        # Case 1: No files loaded
        success, message = self.comparator.apply_transformations()
        self.assertFalse(success, "Should fail when no files are loaded.")
        self.assertIn("NIfTI image not loaded", message)

        # Case 2: Only NIfTI loaded
        self.comparator.load_nifti(self.nifti_path)
        success, message = self.comparator.apply_transformations()
        self.assertFalse(success, "Should fail when only NIfTI is loaded.")
        self.assertIn("Rigid transform not loaded", message)

        # Case 3: NIfTI and REG loaded, but no DVF
        self.comparator.load_rigid_transform(self.reg_path)
        success, message = self.comparator.apply_transformations()
        self.assertFalse(success, "Should fail when DVF is not loaded.")
        self.assertIn("DVF not loaded", message)

    def test_05_three_step_registration_pipeline(self):
        """Test the complete three-step registration pipeline including target space resampling."""
        # Load all required files
        success = self.comparator.load_nifti(self.nifti_path)
        self.assertTrue(success, "Failed to load NIfTI file")

        success = self.comparator.load_rigid_transform(self.reg_path)
        self.assertTrue(success, "Failed to load rigid transform")

        success = self.comparator.load_dvf(self.dvf_path)
        self.assertTrue(success, "Failed to load DVF")

        # Step 1 & 2: Apply rigid + DVF transformations
        success, message = self.comparator.apply_transformations()
        self.assertTrue(success, f"Failed to apply transformations: {message}")

        # Verify DVF space result exists
        self.assertIsNotNone(
            self.comparator.final_transformed_image, "Final transformed image is None"
        )

        # Step 3: Resample to target space
        target_image_path = os.path.join("data", "drm_data", "targetDRM.nii.gz")
        success, message = self.comparator.resample_to_target_space(target_image_path)
        self.assertTrue(success, f"Failed to resample to target space: {message}")

        # Verify target space result exists
        self.assertIsNotNone(
            self.comparator.target_space_image, "Target space image is None"
        )

        # Save target space result
        target_output_file = os.path.join(
            self.output_dir, "test_target_space_output.nii.gz"
        )
        success, message = self.comparator.save_target_space_image(target_output_file)
        self.assertTrue(success, f"Failed to save target space image: {message}")

        # Verify the target space file exists and has correct dimensions
        self.assertTrue(
            os.path.exists(target_output_file),
            "Target space output file was not created",
        )

        try:
            target_output_image = sitk.ReadImage(target_output_file)
            target_ref_image = sitk.ReadImage(target_image_path)

            # Verify dimensions match target space
            self.assertEqual(
                target_output_image.GetSize(),
                target_ref_image.GetSize(),
                "Target space output dimensions don't match reference",
            )

            # Verify spacing matches (approximately)
            output_spacing = target_output_image.GetSpacing()
            ref_spacing = target_ref_image.GetSpacing()
            for i in range(3):
                self.assertAlmostEqual(
                    output_spacing[i],
                    ref_spacing[i],
                    places=6,
                    msg=f"Target space spacing mismatch in dimension {i}",
                )

            print(f"✅ Three-step registration completed successfully!")
            print(
                f"   Original -> Rigid -> DVF -> Target space: {target_output_image.GetSize()}"
            )

        except Exception as e:
            self.fail(f"Failed to verify target space output: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
