#!/usr/bin/env python3
# coding: utf-8
"""
Ungoogled Chromium Portable Updater (Simplified)

1. Fetches the latest Ungoogled Chromium version for Windows 64-bit.
2. Constructs the download URL and downloads the ZIP.
3. Extracts to 'script_directory/app/'.
4. Maintains a version file: 'script_directory/app/ungoogled_chromium_version.txt'.
"""

import sys
# import time # 移除 time 库
import re
import shutil
from pathlib import Path
import zipfile
import requests # type: ignore
from bs4 import BeautifulSoup # type: ignore
from packaging.version import parse as packaging_parse, InvalidVersion as PackagingInvalidVersion # type: ignore
# Conditional import for LegacyVersion fallback
try:
    from packaging.version import LegacyVersion # type: ignore
except ImportError:
    LegacyVersion = None # type: ignore

# Import rich for beautified output
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, TimeRemainingColumn, DownloadColumn, TransferSpeedColumn # 导入rich的进度条相关组件

# Initialize rich console
console = Console()

# --- Configuration ---
BASE_RELEASE_URL = "https://ungoogled-software.github.io/ungoogled-chromium-binaries/releases/windows/64bit/"
APP_SUBDIR_NAME = "app"
VERSION_FILE_NAME = "ungoogled_chromium_version.txt"
# DOWNLOAD_URL_TEMPLATE 将不再直接使用，下载链接将从详情页获取
# DOWNLOAD_URL_TEMPLATE = "https://github.com/ungoogled-software/ungoogled-chromium-windows/releases/download/{version}/ungoogled-chromium_{version}_windows_x64.zip"
TEMP_DIR_NAME = "updater_temp" # Temporary working directory

# --- Helper Functions ---

def get_script_dir() -> Path:
    """Gets the absolute directory of the script or frozen executable."""
    return Path(sys.executable).parent.resolve() if getattr(sys, 'frozen', False) else Path(__file__).parent.resolve()

def robust_parse_version(version_string: str):
    """
    Parses version string using packaging.version.parse.
    Tries to handle cases where older packaging library might not fallback to LegacyVersion.
    If parsing fails, returns None.
    """
    try:
        # Modern packaging.version.parse (>=20.0) handles fallback to LegacyVersion automatically.
        # Attempt to parse normally first
        parsed = packaging_parse(version_string)
        # Check if the parsed version is a LegacyVersion, which might indicate issues
        # Although packaging >= 20.0 handles this better, explicit check can be useful
        # We'll rely on the InvalidVersion exception for primary failure indication
        return parsed
    except PackagingInvalidVersion as e:
        # If standard parsing fails, try LegacyVersion if available
        if LegacyVersion:
            try:
                 # console.print(f"[yellow]警告[/yellow]: 版本 \'{version_string}\' 不符合 PEP440 标准, 尝试作为 LegacyVersion 处理。", style="yellow") # 减少非必要输出
                 return LegacyVersion(version_string)
            except Exception: # Catch errors during LegacyVersion parsing too
                 # console.print(f"[yellow]警告[/yellow]: 版本 \'{version_string}\' 作为 LegacyVersion 处理失败。", style="yellow") # 减少非必要输出
                 return None # Return None if LegacyVersion parsing also fails
        else:
            # console.print(f"[yellow]警告[/yellow]: 版本 \'{version_string}\' 不符合 PEP440 标准，且 LegacyVersion 不可用。", style="yellow") # 减少非必要输出
            return None # Return None if LegacyVersion is not available
    except Exception as e:
        # console.print(f"[yellow]警告[/yellow]: 解析版本 \'{version_string}\' 时发生意外错误: {e}。无法精确解析。", style="yellow") # 减少非必要输出
        return None # Return None on other unexpected errors during parsing


