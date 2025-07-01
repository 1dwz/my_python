import os
import shutil
import subprocess
import platform
import ctypes
import argparse
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_admin():
    """Check if the script is running with admin/root privileges."""
    try:
        if platform.system().lower() == "windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else: # Linux/macOS
            return os.geteuid() == 0
    except AttributeError:
        logging.warning("Could not determine admin status due to AttributeError.")
        return False
    except Exception as e:
        logging.warning(f"Error checking admin status: {e}")
        return False

def normalize_path(path_string):
    """Normalize and return an absolute path."""
    return os.path.abspath(os.path.normpath(path_string))

def create_parent_dirs(file_path):
    """Ensure parent directories for a given file_path exist."""
    parent_dir = os.path.dirname(file_path)
    if parent_dir and not os.path.exists(parent_dir):
        logging.info(f"Parent directory '{parent_dir}' does not exist. Creating it.")
        try:
            os.makedirs(parent_dir, exist_ok=True)
            logging.info(f"Successfully created parent directory '{parent_dir}'.")
        except OSError as e:
            raise OSError(f"Failed to create parent directory '{parent_dir}': {e}")
    elif parent_dir:
        logging.debug(f"Parent directory '{parent_dir}' already exists.")

def copy_directory_contents_robust(source_dir, dest_dir):
    """
    Robustly copies contents of source_dir to dest_dir.
    dest_dir will be created if it doesn't exist.
    If dest_dir exists, contents will be merged/overwritten carefully.
    遇到被占用文件（WinError 32）时跳过并记录。
    返回失败文件列表。
    """
    logging.info(f"Copying contents from '{source_dir}' to '{dest_dir}'...")
    failed_files = []
    try:
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            logging.info(f"Created destination directory '{dest_dir}'.")
        elif not os.path.isdir(dest_dir):
            raise FileExistsError(f"Destination path '{dest_dir}' exists but is not a directory.")

        for item_name in os.listdir(source_dir):
            source_item_path = os.path.join(source_dir, item_name)
            dest_item_path = os.path.join(dest_dir, item_name)

            try:
                if os.path.isdir(source_item_path):
                    if os.path.isfile(dest_item_path):
                        logging.warning(f"Destination item '{dest_item_path}' is a file, removing to copy directory.")
                        os.remove(dest_item_path)
                    shutil.copytree(source_item_path, dest_item_path, symlinks=True, dirs_exist_ok=True)
                elif os.path.isfile(source_item_path):
                    if os.path.isdir(dest_item_path):
                        logging.warning(f"Destination item '{dest_item_path}' is a directory, removing to copy file.")
                        shutil.rmtree(dest_item_path)
                    shutil.copy2(source_item_path, dest_item_path)
                elif os.path.islink(source_item_path):
                    if os.path.lexists(dest_item_path):
                        if os.path.islink(dest_item_path):
                            os.unlink(dest_item_path)
                        elif os.path.isdir(dest_item_path):
                            shutil.rmtree(dest_item_path)
                        else:
                            os.remove(dest_item_path)
                    link_target = os.readlink(source_item_path)
                    os.symlink(link_target, dest_item_path)
                    logging.info(f"Copied symlink '{source_item_path}' to '{dest_item_path}' -> '{link_target}'")
                else:
                    logging.warning(f"Skipping unsupported file type: '{source_item_path}'")
            except Exception as e:
                # 处理WinError 32
                if hasattr(e, 'winerror') and e.winerror == 32:
                    logging.error(f"File in use, skipped: '{source_item_path}' (WinError 32: {e})")
                    failed_files.append(source_item_path)
                    continue
                else:
                    logging.error(f"Failed to copy '{source_item_path}': {e}")
                    failed_files.append(source_item_path)
                    continue

        logging.info(f"Successfully copied contents to '{dest_dir}'.")
        return failed_files
    except Exception as e:
        raise Exception(f"Failed to copy directory contents: {e}")


def validate_copy_basic(source_dir, dest_dir):
    """Basic validation: compare number of items and total size."""
    logging.info(f"Performing basic validation of copy from '{source_dir}' to '{dest_dir}'...")
    try:
        source_items_count = 0
        source_total_size = 0
        for root, dirs, files in os.walk(source_dir):
            source_items_count += len(dirs) + len(files)
            for name in files:
                try:
                    source_total_size += os.path.getsize(os.path.join(root, name))
                except OSError: # Handle potential errors with symlinks or special files
                    pass


        dest_items_count = 0
        dest_total_size = 0
        for root, dirs, files in os.walk(dest_dir):
            dest_items_count += len(dirs) + len(files)
            for name in files:
                try:
                    dest_total_size += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass

        if source_items_count == dest_items_count and source_total_size == dest_total_size:
            logging.info(f"Basic validation passed: Items: {source_items_count}, Size: {source_total_size} bytes.")
            return True
        else:
            logging.warning(f"Basic validation failed: Source (Items: {source_items_count}, Size: {source_total_size}) vs Dest (Items: {dest_items_count}, Size: {dest_total_size})")
            return False
    except Exception as e:
        logging.error(f"Error during basic validation: {e}")
        return False

