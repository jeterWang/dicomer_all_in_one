#!/usr/bin/env python
# -*- coding: utf-8 -*-

import SimpleITK as sitk
import numpy as np
import pyvista as pv
import vtk
from .state import State
import matplotlib.cm as cm

class ImagePlotter:
    """图像可视化类"""
    
    def __init__(self, sitk_image_week0, sitk_image_week4, points, displaced_points, plotter=None, use_qt_controls=False):
        """初始化可视化器
        
        Args:
            sitk_image_week0 (SimpleITK.Image): Week 0的CT图像
            sitk_image_week4 (SimpleITK.Image): Week 4的CT图像
            points (numpy.ndarray): 原始点云数据
            displaced_points (numpy.ndarray): 位移后的点云数据
            plotter (pyvista.Plotter, optional): 外部提供的渲染器
            use_qt_controls (bool, optional): 是否使用Qt控件替代PyVista滑块
        """
        # 创建状态管理器 - 使用正确的图像形状
        self.state = State(sitk.GetArrayFromImage(sitk_image_week0).shape)
        self.use_qt_controls = use_qt_controls
        
        # 打印点云坐标范围
        print("Points coordinate ranges:")
        print(f"X range: [{points[:, 0].min():.2f}, {points[:, 0].max():.2f}]")
        print(f"Y range: [{points[:, 1].min():.2f}, {points[:, 1].max():.2f}]")
        print(f"Z range: [{points[:, 2].min():.2f}, {points[:, 2].max():.2f}]")
        
        # 存储点云的坐标范围
        self.point_ranges = {
            'x': (points[:, 0].min(), points[:, 0].max()),
            'y': (points[:, 1].min(), points[:, 1].max()),
            'z': (points[:, 2].min(), points[:, 2].max())
        }
        
        # 处理Week 0的图像
        self.array_week0 = sitk.GetArrayFromImage(sitk_image_week0)
        print("\nImage dimensions:")
        print(f"Week 0 shape: {self.array_week0.shape}")
        self.spacing_week0 = sitk_image_week0.GetSpacing()
        self.origin_week0 = sitk_image_week0.GetOrigin()
        self.direction_week0 = sitk_image_week0.GetDirection()
        
        # 处理Week 4的图像
        self.array_week4 = sitk.GetArrayFromImage(sitk_image_week4)
        self.spacing_week4 = sitk_image_week4.GetSpacing()
        self.origin_week4 = list(sitk_image_week4.GetOrigin())
        self.direction_week4 = sitk_image_week4.GetDirection()
        
        # 计算两个CT图像的中心点
        center_week0 = np.array([
            self.origin_week0[0] + self.array_week0.shape[2] * self.spacing_week0[0] / 2,
            self.origin_week0[1] + self.array_week0.shape[1] * self.spacing_week0[1] / 2,
            self.origin_week0[2] + self.array_week0.shape[0] * self.spacing_week0[2] / 2
        ])
        
        center_week4_original = np.array([
            self.origin_week4[0] + self.array_week4.shape[2] * self.spacing_week4[0] / 2,
            self.origin_week4[1] + self.array_week4.shape[1] * self.spacing_week4[1] / 2,
            self.origin_week4[2] + self.array_week4.shape[0] * self.spacing_week4[2] / 2
        ])
        
        # 计算水平偏移（保持X方向的间距，但对齐Y和Z）
        x_offset = (self.array_week0.shape[2] * self.spacing_week0[0]) * 1.2  # X方向保持固定间距
        y_offset = center_week0[1] - center_week4_original[1]  # Y方向对齐中心
        z_offset = center_week0[2] - center_week4_original[2]  # Z方向对齐中心
        
        # 更新Week 4的原点
        self.origin_week4[0] += x_offset
        self.origin_week4[1] += y_offset
        self.origin_week4[2] += z_offset
        
        # 处理点云数据
        self.points = points.copy()
        
        # 计算实际的位移向量（考虑空间变换）
        
        # 2. 将位移点云移动到正确位置
        self.displaced_points = displaced_points.copy()
        self.displaced_points[:, 0] += x_offset
        self.displaced_points[:, 1] += y_offset
        self.displaced_points[:, 2] += z_offset
        
        # 3. 计算箭头的方向（从原始点指向变换后的位移点）
        self.displacement_vectors = self.displaced_points - self.points
        
        # 计算位移向量的大小
        self.displacement_magnitudes = np.linalg.norm(self.displacement_vectors, axis=1)
        self.max_magnitude = np.max(self.displacement_magnitudes)
        
        # 创建Week 0的PyVista ImageData
        self.grid_week0 = pv.ImageData()
        self.grid_week0.dimensions = self.array_week0.shape[::-1]
        self.grid_week0.spacing = self.spacing_week0
        self.grid_week0.origin = self.origin_week0
        self.grid_week0.point_data["CT_values"] = self.array_week0.ravel()
        
        # 创建Week 4的PyVista ImageData
        self.grid_week4 = pv.ImageData()
        self.grid_week4.dimensions = self.array_week4.shape[::-1]
        self.grid_week4.spacing = self.spacing_week4
        self.grid_week4.origin = self.origin_week4
        self.grid_week4.point_data["CT_values"] = self.array_week4.ravel()
        
        # 创建点云对象
        self.point_cloud = pv.PolyData(self.points)
        self.displaced_point_cloud = pv.PolyData(self.displaced_points)
        
        # 使用外部提供的渲染器或创建新的
        self.plotter = plotter if plotter is not None else pv.Plotter()
        
        # 添加点击回调
        def callback(point):
            print(f"Picked point: {point}")
            self._point_picked(point)
            
        if hasattr(self.plotter, 'enable_point_picking'):
            self.plotter.enable_point_picking(callback=callback,
                                          show_message=False,
                                          show_point=False,
                                          left_clicking=True)
        
        # 添加用于显示CT值的文本
        self.ct_value_text = None
        
        # 添加更新标志位
        self._needs_full_update = True
        self._last_slice_min_week0 = None
        self._last_slice_max_week0 = None
        self._last_slice_min_week4 = None
        self._last_slice_max_week4 = None
        self._last_point_slice_min = None
        self._last_point_slice_max = None
        
    def _point_picked(self, point):
        """处理点击事件
        
        Args:
            point: 点击位置的坐标 (x, y, z)
        """
        if point is None:
            print("No valid pick")
            return
            
        print(f"\nPicked point coordinates: ({point[0]:.2f}, {point[1]:.2f}, {point[2]:.2f})")
            
        # 将世界坐标转换为图像索引
        if point[0] < (self.origin_week4[0] - self.spacing_week4[0]):  # 判断是Week 0还是Week 4的图像
            # Week 0图像
            print("Picked Week 0 image")
            image_array = self.array_week0
            spacing = self.spacing_week0
            origin = self.origin_week0
            # 使用max slice的值
            current_slice = self.state.slice_max_week0
        else:
            # Week 4图像
            print("Picked Week 4 image")
            image_array = self.array_week4
            spacing = self.spacing_week4
            origin = self.origin_week4
            # 使用max slice的值
            current_slice = self.state.slice_max_week4
            
        # 计算图像索引（只计算y和x坐标，z使用当前切片）
        index = [
            current_slice,  # 使用max slice的值
            int(round((point[1] - origin[1]) / spacing[1])),  # y
            int(round((point[0] - origin[0]) / spacing[0]))   # x
        ]
        
        print(f"Origin: {origin}")
        print(f"Spacing: {spacing}")
        print(f"Using max slice: {current_slice}")
        print(f"Calculated image indices: {index}")
        print(f"Image shape: {image_array.shape}")
        
        # 确保索引在有效范围内
        shape = image_array.shape
        if (0 <= index[0] < shape[0] and
            0 <= index[1] < shape[1] and 
            0 <= index[2] < shape[2]):
            
            # 获取CT值
            ct_value = image_array[index[0], index[1], index[2]]
            print(f"CT value at position: {ct_value}")
            
            # 更新显示文本
            if self.ct_value_text is not None:
                self.plotter.remove_actor(self.ct_value_text)
            
            text = f"CT Value: {ct_value:.1f}\nSlice: {current_slice}\nPosition: ({index[1]}, {index[2]})"
            self.ct_value_text = self.plotter.add_text(text, 
                                                      position='upper_right',
                                                      font_size=12,
                                                      shadow=True)
            
            # 强制更新显示
            self.plotter.render()
        else:
            print(f"Invalid indices: {index} for image shape: {shape}")
        
    def update_volume(self, full_update=False, update_where='all'):
        """更新体积渲染和点云
        
        Args:
            full_update (bool): 是否进行完全更新
            update_where (str): 指定更新区域 'all', 'week0', 'week4', 'points'
        """
        try:
            # if full_update:
            #     self._needs_full_update = True
            #     update_where = 'all'  # 强制完全更新
                
            print(f"更新渲染区域: {update_where}")
                
            # 根据更新区域进行不同的更新操作
            if update_where == 'all' or self._needs_full_update:
                # 完整更新所有内容
                print("完整更新所有内容...")
                
                # 移除现有的actors
                if self.state.current_mapper_week0 is not None:
                    self.plotter.remove_actor(self.state.current_mapper_week0)
                if self.state.current_mapper_week4 is not None:
                    self.plotter.remove_actor(self.state.current_mapper_week4)
                if self.state.current_points is not None:
                    self.plotter.remove_actor(self.state.current_points)
                if self.state.current_displaced_points is not None:
                    self.plotter.remove_actor(self.state.current_displaced_points)
                if self.state.current_arrows is not None:
                    self.plotter.remove_actor(self.state.current_arrows)
                
                # 更新Week 0体积
                self._update_week0_volume()
                
                # 更新Week 4体积
                self._update_week4_volume()
                
                # 更新点云
                self._update_points()
                
                # 更新切片范围缓存
                self._last_slice_min_week0 = self.state.slice_min_week0
                self._last_slice_max_week0 = self.state.slice_max_week0
                self._last_slice_min_week4 = self.state.slice_min_week4
                self._last_slice_max_week4 = self.state.slice_max_week4
                self._last_point_slice_min = self.state.point_slice_min
                self._last_point_slice_max = self.state.point_slice_max
                
            elif update_where == 'week0':
                # 只更新Week 0体积
                print("只更新Week 0体积...")
                if self.state.current_mapper_week0 is not None:
                    self.plotter.remove_actor(self.state.current_mapper_week0)
                self._update_week0_volume()
                
            elif update_where == 'week4':
                # 只更新Week 4体积
                print("只更新Week 4体积...")
                if self.state.current_mapper_week4 is not None:
                    self.plotter.remove_actor(self.state.current_mapper_week4)
                self._update_week4_volume()
                
            elif update_where == 'points':
                # 只更新点云
                print("只更新点云...")
                if self.state.current_points is not None:
                    self.plotter.remove_actor(self.state.current_points)
                if self.state.current_displaced_points is not None:
                    self.plotter.remove_actor(self.state.current_displaced_points)
                if self.state.current_arrows is not None:
                    self.plotter.remove_actor(self.state.current_arrows)
                self._update_points()
                
            # 强制刷新渲染
            print("渲染更新...")
            if hasattr(self.plotter, 'render'):
                self.plotter.render()
            
            # 重置更新标志
            self._needs_full_update = False
            
        except Exception as e:
            import traceback
            print(f"更新体积时出错: {str(e)}")
            traceback.print_exc()
            
    def _update_week0_volume(self):
        """只更新Week 0体积渲染"""
        # 提取Week 0图像的切片
        extracted_week0 = self.grid_week0.extract_subset([
            0, self.grid_week0.dimensions[0] - 1,
            0, self.grid_week0.dimensions[1] - 1,
            self.state.slice_min_week0, self.state.slice_max_week0
        ])
        
        # 使用正确的映射范围
        window_week0 = self.state.window_week0
        level_week0 = self.state.level_week0
        clim_week0 = [level_week0 - window_week0 / 2, level_week0 + window_week0 / 2]
        
        # 添加Week 0的切片
        mapper_week0 = self.plotter.add_volume(
            extracted_week0,
            cmap='gray',
            clim=clim_week0,
            opacity=self.state.opacity_week0,
            reset_camera=False
        )
        
        self.state.current_mapper_week0 = mapper_week0
        
    def _update_week4_volume(self):
        """只更新Week 4体积渲染"""
        # 提取Week 4图像的切片
        extracted_week4 = self.grid_week4.extract_subset([
            0, self.grid_week4.dimensions[0] - 1,
            0, self.grid_week4.dimensions[1] - 1,
            self.state.slice_min_week4, self.state.slice_max_week4
        ])
        
        # 使用正确的映射范围
        window_week4 = self.state.window_week4
        level_week4 = self.state.level_week4
        clim_week4 = [level_week4 - window_week4 / 2, level_week4 + window_week4 / 2]
        
        # 添加Week 4的切片
        mapper_week4 = self.plotter.add_volume(
            extracted_week4,
            cmap='gray',
            clim=clim_week4,
            opacity=self.state.opacity_week4,
            reset_camera=False
        )
        
        self.state.current_mapper_week4 = mapper_week4
            
    def _update_points(self):
        """只更新点云渲染"""
        # 同时考虑原始点云和位移点云的Z坐标
        min_z = self.origin_week0[2] + self.state.point_slice_min * self.spacing_week0[2]
        max_z = self.origin_week0[2] + self.state.point_slice_max * self.spacing_week0[2]
        
        # 创建分开的掩码，以便单独筛选两种点云
        orig_mask = np.logical_and(
            self.points[:, 2] >= min_z,
            self.points[:, 2] <= max_z
        )
        
        disp_mask = np.logical_and(
            self.displaced_points[:, 2] >= min_z,
            self.displaced_points[:, 2] <= max_z
        )
        
        # 合并掩码 - 保留任一点云在范围内的点
        combined_mask = np.logical_or(orig_mask, disp_mask)
        
        # 应用合并的掩码
        filtered_points = self.points[combined_mask]
        filtered_displaced_points = self.displaced_points[combined_mask]
        
        if len(filtered_points) > 0:
            # 创建筛选后的点云对象
            filtered_point_cloud = pv.PolyData(filtered_points)
            filtered_displaced_point_cloud = pv.PolyData(filtered_displaced_points)
            
            # 创建颜色映射
            n_points = len(filtered_point_cloud.points)
            colormap = cm.rainbow(np.linspace(0, 1, n_points))
            
            # 为点云设置颜色数据
            colors = np.zeros((n_points, 3))
            for i in range(n_points):
                colors[i] = colormap[i, :3]  # 取RGB部分，忽略Alpha通道
            
            # 将颜色数据添加到点云
            filtered_point_cloud.point_data["colors"] = colors
            filtered_displaced_point_cloud.point_data["colors"] = colors  # 位移点使用相同颜色映射
            
            # 添加原始点云 - 使用自定义颜色映射
            point_actor = self.plotter.add_points(
                filtered_point_cloud,
                scalars="colors",
                rgb=True,
                point_size=self.state.point_size,
                reset_camera=False
            )

            # 添加位移点云 - 使用相同的颜色映射
            displaced_point_actor = self.plotter.add_points(
                filtered_displaced_point_cloud,
                scalars="colors",
                rgb=True,
                point_size=self.state.point_size,
                reset_camera=False
            )
            
            # 将两个点云actor都保存到状态中
            self.state.current_points = point_actor
            self.state.current_displaced_points = displaced_point_actor
            
            if self.state.show_arrows and len(filtered_points) > 0:
                # 创建箭头数据
                arrow_actors = []
                
                # 计算规范化系数 - 全局最大值的50%
                scale_factor = self.max_magnitude * 0.5
                                
                # 绘制部分箭头（太多会影响性能）
                step = max(1, len(filtered_points) // 100)  # 最多显示100个箭头
                
                for i in range(0, len(filtered_points), step):
                    start = filtered_points[i]
                    end = filtered_displaced_points[i]
                    direction = end - start
                    
                    # 计算箭头长度
                    length = np.linalg.norm(direction)
                    if length < 1e-6:  # 避免零长度箭头
                        continue
                        
                    # 使用 pyvista 创建箭头
                    direction_normalized = direction / length
                    arrow = pv.Arrow(start, direction_normalized, scale=length/scale_factor)
                                        
                    # 添加到场景
                    arrow_actor = self.plotter.add_mesh(
                        arrow,
                        color='yellow',
                        reset_camera=False
                    )
                    arrow_actors.append(arrow_actor)
                
                # 存储所有箭头
                self.state.current_arrows = arrow_actors
                
        # 更新点云切片范围缓存
        self._last_point_slice_min = self.state.point_slice_min
        self._last_point_slice_max = self.state.point_slice_max
        
    def _update_slice_min_week0(self, value):
        self.state.slice_min_week0 = int(value)
        self.update_volume(update_where='week0')
        
    def _update_slice_max_week0(self, value):
        self.state.slice_max_week0 = int(value)
        self.update_volume(update_where='week0')
        
    def _update_window_week0(self, value):
        self.state.window_week0 = value
        self.update_volume(update_where='week0')
        
    def _update_level_week0(self, value):
        self.state.level_week0 = value
        self.update_volume(update_where='week0')
        
    def _update_opacity_week0(self, value):
        self.state.opacity_week0 = value
        self.update_volume(update_where='week0')
        
    def _update_slice_min_week4(self, value):
        self.state.slice_min_week4 = int(value)
        self.update_volume(update_where='week4')
        
    def _update_slice_max_week4(self, value):
        self.state.slice_max_week4 = int(value)
        self.update_volume(update_where='week4')
        
    def _update_window_week4(self, value):
        self.state.window_week4 = value
        self.update_volume(update_where='week4')
        
    def _update_level_week4(self, value):
        self.state.level_week4 = value
        self.update_volume(update_where='week4')
        
    def _update_opacity_week4(self, value):
        self.state.opacity_week4 = value
        self.update_volume(update_where='week4')
        
    def _update_point_size(self, value):
        self.state.point_size = value
        self.update_volume(update_where='points')
        
    def _update_point_slice_min(self, value):
        self.state.point_slice_min = int(value)
        self.update_volume(update_where='points')
        
    def _update_point_slice_max(self, value):
        self.state.point_slice_max = int(value)
        self.update_volume(update_where='points')
        
    def _toggle_arrows(self, state):
        self.state.show_arrows = state
        self.update_volume(update_where='points')
        
    def show(self):
        """显示可视化结果"""
        self.plotter.add_axes()
        self.plotter.view_isometric()
        self.plotter.reset_camera()
        
        # 检查是否是运行在Qt环境中的pyvistaqt.QtInteractor
        if hasattr(self.plotter, 'update') and callable(getattr(self.plotter, 'update')):
            # 如果是Qt环境中，只更新显示而不弹出独立窗口
            self.plotter.update()
        else:
            # 否则使用独立窗口显示
            self.plotter.show()