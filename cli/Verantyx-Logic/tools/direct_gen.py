import json
import random
from pathlib import Path

# --- Batch 6: Structured Thinking ---
START = 10001
COUNT = 2000
OUT_FILE = Path("avh_math/db/text_cross_seed.jsonl")

# More dynamic generation
def gen_complex():
    subj = random.choice(["Assume", "Suppose", "Given", "仮定:", "前提:"])
    formula = f"A[{random.randint(0,9)}] = {random.choice(['True', 'False', 'None'])}"
    action = random.choice(["then prove", "implies", "leads to", "ならば", "より"])
    target = f"B({random.randint(10,99)})"
    return f"{subj} \"{formula}\", {action} \"{target}\"."

lines = [ {"id": f"seed_{START+i:06d}", "text": gen_complex()} for i in range(COUNT) ]
with OUT_FILE.open("a", encoding="utf-8") as f_out:
    for e in lines: f_out.write(json.dumps(e, ensure_ascii=False) + "\n")
print("Batch 6 Done.")
