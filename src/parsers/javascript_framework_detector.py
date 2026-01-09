"""
JavaScript Framework Intelligence
Detects Express, React, Next.js, and NestJS constructs
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import logging
from tree_sitter import Node

logger = logging.getLogger(__name__)


class JavaScriptFrameworkDetector:
    """Detects framework-specific constructs in JavaScript/TypeScript"""

    def __init__(self):
        self.current_file_id: Optional[str] = None
        self.current_snapshot_id: Optional[str] = None

    def detect_frameworks(
        self, root: Node, source: str, file_path: Path, file_id: str, snapshot_id: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Detect framework-specific constructs

        Args:
            root: Tree-sitter root node
            source: Source code
            file_path: File path
            file_id: File ID
            snapshot_id: Snapshot ID

        Returns:
            Dictionary with endpoints, components, etc.
        """
        self.current_file_id = file_id
        self.current_snapshot_id = snapshot_id

        results = {"endpoints": [], "components": [], "middleware": []}

        # Detect Express routes
        results["endpoints"].extend(self._detect_express_routes(root, source))

        # Detect NestJS controllers
        results["endpoints"].extend(self._detect_nestjs_controllers(root, source))

        # Detect Next.js API routes
        if "pages/api" in str(file_path) or "app/api" in str(file_path):
            results["endpoints"].extend(
                self._detect_nextjs_api_routes(root, source, file_path)
            )

        # Detect React components
        results["components"].extend(self._detect_react_components(root, source))

        return results

    def _detect_express_routes(self, root: Node, source: str) -> List[Dict[str, Any]]:
        """Detect Express.js routes

        Patterns:
        - app.get('/path', handler)
        - router.post('/path', middleware, handler)
        - app.use('/path', router)
        """
        endpoints = []

        def visit_node(node: Node):
            if node.type == "call_expression":
                func = node.child_by_field_name("function")
                if func and func.type == "member_expression":
                    obj = func.child_by_field_name("object")
                    prop = func.child_by_field_name("property")

                    if obj and prop:
                        obj_name = source[obj.start_byte : obj.end_byte]
                        method = source[prop.start_byte : prop.end_byte]

                        # Check if it's an Express route method
                        if obj_name in ("app", "router") and method in (
                            "get",
                            "post",
                            "put",
                            "delete",
                            "patch",
                            "use",
                        ):
                            args = node.child_by_field_name("arguments")
                            if args and len(args.children) >= 2:
                                # First arg is the path
                                path_node = args.children[1]
                                if path_node.type == "string":
                                    path = source[
                                        path_node.start_byte : path_node.end_byte
                                    ].strip("'\"")

                                    # Last arg is usually the handler
                                    handler_node = (
                                        args.children[-2]
                                        if len(args.children) > 2
                                        else None
                                    )
                                    handler_name = "anonymous"
                                    if handler_node:
                                        if handler_node.type == "identifier":
                                            handler_name = source[
                                                handler_node.start_byte : handler_node.end_byte
                                            ]
                                        elif handler_node.type == "arrow_function":
                                            handler_name = "arrow_function"

                                    endpoints.append(
                                        {
                                            "snapshot_id": self.current_snapshot_id,
                                            "file_id": self.current_file_id,
                                            "handler_function": handler_name,
                                            "http_method": (
                                                method.upper()
                                                if method != "use"
                                                else "MIDDLEWARE"
                                            ),
                                            "path": path,
                                            "framework": "express",
                                            "tags": ["express"],
                                            "summary": f"Express {method.upper()} {path}",
                                            "description": None,
                                            "response_model": None,
                                            "status_code": 200,
                                            "deprecated": False,
                                        }
                                    )

            for child in node.children:
                visit_node(child)

        visit_node(root)
        return endpoints

    def _detect_nestjs_controllers(
        self, root: Node, source: str
    ) -> List[Dict[str, Any]]:
        """Detect NestJS controllers and routes

        Patterns:
        - @Controller('users')
        - @Get(':id')
        - @Post()
        """
        endpoints = []

        def visit_node(node: Node, controller_path: Optional[str] = None):
            # Look for class declarations with @Controller decorator
            if node.type == "class_declaration":
                # Check for @Controller decorator
                for child in node.children:
                    if (
                        child.type == "decorator"
                        and "@Controller" in source[child.start_byte : child.end_byte]
                    ):
                        # Extract controller path
                        call = child.child_by_field_name("call_expression")
                        if call:
                            args = call.child_by_field_name("arguments")
                            if args and len(args.children) > 1:
                                path_node = args.children[1]
                                controller_path = source[
                                    path_node.start_byte : path_node.end_byte
                                ].strip("'\"")

                # Extract methods with route decorators
                body = node.child_by_field_name("body")
                if body and controller_path:
                    for method in body.children:
                        if method.type == "method_definition":
                            # Check for route decorators
                            for decorator in method.children:
                                if decorator.type == "decorator":
                                    decorator_text = source[
                                        decorator.start_byte : decorator.end_byte
                                    ]
                                    for http_method in [
                                        "Get",
                                        "Post",
                                        "Put",
                                        "Delete",
                                        "Patch",
                                    ]:
                                        if f"@{http_method}" in decorator_text:
                                            # Extract route path
                                            route_path = ""
                                            call = decorator.child_by_field_name(
                                                "call_expression"
                                            )
                                            if call:
                                                args = call.child_by_field_name(
                                                    "arguments"
                                                )
                                                if args and len(args.children) > 1:
                                                    path_node = args.children[1]
                                                    route_path = source[
                                                        path_node.start_byte : path_node.end_byte
                                                    ].strip("'\"")

                                            full_path = f"/{controller_path}/{route_path}".replace(
                                                "//", "/"
                                            )

                                            # Get method name
                                            method_name_node = (
                                                method.child_by_field_name("name")
                                            )
                                            method_name = (
                                                source[
                                                    method_name_node.start_byte : method_name_node.end_byte
                                                ]
                                                if method_name_node
                                                else "unknown"
                                            )

                                            endpoints.append(
                                                {
                                                    "snapshot_id": self.current_snapshot_id,
                                                    "file_id": self.current_file_id,
                                                    "handler_function": method_name,
                                                    "http_method": http_method.upper(),
                                                    "path": full_path,
                                                    "framework": "nestjs",
                                                    "tags": ["nestjs"],
                                                    "summary": f"NestJS {http_method.upper()} {full_path}",
                                                    "description": None,
                                                    "response_model": None,
                                                    "status_code": 200,
                                                    "deprecated": False,
                                                }
                                            )

            for child in node.children:
                visit_node(child, controller_path)

        visit_node(root)
        return endpoints

    def _detect_nextjs_api_routes(
        self, root: Node, source: str, file_path: Path
    ) -> List[Dict[str, Any]]:
        """Detect Next.js API routes

        Pattern: export default function handler(req, res) {}
        or: export async function GET(request) {}
        """
        endpoints = []

        # Convert file path to API route
        path_str = str(file_path).replace("\\", "/")
        if "pages/api" in path_str:
            api_path = "/" + path_str.split("pages/api/")[1].replace(".js", "").replace(
                ".ts", ""
            )
        elif "app/api" in path_str:
            api_path = "/" + path_str.split("app/api/")[1].replace(
                "/route.js", ""
            ).replace("/route.ts", "")
        else:
            api_path = "/api/unknown"

        def visit_node(node: Node):
            # Look for exported functions
            if node.type == "export_statement":
                for child in node.children:
                    if child.type == "function_declaration":
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            func_name = source[
                                name_node.start_byte : name_node.end_byte
                            ]

                            # Check if it's a Next.js 13+ route handler (GET, POST, etc.)
                            if func_name in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                                endpoints.append(
                                    {
                                        "snapshot_id": self.current_snapshot_id,
                                        "file_id": self.current_file_id,
                                        "handler_function": func_name,
                                        "http_method": func_name,
                                        "path": api_path,
                                        "framework": "nextjs",
                                        "tags": ["nextjs", "api-routes"],
                                        "summary": f"Next.js {func_name} {api_path}",
                                        "description": None,
                                        "response_model": None,
                                        "status_code": 200,
                                        "deprecated": False,
                                    }
                                )
                            elif func_name == "handler":
                                # Next.js 12 style handler
                                endpoints.append(
                                    {
                                        "snapshot_id": self.current_snapshot_id,
                                        "file_id": self.current_file_id,
                                        "handler_function": "handler",
                                        "http_method": "ALL",
                                        "path": api_path,
                                        "framework": "nextjs",
                                        "tags": ["nextjs", "api-routes"],
                                        "summary": f"Next.js API {api_path}",
                                        "description": None,
                                        "response_model": None,
                                        "status_code": 200,
                                        "deprecated": False,
                                    }
                                )

            for child in node.children:
                visit_node(child)

        visit_node(root)
        return endpoints

    def _detect_react_components(self, root: Node, source: str) -> List[Dict[str, Any]]:
        """Detect React components

        Patterns:
        - function Component() { return <div>...</div> }
        - const Component = () => { return <div>...</div> }
        - class Component extends React.Component {}
        """
        components = []

        def visit_node(node: Node):
            # Function components
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = source[name_node.start_byte : name_node.end_byte]
                    # Check if name starts with uppercase (React convention)
                    if name and name[0].isupper():
                        # Check if it returns JSX
                        if self._contains_jsx(node, source):
                            components.append(
                                {
                                    "name": name,
                                    "type": "function_component",
                                    "framework": "react",
                                }
                            )

            # Arrow function components
            elif node.type == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        name_node = child.child_by_field_name("name")
                        value_node = child.child_by_field_name("value")
                        if (
                            name_node
                            and value_node
                            and value_node.type == "arrow_function"
                        ):
                            name = source[name_node.start_byte : name_node.end_byte]
                            if (
                                name
                                and name[0].isupper()
                                and self._contains_jsx(value_node, source)
                            ):
                                components.append(
                                    {
                                        "name": name,
                                        "type": "arrow_component",
                                        "framework": "react",
                                    }
                                )

            # Class components
            elif node.type == "class_declaration":
                name_node = node.child_by_field_name("name")
                heritage = node.child_by_field_name("heritage")
                if name_node and heritage:
                    heritage_text = source[heritage.start_byte : heritage.end_byte]
                    if (
                        "React.Component" in heritage_text
                        or "Component" in heritage_text
                    ):
                        name = source[name_node.start_byte : name_node.end_byte]
                        components.append(
                            {
                                "name": name,
                                "type": "class_component",
                                "framework": "react",
                            }
                        )

            for child in node.children:
                visit_node(child)

        visit_node(root)
        return components

    def _contains_jsx(self, node: Node, source: str) -> bool:
        """Check if node contains JSX"""

        def check_node(n: Node) -> bool:
            if n.type == "jsx_element" or n.type == "jsx_self_closing_element":
                return True
            for child in n.children:
                if check_node(child):
                    return True
            return False

        return check_node(node)
