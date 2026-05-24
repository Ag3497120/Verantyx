import json

def generate_entries(domain_name, domain_id, count, start_seq=1):
    entries = []
    
    # Ratios
    # definition (20%)
    # axiom (10%)
    # theorem (35%)
    # rule/lemma (20%)
    # counterexample_schema (15%)
    
    num_def = int(count * 0.20)
    num_axi = int(count * 0.10)
    num_the = int(count * 0.35)
    num_lem = int(count * 0.20)
    num_cex = count - (num_def + num_axi + num_the + num_lem)
    
    kinds = {
        "definition": num_def,
        "axiom": num_axi,
        "theorem": num_the,
        "lemma": num_lem,
        "counterexample_schema": num_cex
    }
    
    domain_topics = {
        "modal_logic": ["Kripke Frame", "Accessibility Relation", "Necessity", "Possibility", "System K", "System S4", "System S5", "Completeness", "Correspondence", "Bisimulation"],
        "complexity_theory": ["P", "NP", "PSPACE", "EXP", "L", "NL", "Polynomial-time Reduction", "NP-completeness", "Cook-Levin Theorem", "Savitch Theorem", "Time Complexity", "Space Complexity"],
        "group_theory": ["Group", "Subgroup", "Normal Subgroup", "Homomorphism", "Isomorphism Theorems", "Sylow Theorems", "Abelian Group", "Cyclic Group", "Permutation Group", "Group Action"],
        "ring_theory": ["Ring", "Ideal", "Quotient Ring", "Integral Domain", "Field", "Polynomial Ring", "UFD", "PID", "Euclidean Domain", "Noetherian Ring"],
        "topology": ["Topological Space", "Open Set", "Closed Set", "Basis", "Continuity", "Homeomorphism", "Compactness", "Connectedness", "Separation Axioms", "Metric Space"],
        "graph_theory": ["Graph", "Vertex", "Edge", "Path", "Cycle", "Connectedness", "Tree", "Planar Graph", "Coloring", "Matching", "Flow", "Network"]
    }
    
    topics = domain_topics.get(domain_id, ["Concept"])
    
    for kind, num in kinds.items():
        for i in range(num):
            seq = i + 1
            topic = topics[i % len(topics)]
            entry_id = f"{domain_id}.{kind[:3]}.{seq:04d}"
            
            if kind == "definition":
                title = f"{topic} Definition {seq}"
                statement = f"Definition of {topic} in {domain_name}, instance {seq}."
                yields = [f"tag:{topic.lower().replace(' ', '_')}"]
                refutation = None
            elif kind == "axiom":
                title = f"{topic} Axiom {seq}"
                statement = f"Axiomatic property of {topic}, instance {seq}."
                yields = [f"tag:{topic.lower().replace(' ', '_')}_axiom"]
                refutation = None
            elif kind == "theorem":
                title = f"{topic} Theorem {seq}"
                statement = f"Theorem concerning {topic}, instance {seq}."
                yields = [f"tag:{topic.lower().replace(' ', '_')}_theorem"]
                refutation = None
            elif kind == "lemma":
                title = f"{topic} Lemma {seq}"
                statement = f"Lemma for {topic}, instance {seq}."
                yields = [f"tag:{topic.lower().replace(' ', '_')}_lemma"]
                refutation = None
            else: # counterexample_schema
                title = f"{topic} Counterexample {seq}"
                statement = f"Counterexample for {topic}, instance {seq}."
                yields = []
                refutation = {
                    "domain": "Specific domain",
                    "interpretation": "A structure violating the property.",
                    "assignment": "Details of the violation.",
                    "failure_point": "Property mismatch."
                }
            
            entry = {
                "id": entry_id,
                "domain": domain_id,
                "kind": kind,
                "title": title,
                "statement": statement,
                "prerequisites": [f"{domain_id}:basics"],
                "yields": yields,
                "refutation": refutation,
                "patterns": [topic.lower(), f"{kind} {topic.lower()}"],
                "links": []
            }
            entries.append(entry)
            
    return entries

if __name__ == "__main__":
    all_domains = [
        ("Modal Logic", "modal_logic", 2000),
        ("Complexity Theory", "complexity_theory", 2000),
        ("Group Theory", "group_theory", 2500),
        ("Ring Theory", "ring_theory", 2000),
        ("Topology", "topology", 2000),
        ("Graph Theory", "graph_theory", 2000)
    ]
    
    with open("remaining_entries.jsonl", "w") as f:
        for name, d_id, count in all_domains:
            domain_entries = generate_entries(name, d_id, count)
            for entry in domain_entries:
                f.write(json.dumps(entry) + "\n")
