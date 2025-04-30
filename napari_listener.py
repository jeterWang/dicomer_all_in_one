#!/usr/bin/env python
# -*- coding: utf-8 -*-

import napari
import time
import os
import numpy as np
import json
import SimpleITK as sitk
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tempfile
import traceback
# 导入 Qt 相关组件 (使用 qtpy 保证兼容性)
from qtpy.QtCore import QObject, Signal as pyqtSignal
from typing import Optional

# 使用与 debug_utils.py 中相同的监控目录
NAPARI_WATCH_DIR = os.path.join(tempfile.gettempdir(), 'napari_debug_watch')

# 确保目录存在
if not os.path.exists(NAPARI_WATCH_DIR):
    os.makedirs(NAPARI_WATCH_DIR)

print(f"Napari Listener started.")
print(f"Watching directory: {NAPARI_WATCH_DIR}")

# 全局变量来持有 Napari viewer 实例
viewer = None

# 修改 Handler 继承自 QObject 并添加信号
class NapariFileHandler(QObject, FileSystemEventHandler):
    # 定义信号：参数类型为 (numpy数组, 标题, 是否标签, spacing元组或None, origin元组或None)
    layer_ready = pyqtSignal(object, str, bool, object, object)

    def __init__(self):
        # 注意：需要在主线程中创建 QObject 实例，以便信号连接到主线程槽
        # 因此 __init__ 不再接收 viewer_instance
        # FileSystemEventHandler 不需要 viewer 实例了，我们通过信号传递数据
        QObject.__init__(self)
        FileSystemEventHandler.__init__(self)
        self.processed_files = set()

    def on_created(self, event):
        # 我们只关心新创建的 .meta 文件
        if not event.is_directory and event.src_path.endswith('.meta'):
            meta_filepath = event.src_path
            base_filename = os.path.splitext(os.path.basename(meta_filepath))[0]

            # 防止因事件重复触发而重复处理
            if base_filename in self.processed_files:
                # print(f"Skipping already processed file base: {base_filename}")
                return
            self.processed_files.add(base_filename)

            print(f"Detected new meta file: {meta_filepath}")
            time.sleep(0.2) # 短暂等待，确保 npy 文件也写入完成

            npy_filepath = os.path.join(NAPARI_WATCH_DIR, f"{base_filename}.npy")

            if not os.path.exists(npy_filepath):
                print(f"Error: Corresponding .npy file not found: {npy_filepath}")
                return

            try:
                # 加载元数据
                print(f"Loading metadata from: {meta_filepath}")
                with open(meta_filepath, 'r') as f:
                    metadata = json.load(f)
                print(f"  - Loaded metadata: {metadata}")
                title = metadata.get('title', 'Untitled')
                is_label = metadata.get('is_label', False)
                # 加载 spacing 和 origin (可能为 None)
                spacing_xyz = metadata.get('spacing_xyz')
                origin_xyz = metadata.get('origin_xyz')

                # 加载 NumPy 数组
                print(f"Loading NumPy array from: {npy_filepath}")
                np_image = np.load(npy_filepath)
                print(f"Loaded array shape: {np_image.shape}")

                # !!! 发射信号，包含物理空间信息 !!!
                print(f"Emitting layer_ready signal for '{title}'...")
                self.layer_ready.emit(np_image, title, is_label, spacing_xyz, origin_xyz)

            except Exception as e:
                print(f"Error processing files for {base_filename}: {e}")
                traceback.print_exc()

# 定义一个槽函数，它将在主 GUI 线程中执行
# 修改槽函数签名以接收 spacing 和 origin
def add_layer_to_viewer(np_image: np.ndarray, title: str, is_label: bool, spacing_xyz: Optional[list], origin_xyz: Optional[list]):
    global viewer # 访问全局 viewer 实例
    if viewer: # 确保 viewer 仍然存在
        try:
            # 准备 Napari 参数
            layer_kwargs = {'name': title}

            # 转换物理空间信息 (从 xyz -> zyx)
            if spacing_xyz is not None:
                # SimpleITK (x,y,z) -> Napari (z,y,x)
                scale = list(reversed(spacing_xyz))
                layer_kwargs['scale'] = scale
                print(f"  - Setting scale (z,y,x): {scale}")
            if origin_xyz is not None:
                # SimpleITK (x,y,z) -> Napari (z,y,x)
                translate = list(reversed(origin_xyz))
                layer_kwargs['translate'] = translate
                print(f"  - Setting translate (z,y,x): {translate}")

            print(f"Slot function (GUI thread): Adding layer '{title}' with kwargs: {layer_kwargs}")
            if is_label:
                viewer.add_labels(np_image, **layer_kwargs)
            else:
                viewer.add_image(np_image, **layer_kwargs)
            print(f"Slot function (GUI thread): Layer '{title}' added.")
        except Exception as e:
            print(f"Error in add_layer_to_viewer slot: {e}")
            traceback.print_exc()
    else:
        print("Error in slot: Napari viewer instance is no longer available.")


if __name__ == "__main__":
    # 1. 创建 Napari 查看器实例 (在主线程)
    viewer = napari.Viewer()
    viewer.title = "External Debug Viewer"
    print("Napari viewer instance created.")

    # 2. 创建 Handler 实例 (也在主线程!)
    event_handler = NapariFileHandler()

    # 3. 连接信号到槽! (在主线程完成连接)
    event_handler.layer_ready.connect(add_layer_to_viewer)
    print("Connected file handler signal to viewer slot.")

    # 4. 设置并启动文件系统观察者 (观察者会创建自己的线程)
    observer = Observer()
    observer.schedule(event_handler, NAPARI_WATCH_DIR, recursive=False)
    observer.start()
    print("Filesystem observer started.")

    # 5. 启动 Napari 事件循环 (阻塞主线程)
    print("Starting Napari event loop (napari.run())...")
    napari.run()

    # --- Napari 窗口关闭后执行的代码 ---
    print("Napari event loop finished (window closed). Stopping observer...")
    observer.stop()
    observer.join()
    print("Observer stopped. Exiting listener script.") 