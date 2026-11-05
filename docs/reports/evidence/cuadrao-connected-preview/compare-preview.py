"""Report pixel differences against the retained Preview baseline without edits."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

root = Path(__file__).resolve().parent
rows = []
for folder in ("after", "final-preview"):
    for candidate in sorted((root / folder).glob("*.png")):
        baseline = root / "baseline" / candidate.name
        with Image.open(baseline) as original, Image.open(candidate) as current:
            a, b = original.convert("RGB"), current.convert("RGB")
            if a.size != b.size:
                raise SystemExit(f"Dimensions differ for {candidate.relative_to(root)}")
            difference = np.abs(np.asarray(a).astype(int) - np.asarray(b).astype(int))
            rows.append({
                "image": str(candidate.relative_to(root)),
                "changed_pixels": int(np.any(difference, axis=2).sum()),
                "max_channel_difference": int(difference.max()),
                "diff_bbox": ImageChops.difference(a, b).getbbox(),
                "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
                "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            })
print(json.dumps(rows, indent=2))
