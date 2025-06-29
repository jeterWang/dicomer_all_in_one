import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QLabel
from .drm_comparator import DrmComparator

class DrmComparatorGui(QWidget):
    def __init__(self):
        super().__init__()
        self.comparator = DrmComparator()
        self.init_ui()
        self.nifti_path = ""
        self.reg_path = ""
        self.dvf_path = ""

    def init_ui(self):
        layout = QVBoxLayout()
        
        self.btn_load_nifti = QPushButton("1. Load NIfTI Mask File")
        self.lbl_nifti = QLabel("No file selected.")
        
        self.btn_load_reg = QPushButton("2. Load DICOM REG File (Rigid)")
        self.lbl_reg = QLabel("No file selected.")

        self.btn_load_dvf = QPushButton("3. Load DICOM DVF File (Deformable)")
        self.lbl_dvf = QLabel("No file selected.")

        self.btn_execute = QPushButton("4. Execute Transformations and Save")
        
        layout.addWidget(self.btn_load_nifti)
        layout.addWidget(self.lbl_nifti)
        layout.addWidget(self.btn_load_reg)
        layout.addWidget(self.lbl_reg)
        layout.addWidget(self.btn_load_dvf)
        layout.addWidget(self.lbl_dvf)
        layout.addSpacing(20)
        layout.addWidget(self.btn_execute)
        
        self.setLayout(layout)
        self.setWindowTitle("DRM Comparator")

        # Connect signals to slots
        self.btn_load_nifti.clicked.connect(self.load_nifti_file)
        self.btn_load_reg.clicked.connect(self.load_reg_file)
        self.btn_load_dvf.clicked.connect(self.load_dvf_file)
        self.btn_execute.clicked.connect(self.execute_transforms)

    def load_nifti_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Load NIfTI Mask File", "", "NIfTI Files (*.nii *.nii.gz);;All Files (*)", options=options)
        if file_path:
            if self.comparator.load_nifti(file_path):
                self.nifti_path = file_path
                self.lbl_nifti.setText(f"Loaded: {os.path.basename(self.nifti_path)}")
            else:
                QMessageBox.critical(self, "Error", "Failed to load the NIfTI file. Check the console for details.")
                self.lbl_nifti.setText("Load failed.")

    def load_reg_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Load DICOM REG File", "", "DICOM Files (*.dcm);;All Files (*)", options=options)
        if file_path:
            if self.comparator.load_rigid_transform(file_path):
                self.reg_path = file_path
                self.lbl_reg.setText(f"Loaded: {os.path.basename(self.reg_path)}")
            else:
                QMessageBox.critical(self, "Error", "Failed to load the DICOM REG file. Check the console for details.")
                self.lbl_reg.setText("Load failed.")

    def load_dvf_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Load DICOM DVF File", "", "DICOM Files (*.dcm);;All Files (*)", options=options)
        if file_path:
            if self.comparator.load_dvf(file_path):
                self.dvf_path = file_path
                self.lbl_dvf.setText(f"Loaded: {os.path.basename(self.dvf_path)}")
            else:
                QMessageBox.critical(self, "Error", "Failed to load the DICOM DVF file. Check the console for details.")
                self.lbl_dvf.setText("Load failed.")

    def execute_transforms(self):
        if not all([self.nifti_path, self.reg_path, self.dvf_path]):
            QMessageBox.warning(self, "Warning", "Please load all required files (NIfTI, REG, DVF) before executing.")
            return

        success, message = self.comparator.apply_transformations()

        if not success:
            QMessageBox.critical(self, "Execution Error", message)
            return
        
        # Ask for output directory
        output_dir = QFileDialog.getExistingDirectory(self, "Select Directory to Save Output Files")
        if not output_dir:
            QMessageBox.information(self, "Cancelled", "Save operation was cancelled.")
            return

        try:
            # Save the intermediate (rigidly transformed) and final images
            base_name = os.path.basename(self.nifti_path).split('.')[0]
            
            rigid_output_path = os.path.join(output_dir, f"{base_name}_rigid_transformed.nii.gz")
            final_output_path = os.path.join(output_dir, f"{base_name}_final_deformed.nii.gz")

            rigid_save_ok = self.comparator.save_image(self.comparator.rigid_transformed_image, rigid_output_path)
            final_save_ok = self.comparator.save_image(self.comparator.final_transformed_image, final_output_path)

            if rigid_save_ok and final_save_ok:
                QMessageBox.information(self, "Success", 
                                        f"Transformations applied and results saved successfully in:\n{output_dir}")
            else:
                QMessageBox.critical(self, "Save Error", "Failed to save one or more output files. Check the console.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred during saving: {e}")