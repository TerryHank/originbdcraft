import io
import time
import base64
from typing import List, Dict, Optional

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas as pdf_canvas

from .color_match import ArtkalPalette


def _get_text_color(hex_color: str):
    """Return black or white text color based on background brightness."""
    r, g, b = _hex_to_rgb(hex_color)
    brightness = (r * 299 + g * 587 + b * 114) / 1000
    return (0, 0, 0) if brightness > 128 else (255, 255, 255)


def _try_load_font(size):
    """Try to load a monospace font, fall back to default."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf", size)
        except (OSError, IOError):
            return ImageFont.load_default()


def export_png(
    pixel_matrix: List[List[Optional[str]]],
    color_data: Dict[str, str],
    color_summary: List[Dict],
    cell_size: int = 20,
    show_grid: bool = True,
    show_codes_in_cells: bool = True,
    show_coordinates: bool = True,
    palette_preset: str = "221",
) -> bytes:
    """Export the bead pattern as a PNG with coordinates, cell codes, and color summary.

    Args:
        pixel_matrix: 2D list of color codes
        color_data: Dict mapping color code -> hex color string
        color_summary: List of color summary dicts
        cell_size: Size of each cell in pixels (default 20)
        show_grid: Whether to draw grid lines
        show_codes_in_cells: Whether to draw color codes in cells
        show_coordinates: Whether to draw coordinate axes
        palette_preset: Preset name for display

    Returns:
        PNG image as bytes
    """
    if not pixel_matrix or not pixel_matrix[0]:
        return b''

    grid_h = len(pixel_matrix)
    grid_w = len(pixel_matrix[0])

    coord_size = 20 if show_coordinates else 0
    pattern_w = grid_w * cell_size
    pattern_h = grid_h * cell_size

    # Color summary area height
    summary_line_h = 36
    n_colors = len(color_summary)
    colors_per_row = max(1, pattern_w // 90)
    summary_rows = max(1, (n_colors + colors_per_row - 1) // colors_per_row)
    summary_h = summary_rows * summary_line_h + 28  # extra for total line

    img_w = coord_size + pattern_w + coord_size
    img_h = coord_size + pattern_h + coord_size + 1 + summary_h  # 1px separator

    img = Image.new('RGBA', (img_w, img_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    coord_font = _try_load_font(max(8, cell_size // 3))
    code_font = _try_load_font(max(6, cell_size * 2 // 5)) if show_codes_in_cells else None
    summary_font = _try_load_font(11)
    summary_small = _try_load_font(9)

    ox = coord_size  # pattern area origin x
    oy = coord_size  # pattern area origin y

    # --- Draw coordinate axes ---
    if show_coordinates:
        coord_color = (136, 136, 136)
        # Top column numbers (1 -> N)
        for x in range(grid_w):
            label = str(x + 1)
            cx = ox + x * cell_size + cell_size // 2
            draw.text((cx, oy - 14), label, fill=coord_color, font=coord_font, anchor="mm")
        # Bottom column numbers (N -> 1, reversed)
        for x in range(grid_w):
            label = str(grid_w - x)
            cx = ox + x * cell_size + cell_size // 2
            draw.text((cx, oy + pattern_h + 10), label, fill=coord_color, font=coord_font, anchor="mm")
        # Left row numbers
        for y in range(grid_h):
            label = str(y + 1)
            cy = oy + y * cell_size + cell_size // 2
            draw.text((ox - 10, cy), label, fill=coord_color, font=coord_font, anchor="mm")
        # Right row numbers
        for y in range(grid_h):
            label = str(y + 1)
            cy = oy + y * cell_size + cell_size // 2
            draw.text((ox + pattern_w + 10, cy), label, fill=coord_color, font=coord_font, anchor="mm")

    # --- Draw cells ---
    for y in range(grid_h):
        for x in range(grid_w):
            code = pixel_matrix[y][x]
            x0 = ox + x * cell_size
            y0 = oy + y * cell_size
            x1 = x0 + cell_size
            y1 = y0 + cell_size

            if code is None:
                # Transparent: draw checkerboard
                bk = max(2, cell_size // 5)
                for cy_c in range(y0, y1, bk):
                    for cx_c in range(x0, x1, bk):
                        ix = (cx_c - x0) // bk
                        iy = (cy_c - y0) // bk
                        clr = (220, 220, 220, 255) if (ix + iy) % 2 == 0 else (180, 180, 180, 255)
                        draw.rectangle([cx_c, cy_c, min(cx_c + bk, x1), min(cy_c + bk, y1)], fill=clr)
            else:
                hex_color = color_data.get(code, '#FFFFFF')
                r, g, b = _hex_to_rgb(hex_color)
                draw.rectangle([x0, y0, x1, y1], fill=(r, g, b, 255))

                # Draw code text if cell is large enough
                if show_codes_in_cells and cell_size >= 16 and code_font:
                    tc = _get_text_color(hex_color)
                    cx = x0 + cell_size // 2
                    cy = y0 + cell_size // 2
                    draw.text((cx, cy), code, fill=tc, font=code_font, anchor="mm")

    # --- Draw grid lines ---
    if show_grid:
        grid_color = (180, 180, 180)
        for x in range(grid_w + 1):
            lx = ox + x * cell_size
            draw.line([(lx, oy), (lx, oy + pattern_h)], fill=grid_color, width=1)
        for y in range(grid_h + 1):
            ly = oy + y * cell_size
            draw.line([(ox, ly), (ox + pattern_w, ly)], fill=grid_color, width=1)

    # --- Draw color summary area ---
    summary_top = oy + pattern_h + coord_size + 1
    # Separator line
    draw.line([(ox, summary_top - 1), (ox + pattern_w, summary_top - 1)], fill=(200, 200, 200), width=1)
    # Background
    draw.rectangle([0, summary_top, img_w, img_h], fill=(247, 247, 247, 255))

    sx = ox + 4
    sy = summary_top + 4
    swatch_size = 20
    col_idx = 0

    for item in color_summary:
        hex_c = item.get('hex', '#FFFFFF')
        r, g, b = _hex_to_rgb(hex_c)
        code = item.get('code', '')
        count = item.get('count', 0)

        # Swatch
        draw.rounded_rectangle(
            [sx, sy, sx + swatch_size, sy + swatch_size],
            radius=4, fill=(r, g, b, 255), outline=(180, 180, 180)
        )
        # Code + count
        draw.text((sx + swatch_size + 4, sy + 2), code, fill=(30, 30, 30), font=summary_font)
        draw.text((sx + swatch_size + 4, sy + 14), f"{count}", fill=(120, 120, 120), font=summary_small)

        col_idx += 1
        sx += 90
        if col_idx >= colors_per_row:
            col_idx = 0
            sx = ox + 4
            sy += summary_line_h

    # Total line
    total_beads = sum(item.get('count', 0) for item in color_summary)
    total_y = img_h - 18
    draw.text(
        (ox + 4, total_y),
        f"Artkal M [{palette_preset}]  Total: {total_beads} beads, {n_colors} colors",
        fill=(100, 100, 100), font=summary_small
    )

    # Convert RGBA to RGB for PNG output
    bg = Image.new('RGB', img.size, (255, 255, 255))
    bg.paste(img, mask=img.split()[3])

    buf = io.BytesIO()
    bg.save(buf, format='PNG')
    return buf.getvalue()


def export_pdf(
    pixel_matrix: List[List[Optional[str]]],
    color_summary: List[Dict],
    palette: ArtkalPalette,
    show_codes_in_cells: bool = True,
    show_coordinates: bool = True,
    palette_preset: str = "221",
) -> bytes:
    """Export the bead pattern as a PDF document with pattern, coordinates, and color chart.

    Args:
        pixel_matrix: 2D list of color codes
        color_summary: List of color summary dicts
        palette: ArtkalPalette instance for color lookups
        show_codes_in_cells: Whether to print color codes inside cells
        show_coordinates: Whether to draw coordinate axes
        palette_preset: Preset name for display

    Returns:
        PDF document as bytes
    """
    if not pixel_matrix or not pixel_matrix[0]:
        return b''

    grid_h = len(pixel_matrix)
    grid_w = len(pixel_matrix[0])

    buf = io.BytesIO()

    if grid_w >= grid_h:
        page_size = landscape(A4)
    else:
        page_size = A4

    page_w, page_h = page_size
    margin = 15 * mm
    coord_margin = 8 * mm if show_coordinates else 0

    c = pdf_canvas.Canvas(buf, pagesize=page_size)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # --- Page 1: Pattern ---
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(page_w / 2, page_h - margin, "BeadCraft Pattern")
    c.setFont("Helvetica", 8)
    c.drawCentredString(page_w / 2, page_h - margin - 12, f"Generated: {timestamp}  |  Preset: {palette_preset}")

    available_w = page_w - 2 * margin - 2 * coord_margin
    available_h = page_h - 2 * margin - 30 - 2 * coord_margin

    cell_size = min(available_w / grid_w, available_h / grid_h)
    cell_size = min(cell_size, 6 * mm)

    pattern_w = grid_w * cell_size
    pattern_h = grid_h * cell_size

    offset_x = (page_w - pattern_w) / 2
    offset_y = page_h - margin - 30 - coord_margin - pattern_h

    # Draw coordinate axes
    if show_coordinates:
        c.setFont("Helvetica", max(4, cell_size * 0.4))
        c.setFillColor(HexColor('#888888'))
        for x in range(grid_w):
            # Top
            c.drawCentredString(
                offset_x + x * cell_size + cell_size / 2,
                offset_y + pattern_h + 3,
                str(x + 1)
            )
            # Bottom (reversed)
            c.drawCentredString(
                offset_x + x * cell_size + cell_size / 2,
                offset_y - coord_margin + 2,
                str(grid_w - x)
            )
        for y in range(grid_h):
            # Left
            c.drawRightString(
                offset_x - 2,
                offset_y + pattern_h - (y + 1) * cell_size + cell_size / 2 - 2,
                str(y + 1)
            )
            # Right
            c.drawString(
                offset_x + pattern_w + 2,
                offset_y + pattern_h - (y + 1) * cell_size + cell_size / 2 - 2,
                str(y + 1)
            )

    # Draw cells
    for y in range(grid_h):
        for x in range(grid_w):
            code = pixel_matrix[y][x]
            cx = offset_x + x * cell_size
            cy = offset_y + (grid_h - 1 - y) * cell_size

            if code is None:
                c.setFillColor(HexColor('#E0E0E0'))
                c.rect(cx, cy, cell_size, cell_size, fill=1, stroke=0)
            else:
                color_info = palette.get_by_code(code)
                hex_color = color_info['hex'] if color_info else '#FFFFFF'
                c.setFillColor(HexColor(hex_color))
                c.rect(cx, cy, cell_size, cell_size, fill=1, stroke=0)

                if show_codes_in_cells and cell_size >= 3.5 * mm:
                    r_val, g_val, b_val = _hex_to_rgb(hex_color)
                    brightness = (r_val * 299 + g_val * 587 + b_val * 114) / 1000
                    text_color = black if brightness > 128 else white
                    c.setFillColor(text_color)
                    font_size = max(3, cell_size * 0.35)
                    c.setFont("Helvetica-Bold", font_size)
                    c.drawCentredString(
                        cx + cell_size / 2,
                        cy + cell_size / 2 - font_size / 3,
                        code
                    )

            # Grid border
            c.setStrokeColor(HexColor('#B4B4B4'))
            c.setLineWidth(0.3)
            c.rect(cx, cy, cell_size, cell_size, fill=0, stroke=1)

    c.showPage()

    # --- Page 2: Color Shopping List ---
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(page_w / 2, page_h - margin, "Color Shopping List")
    c.setFont("Helvetica", 8)
    c.drawCentredString(page_w / 2, page_h - margin - 12, f"Generated: {timestamp}")

    table_y = page_h - margin - 36
    col_widths = [15 * mm, 20 * mm, 40 * mm, 25 * mm]
    headers = ["Color", "Code", "Name", "Count"]

    c.setFont("Helvetica-Bold", 10)
    x_pos = margin
    for i, header in enumerate(headers):
        c.setFillColor(black)
        c.drawString(x_pos + 2, table_y, header)
        x_pos += col_widths[i]

    table_y -= 4
    c.setStrokeColor(HexColor('#CCCCCC'))
    c.setLineWidth(0.5)
    c.line(margin, table_y, margin + sum(col_widths), table_y)

    c.setFont("Helvetica", 9)
    row_height = 14
    total_count = 0

    for item in color_summary:
        table_y -= row_height

        if table_y < margin + 30:
            c.showPage()
            table_y = page_h - margin - 20
            c.setFont("Helvetica", 9)

        x_pos = margin
        hex_color = item.get('hex', '#FFFFFF')
        c.setFillColor(HexColor(hex_color))
        c.rect(x_pos + 2, table_y - 1, 10, 10, fill=1, stroke=1)
        x_pos += col_widths[0]

        c.setFillColor(black)
        c.drawString(x_pos + 2, table_y, item.get('code', ''))
        x_pos += col_widths[1]

        c.drawString(x_pos + 2, table_y, item.get('name', ''))
        x_pos += col_widths[2]

        count = item.get('count', 0)
        total_count += count
        c.drawString(x_pos + 2, table_y, str(count))

    table_y -= row_height + 4
    c.setStrokeColor(HexColor('#CCCCCC'))
    c.line(margin, table_y + row_height - 2, margin + sum(col_widths), table_y + row_height - 2)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(black)
    c.drawString(margin + 2, table_y, f"Total: {len(color_summary)} colors, {total_count} beads")

    c.showPage()
    c.save()

    return buf.getvalue()


def generate_preview_base64(
    pixel_matrix: List[List[Optional[str]]],
    palette: ArtkalPalette,
    max_size: int = 400,
) -> str:
    """Generate a base64-encoded preview image for quick display.

    Args:
        pixel_matrix: 2D list of color codes
        palette: ArtkalPalette instance
        max_size: Maximum dimension of the preview image

    Returns:
        Base64-encoded PNG string with data URI prefix
    """
    if not pixel_matrix or not pixel_matrix[0]:
        return ''

    grid_h = len(pixel_matrix)
    grid_w = len(pixel_matrix[0])

    cell_size = max(1, min(max_size // max(grid_w, grid_h), 10))

    img_w = grid_w * cell_size
    img_h = grid_h * cell_size

    img = Image.new('RGB', (img_w, img_h), (255, 255, 255))
    pixels = img.load()

    for y in range(grid_h):
        for x in range(grid_w):
            code = pixel_matrix[y][x]
            if code is not None:
                color_info = palette.get_by_code(code)
                if color_info:
                    r, g, b = color_info['rgb']
                else:
                    r, g, b = 255, 255, 255
            else:
                r, g, b = 220, 220, 220

            for dy in range(cell_size):
                for dx in range(cell_size):
                    px = x * cell_size + dx
                    py = y * cell_size + dy
                    if px < img_w and py < img_h:
                        pixels[px, py] = (r, g, b)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return f'data:image/png;base64,{b64}'


def _hex_to_rgb(hex_str: str):
    """Convert hex color string to RGB tuple."""
    hex_str = hex_str.lstrip('#')
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
