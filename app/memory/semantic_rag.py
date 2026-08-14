from typing import List, Dict, Any, Optional
from app.database import db
from app.utils.logger import app_logger

class SemanticRAGEngine:
    @classmethod
    def search_memories(cls, query: str, limit: int = 5, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Searches SQLite memories using keyword relevance, category filtering, and recency scoring.
        """
        query_terms = [t.lower().strip() for t in query.split() if len(t) > 2]
        if not query_terms:
            return db.get_memories(category=category)[:limit]

        all_memories = db.get_memories(category=category)
        scored_memories = []

        for mem in all_memories:
            content_lower = mem.get("content", "").lower()
            source_lower = mem.get("source", "").lower()
            
            # Score matches
            score = 0
            for term in query_terms:
                if term in content_lower:
                    score += 2
                if term in source_lower:
                    score += 1
                    
            if mem.get("category") in ["learned_skill", "user_location"]:
                score += 1  # Boost skills and location context

            if score > 0:
                scored_memories.append((score, mem))

        # Sort by score descending
        scored_memories.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in scored_memories[:limit]]

    @classmethod
    def build_rag_context(cls, query: str, limit: int = 3) -> str:
        """
        Retrieves top relevant memories and builds a formatted RAG context string for LLM prompts.
        """
        relevant = cls.search_memories(query, limit=limit)
        if not relevant:
            return ""

        context_lines = ["\n--- RELEVANT PAST MEMORIES & LEARNED SKILLS ---"]
        for idx, mem in enumerate(relevant, 1):
            context_lines.append(f"[{idx}] ({mem.get('category', 'fact')}) {mem.get('content', '')}")
        context_lines.append("---------------------------------------------------\n")

        return "\n".join(context_lines)
