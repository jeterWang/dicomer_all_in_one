# DVF Viewer

这是一个用于可视化形变向量场（Deformation Vector Field, DVF）的 Python 工具。该工具可以帮助医疗影像研究人员查看和分析不同时间点的 CT 图像和相应的形变场。

## 项目结构

```
dvf_viewer/
├── main.py              # 主程序入口
├── utils/               # 工具函数
├── visualization/       # 可视化相关代码
└── data/               # 数据目录（未包含在代码仓库中）
```

## 数据要求

由于数据文件较大，未包含在代码仓库中。要运行此程序，您需要准备以下数据文件：

### 数据目录结构
```
data/
└── {patient_id}/
    ├── images/
    │   ├── week0_CT/   # Week 0 的 DICOM 文件
    │   └── week4_CT/   # Week 4 的 DICOM 文件
    └── instances/
        └── {instance_id}/
            ├── voxel_coord.csv                    # 体素坐标文件
            ├── voxel_disp/
            │   └── week0_CT_week4_CT_voxel_disp.csv   # 形变场数据
            ├── FEM/
            │   └── DVF/
            │       └── *.raw                      # FEM 计算的 DVF 文件
            └── withoutFEM/
                └── DVF/
                    ├── *.raw                      # 非 FEM 计算的 DVF 文件
                    └── *.dcm                      # DICOM 格式的 DVF 文件
```

### 数据格式说明

1. **CT 图像**
   - 格式：DICOM
   - 位置：`images/week0_CT/` 和 `images/week4_CT/`
   - 要求：完整的 CT 序列 DICOM 文件

2. **体素坐标文件 (voxel_coord.csv)**
   - 格式：CSV
   - 列：x, y, z（体素坐标）
   - 分隔符：逗号
   - 示例：
     ```
     x,y,z
     123,45,67
     124,46,68
     ...
     ```

3. **形变场数据 (week0_CT_week4_CT_voxel_disp.csv)**
   - 格式：CSV
   - 列：dx, dy, dz（x、y、z方向的位移）
   - 分隔符：逗号
   - 示例：
     ```
     dx,dy,dz
     0.5,-0.3,0.1
     0.6,-0.2,0.2
     ...
     ```

4. **DVF 文件**
   - RAW 格式 (*.raw)：
     - 大小：~100MB
     - 数据类型：32位浮点数
     - 维度：与CT图像尺寸相同
   - DICOM 格式 (*.dcm)：
     - 包含完整的DICOM头信息
     - 与原始CT序列具有相同的空间参考

## 环境要求

```bash
# 使用 uv 安装依赖
uv pip install -r requirements.txt
```

## 使用方法

1. 准备数据文件并按上述结构放置
2. 在 `main.py` 中设置相应的 `patient_id` 和 `instance_id`
3. 运行程序：
```bash
uv python main.py
```

## 注意事项

- 数据文件未包含在代码仓库中，需要单独获取
- 确保有足够的磁盘空间（每个病例约需要 300MB-500MB）
- 推荐使用 SSD 以获得更好的读取性能

## 数据获取

如需获取示例数据，请联系项目维护者。 