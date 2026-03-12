import uuid
import io
import time
from typing import Optional, Dict, Any
from collections import Counter

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from core.color_match import ArtkalPalette
from core.quantizer import process_image
from core.exporter import export_png, export_pdf, generate_preview_base64


app = FastAPI(title="BeadCraft", description="Perler Bead Pattern Generator", version="1.0.0")

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/examples", StaticFiles(directory="docs/examples"), name="examples")
templates = Jinja2Templates(directory="templates")

# Global palette instance
palette = ArtkalPalette()

# In-memory session storage
sessions: Dict[str, Dict[str, Any]] = {}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/palette")
async def get_palette():
    """Return the full Artkal palette data and presets."""
    return {
        'colors': palette.colors,
        'presets': palette.presets,
    }


@app.post("/api/generate")
async def generate_pattern(
    file: UploadFile = File(...),
    mode: str = Form("fixed_grid"),
    grid_width: int = Form(48),
    grid_height: int = Form(48),
    pixel_size: int = Form(8),
    use_dithering: str = Form("false"),
    palette_preset: str = Form("221"),
    max_colors: int = Form(0),
    similarity_threshold: int = Form(0),
    remove_bg: str = Form("false"),
    contrast: float = Form(0.0),
    saturation: float = Form(0.0),
    sharpness: float = Form(0.0),
):
    """Generate a bead pattern from an uploaded image.

    Args:
        file: Image file (JPG, PNG, GIF, WEBP)
        mode: "fixed_grid" or "pixel_size"
        grid_width: Grid width (for fixed_grid mode)
        grid_height: Grid height (for fixed_grid mode)
        pixel_size: Pixel block size (for pixel_size mode)
        use_dithering: Enable Floyd-Steinberg dithering
        palette_preset: Palette preset ("96", "120", "144", "168", "221")
        max_colors: Maximum number of colors (0 = unlimited)
        similarity_threshold: Color merge threshold in Lab distance (0 = disabled)
        remove_bg: Whether to auto-remove background via border flood fill
        contrast: Contrast adjustment (-50 to +50, 0 = auto)
        saturation: Saturation adjustment (-50 to +50, 0 = auto)
        sharpness: Sharpness adjustment (-50 to +50, 0 = auto)
    """
    # Parse booleans from string (FormData sends "true"/"false" as strings)
    dithering_enabled = use_dithering.lower() in ('true', '1', 'yes')
    remove_bg_enabled = remove_bg.lower() in ('true', '1', 'yes')

    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Please upload an image file")

    # Read and validate file size (20MB limit)
    contents = await file.read()
    if len(contents) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 20MB limit")

    try:
        image = Image.open(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to open image: {str(e)}")

    # Process the image
    try:
        result = process_image(
            image=image,
            palette=palette,
            mode=mode,
            grid_width=grid_width,
            grid_height=grid_height,
            pixel_size=pixel_size,
            use_dithering=dithering_enabled,
            palette_preset=palette_preset,
            max_colors=max_colors,
            similarity_threshold=similarity_threshold,
            remove_bg=remove_bg_enabled,
            contrast=contrast,
            saturation=saturation,
            sharpness=sharpness,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    # Generate preview image
    preview_image = generate_preview_base64(result['pixel_matrix'], palette)

    # Create session
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        'pixel_matrix': result['pixel_matrix'],
        'color_summary': result['color_summary'],
        'grid_size': result['grid_size'],
        'total_beads': result['total_beads'],
        'created_at': time.time(),
    }

    # Clean up old sessions (keep last 50)
    if len(sessions) > 50:
        sorted_keys = sorted(sessions.keys(), key=lambda k: sessions[k].get('created_at', 0))
        for key in sorted_keys[:-50]:
            del sessions[key]

    return {
        'session_id': session_id,
        'grid_size': result['grid_size'],
        'pixel_matrix': result['pixel_matrix'],
        'color_summary': result['color_summary'],
        'total_beads': result['total_beads'],
        'palette_preset': palette_preset,
        'preview_image': preview_image,
    }


@app.post("/api/export/png")
async def export_pattern_png(data: dict):
    """Export the pattern as a PNG image.

    Expected JSON body:
        pixel_matrix: List[List[str|None]]
        color_data: Dict[str, str]  (code -> hex)
        color_summary: List[Dict]
        cell_size: int (default 20)
        show_grid: bool (default true)
        show_codes_in_cells: bool (default true)
        show_coordinates: bool (default true)
        palette_preset: str (default "221")
    """
    pixel_matrix = data.get('pixel_matrix')
    color_data = data.get('color_data', {})
    color_summary = data.get('color_summary', [])
    cell_size = data.get('cell_size', 20)
    show_grid = data.get('show_grid', True)
    show_codes_in_cells = data.get('show_codes_in_cells', True)
    show_coordinates = data.get('show_coordinates', True)
    palette_preset = data.get('palette_preset', '221')

    if not pixel_matrix:
        raise HTTPException(status_code=400, detail="pixel_matrix is required")

    try:
        png_bytes = export_png(
            pixel_matrix, color_data, color_summary,
            cell_size, show_grid, show_codes_in_cells,
            show_coordinates, palette_preset
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PNG export failed: {str(e)}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"beadcraft_pattern_{timestamp}.png"

    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/export/pdf")
async def export_pattern_pdf(data: dict):
    """Export the pattern as a PDF document.

    Expected JSON body:
        pixel_matrix: List[List[str|None]]
        color_summary: List[Dict]
        show_codes_in_cells: bool (default true)
        show_coordinates: bool (default true)
        palette_preset: str (default "221")
    """
    pixel_matrix = data.get('pixel_matrix')
    color_summary = data.get('color_summary', [])
    show_codes_in_cells = data.get('show_codes_in_cells', True)
    show_coordinates = data.get('show_coordinates', True)
    palette_preset = data.get('palette_preset', '221')

    if not pixel_matrix:
        raise HTTPException(status_code=400, detail="pixel_matrix is required")

    try:
        pdf_bytes = export_pdf(
            pixel_matrix, color_summary, palette,
            show_codes_in_cells, show_coordinates, palette_preset
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {str(e)}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"beadcraft_pattern_{timestamp}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.post("/api/update_cell")
async def update_cell(data: dict):
    """Update a single cell in the pattern.

    Expected JSON body:
        session_id: str
        row: int
        col: int
        new_code: str
    """
    session_id = data.get('session_id')
    row = data.get('row')
    col = data.get('col')
    new_code = data.get('new_code')

    if not session_id or session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    pixel_matrix = session['pixel_matrix']

    if row is None or col is None or row < 0 or col < 0:
        raise HTTPException(status_code=400, detail="Invalid row/col")

    if row >= len(pixel_matrix) or col >= len(pixel_matrix[0]):
        raise HTTPException(status_code=400, detail="Row/col out of range")

    # Verify new_code exists in palette
    if not palette.get_by_code(new_code):
        raise HTTPException(status_code=400, detail=f"Invalid color code: {new_code}")

    # Update
    old_code = pixel_matrix[row][col]
    pixel_matrix[row][col] = new_code

    # Recompute color summary (skip None/transparent cells)
    counter = Counter()
    for r in pixel_matrix:
        for c in r:
            if c is not None:
                counter[c] += 1

    color_summary = []
    for code, count in counter.most_common():
        color_info = palette.get_by_code(code)
        if color_info:
            color_summary.append({
                'code': color_info['code'],
                'name': color_info['name'],
                'name_zh': color_info['name_zh'],
                'hex': color_info['hex'],
                'count': count,
            })

    session['color_summary'] = color_summary
    session['total_beads'] = sum(c['count'] for c in color_summary)

    return {
        'success': True,
        'old_code': old_code,
        'new_code': new_code,
        'color_summary': color_summary,
        'total_beads': session['total_beads'],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
