# Repository Intelligence Agent

GenAI-Powered Repository Intelligence Agent that analyzes Python/FastAPI codebases using graph-based representation in Neo4j.

## Features

- **Repository Graph Construction**: Parse and model codebases as knowledge graphs
- **Hybrid Code Retrieval**: Natural language Q&A with citations
- **Deep Trace Mode**: Execution flow analysis for FastAPI endpoints
- **Repository Health Analysis**: Code quality and complexity metrics
- **Smart Diff & Impact Analysis**: Predict change impact using graph traversal
- **MCP Integration**: Modular tool integration via Model Context Protocol

## Quick Start

### 1. Start Neo4j Database

```powershell
docker-compose up -d
```

Access Neo4j Browser at: http://localhost:7474
- Username: `neo4j`
- Password: `repoIntel2024!`

### 2. Install Dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment

```powershell
cp .env.example .env
# Edit .env with your Gemini API key
# Get free API key from: https://aistudio.google.com/apikey
```

### 4. Run the API

```powershell
python -m src.api.main
```

API will be available at: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## API Usage

### Ingest a Git Repository

```bash
curl -X POST "http://localhost:8000/api/v1/ingest/git" \
  -H "Content-Type: application/json" \
  -d '{
    "remote_url": "https://github.com/user/repo.git",
    "repo_name": "my-repo"
  }'
```

### List Repositories

```bash
curl "http://localhost:8000/api/v1/repos"
```

### Get Snapshot Files

```bash
curl "http://localhost:8000/api/v1/snapshots/{snapshot_id}/files"
```

## Project Structure

```
├── src/
│   ├── api/           # FastAPI application
│   ├── database/      # Neo4j client and DAOs
│   ├── models/        # Pydantic data models
│   ├── parsers/       # AST parsers (Python, etc.)
│   ├── services/      # Business logic (ingestion, scanning)
│   └── config.py      # Configuration management
├── docker-compose.yml # Neo4j setup
├── requirements.txt   # Python dependencies
└── .env.example       # Environment template
```

## Technology Stack

- **FastAPI**: API framework
- **Neo4j**: Graph database
- **Python AST**: Static code analysis
- **GitPython**: Repository operations
- **Pydantic**: Data validation

## Development

### Run Tests

```powershell
pytest
```

### Code Formatting

```powershell
black src/
ruff check src/
```

## License

MIT
