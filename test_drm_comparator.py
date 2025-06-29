
import unittest
import os
import SimpleITK as sitk
import numpy as np

# Add the project root to the Python path to allow for absolute imports
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.modules.drm_comparator.drm_comparator import DrmComparator

class TestDrmComparator(unittest.TestCase):

    def setUp(self):
        """Set up the test environment."""
        self.comparator = DrmComparator()
        self.test_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'drm_data'))
        self.output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'output', 'test_drm_comparator'))
        
        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        # Define file paths
        self.nifti_path = os.path.join(self.test_data_dir, "DRM.nii.gz")
        self.reg_path = os.path.join(self.test_data_dir, "moving.dcm")
        self.dvf_path = os.path.join(self.test_data_dir, "deformable.dcm")

    def test_01_file_loading(self):
        """Test the loading of NIfTI, DICOM REG, and DICOM DVF files."""
        # Test NIfTI loading
        self.assertTrue(self.comparator.load_nifti(self.nifti_path), "NIfTI file should load successfully.")
        self.assertIsInstance(self.comparator.nifti_image, sitk.Image, "Loaded NIfTI should be a SimpleITK Image.")

        # Test DICOM REG loading
        self.assertTrue(self.comparator.load_rigid_transform(self.reg_path), "DICOM REG file should load successfully.")
        self.assertIsInstance(self.comparator.rigid_transform, sitk.AffineTransform, "Loaded rigid transform should be an AffineTransform.")

        # Test DICOM DVF loading
        # self.assertTrue(self.comparator.load_dvf(self.dvf_path), "DICOM DVF file should load successfully.")
        # self.assertIsInstance(self.comparator.dvf_transform, sitk.DisplacementFieldTransform, "Loaded DVF should be a DisplacementFieldTransform.")
        # self.assertIsInstance(self.comparator.reference_image_for_dvf, sitk.Image, "DVF reference image should be created.")

    @unittest.skip("Skipping full pipeline test until a valid DVF test file is available.")
    def test_02_transformation_pipeline(self):
        """Test the full transformation pipeline from loading to result."""
        # Step 1: Load all necessary files
        self.comparator.load_nifti(self.nifti_path)
        self.comparator.load_rigid_transform(self.reg_path)
        self.comparator.load_dvf(self.dvf_path)

        # Step 2: Apply transformations
        success, message = self.comparator.apply_transformations()
        self.assertTrue(success, f"Transformation pipeline failed with message: {message}")

        # Step 3: Verify the outputs
        self.assertIsNotNone(self.comparator.rigid_transformed_image, "Rigidly transformed image should not be None.")
        self.assertIsNotNone(self.comparator.final_transformed_image, "Final deformed image should not be None.")
        
        # Step 4: Verify metadata of the final image
        # The final image should have the same metadata as the DVF reference grid
        ref_img = self.comparator.reference_image_for_dvf
        final_img = self.comparator.final_transformed_image

        self.assertEqual(final_img.GetSize(), ref_img.GetSize(), "Final image size should match DVF grid size.")
        self.assertTrue(np.allclose(final_img.GetOrigin(), ref_img.GetOrigin()), "Final image origin should match DVF grid origin.")
        self.assertTrue(np.allclose(final_img.GetSpacing(), ref_img.GetSpacing()), "Final image spacing should match DVF grid spacing.")
        self.assertTrue(np.allclose(final_img.GetDirection(), ref_img.GetDirection()), "Final image direction should match DVF grid direction.")

        # Step 5: Save the output files for manual inspection
        rigid_path = os.path.join(self.output_dir, "test_rigid_output.nii.gz")
        final_path = os.path.join(self.output_dir, "test_final_output.nii.gz")
        self.assertTrue(self.comparator.save_image(self.comparator.rigid_transformed_image, rigid_path))
        self.assertTrue(self.comparator.save_image(self.comparator.final_transformed_image, final_path))

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
        # This case is currently not testable as the pipeline is disabled.
        # self.comparator.load_rigid_transform(self.reg_path)
        # success, message = self.comparator.apply_transformations()
        # self.assertFalse(success, "Should fail when DVF is not loaded.")
        # self.assertIn("DVF not loaded", message)

if __name__ == '__main__':
    unittest.main(verbosity=2)
