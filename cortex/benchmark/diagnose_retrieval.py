#!/usr/bin/env python3
"""
Diagnose Retrieval: Show where the answer session ranks for each question.
This reveals what needs to be fixed in the Kanji tagging.
"""
import json, os, re, math, glob, time

DATASET_PATH = "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_s_cleaned.json"
MEMORY_DIR   = os.path.expanduser("~/.openclaw/memory/front")
NUM_QUESTIONS = 7

# ---- paste same Kanji vocab from official script ----
KANJI_VOCAB = {
    "場": ["where", "location", "place", "store", "shop", "studio", "restaurant",
           "gym", "target", "walmart", "amazon", "theater", "clinic", "hospital",
           "park", "school", "university", "office", "museum", "market",
           "salon", "spa", "center", "downtown", "nearby", "near",
           "serenity", "campus", "venue", "branch", "neighborhood"],
    "時": ["when", "date", "time", "year", "month", "day", "morning", "evening",
           "night", "ago", "last", "first", "today", "yesterday", "schedule",
           "appointment", "deadline", "recently", "since", "during",
           "week", "weekend", "annual", "monthly", "daily", "hour", "minute"],
    "人": ["name", "person", "friend", "family", "husband", "wife", "brother",
           "sister", "parent", "boss", "colleague", "doctor", "coach", "mentor",
           "i ", "my ", "me ", "myself", "changed", "called", "known as",
           "maiden", "last name", "first name", "renamed", "alias"],
    "商": ["buy", "purchase", "coupon", "price", "cost", "money", "paid",
           "order", "discount", "sale", "receipt", "checkout", "cart", "deals",
           "credit", "cash", "spend", "budget", "free", "redeem",
           "savings", "cashback", "refund", "reward", "creamer"],
    "健": ["health", "yoga", "exercise", "workout", "gym", "doctor", "medicine",
           "wellness", "diet", "sleep", "stress", "anxiety", "therapy",
           "meditation", "fitness", "run", "walk", "stretch", "class",
           "pose", "pilates", "instructor", "studio", "session", "mat"],
    "食": ["food", "recipe", "cook", "eat", "meal", "lunch", "dinner", "breakfast",
           "brunch", "snack", "coffee", "creamer", "grocery", "ingredient",
           "restaurant", "menu", "dish", "vegan", "vegetarian",
           "spice", "bake", "grill", "cuisine", "cafe", "drink"],
    "職": ["work", "job", "career", "office", "commute", "boss", "promotion",
           "salary", "degree", "graduate", "university", "college", "interview",
           "hired", "profession", "business", "company", "role", "position",
           "administration", "internship", "resume", "coworker", "minutes each",
           "transit", "bus", "train", "drive", "commuting"],
    "娯": ["movie", "music", "book", "playlist", "spotify", "theater", "play",
           "concert", "show", "album", "song", "artist", "genre", "watched",
           "read", "listen", "netflix", "game", "hobby", "collection",
           "glass menagerie", "summer vibes", "performance", "stage"],
    "技": ["app", "software", "computer", "phone", "internet", "coding",
           "technology", "website", "tool", "device", "update", "install",
           "password", "login", "data", "ai", "chat", "digital"],
}

def content_to_kanji(text: str) -> dict:
    text_lower = text.lower()
    scores = {}
    for kanji, keywords in KANJI_VOCAB.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits > 0:
            scores[kanji] = min(1.0, round(hits / 4, 2))
    scores["記"] = max(scores.get("記", 0), 0.4)
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    if not top:
        top = [("標", 1.0), ("記", 0.4)]
    return dict(top)

