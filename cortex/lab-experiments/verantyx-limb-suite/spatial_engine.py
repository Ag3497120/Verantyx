import os
from pathlib import Path

WORKSPACE = Path("/Users/motonishikoudai/verantyx-cli")
MEMORY_ROOT = WORKSPACE / ".verantyx" / "memory"

def _ensure_structure():
    for zone in ["front", "near", "mid", "deep"]:
        (MEMORY_ROOT / zone).mkdir(parents=True, exist_ok=True)

def get_front_memories() -> str:
    _ensure_structure()
    front_dir = MEMORY_ROOT / "front"
    memories = []
    if front_dir.exists():
        for file in front_dir.glob("*.md"):
            content = file.read_text(encoding="utf-8")
            memories.append(f"### [FRONT ZONE] {file.name}\n{content}\n")
    
    if not memories:
        return "(Front Zone is empty)"
    return "\n".join(memories)

def get_near_memories() -> str:
    _ensure_structure()
    near_dir = MEMORY_ROOT / "near"
    memories = []
    if near_dir.exists():
        for file in near_dir.glob("*.md"):
            # near ゾーンは概要だけを注入する（ここでは先頭5行に制限）
            lines = file.read_text(encoding="utf-8").splitlines()
            summary = "\n".join(lines[:5])
            if len(lines) > 5:
                summary += "\n... (omitted)"
            memories.append(f"### [NEAR ZONE] {file.name} (Summary)\n{summary}\n")
            
    if not memories:
        return "(Near Zone is empty)"
    return "\n".join(memories)

def get_spatial_context() -> str:
    context = "#### FRONT MEMORIES (CRITICAL BACKGROUND)\n"
    context += get_front_memories() + "\n\n"
    context += "#### NEAR MEMORIES (RECENT / HIGH-LEVEL CONTEXT)\n"
    context += get_near_memories() + "\n"
    context += "#### MID/DEEP MEMORIES (USE TOOLS TO SEARCH)\n"
    mid_count = len(list((MEMORY_ROOT / "mid").glob("*.md")))
    deep_count = len(list((MEMORY_ROOT / "deep").glob("*.md")))
    context += f"(Mid zone has {mid_count} files, Deep zone has {deep_count} files. Use GlobTool or GrepTool to inspect `.verantyx/memory/mid/` and `.verantyx/memory/deep/` if needed.)\n"
    
    return context
