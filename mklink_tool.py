import os
import shutil
import subprocess
import platform
import ctypes
import argparse
import logging

# Setup basic logging for silent background operation
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
        try:
            os.makedirs(parent_dir, exist_ok=True)
            logging.info(f"Successfully created parent directory '{parent_dir}'.")
        except OSError as e:
            raise OSError(f"Failed to create parent directory '{parent_dir}': {e}")

def remove_path(path):
    """Safely remove a path, whether it's a file, directory, or link."""
    try:
        if os.path.islink(path):
            os.unlink(path)
            logging.info(f"Removed existing symbolic link at '{path}'.")
        elif os.path.isdir(path):
            shutil.rmtree(path)
            logging.info(f"Removed existing directory at '{path}'.")
        elif os.path.isfile(path):
            os.remove(path)
            logging.info(f"Removed existing file at '{path}'.")
    except OSError as e:
        raise OSError(f"Failed to remove existing item at '{path}': {e}")

def create_directory_symlink(link_name, target_path):
    """Create a directory symbolic link, ensuring target is an absolute path."""
    logging.info(f"Creating directory symbolic link: '{link_name}' -> '{target_path}'")
    system = platform.system().lower()
    
    # Ensure link_name path is clear before creating
    if os.path.lexists(link_name):
        logging.warning(f"Path '{link_name}' already exists. It will be removed before creating the new link.")
        remove_path(link_name)

    # Ensure parent directory for the link exists
    create_parent_dirs(link_name)

    try:
        if system == "windows":
            # On Windows, mklink requires an absolute path for reliability.
            cmd = ['cmd', '/c', 'mklink', '/D', link_name, target_path]
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, shell=False)
            logging.debug(f"Windows mklink output: {result.stdout.strip()}")
        else: # Linux/macOS
            os.symlink(target_path, link_name, target_is_directory=True)
        
        logging.info(f"Successfully created symbolic link.")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to create symbolic link using mklink. Return code: {e.returncode}\nError: {e.stderr.strip()}")
    except OSError as e:
        raise OSError(f"Failed to create symbolic link: {e}")

def align_paths_as_link_and_target(link_path_str, data_path_str):
    """
    Ensures that link_path is a symbolic link pointing to data_path.
    The data at data_path has the highest priority.

    Logic:
    1.  If data_path exists as a directory, it's the source of truth. Any conflicting
        item at link_path will be removed.
    2.  If data_path does not exist, the script checks if link_path is a directory.
        If so, it's moved to become the new data_path.
    3.  Finally, a symbolic link is created from link_path to data_path.
    """
    link_path = normalize_path(link_path_str)
    data_path = normalize_path(data_path_str)

    logging.info("--- Starting Alignment Process ---")
    logging.info(f"Desired Link Path: '{link_path}'")
    logging.info(f"Desired Data Path: '{data_path}' (Data here has priority)")
    
    # --- 0. Pre-flight Checks ---
    if link_path == data_path:
        raise ValueError("Link path and data path cannot be the same.")
    if platform.system().lower() == "windows" and not is_admin():
        raise PermissionError("Administrator privileges are required on Windows.")

    # --- 1. Check if the system is already in the desired state ---
    if os.path.islink(link_path):
        try:
            target = os.readlink(link_path)
            # Resolve relative links for accurate comparison
            abs_target = normalize_path(os.path.join(os.path.dirname(link_path), target))
            if abs_target == data_path:
                logging.info("System is already in the desired state. No action needed.")
                logging.info("--- Alignment Process Finished Successfully ---")
                return
        except OSError as e:
            logging.warning(f"Could not read existing link at '{link_path}', will proceed to fix it. Error: {e}")

    # --- 2. Establish the authoritative data_path ---
    # The data at data_path has priority.
    if os.path.isdir(data_path):
        logging.info(f"Authoritative data directory found at '{data_path}'. It will be used as the target.")
    elif os.path.exists(data_path):
        # Path exists but is not a directory (e.g., a file), which is a critical conflict.
        raise FileExistsError(f"Data path '{data_path}' exists but is not a directory. Manual intervention required.")
    else:
        # Data path does not exist. We need to find or create the data.
        create_parent_dirs(data_path)
        if os.path.isdir(link_path):
            logging.info(f"Data path '{data_path}' does not exist. Moving data from '{link_path}'.")
            try:
                shutil.move(link_path, data_path)
                logging.info(f"Successfully moved '{link_path}' to '{data_path}'.")
            except Exception as e:
                raise Exception(f"Failed to move data from '{link_path}' to '{data_path}': {e}")
        else:
            logging.info(f"Data path '{data_path}' does not exist and no source data found at '{link_path}'. Creating empty data directory.")
            os.makedirs(data_path)

    # --- 3. Create the symbolic link ---
    # At this point, data_path is guaranteed to be a directory.
    # The create_directory_symlink function will handle removing any conflicting
    # file, directory, or old link at link_path.
    try:
        create_directory_symlink(link_path, data_path)
    except Exception as e:
        log_message = (f"CRITICAL ERROR: Failed to create symbolic link '{link_path}' -> '{data_path}'.\n"
                       f"Error: {e}\n"
                       f"The data should be safe at '{data_path}', but the link is missing. "
                       "MANUAL INTERVENTION REQUIRED to create the link.")
        logging.critical(log_message)
        raise

    # --- 4. Final Validation ---
    if not os.path.islink(link_path):
        raise Exception(f"Validation Failed: Path '{link_path}' was not created as a symbolic link.")
    
    logging.info("--- Alignment Process Finished Successfully ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ensures a specific path is a symbolic link to a data directory. The data in the target directory (data_path) always has the highest priority.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
This script operates based on a simple, powerful rule: the data at 'data_path' is the source of truth.

Scenarios:
1. If 'data_path' exists:
   Any existing item at 'link_path' (dir, file, or old link) will be REMOVED.
   A new symbolic link will be created from 'link_path' to 'data_path'.

2. If 'data_path' does NOT exist:
   a) If 'link_path' is a directory, it will be MOVED to become the new 'data_path'.
   b) Otherwise, an empty directory will be created at 'data_path'.
   Then, the symbolic link will be created.

Examples (run as Administrator on Windows):
  # Move Docker data from C: to D: (assuming D:\\DockerData doesn't exist yet)
  python mklink_tool.py "C:\\ProgramData\\Docker" "D:\\DockerData"

  # Correct a link for an app, trusting the data on D: is correct
  python mklink_tool.py "C:\\Users\\User\\AppData\\SomeApp" "D:\\Backups\\SomeApp"

WARNING: This script can perform destructive operations (removing the item at 'link_path').
It is designed for automated, non-interactive execution.
"""
    )
    parser.add_argument("link_path", help="The path that should become the symbolic link.")
    parser.add_argument("data_path", help="The path where the actual data is or will be stored. This data has priority.")
    
    args = parser.parse_args()

    try:
        align_paths_as_link_and_target(args.link_path, args.data_path)
    except Exception as e:
        logging.error(f"An unrecoverable error occurred during the process: {e}")
        logging.error("Please check the logs and the state of your directories.")
        exit(1)
