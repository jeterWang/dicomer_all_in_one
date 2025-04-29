from utils.file_reader import read_ct_series, read_point_cloud, read_displacement_field, print_image_info
from visualization.plotter import ImagePlotter

def main():
    # 设置文件路径
    patient_id = "15235455"
    instance_id = "20240527001"
    ct_directory_week0 = f"data/{patient_id}/images/week0_CT"
    ct_directory_week4 = f"data/{patient_id}/images/week4_CT"
    point_cloud_path = f"data/{patient_id}/instances/{instance_id}/voxel_coord.csv"
    displacement_path = f"data/{patient_id}/instances/{instance_id}/voxel_disp/week0_CT_week4_CT_voxel_disp.csv"
    
    try:
        # 读取Week 0的CT序列
        ct_image_week0 = read_ct_series(ct_directory_week0)
        
        # 读取Week 4的CT序列
        ct_image_week4 = read_ct_series(ct_directory_week4)
        
        # 读取原始点云数据
        points = read_point_cloud(point_cloud_path)
        
        # 计算Week 4的X方向偏移量
        offset_x = 0
        
        # 读取位移场并计算位移后的点云
        displaced_points = read_displacement_field(displacement_path, points, offset_x)
        
        # 打印图像信息
        print("Week 0 CT信息:")
        print_image_info(ct_image_week0)
        print("\nWeek 4 CT信息:")
        print_image_info(ct_image_week4)
        
        # 创建可视化器
        plotter = ImagePlotter(ct_image_week0, ct_image_week4, points, displaced_points)
        
        # 设置控制滑块
        plotter.setup_sliders()
        
        # 显示可视化结果
        plotter.show()
        
    except Exception as e:
        print(f"处理过程中出现错误: {str(e)}")

if __name__ == "__main__":
    main() 