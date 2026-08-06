import os

import numpy as np
from PIL import Image

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def is_background_pixel(r, g, b, threshold=20):
    return (max(r, g, b) - min(r, g, b)) < threshold


def make_transparent(input_path, output_path, threshold=20):
    img = Image.open(input_path).convert("RGB")
    arr = np.array(img)

    rgb_max = arr.max(axis=2).astype(int)
    rgb_min = arr.min(axis=2).astype(int)
    is_background = (rgb_max - rgb_min) < threshold

    alpha = np.where(is_background, 0, 255).astype(np.uint8)
    rgba = np.dstack([arr, alpha])
    Image.fromarray(rgba, mode="RGBA").save(output_path)


if __name__ == "__main__":
    make_transparent(
        os.path.join(SCRIPT_DIR, "stage3.jpeg"),
        os.path.join(SCRIPT_DIR, "stage3_transparent.png"),
    )
