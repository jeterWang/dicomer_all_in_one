import SimpleITK as sitk
import numpy as np
import os

def verify_image(file_path, label):
    """Reads an image and prints its statistics."""
    print(f"--- Verifying {label} ---")
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    try:
        image = sitk.ReadImage(file_path)
        stats = sitk.StatisticsImageFilter()
        stats.Execute(image)
        
        print(f"File: {os.path.basename(file_path)}")
        print(f"  Size: {image.GetSize()}")
        print(f"  Spacing: {[round(s, 3) for s in image.GetSpacing()]}")
        print(f"  Origin: {[round(o, 3) for o in image.GetOrigin()]}")
        print(f"  Min: {stats.GetMinimum():.6f}")
        print(f"  Max: {stats.GetMaximum():.6f}")
        print(f"  Mean: {stats.GetMean():.6f}")
        print(f"  StdDev: {stats.GetSigma():.6f}")
        print(f"  Sum: {stats.GetSum():.6f}")
        
        # Check if the image is not just zeros
        if stats.GetSum() == 0.0:
            print("  WARNING: Image is empty (all voxels are zero).")
        else:
            print("  SUCCESS: Image contains non-zero data.")
            
    except Exception as e:
        print(f"Error reading or analyzing image {file_path}: {e}")
    print("-" * (len(label) + 12) + "\n")

if __name__ == "__main__":
    output_dir = "output/test_drm_comparator"
    rigid_output_path = os.path.join(output_dir, "test_rigid_output.nii.gz")
    final_output_path = os.path.join(output_dir, "test_final_output.nii.gz")
    
    verify_image(rigid_output_path, "Rigid-Transformed Image")
    verify_image(final_output_path, "Final Deformed Image")