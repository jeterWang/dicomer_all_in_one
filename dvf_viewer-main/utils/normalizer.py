import numpy as np

def normalize_array(array):
    """标准化数组，处理极值和无效值
    
    Args:
        array (numpy.ndarray): 输入数组
        
    Returns:
        tuple: (标准化后的数组, 最小值, 最大值)
    """
    # 移除无限值和NaN
    array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)
    
    # 获取有效范围
    p1, p99 = np.percentile(array, [1, 99])
    array = np.clip(array, p1, p99)
    
    # 确保有效的数值范围
    data_min, data_max = array.min(), array.max()
    if data_min == data_max:
        data_max = data_min + 1.0  # 避免除以零
        
    return array, data_min, data_max 