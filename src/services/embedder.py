"""
Gemini Embedding Service
Generates embeddings using Google's Gemini API
"""
import google.generativeai as genai
from typing import List
import os
import logging
from src.config import settings

logger = logging.getLogger(__name__)


class GeminiEmbedder:
    """
    Embedding service using Google Gemini API
    Model: models/embedding-001 (768 dimensions)
    """
    
    def __init__(self):
        """Initialize Gemini embedder with API key from settings"""
        api_key = settings.gemini_api_key or os.getenv('GEMINI_API_KEY')
        
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not found in settings or environment. "
                "Please set it in .env file or environment variables."
            )
        
        genai.configure(api_key=api_key)
        self.model = settings.embedding_model
        logger.info(f"Initialized Gemini embedder with model: {self.model}")
    
    def generate_embedding(self, text: str, task_type: str = "retrieval_document") -> List[float]:
        """
        Generate embedding for a single text
        
        Args:
            text: Text to embed
            task_type: Task type for embedding (retrieval_document, retrieval_query, etc.)
            
        Returns:
            Embedding vector (768 dimensions)
        """
        try:
            logger.debug(f"Generating embedding with model: {self.model}")
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type=task_type
            )
            return result['embedding']
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            logger.error(f"Model used: {self.model}")
            raise
    
    def batch_generate_embeddings(
        self, 
        texts: List[str], 
        task_type: str = "retrieval_document",
        batch_size: int = 100,
        max_workers: int = 5
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts with batch API and parallel processing
        
        Args:
            texts: List of texts to embed
            task_type: Task type for embedding
            batch_size: Number of texts per API call (Gemini supports up to 100)
            max_workers: Number of parallel API calls
            
        Returns:
            List of embedding vectors
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        total = len(texts)
        logger.info(f"Generating embeddings for {total} texts using batch API + parallel processing...")
        
        # Split into batches
        batches = []
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            batches.append((i, batch))
        
        logger.info(f"Split into {len(batches)} batches, processing {max_workers} in parallel")
        
        # Process batches in parallel
        embeddings = [None] * total  # Pre-allocate list
        
        def process_batch(batch_info):
            start_idx, batch_texts = batch_info
            try:
                # Use Gemini batch API - send all texts in one call
                result = genai.embed_content(
                    model=self.model,
                    content=batch_texts,  # Send list of texts
                    task_type=task_type
                )
                # Extract embeddings from result
                batch_embeddings = [emb['values'] if isinstance(emb, dict) else emb for emb in result['embedding']]
                return (start_idx, batch_embeddings, None)
            except Exception as e:
                logger.error(f"Batch starting at {start_idx} failed: {e}")
                # Return zero vectors as fallback
                zero_embeddings = [[0.0] * settings.embedding_dimension] * len(batch_texts)
                return (start_idx, zero_embeddings, str(e))
        
        # Execute batches in parallel
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_batch, batch): batch for batch in batches}
            
            for future in as_completed(futures):
                start_idx, batch_embeddings, error = future.result()
                
                # Store embeddings in correct positions
                for i, emb in enumerate(batch_embeddings):
                    embeddings[start_idx + i] = emb
                
                completed += 1
                logger.info(f"Completed batch {completed}/{len(batches)} ({completed/len(batches)*100:.1f}%)")
        
        logger.info(f"Generated {len(embeddings)} embeddings")
        return embeddings
    
    def generate_query_embedding(self, query: str) -> List[float]:
        """
        Generate embedding for a search query
        
        Args:
            query: Search query text
            
        Returns:
            Embedding vector optimized for retrieval
        """
        return self.generate_embedding(query, task_type="retrieval_query")
