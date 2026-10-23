# Screen matching: same screen under self-changing content

Encoder: torchvision mobilenet_v3_small (ImageNet) on mps. Images: 20 from jetstream. Labels are automatic (rule in `fa/ml/screenmatch.py`); thresholds are chosen on one fold and reported on the other.

Pair labels (automatic): same path = SAME; different paths = DIFFERENT only if the focused-node bounds differ OR the focusable-node sets differ by >= 30% (Jaccard of 8px-quantized bounds <= 0.70); other cross-path pairs are ambiguous and skipped. Different-screen pairs are subsampled (seeded) to at most 5x the same-screen pairs.

**WARNING: only 36 test pairs in the smaller fold, ranking is not statistically meaningful. Best mean test F1 is `tree_exact` (0.690, mean false-merge rate 0.000). A simple non-neural method wins; the neural encoder is not needed on this data.**

## calibrate on even-indexed paths, report on odd

Test pairs: 9 same, 27 different (of 27), 0 ambiguous skipped; 9 images. Calibration pairs: 10 same, 37 different.

| method | AUC | threshold | precision | recall | F1 | false-merge rate |
|---|---|---|---|---|---|---|
| tree_exact | - | exact hash equality | 1.000 | 0.556 | 0.714 | 0.000 |
| tree_struct | - | exact hash equality | 0.455 | 0.556 | 0.500 | 0.222 |
| jaccard | 0.753 | 0.353 | 0.455 | 0.556 | 0.500 | 0.222 |
| phash | 0.634 | 0.906 | 1.000 | 0.556 | 0.714 | 0.000 |
| embed | 0.761 | 0.803 | 0.455 | 0.556 | 0.500 | 0.222 |
| fused | - | {"embed": 0.8034806847572327, "tree_struct": "equal"} | 0.455 | 0.556 | 0.500 | 0.222 |

## calibrate on odd-indexed paths, report on even

Test pairs: 10 same, 37 different (of 37), 8 ambiguous skipped; 11 images. Calibration pairs: 9 same, 27 different.

| method | AUC | threshold | precision | recall | F1 | false-merge rate |
|---|---|---|---|---|---|---|
| tree_exact | - | exact hash equality | 1.000 | 0.500 | 0.667 | 0.000 |
| tree_struct | - | exact hash equality | 1.000 | 0.500 | 0.667 | 0.000 |
| jaccard | 0.859 | 0.280 | 0.533 | 0.800 | 0.640 | 0.189 |
| phash | 0.538 | 1.000 | 1.000 | 0.400 | 0.571 | 0.000 |
| embed | 0.873 | 1.000 | 1.000 | 0.400 | 0.571 | 0.000 |
| fused | - | {"embed": 0.9999999403953552, "tree_struct": "equal"} | 1.000 | 0.400 | 0.571 | 0.000 |

## Per-image latency (mean, ms)

| step | ms |
|---|---|
| tree_parse+hash | 0.058 |
| phash | 1.059 |
| embed | 17.278 |
