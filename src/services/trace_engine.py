"""
Trace Engine Service - Analyzes FastAPI endpoint execution flow
Enhanced with sequential diagrams and LLM-powered explanations
"""
import ast
from pathlib import Path
from typing import List, Dict, Optional, Set, Union
import logging

from src.models.trace_schemas import (
    CallNode, ErrorBoundary, TraceResult, NodeType, ErrorType
)

logger = logging.getLogger(__name__)


class TraceEngine:
    """Engine for tracing FastAPI endpoint execution flow"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.node_counter = 0
        self.nodes: List[CallNode] = []
        self.error_boundaries: List[ErrorBoundary] = []
        self.visited_functions: Set[str] = set()
        self.call_sequence: List[Dict] = []  # Track sequential order
    
    def trace_endpoint(
        self,
        endpoint_path: str,
        http_method: str,
        snapshot_id: str,
        main_file: Path
    ) -> TraceResult:
        """
        Trace execution flow for a specific endpoint
        """
        # Reset state
        self.node_counter = 0
        self.nodes = []
        self.error_boundaries = []
        self.visited_functions = set()
        self.call_sequence = []
        
        try:
            # Parse main.py to find the endpoint handler
            with open(main_file, 'r', encoding='utf-8') as f:
                source = f.read()
            
            tree = ast.parse(source)
            
            # Find the endpoint decorator and handler
            handler_func = self._find_endpoint_handler(tree, endpoint_path, http_method)
            
            if not handler_func:
                logger.warning(f"Handler not found for {http_method} {endpoint_path}")
                return self._create_empty_trace(endpoint_path, http_method, snapshot_id)
            
            # Create route node
            route_node = self._create_route_node(endpoint_path, http_method, main_file, handler_func)
            self.nodes.append(route_node)
            self.call_sequence.append({
                "step": 1,
                "type": "route",
                "name": f"{http_method} {endpoint_path}",
                "description": f"API request received at {endpoint_path}"
            })
            
            # Trace the handler function with sequential tracking
            self._trace_function_sequential(handler_func, main_file, source)
            
            # Generate sequential Mermaid diagram
            mermaid = self._generate_sequential_mermaid_diagram(endpoint_path, http_method)
            
            # Generate execution summary
            summary = self._generate_sequential_summary()
            
            return TraceResult(
                endpoint_path=endpoint_path,
                http_method=http_method,
                snapshot_id=snapshot_id,
                nodes=self.nodes,
                error_boundaries=self.error_boundaries,
                mermaid_diagram=mermaid,
                execution_summary=summary
            )
        except Exception as e:
            logger.error(f"Trace failed: {e}")
            return self._create_empty_trace(endpoint_path, http_method, snapshot_id)
    
    def _find_endpoint_handler(
        self,
        tree: ast.Module,
        endpoint_path: str,
        http_method: str
    ) -> Optional[Union[ast.FunctionDef, ast.AsyncFunctionDef]]:
        """Find the function decorated with @app.get/post/etc for this endpoint"""
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        if isinstance(decorator.func, ast.Attribute):
                            method_name = decorator.func.attr.lower()
                            if method_name == http_method.lower():
                                if decorator.args:
                                    if isinstance(decorator.args[0], ast.Constant):
                                        if decorator.args[0].value == endpoint_path:
                                            return node
                                    elif isinstance(decorator.args[0], ast.Str):
                                        if decorator.args[0].s == endpoint_path:
                                            return node
        return None
    
    def _create_route_node(
        self,
        endpoint_path: str,
        http_method: str,
        file_path: Path,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> CallNode:
        """Create a route node"""
        node_id = self._get_next_node_id()
        try:
            rel_path = str(file_path.relative_to(self.project_root))
        except ValueError:
            rel_path = str(file_path)
            
        return CallNode(
            node_id=node_id,
            node_type=NodeType.ROUTE,
            name=f"{http_method} {endpoint_path}",
            file_path=rel_path,
            line_number=func_node.lineno,
            calls=[]
        )
    
    def _trace_function_sequential(
        self,
        func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        file_path: Path,
        source: str
    ):
        """Trace function calls in sequential order"""
        step = 2  # Start from step 2 (step 1 is the route)
        
        # Add handler as step 2
        self.call_sequence.append({
            "step": step,
            "type": "handler",
            "name": func_node.name,
            "description": f"Handler function '{func_node.name}' starts execution"
        })
        step += 1
        
        # Walk through the function body in order
        for stmt in func_node.body:
            step = self._process_statement_sequential(stmt, step, file_path, source)
    
    def _process_statement_sequential(
        self,
        stmt: ast.stmt,
        step: int,
        file_path: Path,
        source: str
    ) -> int:
        """Process a statement and track sequential calls"""
        
        # Handle Try/Except blocks
        if isinstance(stmt, ast.Try):
            self.call_sequence.append({
                "step": step,
                "type": "control",
                "name": "try",
                "description": "Try block begins - error handling starts"
            })
            step += 1
            
            # Process try body
            for try_stmt in stmt.body:
                step = self._process_statement_sequential(try_stmt, step, file_path, source)
            
            # Add except handlers
            for handler in stmt.handlers:
                exc_name = "Exception"
                if handler.type:
                    if isinstance(handler.type, ast.Name):
                        exc_name = handler.type.id
                
                self._error_boundaries_add({
                    "type": "try_except",
                    "exception": exc_name,
                    "line": handler.lineno
                })
            
            return step
        
        # Handle If statements
        elif isinstance(stmt, ast.If):
            self.call_sequence.append({
                "step": step,
                "type": "control",
                "name": "if condition",
                "description": "Conditional branch - decision point"
            })
            step += 1
            
            for if_stmt in stmt.body:
                step = self._process_statement_sequential(if_stmt, step, file_path, source)
            
            return step
        
        # Handle Return statements
        elif isinstance(stmt, ast.Return):
            if stmt.value:
                return_info = self._get_return_info(stmt.value)
                self.call_sequence.append({
                    "step": step,
                    "type": "return",
                    "name": return_info,
                    "description": f"Return response: {return_info}"
                })
                step += 1
            return step
        
        # Handle Raise statements
        elif isinstance(stmt, ast.Raise):
            if stmt.exc and isinstance(stmt.exc, ast.Call):
                if isinstance(stmt.exc.func, ast.Name):
                    self.call_sequence.append({
                        "step": step,
                        "type": "error",
                        "name": stmt.exc.func.id,
                        "description": f"Raise {stmt.exc.func.id} - error response"
                    })
                    step += 1
            return step
        
        # Handle Assign statements with calls
        elif isinstance(stmt, ast.Assign):
            if isinstance(stmt.value, ast.Call):
                call_name = self._get_call_name(stmt.value)
                if call_name:
                    call_type = self._determine_call_type(call_name)
                    self.call_sequence.append({
                        "step": step,
                        "type": call_type,
                        "name": call_name,
                        "description": self._get_call_description(call_name, call_type)
                    })
                    step += 1
            return step
        
        # Handle Expression statements (standalone calls)
        elif isinstance(stmt, ast.Expr):
            if isinstance(stmt.value, ast.Call):
                call_name = self._get_call_name(stmt.value)
                if call_name:
                    call_type = self._determine_call_type(call_name)
                    self.call_sequence.append({
                        "step": step,
                        "type": call_type,
                        "name": call_name,
                        "description": self._get_call_description(call_name, call_type)
                    })
                    step += 1
            elif isinstance(stmt.value, ast.Await):
                if isinstance(stmt.value.value, ast.Call):
                    call_name = self._get_call_name(stmt.value.value)
                    if call_name:
                        call_type = self._determine_call_type(call_name)
                        self.call_sequence.append({
                            "step": step,
                            "type": call_type,
                            "name": f"await {call_name}",
                            "description": self._get_call_description(call_name, call_type)
                        })
                        step += 1
            return step
        
        return step
    
    def _get_call_name(self, call_node: ast.Call) -> Optional[str]:
        """Get the name of a function call"""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        elif isinstance(call_node.func, ast.Attribute):
            if isinstance(call_node.func.value, ast.Name):
                return f"{call_node.func.value.id}.{call_node.func.attr}"
            elif isinstance(call_node.func.value, ast.Attribute):
                # Handle chained calls like a.b.c()
                return call_node.func.attr
        return None
    
    def _get_return_info(self, return_value) -> str:
        """Get info about return value"""
        if isinstance(return_value, ast.Dict):
            return "dict response"
        elif isinstance(return_value, ast.Call):
            return self._get_call_name(return_value) or "response"
        else:
            return "response"
    
    def _determine_call_type(self, call_name: str) -> str:
        """Determine the type of call"""
        call_lower = call_name.lower()
        if "dao" in call_lower or "repository" in call_lower:
            return "service"
        elif "db." in call_name or "execute_query" in call_lower or "execute_write" in call_lower:
            return "database"
        elif "ingest" in call_lower:
            return "service"
        elif "logger" in call_lower or "log" in call_lower:
            return "logging"
        elif "response" in call_lower:
            return "response"
        else:
            return "service"
    
    def _get_call_description(self, call_name: str, call_type: str) -> str:
        """Get description for a call"""
        descriptions = {
            "database": f"Database operation: {call_name}",
            "service": f"Service call: {call_name}",
            "logging": f"Log message: {call_name}",
            "response": f"Create response: {call_name}"
        }
        return descriptions.get(call_type, f"Call: {call_name}")
    
    def _error_boundaries_add(self, error_info: Dict):
        """Add error boundary"""
        error_boundary = ErrorBoundary(
            node_id=f"N{len(self.call_sequence)}",
            error_type=ErrorType.TRY_EXCEPT,
            exception_types=[error_info["exception"]],
            line_number=error_info["line"]
        )
        self.error_boundaries.append(error_boundary)
    
    def _generate_sequential_mermaid_diagram(self, endpoint_path: str, http_method: str) -> str:
        """Generate a sequential flowchart showing execution order"""
        lines = ["flowchart TD"]
        
        # Create nodes for each step in sequence
        prev_id = None
        for seq in self.call_sequence:
            node_id = f"S{seq['step']}"
            # Clean the label - remove special chars that break Mermaid
            node_label = self._clean_label(seq['name'])
            style = self._get_step_style(seq['type'])
            
            # Use quoted labels to handle special characters
            lines.append(f'    {node_id}["Step {seq["step"]}: {node_label}"]')
            lines.append(f"    style {node_id} {style}")
            
            # Add arrow from previous step
            if prev_id:
                lines.append(f"    {prev_id} --> {node_id}")
            
            prev_id = node_id
        
        # Add error boundaries with dashed lines
        for i, error in enumerate(self.error_boundaries):
            error_id = f"ERR{i+1}"
            error_label = ", ".join(error.exception_types)
            lines.append(f'    {error_id}["Catch: {error_label}"]')
            lines.append(f"    style {error_id} fill:#D0021B,stroke:#D0021B,color:#fff")
            # Connect to the try block
            for seq in self.call_sequence:
                if seq['type'] == 'control' and seq['name'] == 'try':
                    lines.append(f"    S{seq['step']} -.-> {error_id}")
                    break
        
        return "\n".join(lines)
    
    def _clean_label(self, text: str) -> str:
        """Clean label for Mermaid compatibility"""
        # Remove or replace problematic characters
        text = text.replace('"', "'")
        text = text.replace('\n', ' ')
        text = text.replace('<', '')
        text = text.replace('>', '')
        text = text.replace('{', '')
        text = text.replace('}', '')
        text = text.replace('[', '')
        text = text.replace(']', '')
        text = text.replace('/', '-')  # Replace slash with dash
        text = text.replace(':', ' ')  # Replace colon with space
        return text.strip()

    
    def _get_step_style(self, step_type: str) -> str:
        """Get Mermaid style for step type"""
        styles = {
            "route": "fill:#4A90E2,stroke:#4A90E2,color:#fff",
            "handler": "fill:#7ED321,stroke:#7ED321,color:#fff",
            "service": "fill:#F5A623,stroke:#F5A623,color:#fff",
            "database": "fill:#F8E71C,stroke:#F8E71C,color:#000",
            "control": "fill:#9B59B6,stroke:#9B59B6,color:#fff",
            "logging": "fill:#95A5A6,stroke:#95A5A6,color:#fff",
            "return": "fill:#27AE60,stroke:#27AE60,color:#fff",
            "response": "fill:#27AE60,stroke:#27AE60,color:#fff",
            "error": "fill:#D0021B,stroke:#D0021B,color:#fff"
        }
        return styles.get(step_type, "fill:#ccc,stroke:#ccc")
    
    def _escape_mermaid(self, text: str) -> str:
        """Escape special characters for Mermaid"""
        return text.replace('"', "'").replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')
    
    def _generate_sequential_summary(self) -> str:
        """Generate human-readable sequential execution summary"""
        lines = ["## Execution Sequence\n"]
        
        for seq in self.call_sequence:
            icon = self._get_type_icon(seq['type'])
            lines.append(f"**Step {seq['step']}**: {icon} {seq['name']}")
            lines.append(f"   - {seq['description']}\n")
        
        if self.error_boundaries:
            lines.append("\n## Error Handling\n")
            for error in self.error_boundaries:
                lines.append(f"- 🛡️ Catches `{', '.join(error.exception_types)}` at line {error.line_number}")
        
        return "\n".join(lines)
    
    def _get_type_icon(self, step_type: str) -> str:
        """Get emoji icon for step type"""
        icons = {
            "route": "🌐",
            "handler": "⚡",
            "service": "🔧",
            "database": "💾",
            "control": "🔀",
            "logging": "📝",
            "return": "✅",
            "response": "📤",
            "error": "❌"
        }
        return icons.get(step_type, "📦")
    
    def _get_next_node_id(self) -> str:
        """Get next node ID"""
        self.node_counter += 1
        return f"N{self.node_counter}"
    
    def _create_empty_trace(
        self,
        endpoint_path: str,
        http_method: str,
        snapshot_id: str
    ) -> TraceResult:
        """Create empty trace when handler not found"""
        return TraceResult(
            endpoint_path=endpoint_path,
            http_method=http_method,
            snapshot_id=snapshot_id,
            nodes=[],
            error_boundaries=[],
            mermaid_diagram="flowchart TD\n    A[Endpoint not found]",
            execution_summary="Endpoint handler not found in source code."
        )
    
    def get_trace_for_llm(self) -> str:
        """Get trace data formatted for LLM analysis"""
        lines = [
            "# API Endpoint Execution Trace",
            "",
            "## Sequential Execution Steps:",
            ""
        ]
        
        for seq in self.call_sequence:
            lines.append(f"{seq['step']}. [{seq['type'].upper()}] {seq['name']}")
            lines.append(f"   Description: {seq['description']}")
        
        if self.error_boundaries:
            lines.append("")
            lines.append("## Error Handling:")
            for error in self.error_boundaries:
                lines.append(f"- Exception: {', '.join(error.exception_types)} (line {error.line_number})")
        
        return "\n".join(lines)
