#!/usr/bin/env python
# -*- coding: utf-8 -*-

import numpy as np
import SimpleITK as sitk
import napari
from typing import Union, Optional
import threading
import time
import traceback # 导入 traceback 模块
import tempfile # 用于创建临时文件
import json     # 用于保存元数据
import uuid     # 用于生成唯一文件名
import os

# 全局变量来跟踪 Napari 查看器实例，防止被垃圾回收
# 注意：这在复杂场景下可能不是最佳实践，但对于调试工具来说通常足够
_napari_viewer_instance = None

def _run_napari_in_thread(np_image: np.ndarray, title: Optional[str], is_label: bool):
    """在单独的线程中运行 Napari 查看器。"""
    global _napari_viewer_instance
    print(f"Napari thread ({threading.current_thread().name}): Entered function.")
    try:
        print(f"Napari thread: Attempting to create viewer using napari.gui_qt()...")
        # 使用 napari.gui_qt() 上下文管理器，它负责启动和管理事件循环
        with napari.gui_qt(startup_logo=False) as viewer:
            _napari_viewer_instance = viewer # 保持引用
            print(f"Napari thread: Viewer instance created: {viewer}")

            if is_label:
                print(f"Napari thread: Adding label layer '{title}'...")
                viewer.add_labels(np_image, name=title)
                print(f"Napari thread: Label layer '{title}' added.")
            else:
                print(f"Napari thread: Adding image layer '{title}'...")
                viewer.add_image(np_image, name=title)
                print(f"Napari thread: Image layer '{title}' added.")

            print(f"Napari thread: napari.gui_qt() context manager is running the event loop. Waiting for window close...")
            # 事件循环由上下文管理器处理，代码会阻塞在这里直到窗口关闭

        print(f"Napari thread: napari.gui_qt() context finished (window closed).")

    except Exception as e:
        # 打印更详细的错误信息和堆栈跟踪
        print(f"!!!!!!!! ERROR IN NAPARI THREAD !!!!!!!!")
        print(f"Error type: {type(e)}")
        print(f"Error message: {e}")
        print("Traceback:")
        traceback.print_exc() # 打印完整的堆栈跟踪
    finally:
        _napari_viewer_instance = None
        print("Napari thread finished.")


def view_image_napari(image_data: Union[np.ndarray, sitk.Image],
                      title: Optional[str] = None,
                      is_label: bool = False):
    """
    使用 Napari 在单独的线程中实时显示 NumPy 数组或 SimpleITK 图像。
    此函数将立即返回，不会阻塞调试器。

    Args:
        image_data: 要显示的图像数据，可以是 NumPy ndarray 或 SimpleITK.Image。
        title: 在 Napari 图层列表中显示的名称。
        is_label: 如果为 True，则作为标签图层添加 (适用于整数掩码)。
    """
    try:
        if isinstance(image_data, sitk.Image):
            print(f"Converting SimpleITK image (Size: {image_data.GetSize()}) to NumPy array for Napari...")
            np_image = sitk.GetArrayFromImage(image_data)
            print(f"Converted NumPy array shape: {np_image.shape}")
        elif isinstance(image_data, np.ndarray):
            print(f"Displaying NumPy array (Shape: {image_data.shape}) with Napari...")
            np_image = image_data.copy() # 复制一份以防万一在显示时被修改
        else:
            print(f"Error: Unsupported data type {type(image_data)}. Provide NumPy array or SimpleITK image.")
            return

        # 创建并启动 Napari 线程
        # 使用 daemon=True 可能有助于在主程序退出时自动清理线程，但这在调试场景下可能不是必需的
        napari_thread = threading.Thread(
            target=_run_napari_in_thread,
            args=(np_image, title, is_label),
            name=f"NapariViewerThread-{title or 'Untitled'}"
            # daemon=True
        )
        print(f"Starting Napari thread for '{title}'...")
        napari_thread.start()

        # 短暂等待，确保线程有机会启动并打印其初始消息（可选）
        # time.sleep(0.5)

        print("view_image_napari function call finished. Napari window should appear shortly in a separate thread.")
        print("Debug console is now unblocked. You can continue debugging.")

    except ImportError:
        print("Error: Napari library not found. Please install it: pip install napari[pyqt5]")
    except Exception as e:
        print(f"Error launching Napari thread: {e}")

# --- 新增：发送数据到外部查看器的函数 ---

# 定义一个共享的目录，用于调试器和监听器之间传递文件
# 使用临时目录是个不错的选择
NAPARI_WATCH_DIR = os.path.join(tempfile.gettempdir(), 'napari_debug_watch')

def ensure_watch_dir():
    """确保监控目录存在"""
    if not os.path.exists(NAPARI_WATCH_DIR):
        try:
            os.makedirs(NAPARI_WATCH_DIR)
            print(f"Created Napari watch directory: {NAPARI_WATCH_DIR}")
        except OSError as e:
            print(f"Error creating watch directory {NAPARI_WATCH_DIR}: {e}")
            return False
    return True

