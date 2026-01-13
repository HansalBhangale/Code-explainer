"""
FastAPI Application - Repository Intelligence API
"""
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import logging

from src.config import settings
from src.database import db
from src.database.repository import RepositoryDAO, SnapshotDAO, FileDAO
from src.services import RepositoryIngestor

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Repository Intelligence API...")
    db.connect()
    db.initialize_schema()
    logger.info("Database connected and schema initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    db.close()


# Create FastAPI app
app = FastAPI(
    title="Repository Intelligence API",
    description="GenAI-Powered Repository Analysis and Intelligence Platform",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routes
from src.api.routes import call_graph, types as type_routes, rag, chat

app.include_router(call_graph.router, prefix="/api/v1")
app.include_router(type_routes.router, prefix="/api/v1")
app.include_router(rag.router)  # RAG routes already have /api/v1/rag prefix
app.include_router(chat.router)  # Chat routes have /api/v1/chat prefix



# ============================================================================
# Request/Response Models
# ============================================================================

class IngestGitRepoRequest(BaseModel):
    """Request to ingest a Git repository"""
    remote_url: str = Field(..., description="Git repository URL")
    repo_name: str = Field(..., description="Repository name")


class IngestLocalRepoRequest(BaseModel):
    """Request to ingest a local repository"""
    local_path: str = Field(..., description="Path to local repository")
    repo_name: Optional[str] = Field(None, description="Optional repository name")


class IngestResponse(BaseModel):
    """Response from repository ingestion"""
    repo_id: str
    repo_name: str
    snapshot_id: str
    status: str
    lang_profile: Dict[str, int]


class RepoResponse(BaseModel):
    """Repository information response"""
    repo_id: str
    name: str
    source_type: str
    remote_url: Optional[str]
    created_at: str


class SnapshotResponse(BaseModel):
    """Snapshot information response"""
    snapshot_id: str
    repo_id: str
    commit_hash: Optional[str]
    status: str
    lang_profile: Dict[str, int]
    created_at: str


class FileResponse(BaseModel):
    """File information response"""
    file_id: str
    path: str
    language: str
    loc: int
    is_test: bool


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Repository Intelligence API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        db.execute_query("RETURN 1 as test")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )


@app.post("/api/v1/ingest/git", response_model=IngestResponse)
async def ingest_git_repository(request: IngestGitRepoRequest):
    """Ingest a Git repository from remote URL
    
    Args:
        request: Ingestion request with remote_url and repo_name
        
    Returns:
        Ingestion result with repo_id and snapshot_id
    """
    try:
        ingestor = RepositoryIngestor()
        result = ingestor.ingest_git_repository(
            remote_url=request.remote_url,
            repo_name=request.repo_name
        )
        return IngestResponse(**result)
    except Exception as e:
        logger.error(f"Git repository ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )


@app.post("/api/v1/ingest/local", response_model=IngestResponse)
async def ingest_local_repository(request: IngestLocalRepoRequest):
    """Ingest a local repository
    
    Args:
        request: Ingestion request with local_path and optional repo_name
        
    Returns:
        Ingestion result with repo_id and snapshot_id
    """
    try:
        ingestor = RepositoryIngestor()
        result = ingestor.ingest_local_repository(
            local_path=request.local_path,
            repo_name=request.repo_name
        )
        return IngestResponse(**result)
    except Exception as e:
        logger.error(f"Local repository ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )


@app.get("/api/v1/repos", response_model=List[RepoResponse])
async def list_repositories():
    """List all repositories
    
    Returns:
        List of repositories
    """
    try:
        repos = RepositoryDAO.list_repos()
        return [
            RepoResponse(
                repo_id=r.repo_id,
                name=r.name,
                source_type=r.source_type.value,
                remote_url=r.remote_url,
                created_at=r.created_at.isoformat()
            )
            for r in repos
        ]
    except Exception as e:
        logger.error(f"Failed to list repositories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/v1/repos/{repo_id}", response_model=RepoResponse)
async def get_repository(repo_id: str):
    """Get repository by ID
    
    Args:
        repo_id: Repository ID
        
    Returns:
        Repository information
    """
    repo = RepositoryDAO.get_repo(repo_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repo_id} not found"
        )
    
    return RepoResponse(
        repo_id=repo.repo_id,
        name=repo.name,
        source_type=repo.source_type.value,
        remote_url=repo.remote_url,
        created_at=repo.created_at.isoformat()
    )


@app.get("/api/v1/repos/{repo_id}/snapshots", response_model=List[SnapshotResponse])
async def list_snapshots(repo_id: str):
    """List all snapshots for a repository
    
    Args:
        repo_id: Repository ID
        
    Returns:
        List of snapshots
    """
    try:
        snapshots = SnapshotDAO.list_snapshots(repo_id)
        return [
            SnapshotResponse(
                snapshot_id=s.snapshot_id,
                repo_id=s.repo_id,
                commit_hash=s.commit_hash,
                status=s.status.value,
                lang_profile=s.lang_profile,
                created_at=s.created_at.isoformat()
            )
            for s in snapshots
        ]
    except Exception as e:
        logger.error(f"Failed to list snapshots: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/v1/snapshots/{snapshot_id}/files", response_model=List[FileResponse])
async def list_files(snapshot_id: str):
    """List all files in a snapshot
    
    Args:
        snapshot_id: Snapshot ID
        
    Returns:
        List of files
    """
    try:
        files = FileDAO.get_files_by_snapshot(snapshot_id)
        return [
            FileResponse(
                file_id=f.file_id,
                path=f.path,
                language=f.language,
                loc=f.loc,
                is_test=f.is_test
            )
            for f in files
        ]
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Import Graph Endpoints
# ============================================================================

@app.get("/api/v1/files/{file_id}/imports")
async def get_file_imports(file_id: str):
    """Get all imports for a specific file
    
    Args:
        file_id: File ID
        
    Returns:
        List of imported files
    """
    try:
        from src.database.repository import ImportDAO
        imports = ImportDAO.get_file_imports(file_id)
        return {
            "file_id": file_id,
            "imports": imports
        }
    except Exception as e:
        logger.error(f"Failed to get file imports: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/v1/snapshots/{snapshot_id}/import-graph")
async def get_import_graph(snapshot_id: str):
    """Get the complete import dependency graph for a snapshot
    
    Args:
        snapshot_id: Snapshot ID
        
    Returns:
        Import dependency graph
    """
    try:
        from src.database.repository import ImportDAO
        graph = ImportDAO.get_import_graph(snapshot_id)
        return {
            "snapshot_id": snapshot_id,
            "edges": graph,
            "node_count": len(set([e["source"] for e in graph] + [e["target"] for e in graph])),
            "edge_count": len(graph)
        }
    except Exception as e:
        logger.error(f"Failed to get import graph: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/v1/snapshots/{snapshot_id}/dependencies/{file_path:path}")
async def get_file_dependencies(snapshot_id: str, file_path: str):
    """Get all files that depend on this file (reverse dependencies)
    
    Args:
        snapshot_id: Snapshot ID
        file_path: File path to find dependencies for
        
    Returns:
        List of dependent files
    """
    try:
        from src.database.repository import ImportDAO
        dependencies = ImportDAO.get_file_dependencies(snapshot_id, file_path)
        return {
            "file_path": file_path,
            "dependent_files": dependencies,
            "dependent_count": len(dependencies)
        }
    except Exception as e:
        logger.error(f"Failed to get file dependencies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# FastAPI Intelligence Endpoints
# ============================================================================

@app.get("/api/v1/snapshots/{snapshot_id}/endpoints")
async def list_endpoints(snapshot_id: str):
    """Get all FastAPI endpoints in a snapshot
    
    Args:
        snapshot_id: Snapshot ID
        
    Returns:
        List of endpoints with metadata
    """
    try:
        from src.database.repository import EndpointDAO
        endpoints = EndpointDAO.get_endpoints_by_snapshot(snapshot_id)
        return {
            "snapshot_id": snapshot_id,
            "endpoints": endpoints,
            "count": len(endpoints)
        }
    except Exception as e:
        logger.error(f"Failed to list endpoints: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/v1/endpoints/{endpoint_id}/dependencies")
async def get_endpoint_dependencies(endpoint_id: str):
    """Get dependency chain for an endpoint
    
    Args:
        endpoint_id: Endpoint ID
        
    Returns:
        List of dependencies
    """
    try:
        from src.database.repository import DependencyDAO
        dependencies = DependencyDAO.get_endpoint_dependencies(endpoint_id)
        return {
            "endpoint_id": endpoint_id,
            "dependencies": dependencies,
            "count": len(dependencies)
        }
    except Exception as e:
        logger.error(f"Failed to get endpoint dependencies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/v1/endpoints/{endpoint_id}/models")
async def get_endpoint_models(endpoint_id: str):
    """Get Pydantic models used by an endpoint
    
    Args:
        endpoint_id: Endpoint ID
        
    Returns:
        List of model usages
    """
    try:
        from src.database.repository import ModelUsageDAO
        models = ModelUsageDAO.get_models_for_endpoint(endpoint_id)
        return {
            "endpoint_id": endpoint_id,
            "models": models,
            "count": len(models)
        }
    except Exception as e:
        logger.error(f"Failed to get endpoint models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/api/v1/snapshots/{snapshot_id}/api-surface")
async def get_api_surface_map(snapshot_id: str):
    """Get complete API surface map
    
    Args:
        snapshot_id: Snapshot ID
        
    Returns:
        Complete API surface with endpoints grouped by tags
    """
    try:
        from src.database.repository import EndpointDAO
        endpoints = EndpointDAO.get_endpoints_by_snapshot(snapshot_id)
        
        # Group by tags
        by_tags = {}
        for ep in endpoints:
            tags = ep.get("tags", "[]")
            # Parse JSON string
            import json
            tag_list = json.loads(tags) if isinstance(tags, str) else tags
            
            for tag in tag_list:
                if tag not in by_tags:
                    by_tags[tag] = []
                by_tags[tag].append(ep)
            
            # Add to "untagged" if no tags
            if not tag_list:
                if "untagged" not in by_tags:
                    by_tags["untagged"] = []
                by_tags["untagged"].append(ep)
        
        return {
            "snapshot_id": snapshot_id,
            "total_endpoints": len(endpoints),
            "by_tags": by_tags,
            "endpoints": endpoints
        }
    except Exception as e:
        logger.error(f"Failed to get API surface map: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Deep Trace Endpoint
# ============================================================================

@app.get("/api/v1/trace")
async def trace_endpoint_flow(
    endpoint_path: str,
    http_method: str = "GET",
    snapshot_id: Optional[str] = None,
    include_llm_explanation: bool = True
):
    """Trace execution flow for a specific FastAPI endpoint
    
    Args:
        endpoint_path: API endpoint path (e.g., "/api/v1/repos")
        http_method: HTTP method (GET, POST, etc.)
        snapshot_id: Optional snapshot ID
        include_llm_explanation: Whether to include LLM-powered explanation
        
    Returns:
        TraceResult with execution flow, error boundaries, Mermaid diagram, and LLM explanation
    """
    try:
        from pathlib import Path
        from src.services.trace_engine import TraceEngine
        
        # Get project root and main.py path
        project_root = Path(__file__).parent.parent.parent
        main_file = Path(__file__)
        
        # Use a default snapshot_id if not provided
        if not snapshot_id:
            snapshot_id = "current"
        
        # Create trace engine and trace the endpoint
        engine = TraceEngine(project_root)
        trace_result = engine.trace_endpoint(
            endpoint_path=endpoint_path,
            http_method=http_method.upper(),
            snapshot_id=snapshot_id,
            main_file=main_file
        )
        
        # Use LLM to generate diagram and explanation
        llm_result = None
        if include_llm_explanation:
            try:
                llm_result = await _get_llm_trace_analysis(
                    endpoint_path,
                    http_method,
                    engine.get_trace_for_llm()
                )
            except Exception as e:
                logger.warning(f"LLM analysis failed: {e}")
                llm_result = {
                    "mermaid_diagram": trace_result.mermaid_diagram,
                    "explanation": "LLM explanation not available."
                }
        
        # Return result with LLM-generated content
        return {
            **trace_result.dict(),
            "mermaid_diagram": llm_result["mermaid_diagram"] if llm_result else trace_result.mermaid_diagram,
            "llm_explanation": llm_result["explanation"] if llm_result else None
        }
    except Exception as e:
        logger.error(f"Failed to trace endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


async def _get_llm_trace_analysis(
    endpoint_path: str,
    http_method: str,
    trace_data: str
) -> Dict[str, str]:
    """Get LLM-powered Mermaid diagram and explanation"""
    try:
        import google.generativeai as genai
        from src.config import settings
        
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        
        prompt = f"""You are an expert code analyst. Analyze this API endpoint execution trace and generate:

1. A Mermaid flowchart diagram showing the sequential execution flow
2. A detailed explanation of the endpoint

**Endpoint:** {http_method} {endpoint_path}

**Execution Trace:**
{trace_data}

**YOUR RESPONSE MUST BE IN THIS EXACT FORMAT:**

## MERMAID_DIAGRAM_START
```mermaid
flowchart TD
    A["Step 1: API Request"] --> B["Step 2: Handler"]
    B --> C["Step 3: Processing"]
    C --> D["Step 4: Response"]
```
## MERMAID_DIAGRAM_END

## EXPLANATION_START
### Overview
(What this endpoint does in 1-2 sentences)

### Step-by-Step Flow
(Explain each step in the execution sequence)

### Data Flow
(How data moves through the system)

### Error Handling
(How errors are caught and handled)

### Key Insights
(Any notable patterns or best practices)
## EXPLANATION_END

**CRITICAL MERMAID RULES - FOLLOW EXACTLY:**
1. ALWAYS use double quotes for ALL labels: A["Label text"]
2. Use simple node IDs: A, B, C, D, E (single letters)
3. Do NOT use special characters like : / < > in labels
4. Replace / with - and : with blank in label text
5. Use --> for solid arrows
6. Use -.-> for dashed arrows (error paths)
7. Use subgraph Name\\n...\\nend for grouping
8. Keep labels SHORT - max 5 words per label

EXAMPLE OF CORRECT SYNTAX:
```mermaid
flowchart TD
    A["POST api-v1-ingest-git"] --> B["ingest_git_repository handler"]
    B --> C["RepositoryIngestor init"]
    C --> D["Process git repo"]
    D --> E["Return IngestResponse"]
    C -.-> F["Error - HTTPException"]
```"""


        response = model.generate_content(prompt)
        response_text = response.text
        
        # Parse the response to extract diagram and explanation
        mermaid_diagram = "flowchart TD\n    A[Diagram generation failed]"
        explanation = "Unable to parse LLM response."
        
        # Extract Mermaid diagram
        if "MERMAID_DIAGRAM_START" in response_text and "MERMAID_DIAGRAM_END" in response_text:
            start = response_text.find("MERMAID_DIAGRAM_START") + len("MERMAID_DIAGRAM_START")
            end = response_text.find("MERMAID_DIAGRAM_END")
            mermaid_section = response_text[start:end].strip()
            
            # Extract just the mermaid code
            if "```mermaid" in mermaid_section:
                mermaid_start = mermaid_section.find("```mermaid") + len("```mermaid")
                mermaid_end = mermaid_section.find("```", mermaid_start)
                mermaid_diagram = mermaid_section[mermaid_start:mermaid_end].strip()
            elif "```" in mermaid_section:
                mermaid_start = mermaid_section.find("```") + 3
                mermaid_end = mermaid_section.find("```", mermaid_start)
                mermaid_diagram = mermaid_section[mermaid_start:mermaid_end].strip()
            else:
                mermaid_diagram = mermaid_section
        
        # Extract explanation
        if "EXPLANATION_START" in response_text and "EXPLANATION_END" in response_text:
            start = response_text.find("EXPLANATION_START") + len("EXPLANATION_START")
            end = response_text.find("EXPLANATION_END")
            explanation = response_text[start:end].strip()
        elif "### Overview" in response_text:
            # Fallback: find from Overview to end
            start = response_text.find("### Overview")
            explanation = response_text[start:].strip()
        
        return {
            "mermaid_diagram": mermaid_diagram,
            "explanation": explanation
        }
    except Exception as e:
        logger.error(f"LLM trace analysis failed: {e}")
        return {
            "mermaid_diagram": "flowchart TD\n    A[LLM Error]",
            "explanation": f"Unable to generate LLM analysis: {str(e)}"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.app_env == "development" else False
    )
