"""
RepoMixer Component

This module provides a utility to traverse a repository, filter files according to rules,
and synthesize them into a single text file for AI context. It includes robust
file handling, .gitignore compatibility, and defensive programming practices.
"""
# Dependencies: gitignore-parser

import argparse
import logging
import sys
from pathlib import Path
from typing import Final, Dict, Callable, Iterator

# Third-party dependency: gitignore-parser
# Justification: Criterion C - Provides robust parsing of complex .gitignore rules,
# which is non-trivial to implement correctly.
# Installation: pip install gitignore-parser
try:
    # --- FIX START ---
    # Import the internal function to handle file streams directly
    from gitignore_parser import _parse_gitignore_lines
    # --- FIX END ---
except ImportError:
    print("Error: 'gitignore-parser' is not installed. Please run 'pip install gitignore-parser'", file=sys.stderr)
    sys.exit(1)

# --- System Constants ---
LOG_FORMAT: Final[str] = "[%(levelname)s] %(message)s"
DEFAULT_OUTPUT_FILENAME: Final[str] = "repomix.txt"
DEFAULT_IGNORE_PATTERNS: Final[tuple[str, ...]] = (".git/",)
BINARY_CHECK_BYTES: Final[int] = 1024

EXTENSION_TO_LANG: Final[Dict[str, str]] = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".cs": "csharp", ".go": "go", ".rs": "rust",
    ".rb": "ruby", ".php": "php", ".kt": "kotlin", ".swift": "swift", ".html": "html",
    ".css": "css", ".scss": "scss", ".json": "json", ".xml": "xml", ".yaml": "yaml",
    ".yml": "yaml", ".md": "markdown", ".sh": "shell", ".bash": "bash",
    "dockerfile": "dockerfile", ".sql": "sql", ".r": "r", ".pl": "perl",
}

# --- Core Component ---

