"""
Repository Ingestion Orchestrator
Coordinates the entire repository analysis pipeline
"""
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from src.models import Repo, Snapshot, File, Import, SnapshotStatus, SourceType
from src.database import db
from src.database.repository import RepositoryDAO, SnapshotDAO, FileDAO, SymbolDAO, ImportDAO
from src.services.repo_loader import RepositoryLoader
from src.services.file_scanner import FileScanner
from src.services.import_resolver import ImportResolver
from src.parsers.python_parser import PythonASTParser

logger = logging.getLogger(__name__)


class RepositoryIngestor:
    """Orchestrates repository ingestion and analysis"""
    
    def __init__(self):
        self.repo_loader = RepositoryLoader()
        self.file_scanner = FileScanner()
        self.python_parser = PythonASTParser()
    
    def ingest_git_repository(
        self,
        remote_url: str,
        repo_name: str
    ) -> Dict[str, Any]:
        """Ingest a Git repository from remote URL
        
        Args:
            remote_url: Git repository URL
            repo_name: Name for the repository
            
        Returns:
            Ingestion result with repo_id and snapshot_id
        """
        logger.info(f"Starting ingestion of Git repository: {repo_name}")
        
        # Clone repository
        repo, local_path = self.repo_loader.clone_git_repo(remote_url, repo_name)
        
        try:
            # Create repository in database
            repo = RepositoryDAO.create_repo(repo)
            
            # Process repository
            snapshot = self._process_repository(repo, local_path)
            
            return {
                "repo_id": repo.repo_id,
                "repo_name": repo.name,
                "snapshot_id": snapshot.snapshot_id,
                "status": snapshot.status.value,
                "lang_profile": snapshot.lang_profile
            }
        
        finally:
            # Cleanup temporary clone
            self.repo_loader.cleanup(local_path)
    
    def ingest_local_repository(
        self,
        local_path: str,
        repo_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Ingest a local repository
        
        Args:
            local_path: Path to local repository
            repo_name: Optional repository name
            
        Returns:
            Ingestion result with repo_id and snapshot_id
        """
        logger.info(f"Starting ingestion of local repository: {local_path}")
        
        # Load repository
        repo, path = self.repo_loader.load_local_git_repo(local_path, repo_name)
        
        # Create repository in database
        repo = RepositoryDAO.create_repo(repo)
        
        # Process repository
        snapshot = self._process_repository(repo, path)
        
        return {
            "repo_id": repo.repo_id,
            "repo_name": repo.name,
            "snapshot_id": snapshot.snapshot_id,
            "status": snapshot.status.value,
            "lang_profile": snapshot.lang_profile
        }
    
    def _process_repository(self, repo: Repo, repo_path: Path) -> Snapshot:
        """Process repository and create snapshot
        
        Args:
            repo: Repo model instance
            repo_path: Path to repository
            
        Returns:
            Created Snapshot instance
        """
        # Create snapshot
        snapshot = Snapshot(
            repo_id=repo.repo_id,
            status=SnapshotStatus.PROCESSING
        )
        snapshot = SnapshotDAO.create_snapshot(snapshot)
        
        try:
            # Scan files
            logger.info("Scanning repository files...")
            files_by_language, large_files = self.file_scanner.scan_repository(repo_path)
            
            # Calculate language profile
            lang_profile = {
                lang: len(files) for lang, files in files_by_language.items()
            }
            if large_files:
                lang_profile["large_files"] = len(large_files)
            snapshot.lang_profile = lang_profile
            
            # Process files by language
            all_files = []
            all_symbols = []
            all_imports_data = []  # Store raw import data
            file_path_to_id = {}  # Map file paths to file IDs
            
            for language, file_paths in files_by_language.items():
                logger.info(f"Processing {len(file_paths)} {language} files...")
                
                for file_path in file_paths:
                    # Create file record
                    relative_path = file_path.relative_to(repo_path)
                    
                    file = File(
                        snapshot_id=snapshot.snapshot_id,
                        path=str(relative_path),
                        language=language,
                        sha256=self.file_scanner.compute_file_hash(file_path),
                        loc=self.file_scanner.count_lines(file_path),
                        is_test=self.file_scanner.is_test_file(file_path),
                        tags=[]
                    )
                    all_files.append(file)
                    file_path_to_id[str(relative_path)] = file.file_id
                    
                    # Parse Python files
                    if language == "python":
                        symbols, imports = self.python_parser.parse_file(
                            file_path,
                            file.file_id,
                            snapshot.snapshot_id
                        )
                        all_symbols.extend(symbols)
                        
                        # Store import data with file info
                        for imp_data in imports:
                            imp_data['file_id'] = file.file_id
                            imp_data['file_path'] = str(relative_path)
                        all_imports_data.extend(imports)
            
            # Process large files (index without parsing)
            if large_files:
                logger.info(f"Indexing {len(large_files)} large files (without parsing)...")
                for file_path in large_files:
                    relative_path = file_path.relative_to(repo_path)
                    language = self.file_scanner._detect_language(file_path) or "unknown"
                    
                    file = File(
                        snapshot_id=snapshot.snapshot_id,
                        path=str(relative_path),
                        language=language,
                        sha256=self.file_scanner.compute_file_hash(file_path),
                        loc=0,  # Skip line counting for large files
                        is_test=False,
                        tags=["large_file"]  # Mark as large file
                    )
                    all_files.append(file)
            
            # Batch insert files
            logger.info(f"Persisting {len(all_files)} files to database...")
            FileDAO.batch_create_files(all_files)
            
            # Batch insert symbols
            if all_symbols:
                logger.info(f"Persisting {len(all_symbols)} symbols to database...")
                SymbolDAO.batch_create_symbols(all_symbols)
            
            # Process imports and build import graph
            if all_imports_data:
                logger.info(f"Processing {len(all_imports_data)} import statements...")
                
                # Create import resolver
                resolver = ImportResolver(repo_path, file_path_to_id)
                
                # Create Import objects and resolve dependencies
                all_imports = []
                import_edges = []
                
                for imp_data in all_imports_data:
                    # Create Import object
                    import_obj = Import(
                        snapshot_id=snapshot.snapshot_id,
                        file_id=imp_data['file_id'],
                        module=imp_data['module'],
                        imported_names=imp_data['imported_names'],
                        alias=imp_data['alias'],
                        is_relative=imp_data['is_relative'],
                        line_number=imp_data['line_number']
                    )
                    all_imports.append(import_obj)
                    
                    # Resolve import to file ID
                    target_file_id = resolver.resolve_import(
                        imp_data['module'],
                        imp_data['file_path'],
                        imp_data['is_relative']
                    )
                    
                    # Create edge if target is internal
                    if target_file_id:
                        import_edges.append({
                            'src_file_id': imp_data['file_id'],
                            'dst_file_id': target_file_id,
                            'module': imp_data['module'],
                            'line_number': imp_data['line_number']
                        })
                
                # Batch insert imports
                ImportDAO.batch_create_imports(all_imports)
                
                # Batch create import edges
                if import_edges:
                    logger.info(f"Creating {len(import_edges)} import relationships...")
                    ImportDAO.batch_create_import_edges(import_edges)
            
            # Update snapshot status
            SnapshotDAO.update_snapshot_status(
                snapshot.snapshot_id,
                SnapshotStatus.COMPLETED
            )
            snapshot.status = SnapshotStatus.COMPLETED
            
            logger.info(f"Repository ingestion completed: {snapshot.snapshot_id}")
            return snapshot
        
        except Exception as e:
            logger.error(f"Repository ingestion failed: {e}")
            SnapshotDAO.update_snapshot_status(
                snapshot.snapshot_id,
                SnapshotStatus.FAILED
            )
            raise
