#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse, json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", required=True)
    ap.add_argument("--append", required=True)
    args = ap.parse_args()

    # Append as-is (JSONL)
    n = 0
    with open(args.append, "r", encoding="utf-8") as src, open(args.kb, "a", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            try:
                # validate json
                json.loads(line)
                dst.write(line + "\n")
                n += 1
            except Exception as e:
                print(f"[WARN] Skipping invalid line: {e}")
                
    print(f"[OK] appended {n} lines into {args.kb}")

if __name__ == "__main__":
    main()

