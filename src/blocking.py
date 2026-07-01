"""
blocking.py
Design doc Section 1 - 'Block' stage (unique add-on).

Groups extracted-and-normalized records into candidate blocks using cheap
keys (normalized email, normalized phone, first+last name initials) BEFORE
any pairwise comparison happens. This avoids O(n^2) comparisons across the
whole dataset and is the standard entity-resolution 'blocking' technique,
which is what makes the pipeline scale to thousands of candidates.

Records that share ANY blocking key end up considered together by match.py.
Records with no usable key at all (e.g. no email/phone, only a free-text
name) fall into their own singleton block - they are never silently merged
into someone else's block on weak evidence.
"""
from collections import defaultdict


def _name_key(name):
    if not name:
        return None
    parts = name.strip().lower().split()
    if len(parts) < 2:
        return None
    return f"{parts[0][0]}_{parts[-1]}"  # e.g. "a_sharma"


def build_blocks(normalized_records):
    """
    normalized_records: list of dicts with at least 'norm_email', 'norm_phone', 'norm_name'.
    Returns: list of blocks, where each block is a list of record indices
    that share at least one blocking key.
    """
    email_index = defaultdict(list)
    phone_index = defaultdict(list)
    name_index = defaultdict(list)

    for i, rec in enumerate(normalized_records):
        if rec.get("norm_email"):
            email_index[rec["norm_email"]].append(i)
        if rec.get("norm_phone"):
            phone_index[rec["norm_phone"]].append(i)
        nk = _name_key(rec.get("norm_name"))
        if nk:
            name_index[nk].append(i)

    # Union-find to merge indices that share any key into one block
    parent = list(range(len(normalized_records)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for index in (email_index, phone_index, name_index):
        for key, members in index.items():
            for m in members[1:]:
                union(members[0], m)

    blocks = defaultdict(list)
    for i in range(len(normalized_records)):
        blocks[find(i)].append(i)

    return list(blocks.values())
