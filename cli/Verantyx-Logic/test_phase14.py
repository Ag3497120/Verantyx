from engine import MathEngine
import json

def test_phase14():
    engine = MathEngine()
    
    # 複雑な様相論理の式をテスト。
    # 通常の探索で見逃される可能性があるケースを想定。
    test_text = "assume:transitive, assume:reflexive. formula: []p -> [][]p"
    
    print("Testing Phase 14 implementation...")
    result = engine.solve(test_text)
    
    print("\n--- Solve Result ---")
    print(f"Assumptions: {result.assumptions}")
    print(f"Best Valid: {result.best_valid}")
    
    for i, candidate in enumerate(result.ranked):
        print(f"\nCandidate {i+1}: {candidate.formula}")
        print(f"Status: {candidate.status}")
        print(f"Energy: {candidate.energy}")
        print(f"Diffs: {candidate.diffs}")
        
    found_phase14 = any("diff:phase14" in str(c.diffs) for c in result.ranked)
    if found_phase14:
        print("\n[SUCCESS] Phase 14 markers found in results.")
    else:
        print("\n[FAILURE] Phase 14 markers not found.")

    # 追跡ログの確認
    phase14_logs = [line for line in result.trace if "PHASE14" in line]
    if phase14_logs:
        print("\n--- Phase 14 Logs ---")
        for log in phase14_logs:
            print(log)
    else:
        print("\n[FAILURE] No Phase 14 logs found in trace.")

if __name__ == "__main__":
    test_phase14()
