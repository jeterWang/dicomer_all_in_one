import SimpleITK as sitk
import numpy as np
import pyvista as pv
from .state import State

class ImagePlotter:
    """图像可视化类"""
    
    def __init__(self, sitk_image_week0, sitk_image_week4, points, displaced_points):
        """初始化可视化器
        
        Args:
            sitk_image_week0 (SimpleITK.Image): Week 0的CT图像
            sitk_image_week4 (SimpleITK.Image): Week 4的CT图像
            points (numpy.ndarray): 原始点云数据
            displaced_points (numpy.ndarray): 位移后的点云数据
        """
        # 创建状态管理器 - 使用正确的图像形状
        self.state = State(sitk.GetArrayFromImage(sitk_image_week0).shape)
        
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
        # 1. 首先计算原始位移
        original_displacement = displaced_points - points
        
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
        
        # 创建plotter
        self.plotter = pv.Plotter()
        
        # 添加点击回调
        def callback(point):
            print(f"Picked point: {point}")
            self._point_picked(point)
            
        self.plotter.enable_point_picking(callback=callback,
                                        show_message=False,
                                        show_point=False,
                                        left_clicking=True)
        
        # 添加用于显示CT值的文本
        self.ct_value_text = None
        
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
        
    def update_volume(self):
        """更新体积渲染和点云"""
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
        if self.ct_value_text is not None:
            self.plotter.remove_actor(self.ct_value_text)
        
        # 创建Week 0的切片体积
        sliced_volume_week0 = self.grid_week0.copy()
        sliced_array_week0 = self.array_week0[self.state.slice_min_week0:self.state.slice_max_week0+1]
        new_dims_week0 = list(sliced_volume_week0.dimensions)
        new_dims_week0[2] = self.state.slice_max_week0 - self.state.slice_min_week0 + 1
        sliced_volume_week0.dimensions = new_dims_week0
        sliced_volume_week0.point_data["CT_values"] = sliced_array_week0.ravel()
        
        # 创建Week 4的切片体积
        sliced_volume_week4 = self.grid_week4.copy()
        sliced_array_week4 = self.array_week4[self.state.slice_min_week4:self.state.slice_max_week4+1]
        new_dims_week4 = list(sliced_volume_week4.dimensions)
        new_dims_week4[2] = self.state.slice_max_week4 - self.state.slice_min_week4 + 1
        sliced_volume_week4.dimensions = new_dims_week4
        sliced_volume_week4.point_data["CT_values"] = sliced_array_week4.ravel()
        
        # 添加Week 0的体积渲染
        self.state.current_mapper_week0 = self.plotter.add_volume(
            sliced_volume_week0,
            cmap="gray",
            opacity=self.state.opacity_week0,
            clim=[self.state.level_week0 - self.state.window_week0/2,
                  self.state.level_week0 + self.state.window_week0/2]
        )
        
        # 添加Week 4的体积渲染
        self.state.current_mapper_week4 = self.plotter.add_volume(
            sliced_volume_week4,
            cmap="gray",
            opacity=self.state.opacity_week4,
            clim=[self.state.level_week4 - self.state.window_week4/2,
                  self.state.level_week4 + self.state.window_week4/2]
        )
        
        # 根据选择的层范围过滤点云
        # 使用Z轴作为切片方向，并添加容差范围
        tolerance = 0.5  # 增加一个容差值以确保能选中点
        point_indices = np.where(
            (self.points[:, 2] >= self.state.point_slice_min - tolerance) & 
            (self.points[:, 2] <= self.state.point_slice_max + tolerance)
        )[0]
        
        if len(point_indices) > 0:
            # 过滤当前层范围内的点
            current_points = self.points[point_indices]
            current_displaced_points = self.displaced_points[point_indices]
            
            # 计算每对点之间的位移距离
            displacements = current_displaced_points - current_points
            distances = np.linalg.norm(displacements, axis=1)
            
            # 创建颜色映射
            min_dist = distances.min()
            max_dist = distances.max()
            normalized_distances = (distances - min_dist) / (max_dist - min_dist)
            
            # 使用matplotlib的颜色映射生成RGB颜色
            import matplotlib.cm as cm
            colors = cm.rainbow(normalized_distances)[:, :3]  # 取RGB值，忽略alpha通道
            
            # 添加原始点云（使用映射的颜色）
            point_cloud = pv.PolyData(current_points)
            point_cloud.point_data["colors"] = colors
            self.state.current_points = self.plotter.add_points(
                point_cloud,
                scalars="colors",
                rgb=True,
                point_size=self.state.point_size,
                render_points_as_spheres=True,
                opacity=1.0
            )
            
            # 添加位移点云（使用相同的颜色映射）
            displaced_point_cloud = pv.PolyData(current_displaced_points)
            displaced_point_cloud.point_data["colors"] = colors
            self.state.current_displaced_points = self.plotter.add_points(
                displaced_point_cloud,
                scalars="colors",
                rgb=True,
                point_size=self.state.point_size,
                render_points_as_spheres=True,
                opacity=1.0
            )
            
            # 只在需要显示箭头且状态对象存在show_arrows属性时添加箭头
            if hasattr(self.state, 'show_arrows') and self.state.show_arrows:
                # 创建当前层范围内的线段
                n_filtered_points = len(point_indices)
                lines = []
                for i in range(n_filtered_points):
                    lines.extend([2, i, i + n_filtered_points])
                    
                # 创建包含过滤后点的PolyData
                all_filtered_points = np.vstack([current_points, current_displaced_points])
                arrows = pv.PolyData(all_filtered_points)
                arrows.lines = lines
                
                # 为箭头设置颜色（重复每个颜色两次，因为每条线段有两个端点）
                arrow_colors = np.vstack([colors, colors])
                arrows.point_data["colors"] = arrow_colors
                
                # 添加到场景
                self.state.current_arrows = self.plotter.add_mesh(
                    arrows,
                    scalars="colors",
                    rgb=True,
                    opacity=1,
                    line_width=2,
                    show_scalar_bar=False
                )
        
    def setup_sliders(self):
        """设置所有控制滑块"""
        
        # 控件位置计算
        x_start = 0.01  # 左边距
        x_width = 0.15   # 控件宽度
        y_start = 1  # 顶部开始位置
        y_step = 0.1   # 垂直间距 (缩小一倍)

        # Week 4 控制组
        # self.plotter.add_text("Week 4 Controls", position=(x_start, y_start), font_size=10, color='white')
        y_pos = y_start - y_step
        
        # Week 4 滑块
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_slice_min_week4(value),
            rng=[0, self.array_week4.shape[0] - 1],
            value=0,
            title="Min Slice",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_slice_max_week4(value),
            rng=[0, self.array_week4.shape[0] - 1],
            value=self.array_week4.shape[0] - 1,
            title="Max Slice",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_window_week4(value),
            rng=[1, self.array_week4.max() - self.array_week4.min()],
            value=self.state.window_week4,
            title="Window Width",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_level_week4(value),
            rng=[self.array_week4.min(), self.array_week4.max()],
            value=self.state.level_week4,
            title="Window Level",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_opacity_week4(value),
            rng=[0, 1],
            value=0.5,
            title="Opacity",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        
        # 当前Y位置
        y_pos = y_start
        
        # Week 0 控制组
        # self.plotter.add_text("Week 0 Controls", position=(x_start, y_pos), font_size=7, color='white')

        y_pos = y_start - y_step
        x_start = 0.01 + x_width
        
        # Week 0 滑块
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_slice_min_week0(value),
            rng=[0, self.array_week0.shape[0] - 1],
            value=0,
            title="Min Slice",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_slice_max_week0(value),
            rng=[0, self.array_week0.shape[0] - 1],
            value=self.array_week0.shape[0] - 1,
            title="Max Slice",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_window_week0(value),
            rng=[1, self.array_week0.max() - self.array_week0.min()],
            value=self.state.window_week0,
            title="Window Width",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_level_week0(value),
            rng=[self.array_week0.min(), self.array_week0.max()],
            value=self.state.level_week0,
            title="Window Level",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_opacity_week0(value),
            rng=[0, 1],
            value=0.5,
            title="Opacity",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
    
        # 点云控制组
        # self.plotter.add_text("Point Cloud Controls", position=(x_start, y_pos), font_size=7, color='white')
        x_start = 0.01
        
        # 点云控制滑块
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_point_size(value),
            rng=[1, 20],
            value=5,
            title="Point Size",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        # 使用点云的实际Z轴范围作为滑块范围
        z_min, z_max = self.point_ranges['z']
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_point_slice_min(value),
            rng=[z_min, z_max],
            value=z_min,
            title="Min Point Slice",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        self.plotter.add_slider_widget(
            callback=lambda value: self._update_point_slice_max(value),
            rng=[z_min, z_max],
            value=z_max,
            title="Max Point Slice",
            pointa=(x_start, y_pos),
            pointb=(x_start + x_width, y_pos),
            style='modern',
            title_color='white'
        )
        y_pos -= y_step
        
        # 箭头显示控制
        self.plotter.add_checkbox_button_widget(
            callback=lambda value: self._toggle_arrows(value),
            value=True,
            # position=(x_start+0.5, y_pos),
            position=(10, 25),
            size=20,
            border_size=1,
            color_on='white',
            color_off='grey'
        )
        self.plotter.add_text("Show Arrows", position=(40, 20), font_size=13, color='white')
        
    def _update_slice_min_week0(self, value):
        """更新Week 0最小切片"""
        self.state.slice_min_week0 = min(int(value), self.state.slice_max_week0 - 1)
        self.update_volume()
        
    def _update_slice_max_week0(self, value):
        """更新Week 0最大切片"""
        self.state.slice_max_week0 = max(int(value), self.state.slice_min_week0 + 1)
        self.update_volume()
        
    def _update_window_week0(self, value):
        """更新Week 0窗宽"""
        self.state.window_week0 = max(value, 1.0)
        self.update_volume()
        
    def _update_level_week0(self, value):
        """更新Week 0窗位"""
        self.state.level_week0 = value
        self.update_volume()
        
    def _update_opacity_week0(self, value):
        """更新Week 0不透明度"""
        self.state.opacity_week0 = value
        self.update_volume()
        
    def _update_slice_min_week4(self, value):
        """更新Week 4最小切片"""
        self.state.slice_min_week4 = min(int(value), self.state.slice_max_week4 - 1)
        self.update_volume()
        
    def _update_slice_max_week4(self, value):
        """更新Week 4最大切片"""
        self.state.slice_max_week4 = max(int(value), self.state.slice_min_week4 + 1)
        self.update_volume()
        
    def _update_window_week4(self, value):
        """更新Week 4窗宽"""
        self.state.window_week4 = max(value, 1.0)
        self.update_volume()
        
    def _update_level_week4(self, value):
        """更新Week 4窗位"""
        self.state.level_week4 = value
        self.update_volume()
        
    def _update_opacity_week4(self, value):
        """更新Week 4不透明度"""
        self.state.opacity_week4 = value
        self.update_volume()
        
    def _update_point_size(self, value):
        """更新点大小"""
        self.state.point_size = value
        self.update_volume()
        
    def _update_point_slice_min(self, value):
        """更新点云显示的最小层"""
        self.state.point_slice_min = min(int(value), self.state.point_slice_max - 1)
        self.update_volume()
        
    def _update_point_slice_max(self, value):
        """更新点云显示的最大层"""
        self.state.point_slice_max = max(int(value), self.state.point_slice_min + 1)
        self.update_volume()
        
    def _toggle_arrows(self, state):
        """切换箭头显示状态"""
        self.state.show_arrows = state
        self.update_volume()
        
    def show(self):
        """显示可视化结果"""
        # 设置初始体积和点云
        self.update_volume()
        
        # 设置相机位置和背景
        self.plotter.camera.zoom(0.8)  # 减小缩放以显示两个图像
        self.plotter.camera.elevation = 0  # 设置相机仰角为0，保持水平视角
        self.plotter.background_color = 'black'
        
        # 显示图像
        self.plotter.show() 