def get_latest_available_version_and_download_url() -> tuple[str | None, str | None]:
    """
    Fetches the release listing, finds the latest version,
    visits the detail page, and finds the download URL.
    Returns a tuple of (latest_version_string, download_url).
    """
    console.print(f"正在获取版本列表: {BASE_RELEASE_URL}")
    versions = [] # 在这里初始化 versions 列表
    try:
        response = requests.get(BASE_RELEASE_URL, timeout=20)
        response.raise_for_status() # Raise an exception for bad status codes
    except requests.RequestException as e:
        console.print(f"[red]错误[/red]: 无法获取版本列表页面: {e}", style="red")
        return None, None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find all version links under the "Available versions" heading
    version_links = []
    # Select h2 with string "Available versions", then the next ul, then li > a
    available_versions_heading = soup.find('h2', string='Available versions')
    if available_versions_heading and available_versions_heading.find_next_sibling('ul'):
        for a_tag in available_versions_heading.find_next_sibling('ul').select('li a'):
            version_str = a_tag.string.strip() if a_tag.string else None
            relative_url = a_tag.get('href')
            
            if version_str and relative_url and re.match(r"^\d+\.\d+\.\d+\.\d+-\d+(\.\d+)?$", version_str):
                versions.append(version_str) # 将符合格式的版本字符串添加到 versions 列表
                version_links.append({
                    'version': version_str,
                    'relative_url': relative_url
                })

    if not version_links:
        console.print("[red]错误[/red]: 未在版本列表页面上找到符合格式的版本链接。", style="red")
        return None, None

    # Sort versions by robustly parsed version
    valid_versions_with_details = []
    for link_info in version_links:
        parsed = robust_parse_version(link_info['version'])
        if parsed is not None:
            valid_versions_with_details.append((parsed, link_info))
    
    if not valid_versions_with_details:
        console.print("[red]错误[/red]: 未能解析任何有效版本号，无法确定最新版本。", style="red")
        # Fallback to simple string sort on original versions if parsing failed completely
        if versions:
             console.print("[yellow]警告[/yellow]: 没有解析到有效版本，回退到简单字符串比较查找最新版本字符串。", style="yellow")
             try:
                 # Sort original version strings lexicographically
                 latest_fallback = max(versions) # Simple string max
                 console.print(f"回退检测到最新版本字符串: {latest_fallback}")
                 # With simple string sort, we only have the version string, not guaranteed detail page URL finding
                 # We will return None for download_url as we can't reliably find it without the detail page.
                 # Need to find the corresponding link_info for the fallback version to get the relative_url
                 fallback_link_info = next((item for item in version_links if item['version'] == latest_fallback), None)
                 if fallback_link_info:
                      latest_detail_relative_url = fallback_link_info['relative_url']
                      latest_detail_url = requests.compat.urljoin(BASE_RELEASE_URL, latest_detail_relative_url)
                      console.print(f"回退尝试访问详情页: {latest_detail_url}")
                      # Attempt to get download URL from fallback detail page as well
                      try:
                          detail_response = requests.get(latest_detail_url, timeout=20)
                          detail_response.raise_for_status() # Raise an exception for bad status codes
                          detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                          downloads_heading = detail_soup.find('h2', string='Downloads')
                          if downloads_heading and downloads_heading.find_next_sibling('ul'):
                               for a_tag in downloads_heading.find_next_sibling('ul').select('li a'):
                                   href = a_tag.get('href')
                                   if href and "windows_x64.zip" in href:
                                        console.print(f"回退找到下载链接: {href}", style="green")
                                        return latest_fallback, href
                          console.print("[yellow]警告[/yellow]: 回退详情页未找到下载链接。", style="yellow")
                          return latest_fallback, None
                      except requests.RequestException as e:
                          console.print(f"[red]错误[/red]: 回退无法获取版本详情页面 {latest_detail_url}: {e}", style="red")
                          return latest_fallback, None
                 else:
                      return latest_fallback, None # Should not happen if max(versions) is in version_links
             except Exception as fallback_e: # Catch errors during fallback string max or detail lookup
                 console.print(f"[red]错误[/red]: 回退字符串比较或详情查找失败: {fallback_e}", style="red")
                 return None, None
        else:
            return None, None # No versions found at all

    # Sort by the parsed version object (index 0 of the tuple), descending
    try:
        valid_versions_with_details.sort(key=lambda item: item[0], reverse=True)

        # The latest version details are in the first element after sorting
        latest_version_details = valid_versions_with_details[0][1]
        latest_version_online = latest_version_details['version']
        latest_detail_relative_url = latest_version_details['relative_url']
        latest_detail_url = requests.compat.urljoin(BASE_RELEASE_URL, latest_detail_relative_url)

        console.print(f"检测到最新版本: [bold green]{latest_version_online}[/bold green]")
        console.print(f"正在访问详情页: {latest_detail_url}")

        # 2. Visit the detail page for the latest version
        try:
            detail_response = requests.get(latest_detail_url, timeout=20)
            detail_response.raise_for_status() # Raise an exception for bad status codes
        except requests.RequestException as e:
            console.print(f"[red]错误[/red]: 无法获取版本详情页面 {latest_detail_url}: {e}", style="red")
            return latest_version_online, None # Return version but not download URL

        detail_soup = BeautifulSoup(detail_response.text, 'html.parser')

        # Find the download link for the Windows 64-bit ZIP file
        download_url = None
        # Select h2 with string "Downloads", then the next ul, then li > a containing "windows_x64.zip"
        downloads_heading = detail_soup.find('h2', string='Downloads')
        if downloads_heading and downloads_heading.find_next_sibling('ul'):
            for a_tag in downloads_heading.find_next_sibling('ul').select('li a'):
                link_text = a_tag.string.strip() if a_tag.string else ''
                href = a_tag.get('href')
                # Look for a link whose text or href contains "windows_x64.zip"
                if href and "windows_x64.zip" in href:
                     download_url = href
                     break # Found the desired link
                # Fallback check on link text if href is relative (less likely for github releases)
                if link_text and "windows_x64.zip" in link_text:
                     download_url = href
                     # Need to handle relative URLs if they occur here, but github releases are usually full URLs
                     # download_url = requests.compat.urljoin(latest_detail_url, href) # This line would be needed for relative hrefs
                     break # Found the desired link

        if not download_url:
            console.print("[red]错误[/red]: 未在详情页上找到 Ungoogled Chromium Windows x64 ZIP 的下载链接。", style="red")
            return latest_version_online, None
        
        console.print(f"找到下载链接: [blue]{download_url}[/blue]", style="blue")
        return latest_version_online, download_url

    except Exception as e:
        console.print(f"[red]错误[/red]: 处理版本或详情页失败: {e}", style="red")
        # If sorting or processing valid versions fails unexpectedly,
        # as a last resort, try simple string max on the original list versions strings to return at least the version string.
        if versions:
             console.print("[yellow]警告[/yellow]: 最终处理失败，尝试回退到简单字符串比较查找最新版本字符串。", style="yellow")
             try:
                 latest_fallback = max(versions) # Simple string max
                 console.print(f"回退检测到最新版本字符串: {latest_fallback}")
                 # Need to find the corresponding link_info for the fallback version to get the relative_url
                 fallback_link_info = next((item for item in version_links if item['version'] == latest_fallback), None)
                 if fallback_link_info:
                      latest_detail_relative_url = fallback_link_info['relative_url']
                      latest_detail_url = requests.compat.urljoin(BASE_RELEASE_URL, latest_detail_relative_url)
                      console.print(f"回退尝试访问详情页: {latest_detail_url}")
                      # Attempt to get download URL from fallback detail page as well
                      try:
                          detail_response = requests.get(latest_detail_url, timeout=20)
                          detail_response.raise_for_status() # Raise an exception for bad status codes
                          detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                          downloads_heading = detail_soup.find('h2', string='Downloads')
                          if downloads_heading and downloads_heading.find_next_sibling('ul'):
                               for a_tag in downloads_heading.find_next_sibling('ul').select('li a'):
                                   href = a_tag.get('href')
                                   if href and "windows_x64.zip" in href:
                                        console.print(f"回退找到下载链接: {href}", style="green")
                                        return latest_fallback, href
                          console.print("[yellow]警告[/yellow]: 回退详情页未找到下载链接。", style="yellow")
                          return latest_fallback, None
                      except requests.RequestException as e:
                          console.print(f"[red]错误[/red]: 回退无法获取版本详情页面 {latest_detail_url}: {e}", style="red")
                          return latest_fallback, None
                 else:
                      return latest_fallback, None # Should not happen if max(versions) is in version_links
             except Exception as fallback_e: # Catch errors during fallback string max or detail lookup
                 console.print(f"[red]错误[/red]: 回退字符串比较或详情查找失败: {fallback_e}", style="red")
                 return None, None
        else:
            return None, None # No versions found at all


