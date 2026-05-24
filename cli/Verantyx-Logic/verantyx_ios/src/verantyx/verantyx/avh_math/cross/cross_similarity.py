from avh_math.cross.cross_signature import cross_signature

def calculate_cross_similarity(sig1, sig2):
    """
    2つのシグネチャ間の完全一致項目数をスコア化。
    """
    score = 0
    # 基本構成（Node数）の比較
    for a, b in zip(sig1[:3], sig2[:3]):
        if a == b:
            score += 1
    # Axis構成の比較
    if sig1[3] == sig2[3]:
        score += 2
    return score

def find_similar_crosses(target_cross, cross_db, top_k=5):
    target_sig = cross_signature(target_cross)
    scored = []

    for c in cross_db:
        score = calculate_cross_similarity(target_sig, cross_signature(c))
        if score > 0:
            scored.append((score, c))

    # スコアの高い順にソート
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
