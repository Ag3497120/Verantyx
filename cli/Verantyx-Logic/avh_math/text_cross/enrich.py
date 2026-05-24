from .cross import TextDecompositionCross


def enrich(cross: TextDecompositionCross, similars: list[TextDecompositionCross]) -> None:
    for sim in similars:
        mapping = (sim.meta or {}).get("mapping")
        if not mapping:
            continue
        cross.meta.setdefault("hints", [])
        cross.meta["hints"].extend(mapping)
