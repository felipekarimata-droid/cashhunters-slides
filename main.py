from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
import os
import uuid
import zipfile

app = FastAPI(title="CashHunters - Gerador de Slides")

# ── Configurações ──────────────────────────────────────────────
WIDTH, HEIGHT   = 1080, 1350
OUTPUT_DIR      = "/tmp/slides"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BG_COLOR        = (52, 168, 120)
DOT_COLOR       = (45, 148, 105)
WHITE           = (255, 255, 255)
BLUE_HIGHLIGHT  = (30,  80, 180)

# ── Models ─────────────────────────────────────────────────────
class Slide(BaseModel):
    frase: str
    subtexto: Optional[str] = ""

class CarrosselRequest(BaseModel):
    slides: List[Slide]
    categoria: Optional[str] = "Cashback e Liberdade Financeira"

# ── Helpers ────────────────────────────────────────────────────
def get_font(size, bold=False):
    font_paths_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    font_paths_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    paths = font_paths_bold if bold else font_paths_regular
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def draw_dot_background(draw, width, height, spacing=54, radius=5):
    for y in range(0, height + spacing, spacing):
        for x in range(0, width + spacing, spacing):
            draw.ellipse(
                [x - radius, y - radius, x + radius, y + radius],
                fill=DOT_COLOR
            )

def draw_logo(draw, x, y):
    font_logo = get_font(42, bold=True)
    font_tag  = get_font(18)
    draw.text((x+2, y+2), "cash hunters*", font=font_logo, fill=(0, 0, 0, 80))
    draw.text((x,   y),   "cash hunters*", font=font_logo, fill=WHITE)
    draw.text((x, y+48),  "CATCH YOUR FREEDOM", font=font_tag, fill=WHITE)

def draw_rounded_rect(draw, x1, y1, x2, y2, radius, fill):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)

def generate_slide(frase, subtexto, slide_num, total_slides, categoria, output_path):
    img  = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img, "RGBA")

    draw_dot_background(draw, WIDTH, HEIGHT)
    draw_logo(draw, x=50, y=48)

    font_num = get_font(26, bold=True)
    font_cat = get_font(22)
    num_text = f"{slide_num}/{total_slides}"
    draw.text((WIDTH - 50, 48), num_text,  font=font_num, fill=WHITE, anchor="ra")
    draw.text((WIDTH - 50, 82), categoria, font=font_cat, fill=WHITE, anchor="ra")

    draw.rectangle([50, 140, WIDTH - 50, 143], fill=(255, 255, 255, 80))

    BOX_X1      = 50
    BOX_X2      = WIDTH - 50
    BOX_INNER_W = BOX_X2 - BOX_X1 - 60
    font_frase  = get_font(68, bold=True)
    lines       = wrap_text(frase.upper(), font_frase, BOX_INNER_W, draw)
    line_h      = 80
    block_h     = len(lines) * line_h
    box_top     = 220
    box_bot     = box_top + block_h + 60

    draw_rounded_rect(draw, BOX_X1, box_top, BOX_X2, box_bot, radius=18, fill=BLUE_HIGHLIGHT)

    text_y = box_top + 30
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_frase)
        lw   = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) // 2, text_y), line, font=font_frase, fill=WHITE)
        text_y += line_h

    if subtexto:
        font_sub  = get_font(38)
        sub_lines = wrap_text(subtexto, font_sub, BOX_INNER_W + 20, draw)
        sub_y     = box_bot + 50
        for line in sub_lines:
            bbox = draw.textbbox((0, 0), line, font=font_sub)
            lw   = bbox[2] - bbox[0]
            draw.text(((WIDTH - lw) // 2, sub_y), line, font=font_sub, fill=WHITE)
            sub_y += 52

    draw.ellipse([WIDTH-220, HEIGHT-320, WIDTH+80, HEIGHT+80], fill=(255, 255, 255, 18))
    draw.ellipse([-80, HEIGHT-280, 180, HEIGHT+60],            fill=(255, 255, 255, 12))

    font_disc  = get_font(20)
    disc_text  = "*Conteúdo meramente educativo e informativo. Não constitui aconselhamento financeiro."
    disc_lines = wrap_text(disc_text, font_disc, WIDTH - 100, draw)
    disc_y     = HEIGHT - 30 - len(disc_lines) * 26
    for line in disc_lines:
        bbox = draw.textbbox((0, 0), line, font=font_disc)
        lw   = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) // 2, disc_y), line, font=font_disc, fill=(255, 255, 255, 160))
        disc_y += 26

    img.save(output_path, "PNG")
    return output_path

# ── Endpoints ──────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "CashHunters Slide Generator"}


@app.post("/gerar-carrossel")
def gerar_carrossel(body: CarrosselRequest):
    """
    Recebe uma lista de slides com frase + subtexto,
    gera as imagens e devolve um ZIP com todos os slides.
    """
    if not body.slides:
        raise HTTPException(status_code=400, detail="Precisa de pelo menos 1 slide.")
    if len(body.slides) > 10:
        raise HTTPException(status_code=400, detail="Máximo de 10 slides por carrossel.")

    session_id  = str(uuid.uuid4())[:8]
    session_dir = os.path.join(OUTPUT_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    total       = len(body.slides)
    slide_paths = []

    for i, slide in enumerate(body.slides, start=1):
        path = os.path.join(session_dir, f"slide_{i}.png")
        generate_slide(
            frase       = slide.frase,
            subtexto    = slide.subtexto or "",
            slide_num   = i,
            total_slides= total,
            categoria   = body.categoria,
            output_path = path
        )
        slide_paths.append(path)

    # Compacta em ZIP
    zip_path = os.path.join(OUTPUT_DIR, f"carrossel_{session_id}.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path in slide_paths:
            zf.write(path, os.path.basename(path))

    return FileResponse(
        zip_path,
        media_type  = "application/zip",
        filename    = f"cashhunters_carrossel_{session_id}.zip"
    )


@app.post("/gerar-slide")
def gerar_slide_unico(
    frase: str,
    subtexto: Optional[str] = "",
    slide_num: int = 1,
    total_slides: int = 1,
    categoria: str = "Cashback e Liberdade Financeira"
):
    """Gera um único slide e devolve a imagem PNG."""
    session_id = str(uuid.uuid4())[:8]
    path       = os.path.join(OUTPUT_DIR, f"slide_{session_id}.png")

    generate_slide(
        frase        = frase,
        subtexto     = subtexto,
        slide_num    = slide_num,
        total_slides = total_slides,
        categoria    = categoria,
        output_path  = path
    )

    return FileResponse(path, media_type="image/png", filename=f"slide_{session_id}.png")
