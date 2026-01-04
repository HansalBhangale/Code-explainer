"""
Import Resolution - Maps Python module names to file paths
"""
from pathlib import Path
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class ImportResolver:
    """Resolves Python import statements to actual file paths"""
    
    def __init__(self, repo_path: Path, files_by_path: Dict[str, str]):
        """Initialize import resolver
        
        Args:
            repo_path: Root path of repository
            files_by_path: Mapping of relative file paths to file IDs
        """
        self.repo_path = repo_path
        self.files_by_path = files_by_path
        
        # Build module name to file path mapping
        self.module_to_file: Dict[str, str] = {}
        for file_path in files_by_path.keys():
            module_name = self._path_to_module(file_path)
            if module_name:
                if module_name in self.module_to_file:
                    logger.warning(
                        f"Module name collision: '{module_name}' maps to both "
                        f"'{self.module_to_file[module_name]}' and '{file_path}'"
                    )
                    continue
                self.module_to_file[module_name] = file_path
    
    def _path_to_module(self, file_path: str) -> Optional[str]:
        """Convert file path to Python module name
        
        Args:
            file_path: Relative file path (e.g., "src/models/schemas.py")
            
        Returns:
            Module name (e.g., "src.models.schemas") or None
        """
        if not file_path.endswith('.py'):
            return None
        
        # Remove .py extension
        module_path = file_path[:-3]
        
        # Remove __init__ from module name
        if module_path.endswith('/__init__'):
            module_path = module_path[:-9]
        
        # Convert path separators to dots
        module_name = module_path.replace('/', '.').replace('\\', '.')
        
        return module_name
    
    def resolve_import(
        self,
        module: str,
        from_file: str,
        is_relative: bool
    ) -> Optional[str]:
        """Resolve an import statement to a file ID
        
        Args:
            module: Module name (e.g., "src.models" or "..models")
            from_file: File path where import is located
            is_relative: Whether this is a relative import
            
        Returns:
            File ID of imported module, or None if external/not found
        """
        if is_relative:
            return self._resolve_relative_import(module, from_file)
        else:
            return self._resolve_absolute_import(module)
    
    def _resolve_absolute_import(self, module: str) -> Optional[str]:
        """Resolve absolute import
        
        Args:
            module: Module name (e.g., "src.models.schemas")
            
        Returns:
            File ID or None
        """
        # Try exact match
        if module in self.module_to_file:
            file_path = self.module_to_file[module]
            return self.files_by_path.get(file_path)
        
        # Try with __init__.py
        init_module = f"{module}.__init__"
        if init_module in self.module_to_file:
            file_path = self.module_to_file[init_module]
            return self.files_by_path.get(file_path)
        
        # External dependency
        return None
    
    def _resolve_relative_import(self, module: str, from_file: str) -> Optional[str]:
        """Resolve relative import
        
        Args:
            module: Relative module (e.g., "..models" or ".schemas")
            from_file: Source file path
            
        Returns:
            File ID or None
        """
        # Count leading dots
        level = 0
        for char in module:
            if char == '.':
                level += 1
            else:
                break
        
        # Get remaining module name after dots
        remaining = module[level:] if level < len(module) else ""
        
        # Get current file's module
        current_module = self._path_to_module(from_file)
        if not current_module:
            return None
        
        # Go up 'level' directories
        parts = current_module.split('.')
        if level > len(parts):
            return None
        
        base_parts = parts[:-level] if level > 0 else parts
        
        # Add remaining module parts
        if remaining:
            target_module = '.'.join(base_parts + [remaining])
        else:
            target_module = '.'.join(base_parts)
        
        return self._resolve_absolute_import(target_module)
