"""
File Scanner - Discovers and categorizes files in a repository
"""
import os
from pathlib import Path
from typing import List, Dict, Set
import hashlib
import logging

logger = logging.getLogger(__name__)


class FileScanner:
    """Scans repository directories and categorizes files"""
    
    # Supported languages and their extensions
    LANGUAGE_EXTENSIONS = {
        "python": {".py", ".pyw"},
        "javascript": {".js", ".jsx", ".mjs"},
        "typescript": {".ts", ".tsx"},
        "java": {".java"},
        "go": {".go"},
        "rust": {".rs"},
        "c": {".c", ".h"},
        "cpp": {".cpp", ".hpp", ".cc", ".cxx", ".hxx"},
        "csharp": {".cs"},
        "ruby": {".rb"},
        "php": {".php"},
        "swift": {".swift"},
        "kotlin": {".kt", ".kts"},
    }
    
    # Directories to ignore
    IGNORE_DIRS = {
        ".git", ".svn", ".hg",
        "node_modules", "__pycache__", ".pytest_cache",
        "venv", "env", ".venv", ".env",
        "build", "dist", "target",
        ".idea", ".vscode",
        "coverage", "htmlcov",
    }
    
    # File patterns to ignore
    IGNORE_PATTERNS = {
        ".pyc", ".pyo", ".so", ".dll", ".dylib",
        ".class", ".jar", ".war",
        ".exe", ".bin",
        ".log", ".tmp",
        ".min.js", ".bundle.js",
    }
    
    def __init__(self, max_file_size_mb: int = None):
        """Initialize file scanner
        
        Args:
            max_file_size_mb: Maximum file size to process (MB)
        """
        from src.config import settings
        self.max_file_size_bytes = (max_file_size_mb or settings.max_file_size_mb) * 1024 * 1024
    
    def scan_repository(self, repo_path: Path) -> tuple[Dict[str, List[Path]], List[Path]]:
        """Scan repository and categorize files by language
        
        Args:
            repo_path: Path to repository root
            
        Returns:
            Tuple of (files_by_language dict, list of large files)
        """
        files_by_language: Dict[str, List[Path]] = {}
        large_files: List[Path] = []
        
        for root, dirs, files in os.walk(repo_path):
            # Filter out ignored directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            
            root_path = Path(root)
            
            for file in files:
                file_path = root_path / file
                
                # Skip ignored patterns
                if any(file.endswith(pattern) for pattern in self.IGNORE_PATTERNS):
                    continue
                
                # Check file size
                try:
                    file_size = file_path.stat().st_size
                    if file_size > self.max_file_size_bytes:
                        logger.info(f"Large file detected ({file_size / 1024 / 1024:.2f} MB): {file_path}")
                        large_files.append(file_path)
                        continue
                except OSError:
                    continue
                
                # Detect language
                language = self._detect_language(file_path)
                if language:
                    if language not in files_by_language:
                        files_by_language[language] = []
                    files_by_language[language].append(file_path)
        
        # Log statistics
        total_files = sum(len(files) for files in files_by_language.values())
        logger.info(f"Scanned {total_files} files across {len(files_by_language)} languages")
        for lang, files in files_by_language.items():
            logger.info(f"  {lang}: {len(files)} files")
        
        if large_files:
            logger.info(f"Found {len(large_files)} large files (will be indexed without parsing)")
        
        return files_by_language, large_files
    
    def _detect_language(self, file_path: Path) -> str | None:
        """Detect programming language from file extension
        
        Args:
            file_path: Path to file
            
        Returns:
            Language name or None
        """
        suffix = file_path.suffix.lower()
        
        for language, extensions in self.LANGUAGE_EXTENSIONS.items():
            if suffix in extensions:
                return language
        
        return None
    
    @staticmethod
    def is_test_file(file_path: Path) -> bool:
        """Check if file is a test file
        
        Args:
            file_path: Path to file
            
        Returns:
            True if test file
        """
        name = file_path.name.lower()
        parts = file_path.parts
        
        # Check filename patterns
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
        
        if "test" in name and any(name.endswith(ext) for ext in [".py", ".js", ".ts"]):
            return True
        
        # Check directory patterns
        if any(part.lower() in {"test", "tests", "__tests__", "spec", "specs"} for part in parts):
            return True
        
        return False
    
    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA256 hash of file contents
        
        Args:
            file_path: Path to file
            
        Returns:
            Hex digest of SHA256 hash
        """
        sha256 = hashlib.sha256()
        
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash file {file_path}: {e}")
            return ""
    
    @staticmethod
    def count_lines(file_path: Path) -> int:
        """Count lines of code in a file
        
        Args:
            file_path: Path to file
            
        Returns:
            Number of lines
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return sum(1 for _ in f)
        except Exception as e:
            logger.error(f"Failed to count lines in {file_path}: {e}")
            return 0
