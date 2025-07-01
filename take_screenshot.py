# -*- coding: utf-8 -*-
import sys
import os
import argparse
import time
import subprocess # Keep for simplified dependency check

# --- Simplified Dependency Check ---
try:
    import mss
    import mss.tools
except ImportError:
    print("Error: Required library 'mss' not found.")
    print("Please install it by running: pip install mss")
    # Optional: Attempt basic install (less robust than original)
    # try:
    #     print("Attempting to install 'mss'...")
    #     subprocess.check_call([sys.executable, "-m", "pip", "install", "mss"])
    #     import mss
    #     import mss.tools
    #     print("'mss' installed successfully.")
    # except Exception as install_err:
    #     print(f"Failed to auto-install 'mss': {install_err}")
    #     print("Please install it manually: pip install mss")
    #     sys.exit(1)
    sys.exit(1) # Exit if not found

# --- Core Screenshot Function ---
def take_screenshot(output_full_path, region=None):
    """Captures screen or region and saves to file."""
    try:
        with mss.mss() as sct:
            if region:
                # Use provided region
                capture_area = region
            else:
                # Default to primary monitor (monitor 1)
                monitor_number = 1
                if len(sct.monitors) <= monitor_number:
                    monitor_number = 0 # Fallback to all monitors combined
                capture_area = sct.monitors[monitor_number]

            sct_img = sct.grab(capture_area)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=output_full_path)
            print(f"Screenshot saved to: {output_full_path}")

    except mss.ScreenShotError as ex:
        print(f"Error during screenshot: {ex}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

# --- Main Execution Logic ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Simple screen capture tool.',
        usage='%(prog)s [X1 Y1 X2 Y2] [output_path]',
        epilog='Examples:\n'
               '  %(prog)s              # Full screen, default name in current dir\n'
               '  %(prog)s my_shot.png  # Full screen, specific file name\n'
               '  %(prog)s C:\\Captures\\ # Full screen, default name in C:\\Captures\\\n'
               '  %(prog)s 100 50 600 450 area.png # Region capture to area.png\n'
               '  %(prog)s 0 0 800 600 C:\\Dir\\ # Region capture, default name in C:\\Dir\\',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('params', nargs='*', help=argparse.SUPPRESS)
    args = parser.parse_args()
    params = args.params
    num_params = len(params)

    capture_region = None
    output_path_str = None

    # --- Argument Interpretation ---
    if num_params == 0:
        # Full screen, default name/path
        pass
    elif num_params == 1:
        # Full screen, specified output
        output_path_str = params[0]
    elif num_params == 5:
        # Region capture, specified output
        try:
            x1, y1, x2, y2 = map(int, params[:4])
            output_path_str = params[4]
            if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1:
                raise ValueError("Invalid coordinates: ensure X2>X1, Y2>Y1, and non-negative.")
            capture_region = {"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1}
        except ValueError as e:
            print(f"Error: Invalid region coordinates or format. {e}", file=sys.stderr)
            parser.print_usage()
            sys.exit(1)
    else:
        print(f"Error: Incorrect number of arguments ({num_params}). Expected 0, 1, or 5.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    # --- Determine Output Directory and Filename ---
    output_dir = "."
    output_filename = f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"

    if output_path_str:
        abs_path = os.path.abspath(output_path_str)
        # Check if the provided path IS a directory or ENDS like one
        if output_path_str.endswith(os.sep) or os.path.isdir(abs_path):
            output_dir = abs_path
            # Keep default filename
        else:
            # Assume it's a file path (even if dir doesn't exist yet)
            output_dir = os.path.dirname(abs_path)
            output_filename = os.path.basename(abs_path)
            # Handle case where only filename is given (no dir part)
            if not output_dir:
                 output_dir = "."
            # Ensure .png extension
            if not output_filename.lower().endswith('.png'):
                output_filename += '.png'

    # --- Create Output Directory if Needed ---
    if not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            print(f"Created directory: {output_dir}")
        except OSError as e:
            print(f"Error: Cannot create directory '{output_dir}'. {e}", file=sys.stderr)
            sys.exit(1)

    # --- Construct Final Path and Capture ---
    full_output_path = os.path.join(output_dir, output_filename)

    print(f"Mode: {'Region' if capture_region else 'Full Screen'}")
    if capture_region:
        print(f"Region: {capture_region}")
    print(f"Output: {full_output_path}")

    take_screenshot(full_output_path, capture_region)

    # print("\nScript finished.") # Optional final message
