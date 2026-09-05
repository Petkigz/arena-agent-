def execute_tool(params=None):
    params = params or {}
    text = str(params.get("text", "") or "")
    return {"success": True,
            "result": str(len(text.split())),
            "details": {"chars": len(text)}}