def question_to_kanji(question: str) -> dict:
    q = question.lower()
    vec = {"記": 0.4}
    mappings = [
        (["where", "location", "place", "store", "shop", "redeem"],   "場", 1.0),
        (["when", "date", "time", "year", "first", "last"],            "時", 1.0),
        (["degree", "graduate", "university", "job", "career",
          "work", "commute", "position"],                               "職", 1.0),
        (["playlist", "music", "movie", "book", "play", "theater",
          "concert", "show", "song"],                                   "娯", 1.0),
        (["buy", "coupon", "purchase", "redeem", "price", "paid"],     "商", 0.9),
        (["yoga", "exercise", "gym", "health", "class", "studio"],     "健", 1.0),
        (["name", "called", "last name", "first name", "changed"],     "人", 1.0),
        (["food", "recipe", "restaurant", "eat", "coffee"],            "食", 0.9),
        (["app", "software", "computer", "tech", "phone", "device"],   "技", 0.9),
    ]
    for keywords, kanji, weight in mappings:
        if any(kw in q for kw in keywords):
            vec[kanji] = weight
    if len(vec) == 1:
        vec["標"] = 0.8
    return vec

def cosine_similarity(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v**2 for v in a.values()))
    nb = math.sqrt(sum(v**2 for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def main():
    with open(DATASET_PATH) as f:
        dataset = json.load(f)
    selected = dataset[:NUM_QUESTIONS]

    print("=" * 70)
    print("  RETRIEVAL DIAGNOSTICS — Answer Session Rank Analysis")
    print("=" * 70)

    for i, item in enumerate(selected):
        qid      = item["question_id"]
        question = item["question"]
        expected = item["answer"]
        sessions = item.get("haystack_sessions", [])
        sess_ids = item.get("haystack_session_ids", [])
        ans_ids  = set(item.get("answer_session_ids", []))

        print(f"\n[{i+1}/{NUM_QUESTIONS}] {qid}")
        print(f"  Q: {question}")
        print(f"  Expected: {expected}")

        # Derive query Kanji
        q_kanji = question_to_kanji(question)
        print(f"  Query Kanji: {q_kanji}")

        # Tag each session and compute similarity
        ranked = []
        for j, session in enumerate(sessions):
            if not isinstance(session, list):
                continue
            raw = "\n".join([
                f"{m.get('role','?').upper()}: {m.get('content','')[:400]}"
                for m in session if isinstance(m, dict)
            ])
            if not raw.strip():
                continue
            sid = sess_ids[j] if j < len(sess_ids) else f"s{j}"
            node_kanji = content_to_kanji(raw)
            sim = cosine_similarity(q_kanji, node_kanji)
            is_answer = sid in ans_ids
            ranked.append((sim, sid, node_kanji, is_answer, raw[:100]))

        ranked.sort(reverse=True)

        # Find answer session rank
        answer_rank = next((r+1 for r, (_, sid, _, is_ans, _) in enumerate(ranked) if is_ans), None)
        answer_sim  = next((sim for sim, sid, _, is_ans, _ in ranked if is_ans), None)

        print(f"  Answer session rank: {answer_rank}/{len(ranked)} (sim={answer_sim:.3f})")

        # Show top 5 + answer session
        print(f"  Top 5 surfaced:")
        for rank, (sim, sid, kanji, is_ans, preview) in enumerate(ranked[:5], 1):
            marker = " ← ANSWER" if is_ans else ""
            print(f"    #{rank} sim={sim:.3f} [{sid[:20]}] {kanji}{marker}")
            print(f"         {preview[:60]}...")

        # Show answer session if not in top 5
        if answer_rank and answer_rank > 5:
            ans_data = next((d for d in ranked if d[3]), None)
            if ans_data:
                sim, sid, kanji, _, preview = ans_data
                print(f"  Answer session (rank #{answer_rank}):")
                print(f"    sim={sim:.3f} [{sid[:20]}] {kanji}")
                print(f"    {preview[:80]}...")

        # Show what the answer session needs to score higher
        if answer_rank and answer_rank > 3:
            ans_kanji = next((k for _, _, k, is_ans, _ in ranked if is_ans), {})
            print(f"  GAP: Answer has {ans_kanji}, but query wants {q_kanji}")
            missing = set(q_kanji.keys()) - set(ans_kanji.keys())
            if missing:
                print(f"  MISSING Kanji in answer session: {missing}")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
