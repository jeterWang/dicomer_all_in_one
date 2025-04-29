class State:
    """状态管理类，用于存储和管理可视化状态"""
    
    def __init__(self, volume_shape):
        """初始化状态
        
        Args:
            volume_shape (tuple): 体积数据的形状
        """
        # Week 0 状态
        self.current_mapper_week0 = None
        self.window_week0 = 2000
        self.level_week0 = 0
        self.opacity_week0 = 0.5
        self.slice_min_week0 = 0
        self.slice_max_week0 = volume_shape[0] - 1
        
        # Week 4 状态
        self.current_mapper_week4 = None
        self.window_week4 = 2000
        self.level_week4 = 0
        self.opacity_week4 = 0.5
        self.slice_min_week4 = 0
        self.slice_max_week4 = volume_shape[0] - 1
        
        # 点云状态
        self.current_points = None
        self.point_size = 5
        self.point_slice_min = 0  # 点云显示的最小层
        self.point_slice_max = volume_shape[0] - 1  # 点云显示的最大层
        
        # 渲染器状态
        self.current_displaced_points = None
        self.current_arrows = None
        self.point_color = 'red'
        self.show_arrows = True  # 控制箭头显示的状态 