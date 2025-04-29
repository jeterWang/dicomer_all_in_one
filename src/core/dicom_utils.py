#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import pydicom
from typing import List, Tuple, Optional, Dict, Any

def read_dicom_file(file_path: str) -> Optional[pydicom.Dataset]:
    """读取DICOM文件
    
    Args:
        file_path: DICOM文件路径
        
    Returns:
        DICOM数据集对象，如果读取失败则返回None
    """
    try:
        return pydicom.dcmread(file_path, force=True)
    except Exception as e:
        print(f"读取DICOM文件失败: {str(e)}")
        return None

def save_dicom_file(dataset: pydicom.Dataset, file_path: str) -> bool:
    """保存DICOM文件
    
    Args:
        dataset: DICOM数据集
        file_path: 保存路径
        
    Returns:
        是否保存成功
    """
    try:
        dataset.save_as(file_path)
        return True
    except Exception as e:
        print(f"保存DICOM文件失败: {str(e)}")
        return False

def find_dicom_files(directory: str) -> List[str]:
    """查找目录中的所有DICOM文件
    
    Args:
        directory: 要搜索的目录
        
    Returns:
        DICOM文件路径列表
    """
    dicom_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(('.dcm', '.dicom', '.ima')) or '.' not in file:
                file_path = os.path.join(root, file)
                dicom_files.append(file_path)
    return dicom_files

def get_dicom_attribute(dataset: pydicom.Dataset, tag: Any) -> Dict[str, Any]:
    """获取DICOM属性的详细信息
    
    Args:
        dataset: DICOM数据集
        tag: DICOM标签
        
    Returns:
        包含属性信息的字典
    """
    try:
        element = dataset[tag]
        # 获取标签的group和element值
        group = tag.group if hasattr(tag, 'group') else tag[0]
        elem = tag.element if hasattr(tag, 'element') else tag[1]
        
        return {
            'tag': f"({group:04x},{elem:04x})",
            'name': element.name,
            'vr': getattr(element, 'VR', ''),
            'value': str(element.value) if not isinstance(element.value, bytes) else f"Binary data ({len(element.value)} bytes)"
        }
    except Exception as e:
        if hasattr(tag, 'group') and hasattr(tag, 'element'):
            tag_str = f"({tag.group:04x},{tag.element:04x})"
        else:
            try:
                tag_str = f"({tag[0]:04x},{tag[1]:04x})"
            except:
                tag_str = str(tag)
                
        return {
            'tag': tag_str,
            'name': 'Unknown',
            'vr': '',
            'value': f"<无法获取: {str(e)}>"
        }

def convert_value(value: str, vr: str) -> Any:
    """根据VR转换值
    
    Args:
        value: 要转换的值
        vr: Value Representation
        
    Returns:
        转换后的值
    """
    try:
        if vr in ['DS', 'FL', 'FD']:
            return float(value)
        elif vr in ['IS', 'SL', 'SS', 'UL', 'US']:
            return int(value)
        elif vr in ['OB', 'OW', 'UN']:
            return value.encode('utf-8')
        else:
            return value
    except ValueError as e:
        raise ValueError(f"无法将值 '{value}' 转换为 {vr} 类型: {str(e)}") 