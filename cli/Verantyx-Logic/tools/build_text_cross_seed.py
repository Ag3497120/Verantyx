from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path if needed
sys.path.append(str(Path(__file__).parent.parent))

try:
    from avh_math.text_cross.builder import build_text_cross
    from avh_math.text_cross.store import store_cross, all_crosses
    from avh_math.text_cross.index import build_index, save_index
    # If store_cross / all_crosses are not directly exposed, adjust import
    # Assuming standard verantyx architecture
except ImportError as e:
    print(f"Error importing avh_math modules: {e}")
    print("Please ensure you are running from the project root and PYTHONPATH is set.")
    sys.exit(1)

SEED_PATH = Path("avh_math/db/text_cross_seed.jsonl")

def build_kb_from_jsonl():
    if not SEED_PATH.exists():
        print(f"Error: {SEED_PATH} not found. Please generate it first.")
        sys.exit(1)
        
    print(f"Reading {SEED_PATH}...")
    
    count = 0
    with SEED_PATH.open("r", encoding="utf-8") as f:
        # Read all lines first or stream? Streaming is better for memory.
        # But build_index might need all objects.
        # Assuming store_cross saves to memory/disk incrementally, 
        # but build_index usually needs the full set.
        
        # Let's check how many we process
        for line in f:
            try:
                rec = json.loads(line)
                text = rec["text"]
                # id = rec["id"] # Not used by builder directly usually, but could be meta
                
                # Build the cross (decomposition)
                cross = build_text_cross(text)
                
                # Add metadata
                cross.meta["source"] = "seed_import"
                cross.meta["seed_id"] = rec.get("id")
                
                # Store
                store_cross(cross)
                
                count += 1
                if count % 5000 == 0:
                    print(f"Processed {count} entries...")
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Skipping line due to error: {e}")
                continue

    print(f"Finished processing {count} entries.")
    
    print("Building index...")
    # Retrieve all stored crosses to build the index
    # Note: all_crosses() might be an iterator or list
    crosses = all_crosses() 
    index = build_index(crosses)
    save_index(index)
    print("Index saved.")

def main():
    build_kb_from_jsonl()

if __name__ == "__main__":
    main()
