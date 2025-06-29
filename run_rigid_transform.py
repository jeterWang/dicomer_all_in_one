

import os
import sys
from src.modules.drm_comparator.drm_comparator import DrmComparator

def main():
    """
    This script applies a rigid transformation from a DICOM REG file
    to a NIfTI mask and saves the result.
    """
    # Ensure the script can find the src module
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

    comparator = DrmComparator()

    # --- Configuration ---
    base_dir = os.path.abspath(os.path.dirname(__file__))
    nifti_path = os.path.join(base_dir, "data", "drm_data", "DRM.nii.gz")
    reg_path = os.path.join(base_dir, "data", "drm_data", "moving.dcm")
    
    output_dir = os.path.join(base_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "DRM_rigid_only.nii.gz")

    # --- Execution ---
    print("--- Loading files ---")
    if not comparator.load_nifti(nifti_path):
        print("Failed to load NIfTI file. Aborting.")
        return

    if not comparator.load_rigid_transform(reg_path):
        print("Failed to load DICOM REG file. Aborting.")
        return

    print("\n--- Applying rigid transformation ---")
    success, message = comparator.apply_rigid_transform_only(output_path)

    if success:
        print(f"\nSuccess! {message}")
    else:
        print(f"\nError! {message}")

if __name__ == "__main__":
    main()

