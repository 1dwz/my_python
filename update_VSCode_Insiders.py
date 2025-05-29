#!/usr/bin/env python3
# coding: utf-8
"""
VSCode Insiders 自动更新工具 (优化版，适用于PyInstaller打包)

用法:
    - 直接运行: python update_VSCode_Insiders.py [可选: 安装目录]
    - 打包后运行: update_VSCode_Insiders.exe [可选: 安装目录]

    如果未提供安装目录，则默认使用脚本/程序自身所在的目录。
    例如，如果 update_VSCode_Insiders.exe 位于 D:\VSCodePortable\，
    则默认更新 D:\VSCodePortable\ 中的 VSCode Insiders。

依赖项: requests, psutil (这些应由PyInstaller打包)
特性:
    - 检查VSCode Insiders进程，等待其退出后再更新
    - 下载最新版VSCode Insiders (win32-x64-archive)
    - 解压并覆盖到指定安装目录
    - 在安装目录创建 'data' 文件夹以启用便携模式 (如果尚不存在)
    - 记录更新后的版本号，避免重复更新
    - 无需手动安装依赖，打包时应包含
"""

import sys
import time
import re
import shutil
from pathlib import Path
import io # Not used for download buffer anymore, but zipfile might use it internally
import zipfile
# subprocess is not used in this version but kept for potential future extensions

# --- Try to import required modules ---
# PyInstaller should bundle these. If running from source, they must be installed.
try:
    import requests
except ImportError:
    print("错误: 缺少 requests 模块。")
    print("如果从源码运行, 请运行: pip install requests")
    print("如果这是打包后的程序, 则打包过程可能不完整或依赖未正确包含。")
    sys.exit(1)

try:
    import psutil
except ImportError:
    print("错误: 缺少 psutil 模块。")
    print("如果从源码运行, 请运行: pip install psutil")
    print("如果这是打包后的程序, 则打包过程可能不完整或依赖未正确包含。")
    sys.exit(1)


DOWNLOAD_URL = "https://code.visualstudio.com/sha/download?build=insider&os=win32-x64-archive"
VERSION_FILE_NAME = "last_version.txt"
PROC_NAME = "Code - Insiders.exe" # Windows specific
PORTABLE_DATA_DIR_NAME = "data"

def get_application_base_path() -> Path:
    """
    获取应用程序的基础路径。
    对于源码执行，是脚本所在目录。
    对于PyInstaller打包的程序（frozen），是可执行文件所在目录。
    """
    if getattr(sys, 'frozen', False): # True if running as a PyInstaller bundle
        return Path(sys.executable).parent.resolve()
    else: # Running as a normal .py script
        return Path(__file__).parent.resolve()

def get_latest_url() -> str:
    print(f"从 {DOWNLOAD_URL} 获取重定向URL...")
    # Increased timeout for initial request, can be slow sometimes
    r = requests.get(DOWNLOAD_URL, allow_redirects=True, timeout=60)
    r.raise_for_status()
    print(f"实际下载URL: {r.url}")
    return r.url

def extract_version(url: str) -> str:
    # This regex matches the timestamp-like version in current VSCode Insider URLs
    # e.g., VSCode-win32-x64-1706080933-insider.zip -> "1706080933"
    m = re.search(r"VSCode-win32-x64-([0-9\.]+)-insider\.zip", url)
    if not m:
        # Fallback for potential commit hash in filename, though less common for this part
        m = re.search(r"VSCode-win32-x64-([0-9a-fA-F]{7,})-insider\.zip", url)
        if not m:
            raise ValueError(f"无法从URL中提取版本标识: {url}")
    return m.group(1)


def read_last_version(vfile: Path) -> str | None:
    if vfile.exists():
        try:
            return vfile.read_text(encoding='utf-8').strip()
        except Exception as e:
            print(f"警告: 读取版本文件 {vfile} 失败: {e}")
            return None
    return None

def write_last_version(vfile: Path, version: str):
    try:
        vfile.write_text(version, encoding='utf-8')
    except Exception as e:
        print(f"警告: 写入版本文件 {vfile} 失败: {e}")

