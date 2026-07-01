"""
match.py
Design doc Section 3 - 'Match keys (tiered, strongest-first)'.

Within each block produced by blocking.py, decides which records actually
refer to the same person, using a tiered confidence hierarchy:
  T1: exact normalized email                -> very high confidence
  T2: exact normalized phone                 -> high confidence
  T3: fuzzy email (edit distance <= 2) + same name -> medium confidence
  T4: fuzzy name (similarity >= 0.9) + same employer -> low-medium confidence
  T5: no reliable key                        -> never auto-merged, standalone

A record is NEVER merged with another on name similarity alone (no
corroborating second signal) - this is a deliberate safety rule from the
design doc to avoid false-positive merges, which are worse than two
separate (honest) profiles for the same person.
"""
import difflib


def _edit_distance_le(a, b, max_dist=2):
    if a is None or b is None:
        return False
    if abs(len(a) - len(b)) > max_dist:
        return False
    # simple DP edit distance
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[m][n] <= max_dist


def _name_similarity(a, b):
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _pair_match_tier(r1, r2):
    """Returns (tier, match_confidence) or (None, 0.0) if no match."""
    e1, e2 = r1.get("norm_email"), r2.get("norm_email")
    p1, p2 = r1.get("norm_phone"), r2.get("norm_phone")
    n1, n2 = r1.get("norm_name"), r2.get("norm_name")
    c1, c2 = (r1.get("raw_company") or "").lower(), (r2.get("raw_company") or "").lower()

    if e1 and e2 and e1 == e2:
        return "T1", 0.98
    if p1 and p2 and p1 == p2:
        return "T2", 0.93
    if e1 and e2 and _edit_distance_le(e1, e2, 2) and n1 and n2 and n1.lower() == n2.lower():
        return "T3", 0.78
    if n1 and n2:
        sim = _name_similarity(n1, n2)
        if sim >= 0.9 and c1 and c2 and (c1 in c2 or c2 in c1):
            return "T4", 0.55

    return None, 0.0


def resolve_clusters(normalized_records, blocks):
    """
    For each block, run pairwise tiered matching and split into final
    clusters using union-find restricted to actual confirmed pairs
    (not "everyone in the block is automatically one entity").

    Returns: list of clusters, each cluster is a dict:
      { "record_indices": [...], "match_confidence": float, "match_tier": str }
    """
    clusters = []

    for block in blocks:
        if len(block) == 1:
            clusters.append({
                "record_indices": block,
                "match_confidence": 1.0,  # single record, trivially "matched" to itself
                "match_tier": "SINGLETON",
            })
            continue

        parent = {i: i for i in block}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        pair_evidence = {}
        for i in range(len(block)):
            for j in range(i + 1, len(block)):
                idx_a, idx_b = block[i], block[j]
                tier, conf = _pair_match_tier(normalized_records[idx_a], normalized_records[idx_b])
                if tier:
                    union(idx_a, idx_b)
                    pair_evidence[(idx_a, idx_b)] = (tier, conf)

        sub_blocks = {}
        for i in block:
            sub_blocks.setdefault(find(i), []).append(i)

        for root, members in sub_blocks.items():
            if len(members) == 1:
                clusters.append({
                    "record_indices": members,
                    "match_confidence": 1.0,
                    "match_tier": "SINGLETON",
                })
            else:
                relevant = [v for k, v in pair_evidence.items()
                            if k[0] in members and k[1] in members]
                best_tier = min((t for t, _ in relevant), default="T5",
                                 key=lambda t: int(t[1]))
                avg_conf = sum(c for _, c in relevant) / len(relevant) if relevant else 0.5
                clusters.append({
                    "record_indices": members,
                    "match_confidence": round(avg_conf, 2),
                    "match_tier": best_tier,
                })

    return clusters
