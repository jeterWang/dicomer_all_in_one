import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import pearsonr

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  # 或者 ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号'-'显示为方块的问题

def analyze_correlation(file_path):
    """
    读取CSV文件，计算并显示 week_0 和 week_1 列的相关性。

    参数:
    file_path (str): CSV文件的路径。
    """
    try:
        # 读取CSV文件
        df = pd.read_csv(file_path)

        # 检查列是否存在
        if 'week_0' not in df.columns or 'week_1' not in df.columns:
            print(f"错误: 文件 {file_path} 中未找到 'week_0' 或 'week_1' 列。")
            return

        # 提取数据
        week_0_data = df['week_0']
        week_1_data = df['week_1']

        # 计算皮尔逊相关系数和p值
        correlation, p_value = pearsonr(week_0_data, week_1_data)
        print(f"Week 0 和 Week 1 之间的皮尔逊相关系数: {correlation:.4f}")
        print(f"P-值: {p_value:.4f}")

        # 创建散点图
        plt.figure(figsize=(10, 6))
        sns.scatterplot(x=week_0_data, y=week_1_data)
        
        # 添加回归线
        sns.regplot(x=week_0_data, y=week_1_data, scatter=False, color='red')
        
        # 在图表上显示相关系数和P值
        text_str = f'Pearson R: {correlation:.4f}\n'
        plt.text(0.05, 0.95, text_str, transform=plt.gca().transAxes, fontsize=10,
                 verticalalignment='top', bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5))

        plt.title('Week 0 与 Week 1 的相关性')
        plt.xlabel('Week 0 SUV')
        plt.ylabel('Week 1 SUV')
        plt.grid(True)
        plt.show()

    except FileNotFoundError:
        print(f"错误: 文件 {file_path} 未找到。")
    except Exception as e:
        print(f"处理文件时发生错误: {e}")

if __name__ == "__main__":
    # 指定CSV文件的路径
    csv_file_path = 'data/show_suv_relation/SUV.csv'
    analyze_correlation(csv_file_path) 