def wait_for_exit(proc_name: str):
    print(f"检测进程: {proc_name}")
    while True:
        process_found_this_iteration = False
        try:
            # Iterate over processes, getting only necessary info
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] == proc_name:
                    print(f"{proc_name} 正在运行 (PID: {proc.info['pid']}), 等待其退出...")
                    process_found_this_iteration = True
                    break # Found one instance, no need to check further in this iteration
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            # These errors can occur if a process terminates or is inaccessible during iteration.
            # Log lightly and continue, as the process might be the one we're waiting for.
            # print(f"  (psutil access issue: {e})") # Optional: for debugging
            pass # Continue to the main check or sleep
        except Exception as e: # Catch any other psutil errors
            print(f"  (psutil unexpected error: {e})")
            pass

        if not process_found_this_iteration:
            print(f"{proc_name} 已退出或未运行。")
            break # No process with that name found in the full scan
        
        time.sleep(3) # Wait before re-scanning all processes
    print(f"继续更新流程...")


def download_extract(url: str, dest_dir: Path):
    print(f"开始下载: {url}")
    
    # Use a requests.Session for connection pooling and configuration
    session = requests.Session()
    # Set a longer read timeout for the actual download stream
    # Connect timeout 15s, read timeout for each chunk 60s
    r = session.get(url, stream=True, timeout=(15, 60)) 
    r.raise_for_status()
    
    total_size = int(r.headers.get("content-length", 0))
    chunk_size = 8192 * 2 # 16KB chunks
    downloaded_size = 0
    
    # Temporary file for download to save RAM, placed in dest_dir's parent
    temp_zip_path = dest_dir.parent / f"vscode_download_{int(time.time())}.zip.tmp"

    try:
        print(f"下载到临时文件: {temp_zip_path}")
        with open(temp_zip_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk: # filter out keep-alive new chunks
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        percentage = downloaded_size * 100 // total_size
                        # Ensure progress bar doesn't exceed 100% due to content-length inaccuracies
                        percentage = min(percentage, 100) 
                        print(f"\r下载进度: {percentage}% ({downloaded_size}/{total_size} bytes)", end="")
                    else:
                        print(f"\r下载进度: {downloaded_size} bytes (总大小未知)", end="")
        print("\n下载完成。")

        print("开始解压...")
        # Temporary directory for extraction contents
        tmp_extract_dir = dest_dir.parent / f"vscode_extract_temp_{int(time.time())}"
        tmp_extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(temp_zip_path, 'r') as z:
                z.extractall(tmp_extract_dir)
            print(f"已解压到临时目录: {tmp_extract_dir}")

            print(f"正在将文件移动到安装目录: {dest_dir}")
            dest_dir.mkdir(parents=True, exist_ok=True) # Ensure destination exists

            for item_in_tmp in tmp_extract_dir.iterdir():
                target_item_path = dest_dir / item_in_tmp.name
                
                # Remove existing item in destination if it exists
                if target_item_path.exists():
                    if target_item_path.is_dir():
                        print(f"  删除已存在的目录: {target_item_path.name}")
                        shutil.rmtree(target_item_path)
                    else:
                        print(f"  删除已存在的文件: {target_item_path.name}")
                        target_item_path.unlink()
                
                # Move item from temp extraction dir to final destination
                # print(f"  移动: {item_in_tmp.name}") # Verbose logging
                shutil.move(str(item_in_tmp), str(dest_dir))
            print("文件移动完成。")

        finally: # Cleanup extraction directory
            if tmp_extract_dir.exists():
                shutil.rmtree(tmp_extract_dir)
                print(f"临时解压目录 {tmp_extract_dir.name} 已清理。")
    
    finally: # Cleanup downloaded zip file
        if temp_zip_path.exists():
            temp_zip_path.unlink()
            print(f"临时下载文件 {temp_zip_path.name} 已清理。")
            
    print("更新操作完成。")


def ensure_portable_mode(install_dir: Path):
    data_dir = install_dir / PORTABLE_DATA_DIR_NAME
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=False) # exist_ok=False to ensure it's newly created
            print(f"已在 {install_dir} 创建 '{PORTABLE_DATA_DIR_NAME}' 目录以启用便携模式。")
        except FileExistsError:
            # This can happen if another process creates it between check and mkdir
            print(f"'{PORTABLE_DATA_DIR_NAME}' 目录已存在于 {install_dir} (可能由并发操作创建)。")
        except Exception as e:
            print(f"创建 '{PORTABLE_DATA_DIR_NAME}' 目录失败: {e}")
    else:
        print(f"'{PORTABLE_DATA_DIR_NAME}' 目录已存在于 {install_dir}，便携模式应已启用。")


