"""
RAG-powered Chat Service
Provides conversational interface for code exploration
"""
import google.generativeai as genai
from typing import List, Dict, Any, Optional
import os
import logging
from src.config import settings
from src.services.retriever import HybridRetriever
from src.database.chunk_dao import ChunkDAO

logger = logging.getLogger(__name__)


class CodeChatService:
    """
    Conversational AI service for exploring codebases
    Uses RAG to retrieve relevant code when needed
    """
    
    def __init__(self):
        """Initialize chat service with Gemini"""
        api_key = settings.gemini_api_key or os.getenv('GEMINI_API_KEY')
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)
        self.retriever = HybridRetriever()
        self.chunk_dao = ChunkDAO()
        
        logger.info(f"Initialized CodeChatService with model: {settings.gemini_model}")
    
    def chat(
        self,
        query: str,
        snapshot_id: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Chat with the codebase
        
        Args:
            query: User's question
            snapshot_id: Snapshot to search in
            conversation_history: Previous messages [{"role": "user"/"assistant", "content": "..."}]
            top_k: Number of code chunks to retrieve
            
        Returns:
            Response with answer and retrieved code chunks
        """
        try:
            # Determine if we need to retrieve code
            needs_code = self._should_retrieve_code(query)
            
            retrieved_chunks = []
            context = ""
            
            if needs_code:
                # Retrieve relevant code chunks
                logger.info(f"Retrieving code for query: {query}")
                results = self.retriever.search(
                    query=query,
                    snapshot_id=snapshot_id,
                    top_k=top_k,
                    lexical_weight=0.3,
                    vector_weight=0.5,
                    graph_weight=0.2,
                    expand_graph=True
                )
                
                # Build context from retrieved chunks
                context = self._build_code_context(results[:3])  # Use top 3
                retrieved_chunks = results[:3]
            
            # Generate conversational response
            answer = self._generate_response(
                query=query,
                code_context=context,
                conversation_history=conversation_history or []
            )
            
            return {
                "answer": answer,
                "retrieved_chunks": retrieved_chunks,
                "used_code_context": needs_code
            }
            
        except Exception as e:
            logger.error(f"Chat failed: {e}", exc_info=True)
            return {
                "answer": f"I encountered an error: {str(e)}",
                "retrieved_chunks": [],
                "used_code_context": False
            }
    
    def _should_retrieve_code(self, query: str) -> bool:
        """
        Determine if query requires code retrieval
        
        Returns True for code-specific questions, False for general questions
        """
        # Keywords that indicate code-specific questions
        code_keywords = [
            "function", "class", "method", "code", "implementation",
            "how does", "show me", "explain the code", "what does this",
            "parse", "handle", "process", "algorithm", "logic"
        ]
        
        # Keywords that indicate general questions
        general_keywords = [
            "what is this project", "what are the features", "overview",
            "purpose", "what does this project do", "architecture",
            "tech stack", "dependencies"
        ]
        
        query_lower = query.lower()
        
        # Check for general questions first
        if any(keyword in query_lower for keyword in general_keywords):
            return False
        
        # Check for code-specific questions
        if any(keyword in query_lower for keyword in code_keywords):
            return True
        
        # Default: retrieve code for ambiguous queries
        return True
    
    def _build_code_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Build formatted context from code chunks"""
        if not chunks:
            return ""
        
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(f"""
**Code Snippet {i}:**
File: {chunk['file_path']}
Symbol: {chunk['symbol_name']} ({chunk['symbol_kind']})

```python
{chunk['content']}
```
""")
        
        return "\n".join(context_parts)
    
    def _generate_response(
        self,
        query: str,
        code_context: str,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """Generate conversational response using Gemini"""
        
        # Build conversation context
        history_text = ""
        if conversation_history:
            history_text = "\n**Previous Conversation:**\n"
            for msg in conversation_history[-4:]:  # Last 4 messages
                role = "User" if msg["role"] == "user" else "Assistant"
                history_text += f"{role}: {msg['content']}\n"
        
        # Build prompt
        if code_context:
            # Code-specific response
            prompt = f"""You are a helpful AI assistant that explains code from a Python codebase.

{history_text}

**User Question:** {query}

**Relevant Code from the Codebase:**
{code_context}

**Instructions:**
1. Answer the user's question clearly and conversationally
2. Reference the specific code snippets when relevant
3. Explain what the code does in simple terms
4. If showing code, use proper formatting
5. Be concise but thorough
6. Maintain conversation context from previous messages

**Your Response:**
"""
        else:
            # General question response
            prompt = f"""You are a helpful AI assistant for a Python code repository intelligence system.

{history_text}

**User Question:** {query}

**About this System:**
This is a Repository Intelligence Agent - a RAG-powered code exploration system that:
- Parses Python codebases and extracts symbols (functions, classes, etc.)
- Creates semantic embeddings for intelligent code search
- Uses hybrid search (lexical + vector + graph) to find relevant code
- Provides AI-powered explanations of code functionality
- Enables conversational exploration of codebases
- Built with FastAPI, Neo4j, and Google Gemini

**Instructions:**
1. Answer the user's question about the project/system
2. Be informative and conversational
3. Highlight key features and capabilities
4. Keep it concise (2-3 paragraphs max)

**Your Response:**
"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return f"I'm having trouble generating a response right now. Error: {str(e)}"
