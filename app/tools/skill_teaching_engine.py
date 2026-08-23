import os
import json
import datetime
from typing import Dict, Any, List, Optional
from app.config import settings
from app.database import db
from app.utils.logger import app_logger
from app.tools.disposable_sandbox import DisposableSandbox
from app.llm import llm_client, extract_reply, require_real_completion

class SkillTeachingEngine:
    """
    Teachable Skill Acquisition & Ethical Hacking Trainer Engine.
    Allows the user to teach the assistant custom pentesting methodologies, ethical hacking playbooks,
    CLI workflows, and domain heuristics, which are stored permanently and executed on demand.
    """

    @staticmethod
    def _init_taught_skills_table():
        """
        Ensures the SQLite taught_skills table exists.
        """
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS taught_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_name TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    trigger_keywords TEXT NOT NULL,
                    instructions TEXT NOT NULL,
                    sample_commands TEXT,
                    safety_rules TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def teach_skill(
        skill_name: str,
        category: str = "cybersecurity_pentesting",
        trigger_keywords: List[str] = None,
        instructions: str = "",
        sample_commands: Optional[str] = "",
        safety_rules: Optional[str] = "Authorized ethical testing scope only."
    ) -> Dict[str, Any]:
        """
        Teaches the assistant a new custom skill, playbook, or methodology.
        """
        SkillTeachingEngine._init_taught_skills_table()
        keywords_str = json.dumps(trigger_keywords or [skill_name.lower()])
        now_str = datetime.datetime.now().isoformat()

        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO taught_skills
                    (skill_name, category, trigger_keywords, instructions, sample_commands, safety_rules, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    skill_name.strip(),
                    category.strip(),
                    keywords_str,
                    instructions.strip(),
                    sample_commands.strip() if sample_commands else "",
                    safety_rules.strip() if safety_rules else "",
                    now_str
                ))
                conn.commit()

            # Save in RAG memory
            db.create_memory({
                "content": f"Taught Skill [{skill_name}] (Category: {category}): {instructions[:300]}",
                "category": "user_taught_skill",
                "source": "skill_teaching_engine",
                "confidence": 1.0
            })

            db.create_audit_log("teach_skill", "success", f"Taught assistant new skill '{skill_name}' ({category})", level=0)

            return {
                "success": True,
                "skill_name": skill_name,
                "category": category,
                "message": f"Successfully taught the assistant new skill '{skill_name}'!"
            }
        except Exception as e:
            app_logger.error(f"Error teaching skill '{skill_name}': {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def list_taught_skills(category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lists all custom skills taught by the user.
        """
        SkillTeachingEngine._init_taught_skills_table()
        with db._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute("SELECT * FROM taught_skills WHERE category = ? ORDER BY created_at DESC", (category,))
            else:
                cursor.execute("SELECT * FROM taught_skills ORDER BY created_at DESC")
            
            rows = cursor.fetchall()
            skills = []
            for r in rows:
                item = dict(r)
                item["trigger_keywords"] = json.loads(item["trigger_keywords"]) if item.get("trigger_keywords") else []
                skills.append(item)
            return skills

    @staticmethod
    def execute_taught_skill(
        skill_name: str,
        target_parameter: str = "",
        run_in_sandbox: bool = True
    ) -> Dict[str, Any]:
        """
        Executes a user-taught skill playbook using runtime parameters.
        Optionally executes commands inside DisposableSandbox for isolated safety.
        """
        skills = SkillTeachingEngine.list_taught_skills()
        target_skill = next((s for s in skills if s["skill_name"].lower() == skill_name.lower()), None)

        if not target_skill:
            return {"success": False, "error": f"Taught skill '{skill_name}' not found."}

        app_logger.info(f"Executing taught skill '{skill_name}' for target parameter: '{target_parameter}'")

        # Format sample commands with target parameter
        raw_cmd = target_skill.get("sample_commands", "")
        formatted_cmd = raw_cmd.replace("{target}", target_parameter).replace("{SCOPE}", target_parameter)

        sandbox_res = None
        if run_in_sandbox and formatted_cmd:
            sb = DisposableSandbox.create_sandbox(f"sb_{skill_name.lower()[:8]}")
            sandbox_id = sb["sandbox_id"]
            
            exec_res = DisposableSandbox.run_in_sandbox(
                sandbox_id, 
                formatted_cmd, 
                use_linux_environment=True
            )
            
            # Clean up sandbox
            DisposableSandbox.destroy_sandbox(sandbox_id)
            sandbox_res = exec_res

        # AI Synthesis of Playbook execution
        prompt = (
            f"Execute taught methodology playbook: '{skill_name}'\n"
            f"Category: {target_skill.get('category')}\n"
            f"Playbook Instructions:\n{target_skill.get('instructions')}\n"
            f"Safety Rules: {target_skill.get('safety_rules')}\n"
            f"Target Parameter: {target_parameter}\n\n"
            f"Command Output / Execution Notes:\n{sandbox_res.get('stdout', '') if sandbox_res else 'Theoretical execution walkthrough.'}\n\n"
            f"Generate a professional execution analysis, key findings, and recommended next steps."
        )

        llm_res = llm_client.generate_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            complexity="main",
            max_tokens=600
        )
        try:
            ai_synthesis = require_real_completion(llm_res)
        except Exception as exc:
            return {
                "success": False,
                "available": False,
                "error_type": "model_unavailable",
                "error": str(exc),
                "sandbox_execution": sandbox_res,
            }

        db.create_audit_log("execute_taught_skill", "success", f"Executed taught skill '{skill_name}'", level=1)

        return {
            "success": True,
            "skill_name": skill_name,
            "category": target_skill.get("category"),
            "target_parameter": target_parameter,
            "executed_commands": formatted_cmd,
            "sandbox_execution": sandbox_res,
            "ai_synthesis": ai_synthesis
        }
