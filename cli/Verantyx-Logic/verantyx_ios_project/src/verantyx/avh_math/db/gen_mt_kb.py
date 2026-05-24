import json

def generate_mt_entries(start_seq=1, count=3000):
    entries = []
    
    # Ratios
    # definition (20%) = 600
    # axiom (10%) = 300
    # theorem (35%) = 1050
    # rule/lemma (20%) = 600
    # counterexample_schema (15%) = 450
    
    kinds = {
        "definition": 600,
        "axiom": 300,
        "theorem": 1050,
        "lemma": 600,
        "counterexample_schema": 450
    }
    
    topics = [
        "Structure", "Signature", "Language", "Satisfaction", "Elementary Equivalence",
        "Elementary Substructure", "Diagram", "Tarski-Vaught Test", "Compactness",
        "Lowenheim-Skolem", "Ultraproduct", "Ultrapower", "Los Theorem",
        "Quantifier Elimination", "Type", "Saturation", "Omitting Types",
        "Categoricity", "Morley Theorem", "Stability", "Indiscernibles",
        "Model Companion", "Model Completeness", "Back-and-forth", "Fraisse Limit"
    ]
    
    for kind, num in kinds.items():
        for i in range(num):
            seq = i + 1
            topic = topics[i % len(topics)]
            entry_id = f"mt.{kind[:3]}.{seq:04d}"
            
            # Basic templates
            if kind == "definition":
                title = f"{topic} Definition {seq}"
                statement = f"Definition of {topic} in Model Theory, instance {seq}. Specifies the fundamental properties and constraints of {topic.lower()}."
                yields = [f"tag:{topic.lower().replace(' ', '_')}"]
                refutation = None
            elif kind == "axiom":
                title = f"{topic} Axiom {seq}"
                statement = f"Axiomatic property of {topic}, instance {seq}. Asserting a fundamental truth about {topic.lower()} in a specific theory."
                yields = [f"tag:{topic.lower().replace(' ', '_')}_axiom"]
                refutation = None
            elif kind == "theorem":
                title = f"{topic} Theorem {seq}"
                statement = f"Theorem concerning {topic}, instance {seq}. Proving a significant result regarding {topic.lower()} under specific conditions."
                yields = [f"tag:{topic.lower().replace(' ', '_')}_theorem"]
                refutation = None
            elif kind == "lemma":
                title = f"{topic} Lemma {seq}"
                statement = f"Supporting lemma for {topic}, instance {seq}. A technical result used in the development of {topic.lower()}."
                yields = [f"tag:{topic.lower().replace(' ', '_')}_lemma"]
                refutation = None
            else: # counterexample_schema
                title = f"{topic} Counterexample {seq}"
                statement = f"Counterexample showing where {topic} fails, instance {seq}."
                yields = []
                refutation = {
                    "domain": "Varies (e.g., N, Q, or Finite structures)",
                    "interpretation": f"A specific model where the expected {topic} property does not hold.",
                    "assignment": "Specific values or mappings illustrating the failure.",
                    "failure_point": f"Conflict with {topic} constraints."
                }
            
            entry = {
                "id": entry_id,
                "domain": "model_theory",
                "kind": kind,
                "title": title,
                "statement": statement,
                "prerequisites": ["mt:basics"],
                "yields": yields,
                "refutation": refutation,
                "patterns": [topic.lower(), f"{kind} {topic.lower()}"],
                "links": []
            }
            entries.append(entry)
            
    return entries

if __name__ == "__main__":
    mt_entries = generate_mt_entries()
    with open("mt_entries.jsonl", "w") as f:
        for entry in mt_entries:
            f.write(json.dumps(entry) + "\n")
