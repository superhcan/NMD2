"""
generalize_test_semantic.py — Kumulativ MMU-generalisering med semantisk likhet.

Vid eliminering av små ytor väljs den angränsande klassen med lägst semantiskt
avstånd (tematiskt närmast). Vid lika avstånd vinner den störst grannen.
Jämför med generalize_test_conn4.py (largest neighbour, gdal_sieve).

Skyddade klasser (53=väg, 61=sjö, 62=vatten) elimineras aldrig.
"""

import shutil
import time
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

# ── Inställningar ─────────────────────────────────────────────────────────────
TILE      = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/tiles/NMD2023bas_tile_r000_c010.tif")
QML_SRC   = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/NMD2023bas_v2_0.qml")
OUT_DIR   = Path("/home/hcn/NMD_workspace/NMD2023_basskikt_v2_0/generalized_test_semantic")
PROTECTED = {51, 52, 53, 54, 61, 62}
MMU_STEPS = [2, 4, 8, 16, 32, 64, 100]
CONN      = 4   # 4=ortogonalt (jämnare kanter)
# ──────────────────────────────────────────────────────────────────────────────

STRUCT = np.array([[0, 1, 0],
                   [1, 1, 1],
                   [0, 1, 0]], dtype=bool) if CONN == 4 else np.ones((3, 3), dtype=bool)

# ── Semantisk distansfunktion för NMD-klasser ─────────────────────────────────
# Grupperingslogik: 3→3, 5x→5, 6x→6, 1xx→1, 2xx→2, 3xx→3, 4xx→4, 4xxx→4
def nmd_group(v: int) -> int:
    if v <= 0:   return -1
    if v < 10:   return v
    if v < 100:  return v // 10
    if v < 1000: return v // 100
    return v // 1000

# Avstånd mellan NMD-huvudgrupper
# 1=skog, 2=öppen mark, 3=gles/fjäll, 4=jordbruk, 5=bebyggelse, 6=vatten
_GDIST = {
    (1, 2): 2,   # skog ↔ öppen mark
    (1, 3): 3,   # skog ↔ gles mark
    (1, 4): 3,   # skog ↔ jordbruk
    (1, 5): 4,   # skog ↔ bebyggelse
    (1, 6): 5,   # skog ↔ vatten
    (2, 3): 2,   # öppen ↔ gles mark
    (2, 4): 1,   # öppen ↔ jordbruk (ekologiskt nära)
    (2, 5): 3,   # öppen ↔ bebyggelse
    (2, 6): 4,   # öppen ↔ vatten
    (3, 4): 3,   # gles ↔ jordbruk
    (3, 5): 4,   # gles ↔ bebyggelse
    (3, 6): 3,   # gles ↔ vatten (kan vara strandnära)
    (4, 5): 3,   # jordbruk ↔ bebyggelse
    (4, 6): 4,   # jordbruk ↔ vatten
    (5, 6): 4,   # bebyggelse ↔ vatten
}

def sem_dist(a: int, b: int) -> int:
    """Semantiskt avstånd mellan två NMD-klassvärden (0=identisk, 5=maximalt)."""
    if a == b:
        return 0
    ga, gb = nmd_group(a), nmd_group(b)
    if ga == gb:
        return 1   # samma huvudgrupp, olika underklass
    return _GDIST.get((min(ga, gb), max(ga, gb)), 5)


# ── Label- och grannfunktioner ────────────────────────────────────────────────

def build_labels(data: np.ndarray, protected: set):
    """Lablar varje sammanhängande samma-klass-region (per klass, snabbt)."""
    prot   = np.isin(data, list(protected))
    active = ~prot & (data > 0)
    labels  = np.zeros(data.shape, dtype=np.int32)
    lbl_cls = {}
    cur = 1
    for cls in np.unique(data[active]):
        cls = int(cls)
        cls_mask = active & (data == cls)
        lbl, n = ndimage.label(cls_mask, structure=STRUCT)
        if n > 0:
            # Vektoriserad tilldelning: lägg till offset (cur-1) på hela klassen
            labels[cls_mask] = lbl[cls_mask] + (cur - 1)
            for i in range(n):
                lbl_cls[cur + i] = cls
            cur += n
    return labels, lbl_cls


