"""Dynamic Instruction Slicer & Hallucination Prevention Guard."""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class SlicedPromptContext(BaseModel):
    selected_instructions: List[str]
    active_tool_schemas: List[Dict[str, Any]]
    compact_prompt_str: str

class PromptSlicerEngine:
    """
    Prevents instruction dilution and model hallucinations by slicing system instructions
    down to hyper-relevant sub-instructions per execution step.
    """

    INSTRUCTION_REGISTRY = {
        "os_control": "Rule: Operate OS applications via SystemAppInventory. Verify process state.",
        "search": "Rule: Search local filesystem or live web before generating facts. Cite source paths.",
        "security": "Rule: Enforce Level 0-3 Safety Policies. Do not run destructive actions outside sandbox.",
        "code": "Rule: Output executable Python code blocks inside markdown blocks. Test in sandbox.",
        "coworker_tone": "Rule: Be concise (2-3 sentences), direct, and conversational. Avoid 'As an AI' cliches."
    }

    @classmethod
    def slice_context_for_task(cls, user_text: str) -> SlicedPromptContext:
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

        compact = "\n".join(f"• {rule}" for rule in active_rules)

        return SlicedPromptContext(
            selected_instructions=active_rules,
            active_tool_schemas=[],
            compact_prompt_str=compact
        )
