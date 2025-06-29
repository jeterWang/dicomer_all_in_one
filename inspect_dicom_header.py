

import pydicom
import os

def inspect_dicom_header(file_path):
    """
    Reads a DICOM file and prints its complete header information.

    Args:
        file_path (str): The path to the DICOM file.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    try:
        # Read the DICOM file
        ds = pydicom.dcmread(file_path)

        print("-" * 50)
        print(f"DICOM Header Inspection for: {os.path.basename(file_path)}")
        print("-" * 50)

        # Print the entire dataset as a string
        # This provides a comprehensive view of all tags and their values.
        print(ds)

        # Specifically check for the Registration Sequence to see the matrix
        if "RegistrationSequence" in ds:
            print("\n" + "-" * 20 + " Found Registration Sequence " + "-" * 20)
            reg_seq = ds.RegistrationSequence
            for i, reg_item in enumerate(reg_seq):
                print(f"\n--- Registration Item #{i+1} ---")
                if "MatrixRegistrationSequence" in reg_item:
                    matrix_reg_seq = reg_item.MatrixRegistrationSequence
                    for j, matrix_reg_item in enumerate(matrix_reg_seq):
                        print(f"  --- Matrix Registration Item #{j+1} ---")
                        if "MatrixSequence" in matrix_reg_item:
                            matrix_seq = matrix_reg_item.MatrixSequence
                            for k, matrix_item in enumerate(matrix_seq):
                                print(f"    --- Matrix Item #{k+1} ---")
                                if "FrameOfReferenceTransformationMatrix" in matrix_item:
                                    matrix = matrix_item.FrameOfReferenceTransformationMatrix
                                    print(f"      (0064, 000C) Frame of Reference Transformation Matrix: {matrix.value}")
                                else:
                                    print("      (0064, 000C) Frame of Reference Transformation Matrix: NOT FOUND")
                        else:
                            print("    MatrixSequence: NOT FOUND")
                else:
                    print("  MatrixRegistrationSequence: NOT FOUND")
        else:
            print("\n" + "-"*20 + " Registration Sequence NOT FOUND " + "-"*20)


    except Exception as e:
        print(f"An error occurred while reading or parsing the DICOM file: {e}")

if __name__ == "__main__":
    # --- Configuration ---
    # Note: This script is in the root directory, so paths are relative to it.
    file_to_inspect = os.path.join("data", "drm_data", "deformable.dcm")
    
    inspect_dicom_header(file_to_inspect)

