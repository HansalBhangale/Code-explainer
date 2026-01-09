"""
FastAPI Parser - Extracts FastAPI-specific constructs
"""

import ast
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import logging

logger = logging.getLogger(__name__)


class FastAPIParser:
    """Specialized parser for FastAPI framework constructs"""

    # FastAPI HTTP method decorators
    HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}

    def __init__(self):
        self.current_file_id: Optional[str] = None
        self.current_snapshot_id: Optional[str] = None
        self.app_instances: Set[str] = set()  # Track app/router variable names

    def parse_file(
        self, file_path: Path, file_id: str, snapshot_id: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Parse a Python file for FastAPI constructs

        Args:
            file_path: Path to Python file
            file_id: File ID in database
            snapshot_id: Snapshot ID

        Returns:
            Dictionary with endpoints, dependencies, and model_usages
        """
        self.current_file_id = file_id
        self.current_snapshot_id = snapshot_id
        self.app_instances = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            tree = ast.parse(source, filename=str(file_path))

            # Find FastAPI/APIRouter instances
            self._find_app_instances(tree)

            # Extract endpoints
            endpoints = self._extract_routes(tree)

            # Extract dependencies and model usages from endpoints
            dependencies = []
            model_usages = []

            for endpoint_data in endpoints:
                # Extract dependencies for this endpoint
                deps = self._extract_endpoint_dependencies(endpoint_data)
                dependencies.extend(deps)

                # Extract model usages
                models = self._extract_endpoint_models(endpoint_data)
                model_usages.extend(models)

            logger.debug(
                f"Extracted {len(endpoints)} endpoints, {len(dependencies)} dependencies, "
                f"{len(model_usages)} model usages from {file_path.name}"
            )

            return {
                "endpoints": endpoints,
                "dependencies": dependencies,
                "model_usages": model_usages,
            }

        except SyntaxError as e:
            logger.error(f"Syntax error in {file_path}: {e}")
            return {"endpoints": [], "dependencies": [], "model_usages": []}
        except Exception as e:
            logger.error(f"Failed to parse FastAPI constructs in {file_path}: {e}")
            return {"endpoints": [], "dependencies": [], "model_usages": []}

    def _find_app_instances(self, tree: ast.AST) -> None:
        """Find FastAPI() and APIRouter() instantiations

        Args:
            tree: AST tree
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                # Look for: app = FastAPI() or router = APIRouter()
                if isinstance(node.value, ast.Call):
                    func_name = self._get_name(node.value.func)
                    if func_name in ("FastAPI", "APIRouter"):
                        # Get variable name
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                self.app_instances.add(target.id)
                                logger.debug(f"Found FastAPI instance: {target.id}")

    def _extract_routes(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Extract FastAPI route definitions

        Args:
            tree: AST tree

        Returns:
            List of endpoint data dictionaries
        """
        endpoints = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check decorators for route definitions
                for decorator in node.decorator_list:
                    endpoint_data = self._parse_route_decorator(decorator, node)
                    if endpoint_data:
                        endpoints.append(endpoint_data)

        return endpoints

    def _parse_route_decorator(
        self, decorator: ast.expr, func_node: ast.FunctionDef
    ) -> Optional[Dict[str, Any]]:
        """Parse a route decorator

        Args:
            decorator: Decorator AST node
            func_node: Function definition node

        Returns:
            Endpoint data dictionary or None
        """
        if not isinstance(decorator, ast.Call):
            return None

        # Get decorator name (e.g., "app.get", "router.post")
        decorator_name = self._get_name(decorator.func)

        # Check if it's a FastAPI route decorator
        parts = decorator_name.split(".")
        if len(parts) != 2:
            return None

        instance_name, method = parts

        # Check if instance is a known FastAPI app/router
        if instance_name not in self.app_instances:
            return None

        # Check if method is an HTTP method
        if method.lower() not in self.HTTP_METHODS and method != "api_route":
            return None

        # Extract path (first positional argument)
        path = None
        if decorator.args:
            if isinstance(decorator.args[0], ast.Constant):
                path = decorator.args[0].value

        if not path:
            return None

        # Extract keyword arguments
        http_method = method.upper() if method != "api_route" else "GET"
        response_model = None
        status_code = 200
        tags = []
        summary = None
        description = None
        deprecated = False

        for keyword in decorator.keywords:
            if keyword.arg == "response_model":
                response_model = self._get_name(keyword.value)
            elif keyword.arg == "status_code":
                if isinstance(keyword.value, ast.Constant):
                    status_code = keyword.value.value
            elif keyword.arg == "tags":
                if isinstance(keyword.value, ast.List):
                    tags = [
                        elt.value
                        for elt in keyword.value.elts
                        if isinstance(elt, ast.Constant)
                    ]
            elif keyword.arg == "summary":
                if isinstance(keyword.value, ast.Constant):
                    summary = keyword.value.value
            elif keyword.arg == "description":
                if isinstance(keyword.value, ast.Constant):
                    description = keyword.value.value
            elif keyword.arg == "deprecated":
                if isinstance(keyword.value, ast.Constant):
                    deprecated = keyword.value.value
            elif keyword.arg == "methods":
                # For api_route
                if isinstance(keyword.value, ast.List):
                    methods = [
                        elt.value
                        for elt in keyword.value.elts
                        if isinstance(elt, ast.Constant)
                    ]
                    if methods:
                        http_method = methods[0]

        return {
            "file_id": self.current_file_id,
            "snapshot_id": self.current_snapshot_id,
            "handler_function": func_node.name,
            "handler_qualname": func_node.name,  # Will be updated if in class
            "http_method": http_method,
            "path": path,
            "router_prefix": None,  # TODO: Track from include_router
            "tags": tags,
            "summary": summary or func_node.name.replace("_", " ").title(),
            "description": description,
            "response_model": response_model,
            "status_code": status_code,
            "deprecated": deprecated,
            "function_node": func_node,  # Keep for dependency/model extraction
        }

    def _extract_endpoint_dependencies(
        self, endpoint_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract dependencies from endpoint function

        Args:
            endpoint_data: Endpoint data with function_node

        Returns:
            List of dependency dictionaries
        """
        dependencies = []
        func_node = endpoint_data.get("function_node")

        if not func_node:
            return dependencies

        # Parse function parameters
        for arg in func_node.args.args:
            # Check if parameter has Depends() default
            if arg.arg in [d.arg for d in func_node.args.defaults]:
                # Find the default value
                idx = func_node.args.args.index(arg)
                default_idx = idx - (
                    len(func_node.args.args) - len(func_node.args.defaults)
                )

                if default_idx >= 0:
                    default = func_node.args.defaults[default_idx]

                    # Check if it's Depends(...)
                    if isinstance(default, ast.Call):
                        func_name = self._get_name(default.func)
                        if func_name == "Depends":
                            # Extract dependency function
                            if default.args:
                                dep_func = self._get_name(default.args[0])
                                dependencies.append(
                                    {
                                        "snapshot_id": self.current_snapshot_id,
                                        "endpoint_handler": endpoint_data[
                                            "handler_function"
                                        ],
                                        "parameter_name": arg.arg,
                                        "dependency_function": dep_func,
                                        "scope": self._infer_dependency_scope(arg),
                                    }
                                )

        return dependencies

    def _extract_endpoint_models(
        self, endpoint_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract Pydantic model usages from endpoint

        Args:
            endpoint_data: Endpoint data with function_node

        Returns:
            List of model usage dictionaries
        """
        model_usages = []
        func_node = endpoint_data.get("function_node")

        if not func_node:
            return model_usages

        # Check response_model from decorator
        if endpoint_data.get("response_model"):
            model_usages.append(
                {
                    "snapshot_id": self.current_snapshot_id,
                    "endpoint_handler": endpoint_data["handler_function"],
                    "model_name": endpoint_data["response_model"],
                    "usage_type": "response",
                    "is_list": False,  # TODO: Detect List[Model]
                }
            )

        # Check request body parameters (type annotations)
        for arg in func_node.args.args:
            if arg.annotation:
                type_name = self._get_name(arg.annotation)

                # Skip common types
                if type_name in ("str", "int", "float", "bool", "dict", "list"):
                    continue

                # Check if it's not a Depends() parameter
                is_dependency = False
                idx = func_node.args.args.index(arg)
                default_idx = idx - (
                    len(func_node.args.args) - len(func_node.args.defaults)
                )

                if default_idx >= 0:
                    default = func_node.args.defaults[default_idx]
                    if isinstance(default, ast.Call):
                        if self._get_name(default.func) == "Depends":
                            is_dependency = True

                if not is_dependency and type_name:
                    model_usages.append(
                        {
                            "snapshot_id": self.current_snapshot_id,
                            "endpoint_handler": endpoint_data["handler_function"],
                            "model_name": type_name,
                            "usage_type": "request_body",
                            "is_list": False,  # TODO: Detect List[Model]
                        }
                    )

        return model_usages

    def _infer_dependency_scope(self, arg: ast.arg) -> str:
        """Infer dependency scope from parameter name

        Args:
            arg: Function argument

        Returns:
            Scope string
        """
        param_name = arg.arg.lower()

        if "db" in param_name or "session" in param_name:
            return "database"
        elif "user" in param_name or "auth" in param_name:
            return "auth"
        elif "token" in param_name:
            return "header"
        elif "query" in param_name:
            return "query"
        else:
            return "dependency"

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
            return f"{FastAPIParser._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            # For List[Model], Optional[Model], etc.
            return FastAPIParser._get_name(node.value)
        else:
            return ast.unparse(node) if hasattr(ast, "unparse") else "..."