def main():
    print("--- VSCode Insiders 自动更新工具 ---")
    
    install_dir_arg = sys.argv[1] if len(sys.argv) > 1 else None
    
    if install_dir_arg:
        install_dir = Path(install_dir_arg).resolve()
        print(f"使用指定安装目录: {install_dir}")
    else:
        install_dir = get_application_base_path()
        print(f"未提供安装目录，默认使用程序所在目录: {install_dir}")

    try:
        if not install_dir.exists():
            print(f"安装目录 {install_dir} 不存在，尝试创建...")
            install_dir.mkdir(parents=True, exist_ok=True)
            print(f"安装目录 {install_dir} 已创建。")
        elif not install_dir.is_dir():
            print(f"错误: 指定的路径 {install_dir} 已存在但不是一个目录。")
            sys.exit(1)
    except Exception as e:
        print(f"错误: 处理安装目录 {install_dir} 失败: {e}")
        sys.exit(1)
    
    version_file = install_dir / VERSION_FILE_NAME
    
    try:
        print("正在获取最新版本信息...")
        latest_url = get_latest_url()
        latest_ver = extract_version(latest_url)
    except requests.exceptions.RequestException as e:
        print(f"获取最新版本信息失败 (网络请求错误): {e}")
        sys.exit(1)
    except ValueError as e: # From extract_version
        print(f"获取最新版本信息失败 (版本解析错误): {e}")
        sys.exit(1)
    except Exception as e: # Catch-all for other unexpected errors
        print(f"获取最新版本信息时发生未知错误: {e}")
        sys.exit(1)

    last_ver = read_last_version(version_file)
    print(f"最新版本标识: {latest_ver}，当前已记录版本标识: {last_ver or '无记录'}")

    if last_ver == latest_ver:
        print("已是最新版本，无需更新。")
        ensure_portable_mode(install_dir) # Still ensure data dir exists
        print("--- 更新检查完成 ---")
        sys.exit(0)

    wait_for_exit(PROC_NAME)

    try:
        download_extract(latest_url, install_dir)
    except requests.exceptions.RequestException as e:
        print(f"下载失败: {e}")
        sys.exit(1)
    except zipfile.BadZipFile as e:
        print(f"解压失败 (ZIP文件损坏或格式不支持): {e}")
        sys.exit(1)
    except PermissionError as e:
        print(f"更新过程中发生权限错误: {e}")
        print("提示: 如果目标目录受保护 (如 Program Files)，请尝试以管理员身份运行此工具。")
        sys.exit(1)
    except Exception as e:
        print(f"更新过程中发生未知错误: {e}")
        sys.exit(1)
        
    write_last_version(version_file, latest_ver)
    print("版本信息已更新。")

    ensure_portable_mode(install_dir)

    print(f"\nVSCode Insiders 更新成功完成。安装目录: {install_dir}")
    print("程序未自动重启。请根据需要手动启动 VSCode Insiders。")
    print("--- 更新脚本执行完毕 ---")

if __name__ == "__main__":
    try:
        main()
    except SystemExit: # Allow sys.exit() to function normally
        pass # Or `raise` if you want the exit code to propagate
    except KeyboardInterrupt:
        print("\n操作被用户中断。")
        sys.exit(130) # Standard exit code for Ctrl+C
    except Exception as e:
        print(f"脚本执行过程中发生未捕获的严重错误: {e}")
        # For PyInstaller packaged apps, this might be the last message seen if console closes.
        # Consider logging to a file for critical errors in a real product.
        sys.exit(1)
    finally:
        # If packaged and not run from an existing terminal, this can keep window open.
        # However, it can be annoying. Standard CLI tools usually exit.
        # If run by double-clicking the .exe, the window will close on exit.
        # If run from an existing cmd/powershell, the output remains.
        # No explicit input() pause added to maintain standard CLI behavior.
        pass
