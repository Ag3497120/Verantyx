from enum import Enum, auto

class ProblemType(str, Enum):
    VALIDITY_CHECK = "validity_check"
    COUNTEREXAMPLE_CHECK = "counterexample_check"
    AXIOM_DEPENDENT_VALIDITY = "axiom_dependent_validity"
    SATISFIABILITY_CHECK = "satisfiability_check"
    UNDERDEFINED = "underdefined"
    META_QUERY = "meta_query"
