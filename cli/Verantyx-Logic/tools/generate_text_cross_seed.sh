#!/usr/bin/env bash
set -euo pipefail

OUT="avh_math/db/text_cross_seed.jsonl"
PROMPT="tools/prompts/text_cross_chunk_prompt.txt"

# 1回あたりの行数
CHUNK=2000
TOTAL=20000000

# 再開対応: 既存行数から続き番号を決める
if [ -f "$OUT" ]; then
  EXISTING=$(wc -l < "$OUT" | tr -d ' ')
else
  EXISTING=0
fi

start=$((EXISTING + 1))
while [ $start -le $TOTAL ]; do
  end=$((start + CHUNK - 1))
  if [ $end -gt $TOTAL ]; then
    end=$TOTAL
  fi

  # プロンプトを埋める
  tmp_prompt=$(mktemp)
  sed -e "s/{{N}}/$((end-start+1))/g" \
      -e "s/{{START}}/$(printf "%06d" $start)/g" \
      -e "s/{{END}}/$(printf "%06d" $end)/g" \
      "$PROMPT" > "$tmp_prompt"

  echo "Generating $start-$end ..."
  
  # Gemini CLI 呼び出し
  # モデルは gemini-2.5-pro を使用
  # プロンプトはファイルから読み込む (@構文)
  gemini --model gemini-2.5-pro "@$tmp_prompt" >> "$OUT"
  # 簡易整合性チェック（末尾1行がJSONでない場合は停止）
  tail -n 1 "$OUT" | python3 - <<'PY'
import json,sys
line=sys.stdin.read().strip()
if not line:
    raise SystemExit(0)
try:
    json.loads(line)
except Exception:
    print("Last line is not valid JSON. Stopping.", file=sys.stderr)
    raise SystemExit(1)
PY

  rm -f "$tmp_prompt"
  start=$((end+1))
done

echo "DONE: $(wc -l < "$OUT") lines written to $OUT"
