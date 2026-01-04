"""
Data Models for Repository Intelligence
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid


class SourceType(str, Enum):
    """Repository source type"""
    GIT_REMOTE = "git_remote"
    GIT_LOCAL = "git_local"
    DIRECTORY = "directory"


class SnapshotStatus(str, Enum):
    """Snapshot processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SymbolKind(str, Enum):
    """Code symbol types"""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    ENDPOINT = "endpoint"


class EdgeType(str, Enum):
    """Graph edge relationship types"""
    CALLS = "calls"
    IMPORTS = "imports"
    DEPENDS_ON = "depends_on"
    DEFINES = "defines"
    USES = "uses"
    INHERITS = "inherits"


class ChunkType(str, Enum):
    """RAG chunk types"""
    FUNCTION_BODY = "function_body"
    CLASS_BODY = "class_body"
    DOCSTRING = "docstring"
    COMMENT_BLOCK = "comment_block"
    FILE_SUMMARY = "file_summary"


# ============================================================================
# Domain Models
# ============================================================================

class Repo(BaseModel):
    """Repository metadata"""
    repo_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    source_type: SourceType
    remote_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Snapshot(BaseModel):
    """Repository snapshot"""
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repo_id: str
    commit_hash: Optional[str] = None
    status: SnapshotStatus = SnapshotStatus.PENDING
    lang_profile: Dict[str, int] = Field(default_factory=dict)  # {language: line_count}
    config_fingerprint: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class File(BaseModel):
    """Source file metadata"""
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    path: str
    language: str
    sha256: str
    loc: int = 0  # Lines of code
    is_test: bool = False
    tags: List[str] = Field(default_factory=list)


class Symbol(BaseModel):
    """Code symbol (function, class, etc.)"""
    symbol_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    file_id: str
    kind: SymbolKind
    name: str
    qualname: str  # Fully qualified name
    signature: Optional[str] = None
    start_line: int
    end_line: int
    meta: Dict[str, Any] = Field(default_factory=dict)


class Import(BaseModel):
    """Import statement"""
    import_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    file_id: str
    module: str  # e.g., "os", "pathlib", "src.models"
    imported_names: List[Dict[str, Optional[str]]] = Field(default_factory=list)  # [{"name": "Path", "alias": None}]
    alias: Optional[str] = None  # For "import pandas as pd"
    is_relative: bool = False
    line_number: int


class Endpoint(BaseModel):
    """FastAPI endpoint definition"""
    endpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    file_id: str
    symbol_id: Optional[str] = None
    http_method: str  # GET, POST, etc.
    path: str  # /api/users/{id}
    router_prefix: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class Edge(BaseModel):
    """Graph relationship edge"""
    edge_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    src_symbol_id: str
    dst_symbol_id: str
    edge_type: EdgeType
    confidence: float = 1.0
    meta: Dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """RAG chunk with embedding"""
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    file_id: str
    symbol_id: Optional[str] = None
    chunk_type: ChunkType
    content: str
    start_line: int
    end_line: int
    embedding: Optional[List[float]] = None


class Finding(BaseModel):
    """Code quality/security finding"""
    finding_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    severity: str  # critical, high, medium, low
    category: str  # complexity, security, maintainability
    title: str
    description_md: str
    evidence: Dict[str, Any] = Field(default_factory=dict)


class Metric(BaseModel):
    """Quantitative metric"""
    metric_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    metric_type: str  # complexity, coverage, duplication
    target_type: str  # file, symbol, snapshot
    target_id: str
    value_num: Optional[float] = None
    value_json: Optional[Dict[str, Any]] = None


class Diff(BaseModel):
    """Snapshot comparison"""
    diff_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repo_id: str
    base_snapshot_id: str
    head_snapshot_id: str


class ImpactResult(BaseModel):
    """Impact analysis result"""
    impact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    diff_id: str
    blast_radius: Dict[str, Any] = Field(default_factory=dict)
    risk_score: float
    citations: List[Dict[str, Any]] = Field(default_factory=list)