def send_to_external_napari(image_data: Union[np.ndarray, sitk.Image],
                            title: Optional[str] = None,
                            is_label: bool = False):
    """
    将图像数据和元数据保存到临时文件，供外部 Napari 监听器加载。

    Args:
        image_data: 要显示的图像数据 (NumPy or SimpleITK).
        title: 图层标题。
        is_label: 是否为标签图层。
    """
    if not ensure_watch_dir():
        print("Cannot proceed without watch directory.")
        return

    try:
        scale = None
        translate = None
        if isinstance(image_data, sitk.Image):
            print(f"Converting SimpleITK image (Size: {image_data.GetSize()}) to NumPy array...")
            # 提取物理信息 (顺序通常是 x, y, z)
            scale_sitk = image_data.GetSpacing()
            translate_sitk = image_data.GetOrigin()
            print(f"  - Extracted Spacing (x,y,z): {scale_sitk}")
            print(f"  - Extracted Origin (x,y,z): {translate_sitk}")
            np_image = sitk.GetArrayFromImage(image_data)
            print(f"Converted NumPy array shape (z,y,x): {np_image.shape}")
        elif isinstance(image_data, np.ndarray):
            np_image = image_data.copy() # 复制以防原始数据被修改
            print(f"Using provided NumPy array (Shape: {np_image.shape})")
        else:
            print(f"Error: Unsupported data type {type(image_data)}.")
            return

        # 生成唯一的文件名基础
        base_filename = f"napari_data_{uuid.uuid4()}"
        npy_filepath = os.path.join(NAPARI_WATCH_DIR, f"{base_filename}.npy")
        meta_filepath = os.path.join(NAPARI_WATCH_DIR, f"{base_filename}.meta")

        # 保存 NumPy 数组
        print(f"Saving NumPy array to: {npy_filepath}")
        np.save(npy_filepath, np_image)

        # 保存元数据 (标题, is_label, scale, translate)
        metadata = {
            'title': title or 'Untitled Layer',
            'is_label': is_label,
            'npy_file': os.path.basename(npy_filepath), # 关联对应的 npy 文件
            # 保存 SITK 的原始顺序 (x, y, z) 或者 None
            'spacing_xyz': scale_sitk if 'scale_sitk' in locals() else None,
            'origin_xyz': translate_sitk if 'translate_sitk' in locals() else None
        }
        print(f"Saving metadata to: {meta_filepath}")
        print(f"  - Metadata content: {metadata}")
        with open(meta_filepath, 'w') as f:
            json.dump(metadata, f)

        print(f"Data for layer '{title}' sent successfully to watch directory.")

    except Exception as e:
        print(f"Error sending data to external Napari: {e}")
        traceback.print_exc()


# --- 示例用法 (在 __main__ 中) ---
if __name__ == '__main__':
    print("Testing Napari viewer utility (threaded)...")
    # 注意：当直接运行此脚本时，主线程会在启动 Napari 线程后立即尝试退出。
    # Napari 窗口可能会一闪而过，除非采取措施保持主线程活动，
    # 或者 Napari 线程足够快地启动并接管。在调试器中使用时这不是问题。

    print("\n--- Test 1: NumPy Array ---")
    dummy_np_image = (np.random.rand(20, 50, 60) * 255).astype(np.uint8)
    view_image_napari(dummy_np_image, title="Dummy NumPy Image")
    time.sleep(1) # 等待第一个窗口出现

    print("\n--- Test 2: SimpleITK Label Mask ---")
    dummy_mask = np.zeros((20, 50, 60), dtype=np.uint8)
    dummy_mask[5:10, 10:30, 15:40] = 1
    dummy_sitk_mask = sitk.GetImageFromArray(dummy_mask)
    view_image_napari(dummy_sitk_mask, title="Dummy SITK Mask", is_label=True)

    print("\nTesting sending data to external Napari...")
    ensure_watch_dir() # 确保目录存在

    print("\n--- Test Send 1: NumPy Array ---")
    dummy_np_send = (np.random.rand(5, 20, 25) * 100).astype(np.uint8)
    send_to_external_napari(dummy_np_send, title="Sent NumPy Image")

    print("\n--- Test Send 2: SITK Label Mask ---")
    dummy_mask_send = np.zeros((5, 20, 25), dtype=np.uint8)
    dummy_mask_send[1:3, 5:15, 6:18] = 1
    dummy_sitk_send = sitk.GetImageFromArray(dummy_mask_send)
    send_to_external_napari(dummy_sitk_send, title="Sent SITK Mask", is_label=True)

    print(f"\nCheck the directory '{NAPARI_WATCH_DIR}' for .npy and .meta files.")
    print("Run the napari_listener.py script in a separate terminal to view these.")

    print("\nMain thread: Napari view calls made. Waiting a bit before exiting...")
    # 在直接运行脚本时，需要让主线程等待足够长的时间，否则 Napari 线程可能没有机会运行
    time.sleep(10) # 例如等待 10 秒
    print("Main thread finished.") 