import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import Counter
import math

from PIL import Image, ImageEnhance, ImageFilter, ImageColor

from .color_match import ArtkalPalette, rgb_to_lab, lab_distance
from .dithering import floyd_steinberg_dither


def _build_pil_palette_image_from_colors(color_list: List[Dict]) -> Image.Image:
    """Build a PIL palette image from a list of color dicts.

    Each dict must have an 'hex' key. Creates a P-mode image for use
    with PIL quantize().

    Args:
        color_list: List of color dicts with 'hex' key

    Returns:
        PIL Image in 'P' mode
    """
    hex_list = [c['hex'] for c in color_list]
    rgb_tuples = [ImageColor.getrgb(h) for h in hex_list]
    pal_flat = [item for sub in rgb_tuples for item in sub]
    entries = len(rgb_tuples)
    full_palette = pal_flat + [0] * (256 - entries) * 3
    resnp = np.arange(entries, dtype=np.uint8).reshape(entries, 1)
    pal_img = Image.fromarray(resnp, mode='P')
    pal_img.putpalette(full_palette)
    return pal_img


def _estimate_color_count(image: Image.Image, grid_width: int, grid_height: int) -> int:
    """Estimate how many palette colors are needed for this image.

    Uses image variance to decide: simple images (cartoon, logo) need fewer
    colors, complex images (photo) need more. Range: 12 to 40.

    Args:
        image: Preprocessed PIL image (RGB)
        grid_width: Target grid width
        grid_height: Target grid height

    Returns:
        Estimated number of colors (12-40)
    """
    # Analyze at small scale for speed
    small = image.resize((80, 80), Image.LANCZOS)
    arr = np.array(small, dtype=np.float64)
    # Per-channel variance as complexity metric
    total_var = np.sum(np.var(arr.reshape(-1, 3), axis=0))
    # Map variance to color count:
    # Low variance (<500) = simple image -> 12 colors
    # High variance (>4000) = complex photo -> 40 colors
    n = int(12 + (total_var - 500) * 28 / 3500)
    n = max(12, min(40, n))
    # Scale slightly with grid size: larger grids can show more detail
    if grid_width * grid_height > 48 * 48:
        n = min(40, n + 5)
    elif grid_width * grid_height < 29 * 29:
        n = max(12, n - 3)
    return n


