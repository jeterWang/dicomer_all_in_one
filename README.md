# DICOM All-in-One 工具

这是一个集成了多个 DICOM 相关功能的综合工具。

## 功能特点

- DICOM 文件编辑器
- 更多功能正在开发中...

## 安装

1. 克隆仓库：
```bash
git clone [repository_url]
cd dicom_aio
```

2. 创建虚拟环境并安装依赖：
```bash
uv venv
source .venv/Scripts/activate
uv pip install -r requirements.txt
```

## 使用方法

运行主程序：
```bash
python main.py
```

## 项目结构

```
dicom_aio/
├── src/
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py
│   │   └── dicom_editor.py
│   └── __init__.py
├── data/
├── requirements.txt
└── main.py
```

## 开发计划

- [ ] 添加 DICOM 查看器
- [ ] 添加 DICOM 转换工具
- [ ] 添加 DICOM 分析工具
- [ ] 添加批量处理功能 