def build_adjacency(labels: np.ndarray, lbl_cls: dict) -> dict:
    """Returnerar {lbl_id: set(grann_lbl_id)}.

    Vektoriserad: undviker Python-loop per gränspixelpar.
    Immutabel — uppdateras INTE under mergning (union-find löser det).
    """
    N     = int(labels.max()) + 1
    dtype = np.int64

    def pairs_coded(a_flat: np.ndarray, b_flat: np.ndarray) -> np.ndarray:
        mask = (a_flat != b_flat) & (a_flat > 0) & (b_flat > 0)
        a, b = a_flat[mask], b_flat[mask]
        swap = a > b
        a2, b2 = a.copy(), b.copy()
        a2[swap], b2[swap] = b[swap], a[swap]
        return a2.astype(dtype) * N + b2.astype(dtype)

    codes_h = pairs_coded(labels[:, :-1].ravel(), labels[:, 1:].ravel())
    codes_v = pairs_coded(labels[:-1, :].ravel(), labels[1:, :].ravel())
    codes   = np.unique(np.concatenate([codes_h, codes_v]))

    if len(codes) == 0:
        return {l: set() for l in lbl_cls}

    pa = (codes // N).astype(np.int32)
    pb = (codes %  N).astype(np.int32)

    adj: dict = {}

    # Bygg a→b med numpy-groupby (ingen Python-loop per par)
    for src_arr, tgt_arr in [(pa, pb), (pb, pa)]:
        order  = np.argsort(src_arr, kind="stable")
        src_s  = src_arr[order]
        tgt_s  = tgt_arr[order]
        _, first, cnt = np.unique(src_s, return_index=True, return_counts=True)
        for i, (idx, c) in enumerate(zip(first, cnt)):
            key = int(src_s[idx])
            tgt = tgt_s[idx:idx + c].tolist()
            if key in adj:
                adj[key].update(tgt)
            else:
                adj[key] = set(tgt)

    return adj


# ── Generaliseringsfunktion ───────────────────────────────────────────────────

def eliminate_small(data: np.ndarray, min_px: int, protected: set) -> np.ndarray:
    """Eliminerar alla patches < min_px px med semantisk grann-prioritering.

    Förbättrad implementation:
    - Bygger labels ETT enda gång (ingen iterativ rebuild)
    - Adjacency byggs EN gång och är immutabel (union-find löser kedjor)
    - Priority queue (heap) med lazy deletion — ingen yttre for-loop
    - Vektoriserad slutapplicering via label_to_class-array
    """
    import heapq

    if min_px <= 1:
        return data.copy()

    print("    Bygger labels … ", end="", flush=True)
    labels, patch_cls = build_labels(data, protected)
    if not patch_cls:
        return data.copy()

    max_lbl  = int(labels.max())
    counts   = np.bincount(labels.ravel(), minlength=max_lbl + 1)
    patch_sz = {l: int(counts[l]) for l in patch_cls}

    print(f"{len(patch_cls):,} patches. Bygger grannskap … ", end="", flush=True)
    adj = build_adjacency(labels, patch_cls)

    # ── Union-find ──────────────────────────────────────────────────────────
    merge_parent: dict = {}   # lbl → parent (for path compression)

    def find_root(lbl: int) -> int:
        path = []
        while lbl in merge_parent:
            path.append(lbl)
            lbl = merge_parent[lbl]
        for p in path:
            merge_parent[p] = lbl     # path compression
        return lbl

    # ── Priority queue ──────────────────────────────────────────────────────
    heap = [(patch_sz[l], l) for l in patch_cls if patch_sz[l] < min_px]
    heapq.heapify(heap)
    print(f"{len(heap):,} patches < {min_px} px att processa. Kör … ", end="", flush=True)

    merged = 0
    while heap:
        _, lbl_id = heapq.heappop(heap)
        root = find_root(lbl_id)

        # Lazy-deletion: hoppa över om mergad eller tillräckligt stor
        if root not in patch_cls:
            continue
        if patch_sz.get(root, 0) >= min_px:
            continue

        lbl_id    = root
        cls       = patch_cls[lbl_id]
        neighbors = adj.get(lbl_id, set())

        # Sök bästa semantiska granne
        best_nb    = None
        best_score = (999, -1)
        seen       : set = set()
        for nb_orig in neighbors:
            nb_root = find_root(nb_orig)
            if nb_root == lbl_id or nb_root in seen:
                continue
            if nb_root not in patch_cls:
                continue
            seen.add(nb_root)
            nb_cls = patch_cls[nb_root]
            score  = (sem_dist(cls, nb_cls), -patch_sz.get(nb_root, 0))
            if score < best_score:
                best_score = score
                best_nb    = nb_root

        if best_nb is None:
            continue   # isolerad mot skyddade klasser — behåll

        # Slå samman lbl_id → best_nb
        merge_parent[lbl_id]  = best_nb
        patch_sz[best_nb]    += patch_sz.pop(lbl_id)
        del patch_cls[lbl_id]
        merged += 1

    print(f"{merged:,} merges gjorda.")

    # ── Vektoriserad slutapplicering ─────────────────────────────────────────
    lbl2cls          = np.zeros(max_lbl + 1, dtype=data.dtype)
    lbl2cls[0]       = 0
    for lbl in range(1, max_lbl + 1):
        root        = find_root(lbl)
        lbl2cls[lbl] = patch_cls.get(root, 0)

    result = lbl2cls[labels]

    # Återställ skyddade pixlar och bakgrund
    prot_mask            = np.isin(data, list(protected))
    result[prot_mask]    = data[prot_mask]
    result[data == 0]    = 0

    return result


# ── Huvudloop ─────────────────────────────────────────────────────────────────
OUT_DIR.mkdir(parents=True, exist_ok=True)

with rasterio.open(TILE) as src:
    meta = src.meta.copy()
    orig = src.read(1)

meta.update(compress="lzw")

print(f"Testtile  : {TILE.name}  ({orig.shape[1]}×{orig.shape[0]} px)")
print(f"Skyddade  : {sorted(PROTECTED)}")
print(f"Metod     : semantisk likhet  (konnektivitet {CONN})")
print(f"Utmapp    : {OUT_DIR}")
print()

prev_data = orig.copy()

for mmu in MMU_STEPS:
    t0      = time.time()
    outname = f"NMD2023bas_tile_r000_c010_semantic_mmu{mmu:03d}.tif"
    outpath = OUT_DIR / outname

    print(f"MMU={mmu:4d} px  ({mmu * 100 / 10000:.2f} ha) ... ", end="", flush=True)

    result = eliminate_small(prev_data, mmu, PROTECTED)

    with rasterio.open(outpath, "w", **meta) as dst:
        dst.write(result, 1)

    if QML_SRC.exists():
        shutil.copy2(QML_SRC, outpath.with_suffix(".qml"))

    prev_data = result.copy()

    elapsed = time.time() - t0
    changed = int(np.sum(orig != result))
    n_after = len(np.unique(result))
    print(f"klar på {elapsed:.1f}s  |  {changed:,} px ändrade vs orig  |  {n_after} unika klasser")

print("\nKlart!")
