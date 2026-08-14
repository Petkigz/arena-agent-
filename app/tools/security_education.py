from typing import Dict, Any, List, Optional
from app.llm import llm_client
from app.database import db
from app.utils.logger import app_logger, audit_logger

class SecurityEducationTool:
    DEFENSIVE_FRAMEWORKS = {
        "owasp_top_10": "OWASP Top 10 Web Application Security Risks (A01: Broken Access Control, A03: Injection, etc.)",
        "nist_csf": "NIST Cybersecurity Framework (Identify, Protect, Detect, Respond, Recover)",
        "cis_benchmarks": "CIS Benchmarks for OS, Database, and Cloud Hardening",
        "secure_coding": "OWASP Secure Coding Practices Quick Reference Guide"
    }

    @classmethod
    def audit_code_defensively(cls, code_snippet: str, language: str = "python") -> Dict[str, Any]:
        """
        Analyzes source code defensively for security flaws, missing sanitization, 
        and OWASP vulnerabilities, providing secure refactored code fixes.
        """
        system_prompt = (
            "You are a Senior Principal Application Security Architect. "
            "Audit the provided source code defensively. Identify security risks "
            "(SQLi, XSS, CSRF, hardcoded secrets, weak crypto) and provide secure refactored code fixes."
        )

        user_prompt = f"""
Language: {language}

Source Code Snippet to Audit Defensively:
```
{code_snippet[:8000]}
```

Provide:
1. **Defensive Security Findings**: Potential vulnerabilities or missing validation.
2. **OWASP Category Mapping**: Relevant OWASP Top 10 categories.
3. **Secure Refactored Code**: Updated, secure code snippet implementing proper sanitization and defensive checks.
4. **Hardening Recommendations**: Best practices to prevent future issues.
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

            audit_report = llm_res["choices"][0]["message"]["content"] if llm_res.get("choices") else "Defensive audit completed."

            # Index findings in SQLite memory
            mem_id = db.create_memory({
                "content": f"🛡️ [DEFENSIVE CODE AUDIT :: {language.upper()}]\n\n{audit_report}",
                "category": "defensive_security",
                "source": "security_education_tool",
                "confidence": 1.0
            })

            audit_logger.info(f"Completed defensive code audit for {language} snippet.")

            return {
                "success": True,
                "language": language,
                "audit_report": audit_report,
                "memory_id": mem_id
            }
        except Exception as e:
            app_logger.error(f"Defensive code audit error: {e}")
            return {"success": False, "error": str(e), "language": language}
