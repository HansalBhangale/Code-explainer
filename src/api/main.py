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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True if settings.app_env == "development" else False
    )
