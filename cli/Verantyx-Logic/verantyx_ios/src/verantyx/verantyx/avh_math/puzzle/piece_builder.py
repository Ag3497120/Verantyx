from avh_math.puzzle.piece import PuzzlePiece
from avh_math.text_cross.formula_extractor import extract_formula_candidates

def build_pieces_from_text(text: str) -> List[PuzzlePiece]:
    pieces = []

    for cand in extract_formula_candidates(text):
        pieces.append(PuzzlePiece(
            kind="formula",
            content=cand["normalized"],
            confidence=min(1.0, cand["score"] / 3.0),
            source="text",
            metadata={"surface": cand["surface"], "span": cand["span"]}
        ))

    return pieces
