import os
import json
import requests
import time
from tqdm import tqdm

API_KEY = "AIzaSyCQK2KITz6WJmyyiVAk-N08xx0MK6kFN9I"
MODEL = "gemini-2.0-flash" 
SOURCE_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v4"
TARGET_DIR = "/Users/motonishikoudai/verantyx-cli/verantyx-browser/.ronin/jcross_v6_full"
DELAY = 0.05 # Aggressive throughput

INGEST_PROMPT = """You are a High-Density Memory Compressor for the JCross Cortex.
Extract a searchable L1 Cache summary from the following raw memory.

RULES:
1. Extract unique entities (Brands, Model names, People, Specific Locations).
2. Extract specific technical facts, dates, and numbers.
3. Remove all conversational fluff, greetings, and generic advice.
4. Maintain high keyword density for search indexing.
5. Output ONLY the L1 summary text. No preamble.

Raw Memory:
{content}
"""

def call_gemini(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"
    prompt = INGEST_PROMPT.format(content=text)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    for attempt in range(3):
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                print(f"Error {res.status_code}: {res.text}")
                time.sleep(2)
        except Exception as e:
            print(f"Exception: {e}")
            time.sleep(2)
    return ""

def migrate():
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        
    files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".jcross")]
    print(f"Migrating {len(files)} nodes to V6...")
    
    for filename in tqdm(files):
        with open(os.path.join(SOURCE_DIR, filename), "r") as f:
            raw = f.read()
            
        # Basic parsing to extract L1/L2
        # If it already has [本質記憶], we use that as L2_Raw
        content = ""
        if "[本質記憶]" in raw:
            content = raw.split("[本質記憶]")[1].split("===")[0].strip()
        elif "[L1_Cache]" in raw:
             continue # Already converted or weird state
             
        if not content:
            continue
            
        l1_summary = call_gemini(content)
        if not l1_summary:
            print(f"Failed to compress {filename}")
            l1_summary = content[:200] # Fallback
            
        time.sleep(DELAY)
        
        # Construct V6 JCross
        # We reuse the header but update the content part
        header = raw.split("---")[0].strip()
        
        v6_body = f"""
---
[L1_Cache]
{l1_summary}

[L2_Archive]
{content}
===
"""
        with open(os.path.join(TARGET_DIR, filename), "w") as f:
            f.write(header + v6_body)

if __name__ == "__main__":
    migrate()
