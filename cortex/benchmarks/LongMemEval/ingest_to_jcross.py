import json
import os

DB_PATH = "/Users/motonishikoudai/verantyx-cli/jcross-memory/data/jcross_mcp.json"
CHALLENGE_FILE = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/challenge_20.json"

def ingest():
    if not os.path.exists(CHALLENGE_FILE):
        print("Challenge file not found.")
        return

    with open(CHALLENGE_FILE, 'r') as f:
        challenge = json.load(f)

    # Load existing DB or create new
    if os.path.exists(DB_PATH):
        with open(DB_PATH, 'r') as f:
            db = json.load(f)
    else:
        db = {"nodes": [], "active_tensions": []}

    # Extract all unique sessions from the challenge
    all_history = set()
    for item in challenge:
        # Split history by Session marker
        sessions = item['history'].split('--- Session')
        for s in sessions:
            s = s.strip()
            if s:
                # Re-add marker if needed, but cleaner just to store the content
                cleaned = s.split(' ---\n', 1)[-1] if ' ---' in s else s
                all_history.add(cleaned.strip())

    # Ingest into DB
    initial_count = len(db['nodes'])
    for session_text in all_history:
        node_content = f"[LongMemEval_Seed] {session_text}"
        if node_content not in db['nodes']:
            db['nodes'].append(node_content)

    with open(DB_PATH, 'w') as f:
        json.dump(db, f, indent=2)

    print(f"Ingestion complete. Added {len(db['nodes']) - initial_count} new nodes.")
    print(f"Total nodes in JCross: {len(db['nodes'])}")

if __name__ == "__main__":
    ingest()
