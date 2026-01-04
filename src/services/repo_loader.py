"""
Repository Cloning and Loading Service
"""
import os
import shutil
import stat
from pathlib import Path
from typing import Optional
import logging
import hashlib
from git import Repo as GitRepo, GitCommandError

from src.config import settings
from src.models import Repo, SourceType

logger = logging.getLogger(__name__)


class RepositoryLoader:
    """Handles repository cloning and loading"""
    
    def __init__(self, temp_dir: str = None):
        """Initialize repository loader
        
        Args:
            temp_dir: Temporary directory for cloning repos
        """
        self.temp_dir = Path(temp_dir or settings.temp_repo_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def clone_git_repo(self, remote_url: str, repo_name: str) -> tuple[Repo, Path]:
        """Clone a Git repository
        
        Args:
            remote_url: Git repository URL
            repo_name: Name for the repository
            
        Returns:
            Tuple of (Repo model, local path)
        """
        def handle_remove_readonly(func, path, exc):
            """Error handler for Windows read-only files"""
            os.chmod(path, stat.S_IWRITE)
            func(path)
        
        # Create unique directory for this repo
        repo_hash = hashlib.md5(remote_url.encode()).hexdigest()[:8]
        local_path = self.temp_dir / f"{repo_name}_{repo_hash}"
        
        # Remove if exists
        if local_path.exists():
            logger.info(f"Removing existing clone at {local_path}")
            shutil.rmtree(local_path, onerror=handle_remove_readonly)
        
        try:
            logger.info(f"Cloning repository from {remote_url}")
            git_repo = GitRepo.clone_from(remote_url, local_path, depth=1)
            
            # Get current commit hash
            commit_hash = git_repo.head.commit.hexsha
            
            repo = Repo(
                name=repo_name,
                source_type=SourceType.GIT_REMOTE,
                remote_url=remote_url
            )
            
            logger.info(f"Successfully cloned {repo_name} at commit {commit_hash[:8]}")
            return repo, local_path
            
        except GitCommandError as e:
            logger.error(f"Failed to clone repository: {e}")
            raise
    
    def load_local_git_repo(self, local_path: str, repo_name: str = None) -> tuple[Repo, Path]:
        """Load an existing local Git repository
        
        Args:
            local_path: Path to local Git repository
            repo_name: Optional name (defaults to directory name)
            
        Returns:
            Tuple of (Repo model, local path)
        """
        path = Path(local_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {local_path}")
        
        if not (path / ".git").exists():
            raise ValueError(f"Not a Git repository: {local_path}")
        
        try:
            git_repo = GitRepo(path)
            commit_hash = git_repo.head.commit.hexsha
            
            # Get remote URL if available
            remote_url = None
            if git_repo.remotes:
                remote_url = git_repo.remotes.origin.url
            
            repo = Repo(
                name=repo_name or path.name,
                source_type=SourceType.GIT_LOCAL,
                remote_url=remote_url
            )
            
            logger.info(f"Loaded local repository {repo.name} at commit {commit_hash[:8]}")
            return repo, path
            
        except Exception as e:
            logger.error(f"Failed to load local repository: {e}")
            raise
    
    def load_directory(self, directory_path: str, repo_name: str = None) -> tuple[Repo, Path]:
        """Load a directory (non-Git) as a repository
        
        Args:
            directory_path: Path to directory
            repo_name: Optional name (defaults to directory name)
            
        Returns:
            Tuple of (Repo model, local path)
        """
        path = Path(directory_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory_path}")
        
        if not path.is_dir():
            raise ValueError(f"Not a directory: {directory_path}")
        
        repo = Repo(
            name=repo_name or path.name,
            source_type=SourceType.DIRECTORY,
            remote_url=None
        )
        
        logger.info(f"Loaded directory {repo.name}")
        return repo, path
    
    def cleanup(self, local_path: Path) -> None:
        """Clean up temporary repository clone
        
        Args:
            local_path: Path to remove
        """
        def handle_remove_readonly(func, path, exc):
            """Error handler for Windows read-only files"""
            os.chmod(path, stat.S_IWRITE)
            func(path)
        
        if local_path.exists() and local_path.is_relative_to(self.temp_dir):
            logger.info(f"Cleaning up {local_path}")
            shutil.rmtree(local_path, onerror=handle_remove_readonly)