class RepoMixer:
    """
    A component to traverse a repository, filter files according to rules,
    and synthesize them into a single text file for AI context.
    """
    def __init__(self, root_dir: Path, output_file: Path):
        """
        Initializes the RepoMixer with specified paths.

        :param root_dir: The absolute path to the repository's root directory.
        :type root_dir: Path
        :param output_file: The absolute path to the target output file.
        :type output_file: Path
        :raises TypeError: If root_dir or output_file are not Path objects.
        """
        if not isinstance(root_dir, Path) or not isinstance(output_file, Path):
            raise TypeError("root_dir and output_file must be Path objects.")
        self.root_dir = root_dir
        self.output_file = output_file
        self.script_file = Path(__file__).resolve()
        self.ignore_matcher = self._load_ignore_rules()
        self.file_count = 0

    # --- FIX START: This entire method is replaced ---
    def _load_ignore_rules(self) -> Callable[[Path], bool]:
        """
        Loads .gitignore rules and returns a matching function.
        This version manually opens the .gitignore file with UTF-8 encoding
        to prevent UnicodeDecodeError on systems with different default encodings.
        """
        gitignore_path = self.root_dir / ".gitignore"
        if gitignore_path.is_file():
            try:
                logging.info(f"Applying .gitignore rules from: {gitignore_path}")
                # Manually open the file with UTF-8 encoding
                with gitignore_path.open("r", encoding="utf-8", errors="ignore") as f:
                    # Pass the file handle to the internal parser function
                    return _parse_gitignore_lines(f, gitignore_path, base_dir=self.root_dir)
            except (IOError, UnicodeDecodeError) as e:
                logging.error(f"Failed to read or parse .gitignore file at {gitignore_path}: {e}. "
                              "Proceeding without .gitignore rules.")
                return lambda p: False
        logging.warning("No .gitignore file found. Using default ignore rules only.")
        return lambda p: False
    # --- FIX END ---

    @staticmethod
    def _is_binary(filepath: Path) -> bool:
        """
        Checks if a file is likely binary by searching for null bytes within its
        initial segment. Returns False if the file is unreadable.

        :param filepath: The path to the file to check.
        :type filepath: Path
        :return: True if the file is likely binary, False otherwise.
        :rtype: bool
        """
        try:
            with filepath.open("rb") as f:
                return b'\0' in f.read(BINARY_CHECK_BYTES)
        except IOError:
            logging.warning(f"Could not read file to check for binary content: {filepath}")
            return False

    @staticmethod
    def _get_lang(filename: Path) -> str:
        """
        Determines the Markdown language identifier from a filename's extension.

        :param filename: The path to the file.
        :type filename: Path
        :return: The language identifier string (e.g., "python", "javascript"), or an empty string if unknown.
        :rtype: str
        """
        name = filename.name.lower()
        if "dockerfile" in name:
            return "dockerfile"
        return EXTENSION_TO_LANG.get(filename.suffix.lower(), "")

    def _walk_repo(self) -> Iterator[Path]:
        """
        Walks the repository, yielding eligible files while respecting ignore
        rules to prune directory traversal efficiently. This is a non-recursive
        implementation to prevent stack depth issues.

        :yield: Path objects for eligible files.
        :rtype: Iterator[Path]
        :raises OSError: If a directory cannot be accessed during traversal.
        """
        dirs_to_visit = [self.root_dir]

        while dirs_to_visit:
            current_dir = dirs_to_visit.pop()
            try:
                for item_path in current_dir.iterdir():
                    # --- Primary Exclusion Checks (applies to both files and dirs) ---
                    if item_path == self.output_file or item_path == self.script_file:
                        continue

                    # Convert to POSIX path for consistent matching against ignore patterns
                    relative_path_str = str(item_path.relative_to(self.root_dir)).replace('\\', '/')
                    if relative_path_str.startswith(DEFAULT_IGNORE_PATTERNS):
                        continue

                    if self.ignore_matcher(item_path):
                        continue

                    # --- Item Processing ---
                    if item_path.is_dir():
                        dirs_to_visit.append(item_path)
                    elif item_path.is_file():
                        yield item_path

            except OSError as e:
                logging.warning(f"Cannot access directory {current_dir}: {e}")

    def run(self) -> None:
        """
        Executes the main logic to generate the repository mix file.

        This method traverses the repository, filters files, reads their content
        with robust encoding handling, and writes them to the specified output file.

        :raises IOError: If the output file cannot be written to.
        """
        logging.info("Starting repository processing...")
        logging.info(f"Project Root (Base for all paths): {self.root_dir}")

        try:
            # Use errors="ignore" for the output file in case of any unexpected encoding issues
            with self.output_file.open("w", encoding="utf-8", errors="ignore") as f_out:
                f_out.write(f"# Repository Mix Context\n")
                f_out.write(f"# Root Directory (Absolute Path): {self.root_dir}\n")
                f_out.write("# All subsequent file paths are relative to this root.\n\n")

                for file_path in self._walk_repo():
                    relative_path = file_path.relative_to(self.root_dir).as_posix()
                    logging.debug(f"Processing: {relative_path}")

                    try:
                        f_out.write(f"--- {relative_path} ---\n")
                        if self._is_binary(file_path):
                            f_out.write("[Binary file, content not included]\n\n")
                        else:
                            lang = self._get_lang(file_path)
                            f_out.write(f"```{lang}\n")
                            # Use errors="ignore" for robust reading of source files
                            content = file_path.read_text(encoding="utf-8", errors="ignore")
                            f_out.write(content.strip() + "\n")
                            f_out.write("```\n\n")
                        self.file_count += 1
                    except (IOError, UnicodeDecodeError) as e:
                        logging.error(f"Failed to process file {relative_path}: {e}")
                        f_out.write(f"[Error reading file: {e}]\n\n")

            logging.info(f"Successfully processed {self.file_count} files.")
            print(f"\n[SUCCESS] Repository mix created: {self.output_file}")

        except IOError as e:
            logging.critical(f"Failed to write to output file {self.output_file}: {e}")
            sys.exit(1)

# --- Execution Entrypoint ---

def main() -> None:
    """
    Parses command-line arguments and initiates the RepoMixer.

    This function sets up logging, validates input paths, and handles
    the overall execution flow of the RepoMixer.
    """
    parser = argparse.ArgumentParser(
        description="Synthesizes a code repository into a single text file for AI context, respecting .gitignore.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "root_dir", nargs="?", default=".",
        help="Path to the repository root directory (default: current directory)."
    )
    parser.add_argument(
        "-o", "--output", default=DEFAULT_OUTPUT_FILENAME,
        help=f"Name of the output text file (default: {DEFAULT_OUTPUT_FILENAME})."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose logging for debugging."
    )
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format=LOG_FORMAT, stream=sys.stderr)

    try:
        root_path = Path(args.root_dir).resolve(strict=True)
    except FileNotFoundError:
        logging.critical(f"The specified root directory does not exist: {args.root_dir}")
        sys.exit(1)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = root_path / output_path
    # No need to resolve() output_path again, as root_path is already absolute.

    mixer = RepoMixer(root_dir=root_path, output_file=output_path)
    mixer.run()

if __name__ == "__main__":
    main()