def read_local_version(version_file: Path) -> str | None:
    """Reads the currently installed version from the local version file."""
    if version_file.is_file():
        try:
            return version_file.read_text(encoding='utf-8').strip()
        except IOError as e:
            console.print(f"[yellow]警告[/yellow]: 无法读取版本文件 {version_file}: {e}", style="yellow")
    return None

def write_local_version(version_file: Path, version: str):
    """Writes the given version string to the local version file."""
    try:
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(version, encoding='utf-8')
    except IOError as e:
        console.print(f"[yellow]警告[/yellow]: 无法写入版本文件 {version_file}: {e}", style="yellow")

def download_and_extract(url: str, target_app_path: Path, temp_base_dir: Path) -> bool:
    """Downloads a ZIP from URL and extracts its contents to target_app_path."""
    temp_zip_file = temp_base_dir / "chromium_download.zip.tmp" # 简化临时文件名
    temp_extract_subdir = temp_base_dir / "chromium_extract_temp" # 简化临时目录名

    try:
        # 1. Download
        console.print(f"正在下载: [blue]{url}[/blue]", style="blue")
        with requests.get(url, stream=True, timeout=(15, 300)) as r: # connect_timeout, read_timeout
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            # Use rich progress bar for download
            with Progress(
                TextColumn("[bold blue]{task.description}", justify="right"),
                BarColumn(),
                TaskProgressColumn(),
                "", # Separator
                DownloadColumn(),
                "", # Separator
                TransferSpeedColumn(),
                " ", # Separator
                TimeRemainingColumn(),
                " ", # Separator
                TimeElapsedColumn(),
                console=console # Use the initialized console
            ) as progress:
                download_task = progress.add_task("[cyan]下载进度[/cyan]", total=total_size)
                
                downloaded_size = 0
                with open(temp_zip_file, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192 * 4): # 32KB chunks
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        progress.update(download_task, advance=len(chunk))

            console.print("[green]下载完成。[/green]")

        # 2. Extract
        console.print(f"正在解压到临时目录: [blue]{temp_extract_subdir}[/blue]", style="blue")
        temp_extract_subdir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(temp_zip_file, 'r') as zf:
            # Optional: Add progress for extraction if needed, but usually very fast for this size
            zf.extractall(temp_extract_subdir)
        
        # Determine actual content root (e.g., if zip contains a single top-level folder)
        extracted_items = list(temp_extract_subdir.iterdir())
        content_root = temp_extract_subdir
        if len(extracted_items) == 1 and extracted_items[0].is_dir():
            content_root = extracted_items[0]
            console.print(f"内容位于解压后的子目录: [blue]{content_root.name}[/blue]", style="blue")

        # 3. Replace old installation
        if target_app_path.exists():
            console.print(f"正在删除旧的安装: [blue]{target_app_path}[/blue]", style="blue")
            shutil.rmtree(target_app_path)
        # target_app_path will be created by shutil.move if content_root is moved,
        # or ensure it exists if items are moved into it.
        target_app_path.mkdir(parents=True, exist_ok=True)

        console.print(f"正在移动文件从 [blue]{content_root}[/blue] 到: [blue]{target_app_path}[/blue]", style="blue")
        for item in content_root.iterdir():
            shutil.move(str(item), str(target_app_path / item.name))
        
        console.print("[green]更新成功。[/green]")
        return True

    except requests.RequestException as e:
        console.print(f"[red]错误[/red]: 下载失败: {e}", style="red")
    except zipfile.BadZipFile:
        console.print(f"[red]错误[/red]: ZIP文件损坏或格式无效。", style="red")
    except PermissionError as e:
        console.print(f"[red]错误[/red]: 权限不足。无法写入 {target_app_path} 或删除旧文件。 {e}", style="red")
        console.print("[yellow]提示[/yellow]: 如果目标目录受保护或文件被占用, 请关闭 Chromium 并尝试以管理员身份运行。", style="yellow")
    except Exception as e:
        console.print(f"[red]错误[/red]: 更新过程中发生意外错误: {e}", style="red")
        import traceback
        traceback.print_exc(file=sys.stdout) # Print traceback to console
    finally:
        # Clean up specific temporary files and directories used by this function
        if temp_zip_file.exists(): temp_zip_file.unlink(missing_ok=True)
        if temp_extract_subdir.exists(): shutil.rmtree(temp_extract_subdir, ignore_errors=True)
    return False

