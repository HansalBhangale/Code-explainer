"""
Python AST Parser - Extracts symbols and structure from Python code
"""
import ast
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

from src.models import Symbol, SymbolKind

logger = logging.getLogger(__name__)


class PythonASTParser:
    """Parses Python source code using AST"""
    
    def __init__(self):
        self.current_file_id: Optional[str] = None
        self.current_snapshot_id: Optional[str] = None
        self.current_class_stack: List[str] = []
    
    def parse_file(
        self,
        file_path: Path,
        file_id: str,
        snapshot_id: str
    ) -> tuple[List[Symbol], List[Dict[str, Any]]]:
        """Parse a Python file and extract symbols and imports
        
        Args:
            file_path: Path to Python file
            file_id: File ID in database
            snapshot_id: Snapshot ID
            
        Returns:
            Tuple of (symbols list, imports list)
        """
        self.current_file_id = file_id
        self.current_snapshot_id = snapshot_id
        self.current_class_stack = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            
            tree = ast.parse(source, filename=str(file_path))
            symbols = self._extract_symbols(tree)
            imports = self._extract_imports(tree)
            
            logger.debug(f"Extracted {len(symbols)} symbols and {len(imports)} imports from {file_path.name}")
            return symbols, imports
            
        except SyntaxError as e:
            logger.error(f"Syntax error in {file_path}: {e}")
            return [], []
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return [], []
    
    def _extract_symbols(self, tree: ast.AST) -> List[Symbol]:
        """Extract symbols from AST
        
        Args:
            tree: AST tree
            
        Returns:
            List of Symbol instances
        """
        symbols = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                symbol = self._extract_function(node)
                if symbol:
                    symbols.append(symbol)
            
            elif isinstance(node, ast.AsyncFunctionDef):
                symbol = self._extract_function(node, is_async=True)
                if symbol:
                    symbols.append(symbol)
            
            elif isinstance(node, ast.ClassDef):
                symbol = self._extract_class(node)
                if symbol:
                    symbols.append(symbol)
        
        return symbols
    
    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool = False
    ) -> Optional[Symbol]:
        """Extract function/method symbol
        
        Args:
            node: Function AST node
            is_async: Whether function is async
            
        Returns:
            Symbol instance or None
        """
        name = node.name
        
        # Determine if it's a method or function
        is_method = len(self.current_class_stack) > 0
        kind = SymbolKind.METHOD if is_method else SymbolKind.FUNCTION
        
        # Build qualified name
        if is_method:
            qualname = ".".join(self.current_class_stack + [name])
        else:
            qualname = name
        
        # Extract signature
        signature = self._build_signature(node, is_async)
        
        # Extract metadata
        meta = {
            "is_async": is_async,
            "is_method": is_method,
            "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
        }
        
        # Check for FastAPI endpoint decorators
        if self._is_fastapi_endpoint(node):
            meta["is_endpoint"] = True
        
        return Symbol(
            snapshot_id=self.current_snapshot_id,
            file_id=self.current_file_id,
            kind=kind,
            name=name,
            qualname=qualname,
            signature=signature,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            meta=meta
        )
    
    def _extract_class(self, node: ast.ClassDef) -> Optional[Symbol]:
        """Extract class symbol
        
        Args:
            node: Class AST node
            
        Returns:
            Symbol instance or None
        """
        name = node.name
        
        # Build qualified name
        if self.current_class_stack:
            qualname = ".".join(self.current_class_stack + [name])
        else:
            qualname = name
        
        # Extract base classes
        bases = [self._get_name(base) for base in node.bases]
        
        # Extract metadata
        meta = {
            "bases": bases,
            "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
        }
        
        return Symbol(
            snapshot_id=self.current_snapshot_id,
            file_id=self.current_file_id,
            kind=SymbolKind.CLASS,
            name=name,
            qualname=qualname,
            signature=f"class {name}({', '.join(bases)})" if bases else f"class {name}",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            meta=meta
        )
    
    def _build_signature(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool = False
    ) -> str:
        """Build function signature string
        
        Args:
            node: Function AST node
            is_async: Whether function is async
            
        Returns:
            Signature string
        """
        args = node.args
        params = []
        
        # Regular arguments
        for arg in args.args:
            param = arg.arg
            if arg.annotation:
                param += f": {self._get_name(arg.annotation)}"
            params.append(param)
        
        # Return type
        return_type = ""
        if node.returns:
            return_type = f" -> {self._get_name(node.returns)}"
        
        prefix = "async def" if is_async else "def"
        return f"{prefix} {node.name}({', '.join(params)}){return_type}"
    
    @staticmethod
    def _get_name(node: ast.AST) -> str:
        """Get name from AST node
        
        Args:
            node: AST node
            
        Returns:
            Name string
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{PythonASTParser._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return f"{PythonASTParser._get_name(node.value)}[...]"
        else:
            return ast.unparse(node) if hasattr(ast, "unparse") else "..."
    
    @staticmethod
    def _get_decorator_name(node: ast.AST) -> str:
        """Get decorator name
        
        Args:
            node: Decorator AST node
            
        Returns:
            Decorator name
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{PythonASTParser._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return PythonASTParser._get_decorator_name(node.func)
        else:
            return "unknown"
    
    @staticmethod
    def _is_fastapi_endpoint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Check if function is a FastAPI endpoint
        
        Args:
            node: Function AST node
            
        Returns:
            True if FastAPI endpoint
        """
        for decorator in node.decorator_list:
            dec_name = PythonASTParser._get_decorator_name(decorator)
            
            # Check for common FastAPI decorators
            if any(method in dec_name.lower() for method in ["get", "post", "put", "delete", "patch"]):
                if "router" in dec_name.lower() or "app" in dec_name.lower():
                    return True
        
        return False
    
    def _extract_imports(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Extract import statements from AST
        
        Args:
            tree: AST tree
            
        Returns:
            List of import dictionaries
        """
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Handle: import module [as alias]
                for alias in node.names:
                    imports.append({
                        "module": alias.name,
                        "imported_names": [],
                        "alias": alias.asname,
                        "is_relative": False,
                        "line_number": node.lineno
                    })
            
            elif isinstance(node, ast.ImportFrom):
                # Handle: from module import name [as alias]
                module = node.module or ""
                is_relative = node.level > 0
                
                # Handle relative imports (., ..)
                if is_relative:
                    module = "." * node.level + module
                
                imported_names = []
                for alias in node.names:
                    imported_names.append({
                        "name": alias.name,
                        "alias": alias.asname
                    })
                
                imports.append({
                    "module": module,
                    "imported_names": imported_names,
                    "alias": None,
                    "is_relative": is_relative,
                    "line_number": node.lineno
                })
        
        return imports
    
    def extract_call_sites(self, tree: ast.AST, symbols: List[Symbol]) -> List:
        """Extract function/method calls from AST
        
        Args:
            tree: Python AST
            symbols: List of symbols to map callers
            
        Returns:
            List of CallSite objects
        """
        from src.models import CallSite, CallType
        
        call_sites = []
        symbol_map = {s.qualname: s.symbol_id for s in symbols}
        
        class CallVisitor(ast.NodeVisitor):
            def __init__(self, parser):
                self.parser = parser
                self.current_function = None
            
            def visit_FunctionDef(self, node):
                # Track current function context
                old_func = self.current_function
                qualname = self.parser._get_qualname(node.name)
                self.current_function = symbol_map.get(qualname)
                self.generic_visit(node)
                self.current_function = old_func
            
            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)
            
            def visit_Call(self, node):
                if self.current_function:
                    # Extract callee name
                    callee_name = None
                    call_type = CallType.DIRECT
                    
                    if isinstance(node.func, ast.Name):
                        callee_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        callee_name = node.func.attr
                        call_type = CallType.METHOD
                    
                    if callee_name:
                        call_sites.append(CallSite(
                            snapshot_id=self.parser.current_snapshot_id,
                            caller_symbol_id=self.current_function,
                            callee_name=callee_name,
                            line_number=node.lineno,
                            call_type=call_type
                        ))
                
                self.generic_visit(node)
        
        visitor = CallVisitor(self)
        visitor.visit(tree)
        return call_sites
    
    def extract_type_annotations(self, tree: ast.AST, symbols: List[Symbol]) -> List:
        """Extract type annotations from function signatures and variables
        
        Args:
            tree: Python AST
            symbols: List of symbols to attach types to
            
        Returns:
            List of TypeAnnotation objects
        """
        from src.models import TypeAnnotation, TypeCategory
        
        type_annotations = []
        symbol_map = {s.qualname: s.symbol_id for s in symbols}
        
        class TypeVisitor(ast.NodeVisitor):
            def __init__(self, parser):
                self.parser = parser
            
            def visit_FunctionDef(self, node):
                qualname = self.parser._get_qualname(node.name)
                symbol_id = symbol_map.get(qualname)
                
                if symbol_id and node.returns:
                    # Extract return type
                    type_name, category = self._parse_annotation(node.returns)
                    if type_name:
                        type_annotations.append(TypeAnnotation(
                            snapshot_id=self.parser.current_snapshot_id,
                            symbol_id=symbol_id,
                            type_name=type_name,
                            type_category=category
                        ))
                
                # Extract parameter types
                for arg in node.args.args:
                    if arg.annotation:
                        type_name, category = self._parse_annotation(arg.annotation)
                        # Note: parameter types could be stored separately if needed
                
                self.generic_visit(node)
            
            def visit_AsyncFunctionDef(self, node):
                self.visit_FunctionDef(node)
            
            def _parse_annotation(self, annotation) -> tuple[str, TypeCategory]:
                """Parse type annotation node"""
                if isinstance(annotation, ast.Name):
                    type_name = annotation.id
                    category = self._categorize_type(type_name)
                    return type_name, category
                elif isinstance(annotation, ast.Subscript):
                    # Generic types like List[str], Optional[int]
                    if isinstance(annotation.value, ast.Name):
                        base = annotation.value.id
                        return f"{base}[...]", TypeCategory.GENERIC
                elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
                    # Union types (Python 3.10+): str | int
                    return "Union", TypeCategory.UNION
                
                return "Any", TypeCategory.ANY
            
            def _categorize_type(self, type_name: str) -> TypeCategory:
                """Categorize a type name"""
                primitives = {'int', 'str', 'float', 'bool', 'bytes', 'None'}
                if type_name in primitives:
                    return TypeCategory.PRIMITIVE
                elif type_name in {'List', 'Dict', 'Set', 'Tuple', 'Optional'}:
                    return TypeCategory.GENERIC
                elif type_name == 'Callable':
                    return TypeCategory.FUNCTION
                else:
                    return TypeCategory.CLASS
        
        visitor = TypeVisitor(self)
        visitor.visit(tree)
        return type_annotations
