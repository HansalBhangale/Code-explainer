"""
Chat API Routes
Conversational interface for code exploration
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from src.services.chat_service import CodeChatService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    """Chat request model"""
    query: str = Field(..., description="User's question")
    snapshot_id: str = Field(..., description="Snapshot ID to search within")
    conversation_history: Optional[List[ChatMessage]] = Field(
        default=None,
        description="Previous conversation messages"
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Number of code chunks to retrieve")


class CodeChunk(BaseModel):
    """Code chunk in response"""
    chunk_id: str
    symbol_name: str
    symbol_kind: str
    file_path: str
    content: str
    score: float


class ChatResponse(BaseModel):
    """Chat response model"""
    answer: str = Field(..., description="AI-generated answer")
    retrieved_chunks: List[Dict[str, Any]] = Field(
        default=[],
        description="Code chunks used for context"
    )
    used_code_context: bool = Field(
        ...,
        description="Whether code was retrieved for this response"
    )


@router.post("/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest):
    """
    Send a message and get a conversational response
    
    The system intelligently decides whether to retrieve code based on your question:
    - Code-specific questions (e.g., "how does the parser work?") → retrieves relevant code
    - General questions (e.g., "what is this project?") → answers without code retrieval
    
    Args:
        request: Chat request with query and optional conversation history
        
    Returns:
        Conversational response with optional code chunks
    """
    try:
        chat_service = CodeChatService()
        
        # Convert Pydantic models to dicts for service
        history = None
        if request.conversation_history:
            history = [{"role": msg.role, "content": msg.content} 
                      for msg in request.conversation_history]
        
        result = chat_service.chat(
            query=request.query,
            snapshot_id=request.snapshot_id,
            conversation_history=history,
            top_k=request.top_k
        )
        
        return ChatResponse(**result)
        
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")
