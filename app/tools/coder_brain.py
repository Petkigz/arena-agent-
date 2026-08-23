from typing import Dict, Any, List, Optional
from app.llm import llm_client, extract_reply, require_real_completion
from app.tools.doc_manager import DocumentManager
from app.utils.logger import app_logger, audit_logger

class CoderBrainTool:
    LANGUAGES = [
        "python", "typescript", "javascript", "c", "cpp", "rust", "go", 
        "java", "csharp", "php", "swift", "kotlin", "bash", "sql", "html", "css", "ruby", "perl"
    ]

    @classmethod
    def explain_and_debug_code(cls, code_snippet: str, language: str = "python") -> Dict[str, Any]:
        """
        Polyglot Code Explainer & Debugger: Explains logic, identifies bugs, and provides clean refactored code.
        """
        if not code_snippet or not code_snippet.strip():
            return {"success": False, "error": "A code snippet is required."}
        language = (language or "python").lower()
        if language not in cls.LANGUAGES:
            return {"success": False, "error": f"Unsupported language '{language}'. Supported: {', '.join(cls.LANGUAGES)}."}

        system_prompt = (
            "You are an expert Polyglot Software Architect. Explain code logic, "
            "identify syntax/logic bugs, and provide clean, production-grade refactored code."
        )

        user_prompt = f"""
Language: {language}

Code Snippet:
```
{code_snippet[:10000]}
```

Provide:
1. **Code Logic Explanation**: What does this code do?
2. **Identified Bugs or Flaws**: Syntax errors, edge cases, memory leaks, or performance bottlenecks.
3. **Refactored Production Code**: Clean, well-commented, optimized replacement code.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity="main",
                max_tokens=1000
            )

            refactored_code = require_real_completion(llm_res)

            return {
                "success": True,
                "language": language,
                "refactored_code": refactored_code
            }
        except Exception as e:
            app_logger.error(f"Error in code debugger: {e}")
            return {"success": False, "error": str(e), "language": language}

    @classmethod
    def generate_unit_tests(cls, code_snippet: str, language: str = "python") -> Dict[str, Any]:
        """
        Generates comprehensive unit test suites (pytest, jest, cargo test, etc.) for provided code.
        """
        if not code_snippet or not code_snippet.strip():
            return {"success": False, "error": "A code snippet is required."}
        language = (language or "python").lower()
        if language not in cls.LANGUAGES:
            return {"success": False, "error": f"Unsupported language '{language}'."}

        system_prompt = (
            "You are a Quality Assurance & Test Engineering Lead. "
            "Generate complete, passing unit test suites covering normal cases and edge cases."
        )

        user_prompt = f"""
Language: {language}

Source Code:
```
{code_snippet[:8000]}
```

Generate a complete, executable unit test file for this code.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            llm_res = llm_client.generate_chat_completion(
                messages=messages,
                complexity="main",
                max_tokens=900
            )

            test_code = require_real_completion(llm_res)

            # Save test file draft (best-effort — never fail the whole result).
            ext = ".py" if language == "python" else ".js" if language in ["javascript", "typescript"] else ".txt"
            test_file_path = f"drafts/test_suite_{language}{ext}"
            try:
                DocumentManager.create_document(test_file_path, test_code, overwrite=True)
            except Exception as e:
                app_logger.warning(f"Could not save test file draft: {e}")
                test_file_path = None  # don't report a path that wasn't written

            return {
                "success": True,
                "language": language,
                "test_code": test_code,
                "test_file_path": test_file_path
            }
        except Exception as e:
            app_logger.error(f"Unit test generation failed: {e}")
            return {"success": False, "error": str(e)}
