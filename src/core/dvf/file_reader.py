#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import SimpleITK as sitk
import pandas as pd
import numpy as np

def read_ct_series(directory_path):
    """读取CT序列
    
    Args:
        directory_path (str): CT序列文件夹路径
        
    Returns:
        SimpleITK.Image: CT图像
    """
    # 获取目录中所有DICOM文件
    dicom_files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
                   if f.endswith('.dcm')]
    
    # 过滤掉RTSS文件（通过文件大小）
    ct_files = [f for f in dicom_files if os.path.getsize(f) > 100000]  # RTSS文件通常较小
    
    # 读取DICOM序列
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(sorted(ct_files))  # 确保文件按正确顺序读取
    image = reader.Execute()
    
    return image

def read_point_cloud(csv_path):
    """读取点云数据
    
    Args:
        csv_path (str): 点云CSV文件路径
        
    Returns:
        numpy.ndarray: 点云坐标数组
    """
    df = pd.read_csv(csv_path)
    points = df[['x', 'y', 'z']].values
    return points

def read_displacement_field(csv_path, base_points, offset_x=0):
    """读取位移场数据
    
    Args:
        csv_path (str): 位移场CSV文件路径
        base_points (numpy.ndarray): 原始点云坐标
        offset_x (float): X方向的偏移量
        
    Returns:
        numpy.ndarray: 位移后的点云坐标
    """
    df = pd.read_csv(csv_path)
    # 使用正确的列名读取位移数据
    displacements = df[['dx', 'dy', 'dz']].values
    
    # 计算位移后的点坐标
    displaced_points = base_points + displacements
    
    # 添加X方向的偏移
    displaced_points[:, 0] += offset_x
    
    return displaced_points

def print_image_info(image):
    """打印图像信息
    
    Args:
        image (SimpleITK.Image): CT图像
    """
    print(f"图像大小: {image.GetSize()}")
    print(f"像素间距: {image.GetSpacing()}")
    print(f"原点: {image.GetOrigin()}")
    print(f"方向: {image.GetDirection()}") 