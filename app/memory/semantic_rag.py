from typing import List, Dict, Any, Optional
from app.database import db
from app.utils.logger import app_logger
from app.cognition.world_model import WorldModel
from app.config import settings

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
        Retrieves top relevant vector memories AND fuses structured Knowledge Graph entities (WorldModel)
        into a unified, dual-layered RAG context string for LLM prompts.
        """
        relevant = cls.search_memories(query, limit=limit)
        
        # Fuse Knowledge Graph Entity Nodes from WorldModel
        graph_entities = []
        try:
            wm = WorldModel(str(settings.DB_PATH))
            words = [w for w in query.replace("?", "").replace("'", "").split() if len(w) > 3]
            search_key = words[0] if words else query
            matched_nodes = wm.query_entities(query=search_key, limit=3)
            for node in matched_nodes:
                graph_entities.append(f"• Entity [{node.get('entity_type', 'node')}]: '{node.get('name')}'")
        except Exception as e:
            app_logger.warning(f"Knowledge Graph RAG fusion notice: {e}")

        if not relevant and not graph_entities:
            return ""

        context_lines = ["\n--- DUAL-LAYERED RAG MEMORY & KNOWLEDGE GRAPH ENTITIES ---"]
        if graph_entities:
            context_lines.append("STRUCTURED GRAPH ENTITIES:")
            context_lines.extend(graph_entities)

        if relevant:
            context_lines.append("\nRELEVANT PAST MEMORIES:")
            for idx, mem in enumerate(relevant, 1):
                context_lines.append(f"[{idx}] ({mem.get('category', 'fact')}) {mem.get('content', '')}")
                
        context_lines.append("-----------------------------------------------------------\n")

        return "\n".join(context_lines)
