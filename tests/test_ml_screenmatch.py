import pytest

pytest.importorskip("torch")
pytest.importorskip("PIL")
from PIL import Image

from fa.ml import screenmatch as sm
from fa.tree import parse


def X(foc_bounds, others=()):
    def node(b, foc):
        return (f'<node class="V" package="p" text="" content-desc="" focusable="true" focused="{str(foc).lower()}" '
                f'clickable="false" bounds="[{b[0]},{b[1]}][{b[2]},{b[3]}]"/>')
    return parse('<hierarchy>' + node(foc_bounds, True) + "".join(node(b, False) for b in others) + "</hierarchy>")


def item(path, visit, snap, app="a"):
    return {"id": f"{path}{visit}", "set": app, "path": tuple(path), "visit": visit, "snap": snap, "png": ""}


GRID = [(100 * i, 0, 100 * i + 90, 90) for i in range(1, 8)]


def test_pair_rule_same_different_ambiguous():
    s = X((0, 0, 90, 90), GRID)
    assert sm.pair_label(item("AB", 0, s), item("AB", 1, s)) == 1                        # same path
    far = X((500, 500, 590, 590), GRID)
    assert sm.pair_label(item("A", 0, s), item("B", 0, far)) == 0                         # focused bounds differ
    other_set = X((0, 0, 90, 90), [(100 * i, 300, 100 * i + 90, 390) for i in range(1, 8)])
    assert sm.pair_label(item("A", 0, s), item("B", 0, other_set)) == 0                   # >=30% focusable difference
    near = X((0, 0, 90, 90), GRID[:-1] + [(900, 900, 990, 990)])                          # 1 of 8 differs (<30%), same focus
    assert sm.pair_label(item("A", 0, s), item("B", 0, near)) is None                     # ambiguous, skipped
    assert sm.pair_label(item("A", 0, s, "a"), item("B", 0, far, "b")) is None            # different apps never paired


def test_build_pairs_counts_and_negative_cap():
    s, far = X((0, 0, 90, 90), GRID), X((500, 500, 590, 590), GRID)
    items = [item("P%d" % p, v, s if p % 2 else far) for p in range(6) for v in range(3)]
    pairs, c = sm.build_pairs(items)
    assert c["positive"] == 18 and c["negative_used"] <= sm.NEG_PER_POS * 18
    assert all(y in (0, 1) for *_, y in pairs)


def test_auc_toy_and_matches_sklearn():
    y, s = [0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]
    assert sm.roc_auc(y, s) == 0.75
    from sklearn.metrics import roc_auc_score
    y2, s2 = [1, 0, 1, 0, 1, 0, 0], [0.9, 0.9, 0.2, 0.1, 0.7, 0.7, 0.3]
    assert sm.roc_auc(y2, s2) == pytest.approx(roc_auc_score(y2, s2))
    assert sm.roc_auc([1, 1], [0.5, 0.6]) is None


def test_prf_and_threshold():
    m = sm.prf([1, 1, 0, 0], [True, False, True, False])
    assert (m["precision"], m["recall"], m["false_merge_rate"]) == (0.5, 0.5, 0.5)
    assert sm.pick_threshold([1, 1, 0, 0], [0.9, 0.8, 0.3, 0.2]) == 0.8


def test_phash_stable_to_small_noise_and_hamming():
    a = Image.effect_noise((64, 64), 40).convert("RGB")
    b = a.copy()
    b.putpixel((1, 1), (255, 255, 255))
    c = Image.effect_noise((64, 64), 90).convert("RGB").transpose(Image.FLIP_LEFT_RIGHT)
    assert sm.hamming(sm.phash(a), sm.phash(b)) <= sm.hamming(sm.phash(a), sm.phash(c)) + 0  # noise moves the hash less than a different image
    assert sm.hamming(0b1011, 0b0001) == 2


def test_tree_hashes_ignore_text_in_struct_only():
    a, b = X((0, 0, 90, 90), GRID), X((0, 0, 90, 90), GRID)
    assert sm.tree_exact(a) == sm.tree_exact(b) and sm.tree_struct(a) == sm.tree_struct(b)
    c = parse(a.raw.replace('text=""', 'text="hero 2"', 1))
    assert sm.tree_exact(a) != sm.tree_exact(c) and sm.tree_struct(a) == sm.tree_struct(c)
