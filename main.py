from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
import os
import uuid
import base64
import requests
from io import BytesIO

app = FastAPI(title="CashHunters - Gerador de Slides")

# ── Configurações ──────────────────────────────────────────────
WIDTH, HEIGHT   = 1080, 1350
OUTPUT_DIR      = "/tmp/slides"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BG_COLOR        = (52, 168, 120)
DOT_COLOR       = (45, 148, 105)
WHITE           = (255, 255, 255)
BLUE_HIGHLIGHT  = (30,  80, 180)

IMAGE_AREA_TOP    = 820   # onde começa a área da imagem
IMAGE_AREA_HEIGHT = 400   # altura reservada para a imagem
IMAGE_AREA_MARGIN = 50    # margem lateral

# ── Models ─────────────────────────────────────────────────────
class Slide(BaseModel):
    frase: str
    subtexto: Optional[str] = ""
    image_url: Optional[str] = None   # <-- NOVO campo opcional

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

def fetch_image(url: str) -> Optional[Image.Image]:
    """Faz download da imagem ou descodifica base64 data URI, devolve PIL ou None."""
    try:
        if url.startswith("data:"):
            # data:image/png;base64,XXXX
            header, b64data = url.split(",", 1)
            img_bytes = base64.b64decode(b64data)
            return Image.open(BytesIO(img_bytes)).convert("RGB")
        else:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None

def paste_image_bottom(base_img: Image.Image, img_url: str):
    """
    Cola a imagem descarregada na zona inferior do slide,
    com cantos arredondados e um leve overlay escuro para separar do fundo.
    """
    remote = fetch_image(img_url)
    if remote is None:
        return  # sem imagem, não faz nada

    x1 = IMAGE_AREA_MARGIN
    x2 = WIDTH - IMAGE_AREA_MARGIN
    y1 = IMAGE_AREA_TOP
    y2 = IMAGE_AREA_TOP + IMAGE_AREA_HEIGHT
    box_w = x2 - x1
    box_h = y2 - y1

    # Redimensiona mantendo proporção e corta ao centro (cover)
    img_ratio  = remote.width / remote.height
    box_ratio  = box_w / box_h

    if img_ratio > box_ratio:
        # imagem mais larga — ajusta altura
        new_h = box_h
        new_w = int(new_h * img_ratio)
    else:
        # imagem mais alta — ajusta largura
        new_w = box_w
        new_h = int(new_w / img_ratio)

    remote = remote.resize((new_w, new_h), Image.LANCZOS)

    # Crop centrado
    left = (new_w - box_w) // 2
    top  = (new_h - box_h) // 2
    remote = remote.crop((left, top, left + box_w, top + box_h))

    # Máscara com cantos arredondados
    radius = 24
    mask = Image.new("L", (box_w, box_h), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, box_w, box_h], radius=radius, fill=255)

    # Leve overlay escuro sobre a imagem (20% opacidade) para separar visualmente
    overlay = Image.new("RGB", (box_w, box_h), (0, 0, 0))
    remote  = Image.blend(remote, overlay, alpha=0.15)

    base_img.paste(remote, (x1, y1), mask)


def generate_slide(frase, subtexto, slide_num, total_slides, categoria, output_path, image_url=None):
    has_image = bool(image_url)

    # Se tiver imagem, reduz o espaço do texto para caber tudo
    effective_height = IMAGE_AREA_TOP - 20 if has_image else HEIGHT

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

    # Tamanho da fonte ajustado se tiver imagem (mais pequeno para caber)
    frase_font_size = 62 if has_image else 68
    font_frase  = get_font(frase_font_size, bold=True)
    lines       = wrap_text(frase.upper(), font_frase, BOX_INNER_W, draw)
    line_h      = 76 if has_image else 80
    block_h     = len(lines) * line_h
    box_top     = 200
    box_bot     = box_top + block_h + 60

    draw_rounded_rect(draw, BOX_X1, box_top, BOX_X2, box_bot, radius=18, fill=BLUE_HIGHLIGHT)

    text_y = box_top + 30
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_frase)
        lw   = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) // 2, text_y), line, font=font_frase, fill=WHITE)
        text_y += line_h

    if subtexto:
        sub_font_size = 34 if has_image else 38
        font_sub  = get_font(sub_font_size)
        sub_lines = wrap_text(subtexto, font_sub, BOX_INNER_W + 20, draw)
        sub_y     = box_bot + 40
        line_gap  = 46 if has_image else 52
        for line in sub_lines:
            bbox = draw.textbbox((0, 0), line, font=font_sub)
            lw   = bbox[2] - bbox[0]
            draw.text(((WIDTH - lw) // 2, sub_y), line, font=font_sub, fill=WHITE)
            sub_y += line_gap

    # Decoração de fundo (só se não tiver imagem para não sobrepor)
    if not has_image:
        draw.ellipse([WIDTH-220, HEIGHT-320, WIDTH+80, HEIGHT+80], fill=(255, 255, 255, 18))
        draw.ellipse([-80, HEIGHT-280, 180, HEIGHT+60],            fill=(255, 255, 255, 12))

    # Disclaimer
    font_disc  = get_font(18)
    disc_text  = "*Conteúdo meramente educativo e informativo. Não constitui aconselhamento financeiro."
    disc_lines = wrap_text(disc_text, font_disc, WIDTH - 100, draw)
    disc_y     = HEIGHT - 28 - len(disc_lines) * 24
    for line in disc_lines:
        bbox = draw.textbbox((0, 0), line, font=font_disc)
        lw   = bbox[2] - bbox[0]
        draw.text(((WIDTH - lw) // 2, disc_y), line, font=font_disc, fill=(255, 255, 255, 160))
        disc_y += 24

    # Cola imagem na zona inferior (se existir)
    if has_image:
        paste_image_bottom(img, image_url)

    img.save(output_path, "PNG")
    return output_path

# ── Endpoints ──────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "CashHunters Slide Generator"}


@app.post("/gerar-carrossel")
def gerar_carrossel(body: CarrosselRequest):
    if not body.slides:
        raise HTTPException(status_code=400, detail="Precisa de pelo menos 1 slide.")
    if len(body.slides) > 12:
        raise HTTPException(status_code=400, detail="Máximo de 12 slides por carrossel.")

    session_id  = str(uuid.uuid4())[:8]
    session_dir = os.path.join(OUTPUT_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    total   = len(body.slides)
    result  = []

    for i, slide in enumerate(body.slides, start=1):
        path = os.path.join(session_dir, f"slide_{i}.png")
        generate_slide(
            frase        = slide.frase,
            subtexto     = slide.subtexto or "",
            slide_num    = i,
            total_slides = total,
            categoria    = body.categoria,
            output_path  = path,
            image_url    = slide.image_url or None
        )
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        result.append({
            "filename": f"slide_{i}.png",
            "data": b64
        })

    return JSONResponse(content={"slides": result})


@app.post("/gerar-slide")
def gerar_slide_unico(
    frase: str,
    subtexto: Optional[str] = "",
    slide_num: int = 1,
    total_slides: int = 1,
    categoria: str = "Cashback e Liberdade Financeira",
    image_url: Optional[str] = None
):
    session_id = str(uuid.uuid4())[:8]
    path       = os.path.join(OUTPUT_DIR, f"slide_{session_id}.png")

    generate_slide(
        frase        = frase,
        subtexto     = subtexto,
        slide_num    = slide_num,
        total_slides = total_slides,
        categoria    = categoria,
        output_path  = path,
        image_url    = image_url
    )

    return FileResponse(path, media_type="image/png", filename=f"slide_{session_id}.png")
