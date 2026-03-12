import numpy as np
from typing import Optional

from .color_match import ArtkalPalette, rgb_array_to_lab, lab_distance_batch


def floyd_steinberg_dither(
    image_array: np.ndarray,
    palette: ArtkalPalette,
    allowed_indices: Optional[np.ndarray] = None
) -> np.ndarray:
    """Apply Floyd-Steinberg dithering to an image array.

    The dithering is applied BEFORE color quantization, diffusing the
    quantization error to neighboring pixels for smoother color transitions.

    Args:
        image_array: (H, W, 3) float64 array of RGB values [0, 255]
        palette: ArtkalPalette instance
        allowed_indices: Optional array of allowed palette color indices

    Returns:
        (H, W) int array of palette indices for each pixel
    """
    h, w, _ = image_array.shape
    # Work on a float copy to allow error diffusion with sub-pixel precision
    img = image_array.astype(np.float64).copy()
    result = np.zeros((h, w), dtype=np.int32)

    if allowed_indices is not None:
        palette_rgb = palette.rgb_array[allowed_indices]
        palette_lab = palette.lab_array[allowed_indices]
    else:
        palette_rgb = palette.rgb_array
        palette_lab = palette.lab_array

    for y in range(h):
        for x in range(w):
            old_pixel = img[y, x].copy()

            # Clamp to valid range
            old_pixel = np.clip(old_pixel, 0, 255)

            # Find closest palette color in Lab space
            lab_pixel = _fast_rgb_to_lab_single(old_pixel)
            diff = palette_lab - lab_pixel
            distances = np.sqrt(np.sum(diff * diff, axis=1))
            closest_idx = int(np.argmin(distances))

            # Map back to global palette index
            if allowed_indices is not None:
                result[y, x] = allowed_indices[closest_idx]
            else:
                result[y, x] = closest_idx

            new_pixel = palette_rgb[closest_idx]

            # Compute quantization error in RGB space
            error = old_pixel - new_pixel

            # Distribute error to neighboring pixels (Floyd-Steinberg coefficients)
            if x + 1 < w:
                img[y, x + 1] += error * (7.0 / 16.0)
            if y + 1 < h:
                if x - 1 >= 0:
                    img[y + 1, x - 1] += error * (3.0 / 16.0)
                img[y + 1, x] += error * (5.0 / 16.0)
                if x + 1 < w:
                    img[y + 1, x + 1] += error * (1.0 / 16.0)

    return result


def _fast_rgb_to_lab_single(rgb: np.ndarray) -> np.ndarray:
    """Convert a single RGB pixel (3,) to Lab. Inline for performance."""
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0

    # Inverse sRGB companding
    def linearize(c):
        if c > 0.04045:
            return ((c + 0.055) / 1.055) ** 2.4
        else:
            return c / 12.92

    r_lin = linearize(r)
    g_lin = linearize(g)
    b_lin = linearize(b)

    # sRGB to XYZ
    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041

    # XYZ to Lab
    xn, yn, zn = 0.95047, 1.00000, 1.08883
    delta = 6.0 / 29.0
    delta3 = delta ** 3

    def f(t):
        if t > delta3:
            return t ** (1.0 / 3.0)
        else:
            return t / (3.0 * delta * delta) + 4.0 / 29.0

    fx = f(x / xn)
    fy = f(y / yn)
    fz = f(z / zn)

    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b_val = 200.0 * (fy - fz)

    return np.array([L, a, b_val])
