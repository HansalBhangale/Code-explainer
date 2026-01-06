"""
JavaScript/TypeScript Parser using Tree-sitter
Extracts symbols, imports, and framework-specific constructs
"""
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from tree_sitter import Language, Parser, Node
from src.models import Symbol, Import
from src.models.schemas import SymbolKind

logger = logging.getLogger(__name__)


class JavaScriptParser:
    """Parser for JavaScript and TypeScript files using Tree-sitter"""
    
    def __init__(self):
        self.current_file_id: Optional[str] = None
        self.current_snapshot_id: Optional[str] = None
        self._parser = None
        self._language = None
        self._init_parser()
    
    def _init_parser(self):
        """Initialize tree-sitter parser"""
        try:
            # For tree-sitter 0.25+, load language from grammar package
            import tree_sitter_javascript as tsjs
            
            # Get JavaScript language (returns PyCapsule)
            js_lang_capsule = tsjs.language()
            
            # Wrap in Language object
            self._language = Language(js_lang_capsule)
            self._parser = Parser(self._language)
            logger.info("JavaScript parser initialized successfully")
        except ImportError:
            # Fallback: try loading from vendor directory
            try:
                from tree_sitter import Language as TSLanguage
                js_path = Path("vendor/tree-sitter-javascript")
                
                # Try to load pre-built library
                lib_path = Path("build/languages.dll")
                if lib_path.exists():
                    self._language = TSLanguage(str(lib_path), "javascript")
                    self._parser = Parser()
                    self._parser.set_language(self._language)
                    logger.info("JavaScript parser initialized from build")
                else:
                    logger.warning("JavaScript grammar not found, parser disabled")
                    self._parser = None
            except Exception as e2:
                logger.error(f"Failed to initialize JavaScript parser (fallback): {e2}")
                self._parser = None
        except Exception as e:
            logger.error(f"Failed to initialize JavaScript parser: {e}")
            self._parser = None
    
    def parse_file(
        self,
        file_path: Path,
        file_id: str,
        snapshot_id: str
    ) -> Tuple[List[Symbol], List[Import]]:
        """Parse a JavaScript/TypeScript file
        
        Args:
            file_path: Path to JS/TS file
            file_id: File ID in database
            snapshot_id: Snapshot ID
            
        Returns:
            Tuple of (symbols, imports)
        """
        if not self._parser:
            logger.warning("Parser not initialized, skipping file")
            return [], []
        
        self.current_file_id = file_id
        self.current_snapshot_id = snapshot_id
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
            
            # Parse source code
            tree = self._parser.parse(bytes(source, "utf8"))
            root = tree.root_node
            
            # Extract symbols and imports
            symbols = self._extract_symbols(root, source)
            imports = self._extract_imports(root, source)
            
            logger.debug(
                f"Extracted {len(symbols)} symbols and {len(imports)} imports from {file_path.name}"
            )
            
            return symbols, imports
            
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return [], []
    
    def _extract_symbols(self, root: Node, source: str) -> List[Symbol]:
        """Extract symbols (functions, classes, etc.)
        
        Args:
            root: Tree-sitter root node
            source: Source code
            
        Returns:
            List of Symbol instances
        """
        symbols = []
        
        def visit_node(node: Node, parent_class: Optional[str] = None):
            """Recursively visit nodes to extract symbols"""
            
            # Function declarations
            if node.type == "function_declaration":
                logger.debug(f"Found function_declaration node")
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = source[name_node.start_byte:name_node.end_byte]
                    logger.info(f"Extracting function: {name}")
                    symbol = Symbol(
                        snapshot_id=self.current_snapshot_id,
                        file_id=self.current_file_id,
                        kind=SymbolKind.FUNCTION,
                        name=name,
                        qualname=f"{parent_class}.{name}" if parent_class else name,
                        signature=self._get_function_signature(node, source),
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        meta={"async": "async" in source[node.start_byte:node.end_byte][:20]}
                    )
                    symbols.append(symbol)
                    logger.debug(f"Added symbol: {symbol.name}")
            
            # Arrow functions (const foo = () => {})
            elif node.type == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        value_node = child.child_by_field_name("value")
                        if name_node and value_node and value_node.type == "arrow_function":
                            name = source[name_node.start_byte:name_node.end_byte]
                            symbol = Symbol(
                                snapshot_id=self.current_snapshot_id,
                                file_id=self.current_file_id,
                                kind=SymbolKind.FUNCTION,
                                name=name,
                                qualname=f"{parent_class}.{name}" if parent_class else name,
                                signature=f"const {name} = (...) => {{}}",
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                meta={"arrow_function": True}
                            )
                            symbols.append(symbol)
            
            # Class declarations
            elif node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    class_name = source[name_node.start_byte:name_node.end_byte]
                    symbol = Symbol(
                        snapshot_id=self.current_snapshot_id,
                        file_id=self.current_file_id,
                        kind=SymbolKind.CLASS,
                        name=class_name,
                        qualname=class_name,
                        signature=f"class {class_name}",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        meta={}
                    )
                    symbols.append(symbol)
                    
                    # Extract methods from class
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            if child.type == "method_definition":
                                method_name_node = child.child_by_field_name("name")
                                if method_name_node:
                                    method_name = source[method_name_node.start_byte:method_name_node.end_byte]
                                    method_symbol = Symbol(
                                        snapshot_id=self.current_snapshot_id,
                                        file_id=self.current_file_id,
                                        kind=SymbolKind.METHOD,
                                        name=method_name,
                                        qualname=f"{class_name}.{method_name}",
                                        signature=self._get_function_signature(child, source),
                                        start_line=child.start_point[0] + 1,
                                        end_line=child.end_point[0] + 1,
                                        meta={"class": class_name}
                                    )
                                    symbols.append(method_symbol)
            
            # Recurse into children
            for child in node.children:
                visit_node(child, parent_class)
        
        logger.debug(f"Starting symbol extraction from root node type: {root.type}")
        visit_node(root)
        logger.info(f"Symbol extraction complete. Found {len(symbols)} symbols")
        return symbols
    
    def _extract_imports(self, root: Node, source: str) -> List[Import]:
        """Extract import statements
        
        Args:
            root: Tree-sitter root node
            source: Source code
            
        Returns:
            List of Import instances
        """
        imports = []
        
        def visit_node(node: Node):
            """Recursively visit nodes to extract imports"""
            
            # ES6 imports: import { foo } from 'module'
            if node.type == "import_statement":
                source_node = node.child_by_field_name("source")
                if source_node:
                    module = source[source_node.start_byte:source_node.end_byte].strip('\'"')
                    
                    # Extract imported names
                    imported_names = []
                    for child in node.children:
                        if child.type == "import_clause":
                            for spec in child.children:
                                if spec.type == "named_imports":
                                    for imp in spec.children:
                                        if imp.type == "import_specifier":
                                            name_node = imp.child_by_field_name("name")
                                            if name_node:
                                                imported_names.append({
                                                    "name": source[name_node.start_byte:name_node.end_byte],
                                                    "alias": None
                                                })
                    
                    import_obj = Import(
                        snapshot_id=self.current_snapshot_id,
                        file_id=self.current_file_id,
                        module=module,
                        imported_names=imported_names,
                        alias=None,
                        is_relative=module.startswith('.'),
                        line_number=node.start_point[0] + 1
                    )
                    imports.append(import_obj)
            
            # CommonJS require: const foo = require('module')
            elif node.type == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        value_node = child.child_by_field_name("value")
                        if value_node and value_node.type == "call_expression":
                            func = value_node.child_by_field_name("function")
                            if func and source[func.start_byte:func.end_byte] == "require":
                                args = value_node.child_by_field_name("arguments")
                                if args and len(args.children) > 1:
                                    module_node = args.children[1]
                                    module = source[module_node.start_byte:module_node.end_byte].strip('\'"')
                                    
                                    import_obj = Import(
                                        snapshot_id=self.current_snapshot_id,
                                        file_id=self.current_file_id,
                                        module=module,
                                        imported_names=[],
                                        alias=None,
                                        is_relative=module.startswith('.'),
                                        line_number=node.start_point[0] + 1
                                    )
                                    imports.append(import_obj)
            
            # Recurse into children
            for child in node.children:
                visit_node(child)
        
        visit_node(root)
        return imports
    
    def _get_function_signature(self, node: Node, source: str) -> str:
        """Extract function signature
        
        Args:
            node: Function node
            source: Source code
            
        Returns:
            Function signature string
        """
        try:
            # Get function name
            name_node = node.child_by_field_name("name")
            name = source[name_node.start_byte:name_node.end_byte] if name_node else "anonymous"
            
            # Get parameters
            params_node = node.child_by_field_name("parameters")
            params = source[params_node.start_byte:params_node.end_byte] if params_node else "()"
            
            return f"{name}{params}"
        except Exception:
            return "(...)"
