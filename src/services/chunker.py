"""
Code Chunker Service
Extracts parent and child chunks from code symbols for RAG
"""
from typing import Tuple, Optional
from src.models.schemas import Chunk, ChunkType, Symbol
import logging

logger = logging.getLogger(__name__)


class CodeChunker:
    """
    Creates parent-child chunks for RAG retrieval
    
    Child Chunk: Exact function/class body
    Parent Chunk: Surrounding context (imports, docstrings, neighboring code)
    """
    
    def __init__(self, context_lines: int = 10):
        """
        Args:
            context_lines: Number of lines to include before/after for parent context
        """
        self.context_lines = context_lines
    
    def chunk_symbol(
        self, 
        symbol: Symbol, 
        file_content: str,
        file_id: str,
        language: str = "unknown"
    ) -> Tuple[Chunk, Chunk]:
        """
        Create parent and child chunks for a symbol
        
        Args:
            symbol: Symbol to chunk
            file_content: Full file content
            file_id: File ID for the chunk
            language: Programming language
            
        Returns:
            Tuple of (child_chunk, parent_chunk)
        """
        lines = file_content.split('\n')
        
        # Extract child chunk (exact symbol body)
        child_content = self._extract_child_content(
            lines, 
            symbol.start_line, 
            symbol.end_line
        )
        
        # Extract parent chunk (surrounding context)
        parent_content = self._extract_parent_context(
            lines,
            symbol.start_line,
            symbol.end_line,
            file_content
        )
        
        # Create child chunk
        child_chunk = Chunk(
            snapshot_id=symbol.snapshot_id,
            file_id=file_id,
            symbol_id=symbol.symbol_id,
            parent_chunk_id=None,  # Will be set after parent is created
            chunk_type=ChunkType.CHILD,
            content=child_content,
            language=language,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            metadata={
                "symbol_name": symbol.name,
                "symbol_kind": symbol.kind.value,
                "qualname": symbol.qualname,
                "signature": symbol.signature
            }
        )
        
        # Create parent chunk
        parent_start = max(1, symbol.start_line - self.context_lines)
        parent_end = min(len(lines), symbol.end_line + self.context_lines)
        
        parent_chunk = Chunk(
            snapshot_id=symbol.snapshot_id,
            file_id=file_id,
            symbol_id=symbol.symbol_id,
            parent_chunk_id=None,  # Parent chunks don't have parents
            chunk_type=ChunkType.PARENT,
            content=parent_content,
            language=language,
            start_line=parent_start,
            end_line=parent_end,
            metadata={
                "symbol_name": symbol.name,
                "symbol_kind": symbol.kind.value,
                "context_type": "surrounding_code",
                "includes_imports": self._has_imports(parent_content),
                "includes_docstring": self._has_docstring(parent_content)
            }
        )
        
        # Link child to parent
        child_chunk.parent_chunk_id = parent_chunk.chunk_id
        
        return child_chunk, parent_chunk
    
    def _extract_child_content(
        self, 
        lines: list, 
        start_line: int, 
        end_line: int
    ) -> str:
        """Extract exact symbol body"""
        # Lines are 1-indexed
        return '\n'.join(lines[start_line-1:end_line])
    
    def _extract_parent_context(
        self,
        lines: list,
        start_line: int,
        end_line: int,
        file_content: str
    ) -> str:
        """
        Extract parent context including:
        - File-level imports
        - Docstrings
        - Surrounding code
        """
        # Get file-level imports (usually at the top)
        imports = self._extract_imports(lines)
        
        # Get surrounding context
        context_start = max(0, start_line - 1 - self.context_lines)
        context_end = min(len(lines), end_line + self.context_lines)
        
        surrounding_code = '\n'.join(lines[context_start:context_end])
        
        # Combine imports + surrounding code
        if imports:
            parent_content = imports + '\n\n' + surrounding_code
        else:
            parent_content = surrounding_code
        
        return parent_content
    
    def _extract_imports(self, lines: list) -> str:
        """Extract import statements from file"""
        imports = []
        for line in lines[:50]:  # Check first 50 lines
            stripped = line.strip()
            if stripped.startswith(('import ', 'from ')):
                imports.append(line)
            elif stripped.startswith(('const ', 'let ', 'var ', 'import{')):
                # JavaScript imports
                if 'require(' in stripped or 'import' in stripped:
                    imports.append(line)
        
        return '\n'.join(imports) if imports else ""
    
    def _detect_language(self, file_id: str) -> str:
        """Detect language from file extension"""
        # This is a simplified version - in production, get from File node
        if '.py' in file_id:
            return 'python'
        elif '.js' in file_id or '.jsx' in file_id:
            return 'javascript'
        elif '.ts' in file_id or '.tsx' in file_id:
            return 'typescript'
        else:
            return 'unknown'
    
    def _has_imports(self, content: str) -> bool:
        """Check if content has import statements"""
        return 'import ' in content or 'from ' in content or 'require(' in content
    
    def _has_docstring(self, content: str) -> bool:
        """Check if content has docstrings"""
        return '"""' in content or "'''" in content or '/**' in content
