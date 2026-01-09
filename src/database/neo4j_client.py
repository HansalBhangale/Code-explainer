"""
Neo4j Database Connection and Schema Management
"""

from neo4j import GraphDatabase, Driver, Session
from typing import Any, Dict, List, Optional
import logging
from contextlib import contextmanager

from src.config import settings

logger = logging.getLogger(__name__)


class Neo4jConnection:
    """Manages Neo4j database connection and operations"""

    def __init__(self, uri: str = None, user: str = None, password: str = None):
        """Initialize Neo4j connection

        Args:
            uri: Neo4j connection URI (defaults to settings)
            user: Neo4j username (defaults to settings)
            password: Neo4j password (defaults to settings)
        """
        self.uri = uri or settings.neo4j_uri
        self.user = user or settings.neo4j_user
        self.password = password or settings.neo4j_password
        self._driver: Optional[Driver] = None

    def connect(self) -> None:
        """Establish connection to Neo4j database"""
        try:
            self._driver = GraphDatabase.driver(
                self.uri, auth=(self.user, self.password)
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {self.uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    def close(self) -> None:
        """Close the database connection"""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j connection closed")

    @contextmanager
    def session(self, **kwargs) -> Session:
        """Context manager for Neo4j sessions

        Yields:
            Neo4j session object
        """
        if not self._driver:
            raise RuntimeError("Database not connected. Call connect() first.")

        session = self._driver.session(**kwargs)
        try:
            yield session
        finally:
            session.close()

    def execute_query(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query and return results

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            List of result records as dictionaries
        """
        with self.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def execute_write(
        self, query: str, parameters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute a write transaction

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            List of result records as dictionaries
        """

        def _write_tx(tx, query, params):
            result = tx.run(query, params)
            return [record.data() for record in result]

        with self.session() as session:
            return session.execute_write(_write_tx, query, parameters or {})

    def initialize_schema(self) -> None:
        """Initialize Neo4j schema with constraints and indexes"""
        logger.info("Initializing Neo4j schema...")

        # Unique constraints (also create indexes)
        constraints = [
            "CREATE CONSTRAINT repo_id IF NOT EXISTS FOR (r:Repo) REQUIRE r.repo_id IS UNIQUE",
            "CREATE CONSTRAINT snapshot_id IF NOT EXISTS FOR (s:Snapshot) REQUIRE s.snapshot_id IS UNIQUE",
            "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (f:File) REQUIRE f.file_id IS UNIQUE",
            "CREATE CONSTRAINT symbol_id IF NOT EXISTS FOR (sym:Symbol) REQUIRE sym.symbol_id IS UNIQUE",
            "CREATE CONSTRAINT endpoint_id IF NOT EXISTS FOR (e:Endpoint) REQUIRE e.endpoint_id IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
            "CREATE CONSTRAINT finding_id IF NOT EXISTS FOR (f:Finding) REQUIRE f.finding_id IS UNIQUE",
            "CREATE CONSTRAINT metric_id IF NOT EXISTS FOR (m:Metric) REQUIRE m.metric_id IS UNIQUE",
            "CREATE CONSTRAINT diff_id IF NOT EXISTS FOR (d:Diff) REQUIRE d.diff_id IS UNIQUE",
            "CREATE CONSTRAINT impact_id IF NOT EXISTS FOR (i:ImpactResult) REQUIRE i.impact_id IS UNIQUE",
            "CREATE CONSTRAINT call_id IF NOT EXISTS FOR (c:CallSite) REQUIRE c.call_id IS UNIQUE",
            "CREATE CONSTRAINT type_id IF NOT EXISTS FOR (t:TypeAnnotation) REQUIRE t.type_id IS UNIQUE",
        ]

        for constraint in constraints:
            try:
                self.execute_write(constraint)
                logger.info(
                    f"Created constraint: {constraint.split('FOR')[1].split('REQUIRE')[0].strip()}"
                )
            except Exception as e:
                logger.warning(f"Constraint already exists or error: {e}")

        # Full-text search indexes
        fulltext_indexes = [
            """
            CREATE FULLTEXT INDEX symbol_search IF NOT EXISTS
            FOR (s:Symbol) ON EACH [s.name, s.qualname, s.signature]
            """,
            """
            CREATE FULLTEXT INDEX file_search IF NOT EXISTS
            FOR (f:File) ON EACH [f.path]
            """,
            """
            CREATE FULLTEXT INDEX chunk_search IF NOT EXISTS
            FOR (c:Chunk) ON EACH [c.content]
            """,
        ]

        for index in fulltext_indexes:
            try:
                self.execute_write(index)
                logger.info("Created fulltext index")
            except Exception as e:
                logger.warning(f"Fulltext index already exists or error: {e}")

        # Vector index for embeddings (Neo4j 5.11+)
        try:
            vector_index = f"""
            CREATE VECTOR INDEX chunk_embeddings IF NOT EXISTS
            FOR (c:Chunk) ON (c.embedding)
            OPTIONS {{indexConfig: {{
              `vector.dimensions`: {settings.embedding_dimension},
              `vector.similarity_function`: 'cosine'
            }}}}
            """
            self.execute_write(vector_index)
            logger.info("Created vector index for embeddings")
        except Exception as e:
            logger.warning(f"Vector index already exists or error: {e}")

        logger.info("Schema initialization complete")

    def clear_database(self) -> None:
        """Clear all nodes and relationships (USE WITH CAUTION!)"""
        logger.warning("Clearing entire database...")
        self.execute_write("MATCH (n) DETACH DELETE n")
        logger.info("Database cleared")


# Global database instance
db = Neo4jConnection()
