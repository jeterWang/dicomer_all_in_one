import pydicom

def print_dicom_header(dcm_path):
    ds = pydicom.dcmread(dcm_path, stop_before_pixels=True)
    for elem in ds.iterall():
        tag = elem.tag
        name = elem.name
        VR = elem.VR
        value = elem.value
        # 截断长字符串
        if isinstance(value, (str, bytes)) and len(str(value)) > 100:
            value = str(value)[:100] + '...'
        print(f"{tag} | {name} | {VR} | {value}")

if __name__ == "__main__":
    print_dicom_header("data/drm_converter/mode/slice1.dcm")