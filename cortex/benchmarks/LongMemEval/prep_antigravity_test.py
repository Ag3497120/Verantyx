import json
import os

def prepare_challenge(input_file, output_file, count=20):
    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}")
        return
    
    with open(input_file, 'r') as f:
        data = json.load(f)
        
    challenge = []
    for i in range(min(count, len(data))):
        item = data[i]
        
        # Flatten and format haystack sessions
        # For oracle, they might not be sorted by timestamp, but they follow the dialogue flow
        history_text = ""
        for session_idx, session in enumerate(item['haystack_sessions']):
            history_text += f"\n--- Session {session_idx + 1} ---\n"
            for turn in session:
                history_text += f"{turn['role'].capitalize()}: {turn['content']}\n"
        
        challenge.append({
            "question_id": item['question_id'],
            "question_type": item['question_type'],
            "history": history_text.strip(),
            "question": item['question'],
            "ground_truth": item['answer']
        })
        
    with open(output_file, 'w') as f:
        json.dump(challenge, f, indent=2)
    print(f"Created {output_file} with {len(challenge)} questions.")

if __name__ == "__main__":
    prepare_challenge(
        "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/data/longmemeval_oracle.json",
        "/Users/motonishikoudai/verantyx-cli/benchmarks/LongMemEval/challenge_20.json"
    )
