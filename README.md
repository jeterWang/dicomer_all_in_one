# DICOM All-in-One 工具

这是一个集成了多个 DICOM 相关功能的综合工具，使用 Python 和 PyQt5 构建，并采用 UV 进行包管理。

## 功能特点

- **DICOM 文件编辑器**: 查看和修改 DICOM 文件的元数据标签。
- **RTSS Copier**: 
    - 扫描指定患者文件夹（按 `weekN_Modality` 结构组织，如 `week0_CT`, `week0_PT`, `week4_CT`, `week4_PT`）。
    - 基于文件大小分布和 DICOM Modality 识别 RT Structure Set (RTSS) 文件。
    - **复制 PT->CT RTSS**: 将 Week 0 或 Week 4 的 PT RTSS 文件中的 ROI 轮廓，经过重采样适配到对应的 CT 图像空间，并生成新的 RTSS 文件保存在 CT 目录下。
- **DVF 可视化器** (开发中): 用于查看形变矢量场 (DVF)。
- **(可选) 外部调试查看器**: 配合 `napari_listener.py` 脚本，可以在调试时将图像数据发送到独立的 Napari 窗口进行查看。

## 安装

1.  克隆仓库：
    ```bash
    git clone [repository_url]
    cd dicom_aio
    ```

2.  创建虚拟环境并安装依赖：
    ```bash
    # 使用 uv 创建和管理虚拟环境
    uv venv 
    # 激活虚拟环境 (根据你的 shell 可能不同)
    # Windows (Command Prompt/PowerShell):
    .venv\Scripts\activate
    # Linux/macOS (bash/zsh):
    # source .venv/bin/activate 
    
    # 使用 uv 安装依赖
    uv pip install -r requirements.txt
    ```

## 使用方法

运行主应用程序：
```bash
# 使用 uv 运行
uv run python main.py
# 或者直接用激活环境的 python
# python main.py 
```

**使用 RTSS Copier:**
1. 运行主程序。
2. 切换到 "RTSS Copier" 标签页。
3. 点击 "选择患者文件夹" 按钮，选择包含 `week0_CT`, `week0_PT`, `week4_CT`, `week4_PT` 子目录的父文件夹。
4. 扫描结果会显示在文本区域。
5. 如果扫描成功并找到了必要的 PT RTSS 文件以及对应的 CT/PT 目录，相应的 "复制 WeekN PT->CT RTSS" 按钮会被启用。
6. 点击按钮，确认操作后，程序会将 PT RTSS 适配并保存到对应的 CT 目录下。

**（可选）使用外部调试查看器:**
1. 在一个**单独的**终端窗口中，进入项目目录并运行监听器：
   ```bash
   python napari_listener.py
   ```
   一个空的 Napari 窗口会打开并等待。
2. 在 VS Code 中调试你的代码。
3. 在调试控制台中，导入并调用发送函数：
   ```python
   from src.debug_utils import send_to_external_napari
   send_to_external_napari(your_image_or_mask_variable, title='...', is_label=True/False)
   ```
4. 图像/掩码会作为新图层添加到运行中的 Napari 窗口。
5. 调试结束后关闭 Napari 窗口即可停止监听器。

## 项目结构 (示例)

```
dicom_aio/
├── .venv/                # 虚拟环境
├── data/                 # 示例数据
│   └── rtss_copier/
│       └── patient_folder/
│           ├── week0_CT/
│           ├── week0_PT/
│           ├── week4_CT/
│           └── week4_PT/
├── src/
│   ├── core/             # 核心逻辑 (DICOM 处理, RTStruct 工具等)
│   │   ├── __init__.py
│   │   ├── dicom_utils.py
│   │   └── rtstruct_utils.py
│   ├── gui/              # GUI 相关代码
│   │   ├── __init__.py
│   │   ├── main_window.py
│   │   ├── modules/        # GUI 功能模块 (如 RTSS Copier)
│   │   │   ├── __init__.py
│   │   │   └── rtss_copier.py
│   │   └── widgets/        # 可复用的小部件
│   ├── debug_utils.py    # 调试工具 (如 Napari 发送器)
│   └── __init__.py
├── .gitignore
├── main.py               # 程序入口
├── napari_listener.py    # 外部 Napari 查看器监听脚本
├── README.md
└── requirements.txt      # 项目依赖
```

## 主要依赖

- PyQt5: GUI 框架。
- pydicom: 读取和写入 DICOM 文件。
- SimpleITK: 图像处理和几何操作。
- rt-utils: 简化 RTStruct 的读取和掩码生成/添加。
- numpy: 数值计算基础。
- napari: 图像可视化 (用于调试)。
- watchdog: 文件系统监控 (用于调试)。

## 开发计划

- [x] DICOM 文件编辑器
- [x] RTSS Copier (PT->CT for Week0/4)
- [ ] 添加 DICOM 查看器集成到主窗口
- [ ] 添加 DVF 可视化和处理功能
- [ ] 完善错误处理和用户反馈 