def process_image(
    image: Image.Image,
    palette: ArtkalPalette,
    mode: str = "fixed_grid",
    grid_width: int = 48,
    grid_height: int = 48,
    pixel_size: int = 8,
    use_dithering: bool = False,
    palette_preset: str = "221",
    max_colors: int = 0,
    similarity_threshold: int = 0,
    remove_bg: bool = False,
    contrast: float = 0.0,
    saturation: float = 0.0,
    sharpness: float = 0.0,
) -> Dict:
    """Process an uploaded image into a bead pattern.

    Pipeline (PixArt-Beads inspired: quantize-first-then-downscale):
    1. Preprocess image (contrast, saturation, sharpness)
    2. Quantize full-resolution image to bead palette (PIL median cut)
    3. Downscale quantized image to grid size (NEAREST to preserve palette colors)
    4. Map pixel RGB to palette color codes
    5. Post-processing: color merging, max colors cap, edge smoothing
    6. Background removal: flood-fill from border edges

    The key insight from PixArt-Beads: quantize at full resolution FIRST
    so the median-cut algorithm has maximum pixel information for optimal
    color assignment. Then NEAREST downscale to grid -- NEAREST is critical
    because the image already contains only valid palette colors, and any
    other interpolation (BILINEAR/LANCZOS) would create ~1500 interpolated
    RGB values that don't exist in the palette, corrupting the result.

    Args:
        image: PIL Image object (RGB)
        palette: ArtkalPalette instance
        mode: "fixed_grid" or "pixel_size"
        grid_width: Target grid width (used when mode="fixed_grid")
        grid_height: Target grid height (used when mode="fixed_grid")
        pixel_size: Pixel block size (used when mode="pixel_size")
        use_dithering: Whether to apply Floyd-Steinberg dithering
        palette_preset: Preset key ("96", "120", "144", "168", "221")
        max_colors: Maximum number of colors (0 = unlimited)
        similarity_threshold: Merge similar colors below this Lab distance (0 = disabled)
        remove_bg: Whether to auto-remove background via border flood fill
        contrast: User contrast adjustment (-50 to +50, 0 = auto)
        saturation: User saturation adjustment (-50 to +50, 0 = auto)
        sharpness: User sharpness adjustment (-50 to +50, 0 = auto)

    Returns:
        Dict with keys: pixel_matrix, color_summary, grid_size, total_beads
    """
    # Ensure RGB mode
    if image.mode != 'RGB':
        image = image.convert('RGB')

    img_width, img_height = image.size

    # Step 1: Determine grid dimensions
    if mode == "pixel_size":
        grid_width = max(1, img_width // pixel_size)
        grid_height = max(1, img_height // pixel_size)

    # Step 2: Image preprocessing (contrast, saturation, sharpness)
    image = _preprocess_image(image, contrast, saturation, sharpness)

    # Step 3: Consolidate near-black and near-white pixels
    # Human eyes cannot distinguish dark colors or very light colors,
    # but median cut treats every tiny RGB difference as separate.
    # Desaturate extreme-luminance pixels to reduce spurious dark/light shades.
    image = _consolidate_extremes(image)

    # Step 4: Pre-select a small sub-palette from the full preset
    # PixArt-Beads works with 36-46 color palettes. Our Artkal has 221 colors
    # with 884 pairs at Lab dist < 15. Quantizing with all 221 maps tiny RGB
    # differences to different palette entries. Solution: analyze image at
    # low-res, find the top N most-needed palette colors, quantize with those.
    preset_indices = palette.get_preset_indices(palette_preset)
    sub_palette_size = max_colors if max_colors > 0 else _estimate_color_count(image, grid_width, grid_height)
    sub_indices = palette.select_top_n_colors(
        np.array(image.resize((120, 120), Image.LANCZOS)).reshape(-1, 3).astype(np.float64),
        n=sub_palette_size,
        allowed_indices=preset_indices,
    )
    sub_colors = [palette.colors[int(i)] for i in sub_indices]

    # Build PIL palette image from the sub-palette
    sub_pal_img = _build_pil_palette_image_from_colors(sub_colors)

    # Step 5: PixArt-Beads inspired mosaic pipeline
    # Hybrid approach combining anti-aliasing with clean color selection:
    #   a) LANCZOS downscale to 4x grid size (anti-aliased, smooth edges)
    #   b) Quantize at 4x resolution (enough pixels for good color decisions)
    #   c) Mode-pool each 4x4 block to grid (majority vote = clean colors)
    # This mimics PixArt's "quantize then downscale in P-mode" approach
    # while adding LANCZOS anti-aliasing for photos.
    POOL_FACTOR = 4
    mid_w, mid_h = grid_width * POOL_FACTOR, grid_height * POOL_FACTOR
    img_mid = image.resize((mid_w, mid_h), Image.LANCZOS)

    # Step 6: Quantize at intermediate resolution
    dither_flag = 1 if use_dithering else 0
    img_mid_quantized = img_mid.quantize(
        palette=sub_pal_img, method=0, dither=dither_flag
    )

    # Step 7: Mode-pool to grid (majority vote per block)
    # For each POOL_FACTORxPOOL_FACTOR block, pick the most common palette
    # index. This is cleaner than NEAREST (random pick) or LANCZOS (blurs
    # colors). It's the closest equivalent to PixArt's P-mode BILINEAR.
    qnt_indices = np.array(img_mid_quantized, dtype=np.uint8)
    pal_data = img_mid_quantized.getpalette()

    # Build mapping from quantized image's palette indices to our sub_palette indices
    # PIL's quantize() may produce indices that don't directly correspond to our sub_palette
    n_colors = len(sub_colors)
    
    # Build lookup: sub_palette RGB -> sub_palette index
    sub_rgb_to_idx = {}
    for i, c in enumerate(sub_colors):
        sub_rgb_to_idx[tuple(c['rgb'])] = i
    
    # Build mapping: actual palette index (0-255) -> sub_palette index
    idx_mapping = np.zeros(256, dtype=np.uint8)
    for actual_idx in range(256):
        r = pal_data[actual_idx * 3]
        g = pal_data[actual_idx * 3 + 1]
        b = pal_data[actual_idx * 3 + 2]
        rgb = (r, g, b)
        if rgb in sub_rgb_to_idx:
            idx_mapping[actual_idx] = sub_rgb_to_idx[rgb]
        else:
            # Find closest match in sub_palette using Lab distance
            best_idx = 0
            best_dist = float('inf')
            for sub_idx, c in enumerate(sub_colors):
                dr = r - c['rgb'][0]
                dg = g - c['rgb'][1]
                db = b - c['rgb'][2]
                dist = dr*dr + dg*dg + db*db
                if dist < best_dist:
                    best_dist = dist
                    best_idx = sub_idx
            idx_mapping[actual_idx] = best_idx
    
    # Remap quantized indices to sub_palette indices
    qnt_indices = idx_mapping[qnt_indices]

    # Vectorized mode-pool: reshape into blocks, then find mode per block
    # Reshape (mid_h, mid_w) -> (grid_h, POOL, grid_w, POOL) -> (grid_h, grid_w, POOL*POOL)
    blocks = qnt_indices.reshape(grid_height, POOL_FACTOR, grid_width, POOL_FACTOR)
    blocks = blocks.transpose(0, 2, 1, 3).reshape(grid_height, grid_width, POOL_FACTOR * POOL_FACTOR)
    # For each block, find the most frequent index using vectorized bincount
    grid_indices = np.zeros((grid_height, grid_width), dtype=np.uint8)
    for y in range(grid_height):
        for x in range(grid_width):
            grid_indices[y, x] = np.bincount(blocks[y, x], minlength=n_colors).argmax()

    # Convert palette indices to RGB using vectorized lookup
    pal_array = np.array([c['rgb'] for c in sub_colors], dtype=np.uint8)
    grid_rgb = pal_array[grid_indices]

    # Step 8: Build code matrix by mapping pixel RGB -> palette code
    rgb_to_code = {}
    for c in sub_colors:
        r, g, b = c['rgb']
        rgb_to_code[(r, g, b)] = c['code']

    code_matrix = []
    for y in range(grid_height):
        row = []
        for x in range(grid_width):
            r, g, b = int(grid_rgb[y, x, 0]), int(grid_rgb[y, x, 1]), int(grid_rgb[y, x, 2])
            code = rgb_to_code.get((r, g, b))
            if code is None:
                color_info = palette.find_closest(r, g, b, allowed_indices=sub_indices)
                code = color_info['code']
            row.append(code)
        code_matrix.append(row)

    # Step 9: Auto-cleanup rare colors (< 0.5% of total pixels)
    total_pixels = grid_width * grid_height
    min_pixel_ratio = 0.005
    code_matrix = _cleanup_rare_colors(code_matrix, palette, total_pixels, min_pixel_ratio)

    # Step 10: Color merging by similarity threshold (perler-beads-master approach)
    if similarity_threshold > 0:
        code_matrix = _merge_similar_colors(code_matrix, palette, similarity_threshold)

    # Step 11: Max colors cap - keep top N, remap rest to nearest allowed
    if max_colors > 0:
        code_matrix = _cap_max_colors(code_matrix, palette, max_colors)

    # Step 12: Edge smoothing - remove isolated single-pixel color islands
    code_matrix = _smooth_edges(code_matrix, palette)

    # Step 13: Background removal via border flood fill
    if remove_bg:
        code_matrix = _remove_background_flood_fill(code_matrix)

    # Step 14: Build final result
    pixel_matrix = code_matrix
    color_counter = Counter()
    for row in pixel_matrix:
        for code in row:
            if code is not None:
                color_counter[code] += 1

    # Build color summary sorted by count (descending)
    color_summary = []
    for code, count in color_counter.most_common():
        color_info = palette.get_by_code(code)
        if color_info:
            color_summary.append({
                'code': color_info['code'],
                'name': color_info['name'],
                'name_zh': color_info['name_zh'],
                'hex': color_info['hex'],
                'count': count,
            })

    total_beads = sum(c['count'] for c in color_summary)

    return {
        'pixel_matrix': pixel_matrix,
        'color_summary': color_summary,
        'grid_size': {'width': grid_width, 'height': grid_height},
        'total_beads': total_beads,
    }


def _preprocess_image(
    image: Image.Image,
    contrast: float = 0.0,
    saturation: float = 0.0,
    sharpness: float = 0.0,
) -> Image.Image:
    """Preprocess image before quantization.

    Apply contrast / saturation / sharpness enhancement.
    No pre-downscale needed in the new pipeline because PIL quantize()
    operates efficiently on full-resolution images in C code.

    User adjustment range is [-50, +50]:
      - 0 means "auto" (adaptive based on image histogram)
      - Negative = reduce
      - Positive = boost

    Args:
        image: Original PIL image (RGB)
        contrast: User contrast adjustment (-50 to +50, 0 = auto)
        saturation: User saturation adjustment (-50 to +50, 0 = auto)
        sharpness: User sharpness adjustment (-50 to +50, 0 = auto)

    Returns:
        Preprocessed PIL image
    """
    # --- Contrast ---
    if contrast == 0.0:
        # Auto: analyze histogram spread to decide enhancement
        gray = image.convert('L')
        hist = gray.histogram()  # 256 bins
        total = sum(hist)
        # Compute percentile spread (5th to 95th)
        cumsum = 0
        p5 = 0
        p95 = 255
        for i, count in enumerate(hist):
            cumsum += count
            if cumsum >= total * 0.05 and p5 == 0:
                p5 = i
            if cumsum >= total * 0.95:
                p95 = i
                break
        spread = p95 - p5
        if spread < 100:
            auto_contrast = 1.25
        elif spread < 160:
            auto_contrast = 1.15
        else:
            auto_contrast = 1.05
        image = ImageEnhance.Contrast(image).enhance(auto_contrast)
    else:
        factor = 1.0 + contrast / 100.0
        factor = max(0.5, min(1.5, factor))
        image = ImageEnhance.Contrast(image).enhance(factor)

    # --- Saturation ---
    if saturation == 0.0:
        image = ImageEnhance.Color(image).enhance(1.1)
    else:
        factor = 1.0 + saturation / 100.0
        factor = max(0.5, min(1.5, factor))
        image = ImageEnhance.Color(image).enhance(factor)

    # --- Sharpness ---
    if sharpness == 0.0:
        image = ImageEnhance.Sharpness(image).enhance(1.3)
    else:
        factor = 1.0 + sharpness / 50.0
        factor = max(0.0, min(2.0, factor))
        image = ImageEnhance.Sharpness(image).enhance(factor)

    return image


def _consolidate_extremes(image: Image.Image) -> Image.Image:
    """Consolidate near-black and near-white pixels before quantization.

    Human vision has very low color sensitivity in dark and very bright regions.
    For example, (68,66,54), (24,56,35), (58,58,58) all look "black" to the eye,
    but median cut sees three distinct colors and maps them to different palette
    entries (dark olive, dark green, dark gray), inflating the color count.

    This function uses luminance-based desaturation for extreme regions:
    - Dark pixels (luma < 50): progressively desaturate toward grayscale.
      At luma=0 the pixel is fully gray; at luma=50 it's unchanged.
      This eliminates color variation in dark areas while preserving structure.
    - Light pixels (luma > 220): progressively desaturate toward grayscale.
      At luma=255 the pixel is fully gray; at luma=220 it's unchanged.

    The result: median cut sees far fewer "distinct" dark/light colors,
    producing a cleaner palette that matches human perception.

    Args:
        image: PIL Image in RGB mode

    Returns:
        Image with extreme-region color variation reduced
    """
    arr = np.array(image, dtype=np.float64)

    # Compute per-pixel luminance: standard BT.601 weights
    luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    # --- Dark region desaturation ---
    # 80 captures colors like #444236 (luma=65) which look "black" to the eye
    dark_limit = 80.0
    dark_mask = luma < dark_limit
    if np.any(dark_mask):
        # Blend factor: 0 at luma=0 (fully gray), 1 at luma=dark_limit (unchanged)
        factor = luma[dark_mask] / dark_limit  # range [0, 1)
        factor = factor[:, np.newaxis]  # broadcast to (N, 1) for RGB channels
        gray = luma[dark_mask][:, np.newaxis]  # grayscale value
        # Blend: pixel = gray + factor * (pixel - gray)
        arr[dark_mask] = gray + factor * (arr[dark_mask] - gray)

    # --- Light region desaturation ---
    light_limit = 210.0
    light_mask = luma > light_limit
    if np.any(light_mask):
        # Blend factor: 1 at luma=light_limit (unchanged), 0 at luma=255 (fully gray)
        factor = (255.0 - luma[light_mask]) / (255.0 - light_limit)
        factor = factor[:, np.newaxis]
        gray = luma[light_mask][:, np.newaxis]
        arr[light_mask] = gray + factor * (arr[light_mask] - gray)

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, 'RGB')


def _cleanup_rare_colors(
    code_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    total_pixels: int,
    min_ratio: float = 0.003,
) -> List[List[Optional[str]]]:
    """Remove rare colors that appear in fewer than min_ratio of total pixels.

    Colors that occupy < 0.3% of the grid are almost certainly noise from
    quantization. Remap each rare color to the closest non-rare color
    using Lab distance.

    Args:
        code_matrix: 2D list of color codes (may contain None)
        palette: ArtkalPalette instance
        total_pixels: Total number of pixels in the grid
        min_ratio: Minimum ratio of pixels for a color to be kept (default 0.003)

    Returns:
        Updated code_matrix with rare colors remapped
    """
    h = len(code_matrix)
    w = len(code_matrix[0]) if h > 0 else 0

    freq = Counter()
    for row in code_matrix:
        for code in row:
            if code is not None:
                freq[code] += 1

    min_count = max(2, int(total_pixels * min_ratio))
    kept_codes = set(code for code, cnt in freq.items() if cnt >= min_count)
    rare_codes = set(freq.keys()) - kept_codes

    if not rare_codes:
        return code_matrix

    # Build Lab values for kept codes
    kept_labs = {}
    for code in kept_codes:
        info = palette.get_by_code(code)
        if info:
            r, g, b = info['rgb']
            kept_labs[code] = rgb_to_lab(r, g, b)

    if not kept_labs:
        return code_matrix

    # Map each rare code to nearest kept code
    remap = {}
    for code in rare_codes:
        info = palette.get_by_code(code)
        if not info:
            continue
        r, g, b = info['rgb']
        lab_val = rgb_to_lab(r, g, b)
        best_code = None
        best_dist = float('inf')
        for kc, kl in kept_labs.items():
            d = lab_distance(lab_val, kl)
            if d < best_dist:
                best_dist = d
                best_code = kc
        if best_code:
            remap[code] = best_code

    # Apply remap
    if remap:
        for y in range(h):
            for x in range(w):
                code = code_matrix[y][x]
                if code in remap:
                    code_matrix[y][x] = remap[code]

    return code_matrix


def _merge_similar_colors(
    code_matrix: List[List[str]],
    palette: ArtkalPalette,
    threshold: int,
) -> List[List[str]]:
    """Merge similar low-frequency colors into high-frequency neighbors.

    Algorithm (from perler-beads-master):
    1. Count frequency of each color code
    2. Sort by frequency descending
    3. For each high-frequency color, check all lower-frequency colors
    4. If Lab distance < threshold, replace low-freq with high-freq everywhere

    Args:
        code_matrix: 2D list of color codes
        palette: ArtkalPalette instance
        threshold: Lab distance threshold for merging

    Returns:
        Updated code_matrix with merged colors
    """
    if threshold <= 0:
        return code_matrix

    h = len(code_matrix)
    w = len(code_matrix[0]) if h > 0 else 0

    # Count frequencies
    freq = Counter()
    for row in code_matrix:
        for code in row:
            freq[code] += 1

    # Sort by frequency descending
    sorted_codes = [code for code, _ in freq.most_common()]

    # Build Lab cache for each code
    lab_cache = {}
    for code in sorted_codes:
        info = palette.get_by_code(code)
        if info:
            r, g, b = info['rgb']
            lab_cache[code] = rgb_to_lab(r, g, b)

    # Track which codes have been replaced
    replaced = set()
    # Map: old_code -> new_code
    merge_map = {}

    for i in range(len(sorted_codes)):
        current = sorted_codes[i]
        if current in replaced:
            continue
        if current not in lab_cache:
            continue

        for j in range(i + 1, len(sorted_codes)):
            lower = sorted_codes[j]
            if lower in replaced:
                continue
            if lower not in lab_cache:
                continue

            dist = lab_distance(lab_cache[current], lab_cache[lower])
            if dist < threshold:
                replaced.add(lower)
                merge_map[lower] = current

    # Apply merges
    if merge_map:
        for y in range(h):
            for x in range(w):
                code = code_matrix[y][x]
                if code in merge_map:
                    code_matrix[y][x] = merge_map[code]

    return code_matrix


def _cap_max_colors(
    code_matrix: List[List[str]],
    palette: ArtkalPalette,
    max_colors: int,
) -> List[List[str]]:
    """Keep only the top N most frequent colors, remap the rest.

    For each removed color, find the closest allowed (top-N) color
    using Lab distance and replace all its cells.

    Args:
        code_matrix: 2D list of color codes
        palette: ArtkalPalette instance
        max_colors: Maximum number of colors to keep

    Returns:
        Updated code_matrix with at most max_colors unique colors
    """
    h = len(code_matrix)
    w = len(code_matrix[0]) if h > 0 else 0

    # Count frequencies
    freq = Counter()
    for row in code_matrix:
        for code in row:
            if code is not None:
                freq[code] += 1

    if len(freq) <= max_colors:
        return code_matrix

    # Keep top N
    top_codes = set(code for code, _ in freq.most_common(max_colors))
    removed_codes = set(freq.keys()) - top_codes

    if not removed_codes:
        return code_matrix

    # Build Lab values for top codes
    top_labs = {}
    for code in top_codes:
        info = palette.get_by_code(code)
        if info:
            r, g, b = info['rgb']
            top_labs[code] = rgb_to_lab(r, g, b)

    # Map each removed code to nearest top code
    remap = {}
    for code in removed_codes:
        info = palette.get_by_code(code)
        if not info:
            continue
        r, g, b = info['rgb']
        lab_val = rgb_to_lab(r, g, b)
        best_code = None
        best_dist = float('inf')
        for tc, tl in top_labs.items():
            d = lab_distance(lab_val, tl)
            if d < best_dist:
                best_dist = d
                best_code = tc
        if best_code:
            remap[code] = best_code

    # Apply remap
    for y in range(h):
        for x in range(w):
            code = code_matrix[y][x]
            if code in remap:
                code_matrix[y][x] = remap[code]

    return code_matrix


def _smooth_edges(
    code_matrix: List[List[Optional[str]]],
    palette: Optional[ArtkalPalette] = None,
) -> List[List[Optional[str]]]:
    """Smooth edges by replacing isolated single-pixel color islands.

    A cell is "isolated" if none of its 4-neighbors share its color.
    However, if the isolated cell is very different from its neighbors
    (Lab distance > 30), it may be an intentional detail (e.g. eye highlight,
    small feature) and is preserved.

    This prevents the smoothing from destroying fine details while still
    removing salt-and-pepper noise.

    Args:
        code_matrix: 2D list of color codes (may contain None)
        palette: ArtkalPalette instance (optional, for Lab-based detail preservation)

    Returns:
        Smoothed code_matrix
    """
    h = len(code_matrix)
    w = len(code_matrix[0]) if h > 0 else 0
    if h < 3 or w < 3:
        return code_matrix

    # Build Lab cache for detail-preservation check
    lab_cache = {}
    if palette is not None:
        for row in code_matrix:
            for code in row:
                if code is not None and code not in lab_cache:
                    info = palette.get_by_code(code)
                    if info:
                        r, g, b = info['rgb']
                        lab_cache[code] = rgb_to_lab(r, g, b)

    # Work on a copy to avoid cascading changes
    result = [row[:] for row in code_matrix]

    for y in range(h):
        for x in range(w):
            current = code_matrix[y][x]
            if current is None:
                continue

            # Gather 4-neighbors
            neighbors = []
            if y > 0:
                neighbors.append(code_matrix[y - 1][x])
            if y < h - 1:
                neighbors.append(code_matrix[y + 1][x])
            if x > 0:
                neighbors.append(code_matrix[y][x - 1])
            if x < w - 1:
                neighbors.append(code_matrix[y][x + 1])

            # Filter non-None neighbors
            valid_neighbors = [n for n in neighbors if n is not None]
            if not valid_neighbors:
                continue

            # Check if current is isolated (no neighbor shares its color)
            if current not in valid_neighbors:
                # Detail preservation: if this pixel is very different from
                # neighbors, it might be intentional (highlight, small feature).
                # Only smooth if the color is similar to the replacement.
                replacement = Counter(valid_neighbors).most_common(1)[0][0]

                if palette is not None and current in lab_cache and replacement in lab_cache:
                    dist = lab_distance(lab_cache[current], lab_cache[replacement])
                    if dist > 30.0:
                        # Very different color - likely intentional detail, preserve it
                        continue

                result[y][x] = replacement

    return result


def _remove_background_flood_fill(
    code_matrix: List[List[Optional[str]]],
) -> List[List[Optional[str]]]:
    """Remove background via border flood fill (reference: perler-beads-master).

    Algorithm:
    1. Count color frequency on all 4 border edges
    2. The most frequent border color is the background
    3. Flood fill from all border cells of that color, setting them to None

    Args:
        code_matrix: 2D list of color codes

    Returns:
        Updated code_matrix with background cells set to None
    """
    h = len(code_matrix)
    w = len(code_matrix[0]) if h > 0 else 0
    if h == 0 or w == 0:
        return code_matrix

    # Count border cell colors
    border_freq = Counter()
    for x in range(w):
        c = code_matrix[0][x]
        if c is not None:
            border_freq[c] += 1
        if h > 1:
            c = code_matrix[h - 1][x]
            if c is not None:
                border_freq[c] += 1
    for y in range(1, h - 1):
        c = code_matrix[y][0]
        if c is not None:
            border_freq[c] += 1
        if w > 1:
            c = code_matrix[y][w - 1]
            if c is not None:
                border_freq[c] += 1

    if not border_freq:
        return code_matrix

    # Most frequent border color is the background
    bg_code = border_freq.most_common(1)[0][0]

    # Flood fill from border cells of that color
    visited = [[False] * w for _ in range(h)]
    stack = []

    def push_if_bg(r, c):
        if 0 <= r < h and 0 <= c < w and not visited[r][c]:
            if code_matrix[r][c] == bg_code:
                visited[r][c] = True
                stack.append((r, c))

    # Seed from all border cells matching bg_code
    for x in range(w):
        push_if_bg(0, x)
        push_if_bg(h - 1, x)
    for y in range(1, h - 1):
        push_if_bg(y, 0)
        push_if_bg(y, w - 1)

    # BFS flood fill
    while stack:
        r, c = stack.pop()
        code_matrix[r][c] = None
        push_if_bg(r - 1, c)
        push_if_bg(r + 1, c)
        push_if_bg(r, c - 1)
        push_if_bg(r, c + 1)

    return code_matrix
