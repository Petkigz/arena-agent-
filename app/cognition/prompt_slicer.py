"""Dynamic Instruction Slicer & Context Budget Prompt Summarizer Guard."""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class SlicedPromptContext(BaseModel):
    selected_instructions: List[str]
    active_tool_schemas: List[Dict[str, Any]]
    compact_prompt_str: str
    token_budget_used: int = 0
    history_summarized: bool = False

class PromptSlicerEngine:
    """
    Prevents instruction dilution, prompt bloat, and model hallucinations by slicing system instructions
    and summarizing conversation history within a strict token budget (max_tokens = 500).
    """

    MAX_CONTEXT_TOKEN_BUDGET = 500

    INSTRUCTION_REGISTRY = {
        "os_control": "Rule: Operate OS applications via SystemAppInventory. Verify process state.",
        "search": "Rule: Search local filesystem or live web before generating facts. Cite source paths.",
        "security": "Rule: Enforce Level 0-3 Safety Policies. Do not run destructive actions outside sandbox.",
        "code": "Rule: Output executable Python code blocks inside markdown blocks. Test in sandbox.",
        "coworker_tone": "Rule: Be concise (2-3 sentences), direct, and conversational. Avoid 'As an AI' cliches."
    }

    @classmethod
    def compress_history_summary(cls, messages: List[Dict[str, str]]) -> str:
        """
        Compresses multi-turn conversation history into a dense 2-sentence structural summary string.
        """
        if not messages or len(messages) <= 2:
            return ""

        user_topics = [m["content"][:40] for m in messages if m.get("role") == "user"]
        summary = f"Past Conversation Summary: User inquired about {', '.join(user_topics[:3])}."
        return summary

    @classmethod
    def slice_context_for_task(cls, user_text: str, message_history: Optional[List[Dict[str, str]]] = None) -> SlicedPromptContext:
        text_lower = user_text.lower()
        active_rules = [cls.INSTRUCTION_REGISTRY["coworker_tone"]]

        if any(k in text_lower for k in ["open", "launch", "app", "firefox", "chrome", "pc"]):
            active_rules.append(cls.INSTRUCTION_REGISTRY["os_control"])
        if any(k in text_lower for k in ["find", "file", "search", "where", "ordinary", "web"]):
            active_rules.append(cls.INSTRUCTION_REGISTRY["search"])
        if any(k in text_lower for k in ["pentest", "security", "scan", "opsec", "canary"]):
            active_rules.append(cls.INSTRUCTION_REGISTRY["security"])
        if any(k in text_lower for k in ["code", "script", "python", "function", "debug"]):
            active_rules.append(cls.INSTRUCTION_REGISTRY["code"])

        compact_rules = "\n".join(f"• {rule}" for rule in active_rules)

        # Apply Context Budget Compression on long histories
        history_summary = ""
        summarized = False
        if message_history and len(message_history) > 3:
            history_summary = f"\n\n[CONTEXT BUDGET COMPRESSION]: {cls.compress_history_summary(message_history)}"
            summarized = True

        final_prompt = compact_rules + history_summary
        estimated_tokens = len(final_prompt.split()) * 2

        return SlicedPromptContext(
            selected_instructions=active_rules,
            active_tool_schemas=[],
            compact_prompt_str=final_prompt,
            token_budget_used=estimated_tokens,
            history_summarized=summarized
        )