def remove_directory_recursive(dir_path):
    """Recursively remove a directory and its contents."""
    logging.info(f"Removing directory '{dir_path}'...")
    try:
        shutil.rmtree(dir_path)
        logging.info(f"Successfully removed directory '{dir_path}'.")
    except OSError as e:
        raise OSError(f"Failed to remove directory '{dir_path}': {e}")

def create_directory_symlink(link_name, target_path):
    """Create a directory symbolic link."""
    logging.info(f"Creating directory symbolic link: '{link_name}' -> '{target_path}'")
    system = platform.system().lower()
    try:
        if os.path.lexists(link_name): # Use lexists to check if link_name itself exists (could be a broken link)
            logging.warning(f"Path '{link_name}' already exists. Attempting to remove before creating symlink.")
            if os.path.islink(link_name):
                os.unlink(link_name)
            elif os.path.isdir(link_name): # Should not happen if original was deleted
                shutil.rmtree(link_name)
            else: # A file
                os.remove(link_name)
            logging.info(f"Removed existing path at '{link_name}'.")


        if system == "windows":
            cmd = ['cmd', '/c', 'mklink', '/D', link_name, target_path]
            logging.debug(f"Executing command: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, shell=False) # shell=False is safer
            logging.info(f"Windows mklink output: {result.stdout.strip()}")
        else: # Linux/macOS
            os.symlink(target_path, link_name, target_is_directory=True)
        logging.info(f"Successfully created symbolic link.")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to create symbolic link using mklink. Return code: {e.returncode}\nError: {e.stderr.strip()}\nOutput: {e.stdout.strip()}")
    except OSError as e:
        raise OSError(f"Failed to create symbolic link: {e}")


def migrate_and_link_directory(original_data_path, new_data_storage_path, skip_validation=False):
    """
    Migrates data from original_data_path to new_data_storage_path,
    deletes the original, and creates a symbolic link.
    If original_data_path does not exist, it attempts to create the link directly,
    assuming new_data_storage_path exists and contains the data.
    """
    logging.info(f"Starting migration and link process:")
    logging.info(f"  Original path: '{original_data_path}'")
    logging.info(f"  New storage path: '{new_data_storage_path}'")

    # --- 新增：如果原路径已是符号链接，直接提示并终止 ---
    norm_orig_path = normalize_path(original_data_path)
    norm_new_storage_path = normalize_path(new_data_storage_path)
    if os.path.islink(norm_orig_path):
        link_target = os.readlink(norm_orig_path)
        # 统一处理 Windows 下的 \?\ 前缀
        if link_target.startswith('\\\\?\\') or link_target.startswith('\\?\\'):
            link_target_clean = link_target.replace('\\\\?\\', '').replace('\\?\\', '')
        else:
            link_target_clean = link_target
        link_target_clean = os.path.abspath(link_target_clean)
        logging.info(f"原路径 '{norm_orig_path}' 已经是符号链接，指向: '{link_target}'。无需迁移。")
        # 检查目标是否一致
        if link_target_clean == norm_new_storage_path:
            logging.info("原路径已经是符号链接，且目标与预期一致，无需操作。")
            return
        else:
            logging.warning(f"原路径 '{norm_orig_path}' 已经是符号链接，但目标与预期不一致。当前指向: '{link_target}'，预期: '{norm_new_storage_path}'。将删除并重建。")
            # 继续执行，让 create_directory_symlink 处理删除和重建

    # --- 0. Preparation ---
    logging.info(f"  Normalized original path: '{norm_orig_path}'")
    logging.info(f"  Normalized new storage path: '{norm_new_storage_path}'")

    original_path_existed_as_dir = os.path.isdir(norm_orig_path)

    # --- 1. Basic Validation ---
    if norm_orig_path == norm_new_storage_path:
        raise ValueError("Error: Original data path and new data storage path cannot be the same.")

    if platform.system().lower() == "windows" and not is_admin():
        raise PermissionError("Error: Administrator privileges are required to create directory symbolic links on Windows.")
    # (Non-Windows admin check removed for brevity, can be added back if strictness is needed)

    # --- 2. Handle New Data Storage Path's Parent Directory ---
    try:
        create_parent_dirs(norm_new_storage_path)
        create_parent_dirs(norm_orig_path)
    except OSError as e:
        raise OSError(f"Error preparing parent directory for new storage path: {e}")

    # --- 3. Handle New Data Storage Path Itself ---
    if os.path.exists(norm_new_storage_path) and not os.path.isdir(norm_new_storage_path):
        raise FileExistsError(f"Error: New data storage path '{norm_new_storage_path}' exists but is not a directory.")
    # If new storage path doesn't exist, it will be created by copy_directory_contents_robust
    # or needs to exist if original_path_existed_as_dir is False.

    perform_data_copy = False
    if original_path_existed_as_dir and not os.path.exists(norm_new_storage_path):
        perform_data_copy = True
        logging.info(f"Original data directory '{norm_orig_path}' exists and new storage path '{norm_new_storage_path}' does not. Proceeding with copy and then delete.")
    elif original_path_existed_as_dir and os.path.exists(norm_new_storage_path):
        logging.info(f"Original data directory '{norm_orig_path}' exists and new storage path '{norm_new_storage_path}' already exists. Skipping data copy, proceeding with deletion of original.")
    else: # original_path_existed_as_dir is False
        logging.info(f"Original data path '{norm_orig_path}' does not exist or is not a directory. Skipping data copy and original directory deletion steps.")

    if perform_data_copy:
        # --- 4. Copy/Sync Data ---
        try:
            failed_files = copy_directory_contents_robust(norm_orig_path, norm_new_storage_path)
        except Exception as e:
            logging.error(f"Data copy failed. Original data at '{norm_orig_path}' has NOT been deleted.")
            raise

        if failed_files:
            logging.error(f"以下文件因被占用或其他原因未能复制：")
            for f in failed_files:
                logging.error(f"  {f}")
            logging.error("请关闭相关程序或手动处理这些文件后重试。原始目录未被删除，迁移中止。")
            raise Exception("部分文件复制失败，操作中止。")

        # --- 5. (Optional but recommended) Validate Copy ---
        if not skip_validation:
            if not validate_copy_basic(norm_orig_path, norm_new_storage_path):
                logging.error("Data validation failed. Contents of source and destination may differ.")
                raise Exception("Operation aborted due to data validation failure. Original data has NOT been deleted.")
            logging.info("Data copy validation successful.")
        else:
            logging.info("Skipping data copy validation as per user request.")

    # --- 6. Delete Original Data Path (only if original_path_existed_as_dir was true) ---
    if original_path_existed_as_dir:
        try:
            remove_directory_recursive(norm_orig_path)
            if os.path.exists(norm_orig_path): # Double check
                 raise OSError(f"Error: Directory '{norm_orig_path}' still exists after attempting removal.")
        except OSError as e:
            logging.error(f"Failed to delete original data directory '{norm_orig_path}'. "
                          f"Link creation will be skipped. Error: {e}")
            raise

    # Ensure new storage path exists if it wasn't created by copy_directory_contents_robust
    # This block is needed if original_path_existed_as_dir is False, or if original_path_existed_as_dir is True
    # but new_data_storage_path already existed (so no copy happened).
    if not perform_data_copy and not os.path.isdir(norm_new_storage_path):
        logging.info(f"Target directory '{norm_new_storage_path}' does not exist. Creating it...")
        try:
            os.makedirs(norm_new_storage_path, exist_ok=True)
            logging.info(f"Successfully created target directory: '{norm_new_storage_path}'")
        except OSError as e:
            raise OSError(f"Failed to create target directory '{norm_new_storage_path}': {e}")

    # 确保源目录的父目录存在
    try:
        parent_dir = os.path.dirname(norm_orig_path)
        if parent_dir and not os.path.exists(parent_dir):
            logging.info(f"Creating parent directory for symbolic link: '{parent_dir}'")
            os.makedirs(parent_dir, exist_ok=True)
    except OSError as e:
        raise OSError(f"Failed to create parent directory for symbolic link: {e}")


    # --- 7. Create Symbolic Link ---
    try:
        # Ensure target_path for symlink is absolute for mklink reliability
        abs_target_for_link = normalize_path(norm_new_storage_path)
        create_directory_symlink(norm_orig_path, abs_target_for_link) # Link name is the original path
    except Exception as e:
        log_message = (f"CRITICAL ERROR: Failed to create symbolic link '{norm_orig_path}' -> '{abs_target_for_link}'. "
                       f"Error: {e}")
        if original_path_existed_as_dir:
            log_message += (f"\nOriginal data was DELETED from '{norm_orig_path}' and COPIED to '{abs_target_for_link}', "
                            f"but the link was NOT created. MANUAL INTERVENTION REQUIRED.")
        else:
            log_message += (f"\nAttempted to create link because original path did not exist. "
                            f"MANUAL INTERVENTION REQUIRED to ensure link is correct or target exists.")
        logging.critical(log_message)
        raise

    # --- 8. Validate Symbolic Link ---
    if not os.path.lexists(norm_orig_path): # Use lexists for links
        raise FileNotFoundError(f"Validation Error: Symbolic link '{norm_orig_path}' not found after creation attempt.")
    if not os.path.islink(norm_orig_path):
        raise Exception(f"Validation Error: Path '{norm_orig_path}' exists but is not a symbolic link.")

    try:
        link_target_raw = os.readlink(norm_orig_path)
        # On Windows, os.readlink for a directory symlink might return a path like '\\??\\C:\\Target'
        # or a relative path. We need to normalize it carefully.
        # If link_target_raw is already absolute and normalized, normpath is fine.
        # If it's relative, it's relative to the link's location.
        if platform.system().lower() == "windows" and link_target_raw.startswith("\\??\\"):
            link_target_clean = link_target_raw[4:]
        else:
            link_target_clean = link_target_raw

        if not os.path.isabs(link_target_clean):
            # Resolve relative to the link's parent directory
            link_parent_dir = os.path.dirname(norm_orig_path)
            abs_link_target = normalize_path(os.path.join(link_parent_dir, link_target_clean))
        else:
            abs_link_target = normalize_path(link_target_clean)


        if abs_link_target != norm_new_storage_path:
            raise ValueError(f"Validation Error: Symbolic link '{norm_orig_path}' points to '{abs_link_target}' "
                             f"(raw: '{link_target_raw}') instead of the expected '{norm_new_storage_path}'.")
        logging.info(f"Symbolic link validation successful: '{norm_orig_path}' -> '{abs_link_target}'")
    except OSError as e:
        raise OSError(f"Validation Error: Could not read or validate symbolic link '{norm_orig_path}': {e}")


    logging.info("----------------------------------------------------")
    logging.info("Operation completed successfully!")
    if original_path_existed_as_dir:
        logging.info(f"  Data migrated from: '{original_data_path}'")
        logging.info(f"  To new storage:   '{new_data_storage_path}'")
        logging.info(f"  Original path '{original_data_path}' (formerly a directory) is now a symbolic link.")
    else:
        logging.info(f"  Symbolic link created: '{original_data_path}' -> '{new_data_storage_path}'")
        logging.info(f"  (Original path did not exist as a directory prior to this operation).")
    logging.info("----------------------------------------------------")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrates a directory to a new location, deletes the original, and creates a symbolic link. If the original directory does not exist, it attempts to create the link directly to the new location (which must exist).",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Examples:
  Windows (run as Administrator):
    python script_name.py "C:\\Users\\YourUser\\AppData\\Local\\SomeApp" "D:\\AppDataBackup\\SomeApp"
    python script_name.py "C:\\BrokenLinkLocation" "D:\\ActualDataLocation" --skip-validation (if original doesn't exist)

  Linux/macOS:
    python3 script_name.py "/home/user/my_large_data" "/mnt/external_drive/my_large_data_backup"

WARNING: This script performs destructive operations (deleting the original directory if it exists).
Ensure you have backups and understand the consequences before running.
Administrator/root privileges are typically required for creating directory symbolic links.
"""
    )
    parser.add_argument("original_path", help="The original directory path (will become the link name).")
    parser.add_argument("new_storage_path", help="The new directory path where data will be stored (will be the link target).")
    parser.add_argument("--skip-validation", action="store_true", help="Skip the basic data copy validation step (if original path exists).")
    # --force-admin-check removed for brevity, can be added back if needed.

    args = parser.parse_args()

    if platform.system().lower() == "windows" and not is_admin():
        logging.error("Error: This script requires administrator privileges on Windows to create directory symbolic links.")
        logging.info("Please re-run this script as an administrator.")
        exit(1)

    # 自动执行，无需人工确认
    try:
        migrate_and_link_directory(args.original_path, args.new_storage_path, args.skip_validation)
    except Exception as e:
        logging.error(f"An error occurred during the process: {e}")
        logging.error("Please check the logs and the state of your directories.")
        exit(1)