# --- Main Logic ---
def main():
    console.print("[bold]--- Ungoogled Chromium 简易更新器 ---[/bold]")
    
    script_dir = get_script_dir()
    app_dir = script_dir / APP_SUBDIR_NAME
    version_file = app_dir / VERSION_FILE_NAME
    # Central temporary directory for all operations of this script run
    temp_base_dir = script_dir / TEMP_DIR_NAME 

    # Ensure temp_base_dir is clean for this run
    if temp_base_dir.exists():
        shutil.rmtree(temp_base_dir)
    temp_base_dir.mkdir(parents=True, exist_ok=True)

    try:
        latest_version_online, download_url = get_latest_available_version_and_download_url()
        
        if not latest_version_online or not download_url:
            console.print("[red]错误[/red]: 未能获取到最新版本信息或下载链接。", style="red")
            sys.exit(1)

        current_local_version = read_local_version(version_file)
        console.print(f"当前已安装版本: [bold]{current_local_version or '未安装或未知'}[/bold]")

        if current_local_version:
            try:
                # Use robust_parse_version for comparison
                # Compare parsed versions if possible
                parsed_latest = robust_parse_version(latest_version_online)
                parsed_current = robust_parse_version(current_local_version)
                
                # Check if both parsed versions are comparable (not None or simple strings due to errors)
                # The get_latest_available_version_and_download_url should return a parseable version if it succeeds
                # but we keep this check for robustness.
                if parsed_latest is not None and parsed_current is not None:
                    if parsed_latest <= parsed_current:
                        console.print("[green]已是最新版本，无需更新。[/green]")
                        sys.exit(0)
                else:
                    # Fallback to string comparison if parsing failed for current or latest
                    console.print("[yellow]警告[/yellow]: 版本解析不完整，回退到字符串比较进行是否更新的判断。", style="yellow")
                    if latest_version_online <= current_local_version:
                        console.print("[green]已是最新版本（按字符串比较）。[/green]")
                        sys.exit(0)

            except Exception as e: # Catch errors from robust_parse_version or comparison
                console.print(f"[yellow]警告[/yellow]: 版本比较失败 ({e})。将继续尝试更新。", style="yellow")
        
        console.print(f"准备更新到版本: [bold green]{latest_version_online}[/bold green]")
        
        # Simple warning if chrome.exe exists, as psutil is removed for simplicity
        chrome_exe_path = app_dir / "chrome.exe"
        if chrome_exe_path.exists():
             console.print(f"\n[yellow]警告[/yellow]: [blue]{chrome_exe_path}[/blue] 已存在。", style="yellow")
             console.print("如果 Chromium 正在运行，更新可能会失败。请在继续前手动关闭所有 Chromium 实例。", style="yellow")
             try:
                 input("按 Enter键 继续更新，或按 Ctrl+C 中断...")
             except EOFError: # Handle non-interactive environments
                 console.print("在非交互模式下运行，将继续更新...")


        # Use the obtained download_url
        if download_and_extract(download_url, app_dir, temp_base_dir):
            write_local_version(version_file, latest_version_online)
            console.print(f"[green]Ungoogled Chromium 已成功更新到版本 [bold]{latest_version_online}[/bold][/green]")
            console.print(f"安装目录: [blue]{app_dir}[/blue]")
        else:
            console.print("[red]更新失败。请查看上面的错误信息。[/red]", style="red")
            sys.exit(1)

    finally:
        # Final cleanup of the central temporary directory
        if temp_base_dir.exists():
            shutil.rmtree(temp_base_dir, ignore_errors=True)
            console.print(f"临时工作目录 [blue]{temp_base_dir}[/blue] 已清理。")

    console.print("[bold]--- 更新脚本执行完毕 ---[/bold]")

if __name__ == "__main__":
    # Basic check for essential modules
    missing_modules = []
    try: import requests
    except ImportError: missing_modules.append("requests")
    try: import bs4 # BeautifulSoup is part of bs4
    except ImportError: missing_modules.append("beautifulsoup4")
    try: import packaging # For packaging.version
    except ImportError: missing_modules.append("packaging")
    try: import rich # For beautified output
    except ImportError: missing_modules.append("rich") # Add rich to dependency check

    if missing_modules:
        console.print(f"[red]错误[/red]: 缺少必要的模块: [bold]{', '.join(missing_modules)}[/bold].", style="red")
        console.print(f"如果从源码运行, 请运行: [bold]pip install {' '.join(missing_modules)}[/bold]")
        sys.exit(1)
        
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]操作被用户中断。[/yellow]", style="yellow")
        sys.exit(130) # Standard exit code for Ctrl+C
    except SystemExit:
        pass # Allow sys.exit() to terminate script cleanly
    except Exception as e:
        console.print(f"[red]脚本执行过程中发生未捕获的严重错误[/red]: {e}", style="red")
        import traceback
        traceback.print_exc(file=sys.stdout) # Print traceback to console
        sys.exit(1)
