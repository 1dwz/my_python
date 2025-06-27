import winreg
import os
import shutil
import sys

def delete_registry_key_recursive(root_key, subkey_path):
    """
    递归删除注册表项及其所有子项和值。
    root_key: HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE 等。
    subkey_path: 要删除的子项的路径。
    """
    hkey = None # 初始化为 None，以便在 finally 块中安全关闭

    try:
        # 步骤 1: 以完全访问权限打开注册表项
        hkey = winreg.OpenKey(root_key, subkey_path, 0, winreg.KEY_ALL_ACCESS)
        
        # 步骤 2: 枚举并存储所有子项的名称
        subkeys_to_delete = []
        index = 0
        while True:
            try:
                name = winreg.EnumKey(hkey, index)
                subkeys_to_delete.append(name)
                index += 1
            except OSError as e:
                if e.winerror == 259: # ERROR_NO_MORE_ITEMS
                    break
                else:
                    raise
        
        # 步骤 3: 关闭当前注册表项的句柄。
        winreg.CloseKey(hkey)
        hkey = None # 标记句柄已关闭

        # 步骤 4: 递归删除所有找到的子项
        for name in subkeys_to_delete:
            full_child_path = os.path.join(subkey_path, name)
            print(f"  尝试删除子项: {full_child_path}")
            delete_registry_key_recursive(root_key, full_child_path)

        # 步骤 5: 现在，删除当前注册表项本身。
        winreg.DeleteKey(root_key, subkey_path)
        print(f"成功删除注册表项: {subkey_path}")
        return True

    except FileNotFoundError:
        print(f"注册表项未找到 (可能已删除或从未存在): {subkey_path}")
        return False
    except PermissionError:
        print(f"权限不足，无法删除注册表项: {subkey_path}。请以管理员身份运行脚本。")
        return False
    except Exception as e:
        print(f"删除注册表项 {subkey_path} 时出错: {e}")
        return False
    finally:
        if hkey:
            winreg.CloseKey(hkey)

def delete_file_or_directory(path):
    """删除文件或目录。"""
    if not os.path.exists(path):
        print(f"路径未找到 (可能已删除或从未存在): {path}")
        return False

    try:
        if os.path.isfile(path):
            os.remove(path)
            print(f"成功删除文件: {path}")
        elif os.path.isdir(path):
            shutil.rmtree(path)
            print(f"成功删除目录: {path}")
        return True
    except PermissionError:
        print(f"权限不足，无法删除 {path}。请以管理员身份运行脚本。")
        return False
    except OSError as e:
        print(f"删除 {path} 时出错: {e}")
        return False

def main():
    print("--- RoboTask 试用重置脚本 (最终稳定版本) ---")
    print("警告: 此脚本将直接执行删除操作，无任何用户确认。")
    print("它尝试删除 RoboTask 软件的 COM 组件注册和部分文件。")
    print("它**不会**重置 'HKEY_CURRENT_USER\\SOFTWARE\\TaskAutomation' 下的主配置和用户变量。")
    print("此修改可能**显著降低**试用重置的成功率，因为软件可能在此处存储试用标识。")
    print("它会保留您的任务脚本。此操作不可逆。")
    print("运行此脚本前请确保 RoboTask.exe 已完全关闭。")
    print("-" * 40)

    # --- 注册表：HKCU 相关 COM 注册表项 ---
    # 这些是软件组件注册，通常不包含用户数据，且删除有助于清除安装痕迹。
    hkcu_com_keys_to_delete = [
        r"Software\Classes\CLSID\{BDF32BB5-1D51-4406-831A-C24C353C8EE9}",
        r"Software\Classes\CLSID\{8BA8CFA9-1A98-45F5-A183-BC4DC24698A8}",
        r"Software\Classes\Interface\{5B259C24-EFC3-4D10-B936-913F7E1D8E5D}",
        r"Software\Classes\TypeLib\{F3AD378E-949E-450F-9EBC-55143CAE8097}",
        r"Software\Classes\RoboTask.App",
        r"Software\Classes\WOW6432Node\Interface\{5B259C24-EFC3-4D10-B936-913F7E1D8E5D}",
        r"Software\Microsoft\Windows\CurrentVersion\Run\RoboTask", # 移除开机启动项
    ]

    # --- 文件系统路径 ---
    user_appdata_local = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    user_public_documents = os.path.join(os.path.abspath(os.path.join(os.path.expanduser('~'), os.pardir)), 'Public', 'Documents')
    
    files_and_dirs_to_delete = [
        os.path.join(user_appdata_local, r"RoboTask", r"Logs"), # 只删除 Logs 目录
        r"C:\ProgramData\{108738E9-15F6-4531-BB80-8D0EB391C151}", # ProgramData 下的 GUID 文件夹
        os.path.join(user_public_documents, r"RoboTask", r"ADB4C104-82B7-4682-8D54-464CDF27E560.dat"), # Public Documents 中的特定 .dat 文件
    ]

    # 执行注册表删除
    print("\n--- 正在删除注册表项 ---")
    for item in hkcu_com_keys_to_delete:
        print(f"  删除项: {item}")
        delete_registry_key_recursive(winreg.HKEY_CURRENT_USER, item)

    # 执行文件/目录删除
    print("\n--- 正在删除文件和目录 ---")
    print(f"注意: 目录 '{os.path.join(user_appdata_local, r'RoboTask', r'Tasks')}' 将被保留。")
    for item in files_and_dirs_to_delete:
        print(f"  删除路径: {item}")
        delete_file_or_directory(item)

    print("\n--- 重置过程完成 ---")
    print("由于未重置 RoboTask 的主配置，试用重置可能不成功。")
    print("您的任务脚本（在 AppData\\Local\\RoboTask\\Tasks 中）应该已保留。")
    print("建议重新启动系统以使所有更改完全生效。")

if __name__ == "__main__":
    main()
