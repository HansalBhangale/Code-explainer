"""
Code Explanation Service using Gemini 2.5 Pro
Generates natural language explanations for code snippets
"""
import google.generativeai as genai
from typing import List, Dict, Any, Optional
import os
import logging
from src.config import settings

logger = logging.getLogger(__name__)


class CodeExplainer:
    """
    Service to explain code using Gemini 2.5 Pro
    """
    
    def __init__(self):
        """Initialize Gemini for code explanation"""
        api_key = settings.gemini_api_key or os.getenv('GEMINI_API_KEY')
        
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        
        genai.configure(api_key=api_key)
        
        # Use model name directly (new SDK handles it correctly)
        self.model = genai.GenerativeModel(settings.gemini_model)
        logger.info(f"Initialized CodeExplainer with model: {settings.gemini_model}")
    
    def explain_code(
        self,
        code: str,
        symbol_name: str,
        symbol_kind: str,
        file_path: str,
        language: str = "python",
        context: Optional[str] = None
    ) -> str:
        """
        Generate explanation for a code snippet
        
        Args:
            code: The code snippet to explain
            symbol_name: Name of the function/class
            symbol_kind: Type (function, class, etc.)
            file_path: File path for context
            language: Programming language
            context: Optional parent chunk context
            
        Returns:
            Natural language explanation
        """
        try:
            # Build prompt
            prompt = self._build_explanation_prompt(
                code, symbol_name, symbol_kind, file_path, language, context
            )
            
            # Generate explanation
            response = self.model.generate_content(prompt)
            
            return response.text
            
        except Exception as e:
            logger.error(f"Failed to generate explanation: {e}")
            return f"Error generating explanation: {str(e)}"
    
    def explain_multiple(
        self,
        chunks: List[Dict[str, Any]],
        query: str
    ) -> List[Dict[str, Any]]:
        """
        Generate explanations for multiple code chunks
        
        Args:
            chunks: List of chunk dictionaries with code and metadata
            query: Original user query for context
            
        Returns:
            Chunks with added 'explanation' field
        """
        explained_chunks = []
        
        for chunk in chunks:
            try:
                explanation = self.explain_code(
                    code=chunk['content'],
                    symbol_name=chunk['symbol_name'],
                    symbol_kind=chunk['symbol_kind'],
                    file_path=chunk['file_path'],
                    language=chunk.get('language', 'python'),
                    context=chunk.get('parent_content')
                )
                
                chunk['explanation'] = explanation
                explained_chunks.append(chunk)
                
            except Exception as e:
                logger.error(f"Failed to explain chunk {chunk.get('chunk_id')}: {e}")
                chunk['explanation'] = "Explanation unavailable"
                explained_chunks.append(chunk)
        
        return explained_chunks
    
    def _build_explanation_prompt(
        self,
        code: str,
        symbol_name: str,
        symbol_kind: str,
        file_path: str,
        language: str,
        context: Optional[str]
    ) -> str:
        """Build prompt for code explanation"""
        
        prompt = f"""You are an expert code reviewer and technical writer. Explain the following {language} code clearly and concisely.

**Code Information:**
- Symbol: `{symbol_name}` ({symbol_kind})
- File: `{file_path}`
- Language: {language}

**Code Snippet:**
```{language}
{code}
```
"""
        
        if context:
            prompt += f"""
**Additional Context:**
```{language}
{context}
```
"""
        
        prompt += """
**Instructions:**
1. Provide a clear, concise explanation of what this code does
2. Explain the purpose and key functionality
3. Mention important parameters, return values, or attributes
4. Highlight any notable patterns, algorithms, or design decisions
5. Keep it under 150 words
6. Use markdown formatting for readability

**Explanation:**
"""
        
        return prompt
    
    def explain_with_query_context(
        self,
        code: str,
        symbol_name: str,
        symbol_kind: str,
        file_path: str,
        query: str,
        language: str = "python"
    ) -> str:
        """
        Generate explanation with user query context
        
        Args:
            code: Code snippet
            symbol_name: Symbol name
            symbol_kind: Symbol type
            file_path: File path
            query: User's original query
            language: Programming language
            
        Returns:
            Explanation tailored to the query
        """
        prompt = f"""You are an expert code reviewer helping answer a specific question.

**User Question:** "{query}"

**Relevant Code Found:**
- Symbol: `{symbol_name}` ({symbol_kind})
- File: `{file_path}`

**Code:**
```{language}
{code}
```

**Instructions:**
1. Explain how this code relates to the user's question
2. Describe what the code does
3. Highlight the parts most relevant to their query
4. Keep it concise (under 150 words)
5. Use markdown formatting

**Explanation:**
"""
        
        try:
            logger.debug(f"Generating explanation for '{symbol_name}' with prompt:\n{prompt}")
            response = self.model.generate_content(prompt)
            
            if response.text:
                return response.text
            else:
                logger.warning(f"Received empty explanation for '{symbol_name}'")
                return "AI explanation is unavailable for this snippet."
                
        except Exception as e:
            logger.error(f"Failed to generate query-contextual explanation for '{symbol_name}': {e}", exc_info=True)
            return f"Error generating explanation: {str(e)}"
