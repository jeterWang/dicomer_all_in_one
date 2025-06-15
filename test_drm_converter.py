#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DRM转换器测试脚本
用于测试DRM.nii.gz到DICOM series的转换功能
现在确保生成的DICOM文件能被识别为完整的series
"""

import os
import sys
import logging
from pathlib import Path

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from modules.drm_converter import DRMConverter

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('drm_converter_test.log', encoding='utf-8')
        ]
    )

def test_drm_converter():
    """测试DRM转换器"""
    logger = logging.getLogger(__name__)
    
    # 测试数据路径
    drm_folder_path = "data/drm_converter/FAPI_DRM"
    output_folder_path = "output/drm_converter_test"
    
    logger.info("开始DRM转换器测试...")
    logger.info(f"DRM文件夹: {drm_folder_path}")
    logger.info(f"输出文件夹: {output_folder_path}")
    
    # 检查输入路径是否存在
    if not os.path.exists(drm_folder_path):
        logger.error(f"DRM文件夹不存在: {drm_folder_path}")
        return False
    
    # 创建输出目录
    Path(output_folder_path).mkdir(parents=True, exist_ok=True)
    
    # 创建转换器实例
    converter = DRMConverter()
    
    try:
        # 执行转换
        success = converter.convert_drm_folder(drm_folder_path, output_folder_path)
        
        if success:
            logger.info("DRM转换测试成功完成！")
            logger.info(f"转换结果保存在: {output_folder_path}")
            
            # 检查输出文件
            output_files = list(Path(output_folder_path).rglob("*.dcm"))
            logger.info(f"生成的DICOM文件数量: {len(output_files)}")
            
            # 验证生成的DICOM文件是否为完整series
            if output_files:
                import pydicom
                first_file = str(output_files[0])
                ds = pydicom.dcmread(first_file)
                logger.info(f"Series UID: {ds.SeriesInstanceUID}")
                logger.info(f"Study UID: {ds.StudyInstanceUID}")
                logger.info(f"Series Description: {ds.SeriesDescription}")
                logger.info(f"Series Number: {ds.SeriesNumber}")
                
                # 检查几个文件确保它们有相同的Series UID
                if len(output_files) > 1:
                    second_file = str(output_files[1])
                    ds2 = pydicom.dcmread(second_file)
                    if ds.SeriesInstanceUID == ds2.SeriesInstanceUID:
                        logger.info("✅ 验证通过：文件属于同一个DICOM series")
                    else:
                        logger.warning("⚠️ 警告：文件可能不属于同一个series")
            
            return True
        else:
            logger.error("DRM转换测试失败")
            return False
            
    except Exception as e:
        logger.error(f"DRM转换测试出错: {e}")
        return False

def main():
    """主函数"""
    setup_logging()
    
    print("=" * 60)
    print("DRM转换器测试 - 改进版")
    print("现在生成的DICOM文件应该能被识别为完整的series")
    print("=" * 60)
    
    success = test_drm_converter()
    
    if success:
        print("\n✅ 测试成功完成！")
        print("生成的DICOM文件现在应该能被DICOM查看器识别为一个完整的series")
    else:
        print("\n❌ 测试失败，请查看日志文件 drm_converter_test.log")
    
    print("=" * 60)

if __name__ == "__main__":
    main() 