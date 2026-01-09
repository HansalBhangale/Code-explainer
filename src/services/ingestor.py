"""
Repository Ingestion Orchestrator
Coordinates the entire repository analysis pipeline
"""

from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

from src.models import (
    Repo,
    Snapshot,
    File,
    Symbol,
    Import,
    Endpoint,
    Dependency,
    ModelUsage,
    SnapshotStatus,
)
from src.database.repository import (
    RepositoryDAO,
    SnapshotDAO,
    FileDAO,
    SymbolDAO,
    ImportDAO,
    EndpointDAO,
    DependencyDAO,
    ModelUsageDAO,
)
from src.services.repo_loader import RepositoryLoader
from src.services.file_scanner import FileScanner
from src.services.import_resolver import ImportResolver
from src.parsers.python_parser import PythonASTParser
from src.parsers.fastapi_parser import FastAPIParser
from src.parsers.javascript_parser import JavaScriptParser
from src.parsers.javascript_framework_detector import JavaScriptFrameworkDetector

logger = logging.getLogger(__name__)


class RepositoryIngestor:
    """Orchestrates repository ingestion and analysis"""

    def __init__(self):
        self.repo_loader = RepositoryLoader()
        self.file_scanner = FileScanner()
        self.python_parser = PythonASTParser()
        self.fastapi_parser = FastAPIParser()
        self.javascript_parser = JavaScriptParser()
        self.js_framework_detector = JavaScriptFrameworkDetector()

    def ingest_git_repository(self, remote_url: str, repo_name: str) -> Dict[str, Any]:
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
                "lang_profile": snapshot.lang_profile,
            }

        finally:
            # Cleanup temporary clone
            self.repo_loader.cleanup(local_path)

    def ingest_local_repository(
        self, local_path: str, repo_name: Optional[str] = None
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
            "lang_profile": snapshot.lang_profile,
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
        snapshot = Snapshot(repo_id=repo.repo_id, status=SnapshotStatus.PROCESSING)
        snapshot = SnapshotDAO.create_snapshot(snapshot)

        try:
            # Scan files
            logger.info("Scanning repository files...")
            files_by_language, large_files = self.file_scanner.scan_repository(
                repo_path
            )

            # Calculate language profile
            lang_profile = {
                lang: len(files) for lang, files in files_by_language.items()
            }
            if large_files:
                lang_profile["large_files"] = len(large_files)
            snapshot.lang_profile = lang_profile

            # Process files by language
            all_files = []
            all_symbols: List[Symbol] = []
            all_imports_data: List[Any] = []
            all_call_sites: List = []
            all_type_annotations: List = []
            all_fastapi_endpoints: List[Dict[str, Any]] = []
            all_fastapi_dependencies: List[Dict[str, Any]] = []
            all_fastapi_model_usages: List[Dict[str, Any]] = []
            symbol_by_name: Dict[str, str] = {}  # symbol name -> symbol_id
            file_path_to_id: Dict[str, str] = {}  # file path -> file_id

            # Process each language group
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
                        tags=[],
                    )
                    all_files.append(file)
                    file_path_to_id[str(relative_path)] = file.file_id

                    # Parse Python files
                    if language == "python":
                        symbols, imports = self.python_parser.parse_file(
                            file_path, file.file_id, snapshot.snapshot_id
                        )
                        all_symbols.extend(symbols)

                        # Build symbol name mapping
                        for symbol in symbols:
                            symbol_by_name[symbol.name] = symbol.symbol_id

                        # Store import data with file info
                        for imp_data in imports:
                            imp_data["file_id"] = file.file_id
                            imp_data["file_path"] = str(relative_path)
                        all_imports_data.extend(imports)

                        # Extract call sites and type annotations
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                source = f.read()
                            tree = __import__("ast").parse(
                                source, filename=str(file_path)
                            )

                            call_sites = self.python_parser.extract_call_sites(
                                tree, symbols
                            )
                            all_call_sites.extend(call_sites)

                            type_annotations = (
                                self.python_parser.extract_type_annotations(
                                    tree, symbols
                                )
                            )
                            all_type_annotations.extend(type_annotations)
                        except Exception as e:
                            logger.warning(
                                f"Failed to extract calls/types from {file_path.name}: {e}"
                            )

                        # Parse FastAPI constructs
                        fastapi_data = self.fastapi_parser.parse_file(
                            file_path, file.file_id, snapshot.snapshot_id
                        )
                        all_fastapi_endpoints.extend(fastapi_data["endpoints"])
                        all_fastapi_dependencies.extend(fastapi_data["dependencies"])
                        all_fastapi_model_usages.extend(fastapi_data["model_usages"])

                    # Parse JavaScript/TypeScript files
                    elif language in ("javascript", "typescript"):
                        symbols, imports = self.javascript_parser.parse_file(
                            file_path, file.file_id, snapshot.snapshot_id
                        )
                        all_symbols.extend(symbols)

                        # Build symbol name mapping
                        for symbol in symbols:
                            symbol_by_name[symbol.name] = symbol.symbol_id

                        # Imports already have file_id set during construction
                        all_imports_data.extend(imports)

                        # Extract call sites and type annotations
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                source = f.read()
                            tree = self.javascript_parser._parser.parse(
                                bytes(source, "utf8")
                            )

                            call_sites = self.javascript_parser.extract_call_sites(
                                tree.root_node, source, symbols
                            )
                            all_call_sites.extend(call_sites)

                            type_annotations = (
                                self.javascript_parser.extract_type_annotations(
                                    tree.root_node, source, symbols
                                )
                            )
                            all_type_annotations.extend(type_annotations)
                        except Exception as e:
                            logger.warning(
                                f"Failed to extract calls/types from {file_path.name}: {e}"
                            )

                        # Detect JavaScript framework constructs (only if parser is initialized)
                        if self.javascript_parser._parser:
                            try:
                                # Re-parse for framework detection
                                with open(file_path, "r", encoding="utf-8") as f:
                                    source = f.read()
                                tree = self.javascript_parser._parser.parse(
                                    bytes(source, "utf8")
                                )

                                framework_data = (
                                    self.js_framework_detector.detect_frameworks(
                                        tree.root_node,
                                        source,
                                        file_path,
                                        file.file_id,
                                        snapshot.snapshot_id,
                                    )
                                )
                                all_fastapi_endpoints.extend(
                                    framework_data["endpoints"]
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to detect frameworks in {file_path}: {e}"
                                )
                        else:
                            logger.debug(
                                f"JavaScript parser not initialized, skipping framework detection for {file_path}"
                            )

            # Process large files (index without parsing)
            if large_files:
                logger.info(
                    f"Indexing {len(large_files)} large files (without parsing)..."
                )
                for file_path in large_files:
                    relative_path = file_path.relative_to(repo_path)
                    language = (
                        self.file_scanner._detect_language(file_path) or "unknown"
                    )

                    file = File(
                        snapshot_id=snapshot.snapshot_id,
                        path=str(relative_path),
                        language=language,
                        sha256=self.file_scanner.compute_file_hash(file_path),
                        loc=0,  # Skip line counting for large files
                        is_test=False,
                        tags=["large_file"],  # Mark as large file
                    )
                    all_files.append(file)

            # Batch insert files
            logger.info(f"Persisting {len(all_files)} files to database...")
            FileDAO.batch_create_files(all_files)

            # Batch insert symbols
            if all_symbols:
                logger.info(f"Persisting {len(all_symbols)} symbols to database...")
                SymbolDAO.batch_create_symbols(all_symbols)

            # Batch insert call sites
            if all_call_sites:
                logger.info(
                    f"Persisting {len(all_call_sites)} call sites to database..."
                )
                from src.database.call_graph_dao import CallGraphDAO

                CallGraphDAO.batch_create_call_sites(all_call_sites)
                # Resolve call sites to actual symbols
                CallGraphDAO.resolve_call_sites(snapshot.snapshot_id)

            # Batch insert type annotations
            if all_type_annotations:
                logger.info(
                    f"Persisting {len(all_type_annotations)} type annotations to database..."
                )
                from src.database.type_dao import TypeDAO

                TypeDAO.batch_create_types(all_type_annotations)

            # Process FastAPI endpoints
            if all_fastapi_endpoints:
                logger.info(
                    f"Processing {len(all_fastapi_endpoints)} FastAPI endpoints..."
                )

                # Create Endpoint objects and link to handler symbols
                endpoints = []
                handler_to_endpoint_id = {}  # Map handler names to endpoint IDs

                for ep_data in all_fastapi_endpoints:
                    # Find handler symbol ID
                    handler_name = ep_data["handler_function"]
                    symbol_id = symbol_by_name.get(handler_name)

                    endpoint = Endpoint(
                        snapshot_id=ep_data["snapshot_id"],
                        file_id=ep_data["file_id"],
                        symbol_id=symbol_id,
                        http_method=ep_data["http_method"],
                        path=ep_data["path"],
                        router_prefix=ep_data.get("router_prefix"),
                        tags=ep_data.get("tags", []),
                        summary=ep_data.get("summary"),
                        description=ep_data.get("description"),
                        response_model=ep_data.get("response_model"),
                        status_code=ep_data.get("status_code", 200),
                        deprecated=ep_data.get("deprecated", False),
                    )
                    endpoints.append(endpoint)
                    handler_to_endpoint_id[handler_name] = endpoint.endpoint_id

                EndpointDAO.batch_create_endpoints(endpoints)

            # Process dependencies
            if all_fastapi_dependencies:
                logger.info(
                    f"Processing {len(all_fastapi_dependencies)} dependencies..."
                )

                dependencies = []
                for dep_data in all_fastapi_dependencies:
                    # Find endpoint ID for this dependency
                    handler_name = dep_data.get("endpoint_handler")
                    endpoint_id = (
                        handler_to_endpoint_id.get(handler_name)
                        if handler_name
                        else None
                    )

                    dependency = Dependency(
                        snapshot_id=dep_data["snapshot_id"],
                        endpoint_id=endpoint_id,
                        parameter_name=dep_data["parameter_name"],
                        dependency_function=dep_data["dependency_function"],
                        scope=dep_data["scope"],
                    )
                    dependencies.append(dependency)

                DependencyDAO.batch_create_dependencies(dependencies)

            # Process model usages
            if all_fastapi_model_usages:
                logger.info(
                    f"Processing {len(all_fastapi_model_usages)} model usages..."
                )

                model_usages = []
                for usage_data in all_fastapi_model_usages:
                    # Find endpoint ID for this model usage
                    handler_name = usage_data.get("endpoint_handler")
                    endpoint_id = (
                        handler_to_endpoint_id.get(handler_name)
                        if handler_name
                        else None
                    )

                    usage = ModelUsage(
                        snapshot_id=usage_data["snapshot_id"],
                        endpoint_id=endpoint_id,
                        model_name=usage_data["model_name"],
                        usage_type=usage_data["usage_type"],
                        is_list=usage_data.get("is_list", False),
                    )
                    model_usages.append(usage)

                ModelUsageDAO.batch_track_usages(model_usages)

            # Process imports and build import graph
            if all_imports_data:
                logger.info(f"Processing {len(all_imports_data)} import statements...")

                # Create import resolver
                resolver = ImportResolver(repo_path, file_path_to_id)

                # Create Import objects and resolve dependencies
                all_imports = []
                import_edges = []

                for imp_data in all_imports_data:
                    # Check if imp_data is already an Import object or a dictionary
                    if isinstance(imp_data, Import):
                        # Already an Import object (from JavaScript parser)
                        import_obj = imp_data
                        file_id = imp_data.file_id
                        module = imp_data.module
                        is_relative = imp_data.is_relative
                        # Get file_path from file_id
                        file_path = None
                        for path, fid in file_path_to_id.items():
                            if fid == file_id:
                                file_path = path
                                break
                    else:
                        # Dictionary (from Python parser)
                        import_obj = Import(
                            snapshot_id=snapshot.snapshot_id,
                            file_id=imp_data["file_id"],
                            module=imp_data["module"],
                            imported_names=imp_data["imported_names"],
                            alias=imp_data["alias"],
                            is_relative=imp_data["is_relative"],
                            line_number=imp_data["line_number"],
                        )
                        file_id = imp_data["file_id"]
                        module = imp_data["module"]
                        is_relative = imp_data["is_relative"]
                        file_path = imp_data["file_path"]

                    all_imports.append(import_obj)

                    # Resolve import to file ID
                    target_file_id = resolver.resolve_import(
                        module, file_path, is_relative
                    )

                    # Create edge if target is internal
                    if target_file_id:
                        import_edges.append(
                            {
                                "src_file_id": file_id,
                                "dst_file_id": target_file_id,
                                "module": module,
                                "line_number": imp_data["line_number"],
                            }
                        )

                # Batch insert imports
                ImportDAO.batch_create_imports(all_imports)

                # Batch create import edges
                if import_edges:
                    logger.info(f"Creating {len(import_edges)} import relationships...")
                    ImportDAO.batch_create_import_edges(import_edges)

            # Update snapshot with lang_profile
            SnapshotDAO.update_snapshot_lang_profile(
                snapshot.snapshot_id, snapshot.lang_profile
            )

            # Update snapshot status
            SnapshotDAO.update_snapshot_status(
                snapshot.snapshot_id, SnapshotStatus.COMPLETED
            )
            snapshot.status = SnapshotStatus.COMPLETED

            logger.info(f"Repository ingestion completed: {snapshot.snapshot_id}")
            return snapshot

        except Exception as e:
            logger.error(f"Repository ingestion failed: {e}")
            SnapshotDAO.update_snapshot_status(
                snapshot.snapshot_id, SnapshotStatus.FAILED
            )
            raise
