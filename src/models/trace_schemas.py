"""
Trace Data Models for Deep Trace Mode
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


class NodeType(str, Enum):
    """Types of nodes in execution trace"""
    ROUTE = "route"
    DEPENDENCY = "dependency"
    HANDLER = "handler"
    SERVICE = "service"
    DATABASE = "database"
    ERROR_HANDLER = "error_handler"


class ErrorType(str, Enum):
    """Types of error boundaries"""
    TRY_EXCEPT = "try_except"
    HTTP_EXCEPTION = "http_exception"
    VALIDATION_ERROR = "validation_error"


class CallNode(BaseModel):
    """Represents a node in the execution trace"""
    node_id: str = Field(..., description="Unique identifier for this node")
    node_type: NodeType = Field(..., description="Type of node")
    name: str = Field(..., description="Function/method name")
    file_path: str = Field(..., description="File containing this node")
    line_number: int = Field(..., description="Line number in file")
    calls: List[str] = Field(default_factory=list, description="IDs of nodes this calls")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Function parameters")


class ErrorBoundary(BaseModel):
    """Represents an error handling boundary"""
    node_id: str = Field(..., description="ID of the node containing this boundary")
    error_type: ErrorType = Field(..., description="Type of error boundary")
    exception_types: List[str] = Field(default_factory=list, description="Exception types handled")
    line_number: int = Field(..., description="Line number of error boundary")
    handler_node_id: Optional[str] = Field(default=None, description="ID of error handler node")


class TraceResult(BaseModel):
    """Complete trace result for an endpoint"""
    endpoint_path: str = Field(..., description="API endpoint path")
    http_method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    snapshot_id: str = Field(..., description="Snapshot ID")
    nodes: List[CallNode] = Field(default_factory=list, description="All nodes in execution trace")
    error_boundaries: List[ErrorBoundary] = Field(default_factory=list, description="Error handling boundaries")
    mermaid_diagram: str = Field(..., description="Mermaid flowchart diagram")
    execution_summary: str = Field(..., description="Human-readable execution summary")
