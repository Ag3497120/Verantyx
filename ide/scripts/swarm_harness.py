import os
import json
import logging

logger = logging.getLogger("SwarmHarness")

def read_file(path: str) -> str:
    if not os.path.exists(path):
        return f"Error: File '{path}' not found."
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(path: str, content: str) -> str:
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: Wrote to '{path}'"
    except Exception as e:
        return f"Error writing file: {str(e)}"

def list_directory(path: str) -> str:
    if not os.path.exists(path):
        return f"Error: Directory '{path}' not found."
    try:
        items = os.listdir(path)
        return "\\n".join(items)
    except Exception as e:
        return f"Error listing directory: {str(e)}"

def execute_tool(action: str, params: dict) -> str:
    """エージェントから渡されたツール呼び出しを実行する"""
    logger.info(f"Executing tool: {action} with params: {params}")
    
    if action == "read_file":
        return read_file(params.get("path", ""))
    elif action == "write_file":
        return write_file(params.get("path", ""), params.get("content", ""))
    elif action == "list_directory":
        return list_directory(params.get("path", ""))
    else:
        return f"Error: Unknown action '{action}'"

def parse_tool_call(text: str):
    """
    モデルの出力テキストからツール呼び出しをパースする
    フォーマット想定: [TOOL_CALL] {"action": "read_file", "path": "test.txt"} [/TOOL_CALL]
    """
    try:
        if "[TOOL_CALL]" in text and "[/TOOL_CALL]" in text:
            start = text.find("[TOOL_CALL]") + len("[TOOL_CALL]")
            end = text.find("[/TOOL_CALL]")
            json_str = text[start:end].strip()
            return json.loads(json_str)
    except Exception as e:
        logger.error(f"Failed to parse tool call: {e}")
    return None
