from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
import os
import uuid
import requests
from io import BytesIO

app = FastAPI(title="CashHunters - Gerador de Slides")

# ── Configurações ──────────────────────────────────────────────
WIDTH, HEIGHT = 1080, 1350
OUTPUT_DIR = "/tmp/slides"
os.makedirs(OUTPUT_DIR, exist_ok=True)

WHITE = (255, 255, 255)
BLUE_HIGHLIGHT = (45, 90, 210)
GREEN_TITLE = (123, 181, 138)
BLUE_TEXT = (45, 90, 210)

# Layout geral
HEADER_LINE_Y = 120
TITLE_BOX_TOP = 80
TITLE_BOX_SIDE_MARGIN = 70
TITLE_BOX_HEIGHT = 220

TEXT_LEFT = 85
TEXT_RIGHT = WIDTH - 85
SUBTEXT_TOP_GAP = 45

IMAGE_AREA_MARGIN = 90
IMAGE_AREA_HEIGHT = 470

# Posição padrão da imagem: mantém consistência visual
BASE_IMAGE_TOP = 735

# Espaço mínimo desejado entre texto e imagem
MIN_TEXT_IMAGE_GAP = 40

# Rodapé
FOOTER_TEXT = "*Conteúdo meramente educativo e informativo. Não constitui aconselhamento financeiro."
FOOTER_Y = HEIGHT - 42
BOTTOM_SAFE_MARGIN = 95

# Cabeçalho
LOGO_X = 45
LOGO_Y = 25
CATEGORY_Y = 34

# Fundo
BG_START = (74, 122, 232)
BG_END = (60, 105, 210)
BG_STRIPE = (255, 255, 255, 20)


# ── Models ─────────────────────────────────────────────────────
class Slide(BaseModel):
    frase: str
    subtexto: Optional[str] = ""
    image_url: Optional[str] = None


class CarrosselRequest(BaseModel):
    slides: List[Slide]
    categoria: Optional[str] = "Cashback e Liberdade Financeira"


# ── Helpers ────────────────────────────────────────────────────
def get_font(size: int, bold: bool = False):
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


def get_line_height(font) -> int:
    bbox = font.getbbox("Ay")
    return bbox[3] - bbox[1]


def wrap_text(text: str, font, max_width: int, draw: ImageDraw.ImageDraw):
    if not text or not text.strip():
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        test_width = bbox[2] - bbox[0]

        if test_width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def fit_text_to_box(text: str, draw: ImageDraw.ImageDraw, max_width: int, max_height: int,
                    start_size: int, min_size: int = 30, bold: bool = True):
    """
    Reduz a fonte automaticamente até o texto caber na caixa.
    """
    for size in range(start_size, min_size - 1, -2):
        font = get_font(size, bold=bold)
        lines = wrap_text(text, font, max_width, draw)
        line_height = get_line_height(font)
        line_spacing = max(6, int(size * 0.16))
        total_height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing

        if total_height <= max_height:
            return font, lines, line_height, line_spacing

    font = get_font(min_size, bold=bold)
    lines = wrap_text(text, font, max_width, draw)
    line_height = get_line_height(font)
    line_spacing = max(6, int(min_size * 0.16))
    return font, lines, line_height, line_spacing


def draw_rounded_rectangle(draw: ImageDraw.ImageDraw, xy, radius: int, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def create_striped_gradient_background():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_START)
    px = img.load()

    for y in range(HEIGHT):
        ratio_y = y / max(HEIGHT - 1, 1)
        r = int(BG_START[0] * (1 - ratio_y) + BG_END[0] * ratio_y)
        g = int(BG_START[1] * (1 - ratio_y) + BG_END[1] * ratio_y)
        b = int(BG_START[2] * (1 - ratio_y) + BG_END[2] * ratio_y)

        for x in range(WIDTH):
            stripe = 8 * ((x // 14) % 2)
            px[x, y] = (
                min(255, r + stripe),
                min(255, g + stripe),
                min(255, b + stripe),
            )

    return img


def load_image_from_url(url: str):
    if not url:
        return None

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGB")
    except Exception:
        return None


def fit_image_cover(img: Image.Image, target_w: int, target_h: int):
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h

    if img_ratio > target_ratio:
        new_h = target_h
        new_w = int(new_h * img_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / img_ratio)

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def paste_rounded_image(base_img: Image.Image, img_to_paste: Image.Image, x: int, y: int, radius: int = 22):
    mask = Image.new("L", img_to_paste.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        (0, 0, img_to_paste.width, img_to_paste.height),
        radius=radius,
        fill=255
    )
    base_img.paste(img_to_paste, (x, y), mask)


def draw_header(draw: ImageDraw.ImageDraw, categoria: str):
    logo_font = get_font(34, bold=True)
    slogan_font = get_font(14, bold=False)
    category_font = get_font(16, bold=False)

    draw.text((LOGO_X, LOGO_Y), "Cash hunters", fill=WHITE, font=logo_font)
    draw.text((LOGO_X + 2, LOGO_Y + 40), "CATCH YOUR FREEDOM", fill=WHITE, font=slogan_font)

    category_bbox = draw.textbbox((0, 0), categoria, font=category_font)
    category_width = category_bbox[2] - category_bbox[0]
    draw.text((WIDTH - category_width - 60, CATEGORY_Y), categoria, fill=WHITE, font=category_font)

    draw.line((50, HEADER_LINE_Y, WIDTH - 50, HEADER_LINE_Y), fill=(255, 255, 255), width=2)


def draw_title_box(draw: ImageDraw.ImageDraw, frase: str):
    box_left = TITLE_BOX_SIDE_MARGIN
    box_right = WIDTH - TITLE_BOX_SIDE_MARGIN
    box_top = TITLE_BOX_TOP
    box_bottom = box_top + TITLE_BOX_HEIGHT

    draw_rounded_rectangle(
        draw,
        (box_left, box_top, box_right, box_bottom),
        radius=85,
        fill=GREEN_TITLE
    )

    max_width = (box_right - box_left) - 70
    max_height = TITLE_BOX_HEIGHT - 40

    title_font, lines, line_height, line_spacing = fit_text_to_box(
        frase,
        draw,
        max_width=max_width,
        max_height=max_height,
        start_size=70,
        min_size=36,
        bold=True
    )

    total_height = len(lines) * line_height + max(0, len(lines) - 1) * line_spacing
    y = box_top + (TITLE_BOX_HEIGHT - total_height) // 2

    # destaque em azul para última palavra ou últimas 2 palavras quando fizer sentido
    words = frase.split()
    highlight_words = []

    if len(words) >= 2:
        if len(words[-1]) <= 4:
            highlight_words = words[-2:]
        else:
            highlight_words = [words[-1]]
    elif words:
        highlight_words = [words[-1]]

    highlight_text = " ".join(highlight_words).lower()

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_width = bbox[2] - bbox[0]
        x = (WIDTH - line_width) // 2

        lowered_line = line.lower()

        if highlight_text and highlight_text in lowered_line:
            prefix = lowered_line.split(highlight_text, 1)[0]
            prefix_original = line[:len(prefix)]
            highlight_original = line[len(prefix):len(prefix) + len(highlight_text)]

            prefix_bbox = draw.textbbox((0, 0), prefix_original, font=title_font)
            prefix_w = prefix_bbox[2] - prefix_bbox[0]

            draw.text((x, y), prefix_original, fill=WHITE, font=title_font)
            draw.text((x + prefix_w, y), highlight_original, fill=BLUE_TEXT, font=title_font)
        else:
            draw.text((x, y), line, fill=WHITE, font=title_font)

        y += line_height + line_spacing


def draw_subtext_and_calculate_bottom(draw: ImageDraw.ImageDraw, subtexto: str) -> int:
    if not subtexto or not subtexto.strip():
        return TITLE_BOX_TOP + TITLE_BOX_HEIGHT

    max_width = TEXT_RIGHT - TEXT_LEFT
    sub_font, lines, line_height, line_spacing = fit_text_to_box(
        subtexto,
        draw,
        max_width=max_width,
        max_height=260,
        start_size=46,
        min_size=28,
        bold=False
    )

    start_y = TITLE_BOX_TOP + TITLE_BOX_HEIGHT + SUBTEXT_TOP_GAP
    y = start_y

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=sub_font)
        line_width = bbox[2] - bbox[0]
        x = (WIDTH - line_width) // 2
        draw.text((x, y), line, fill=WHITE, font=sub_font)
        y += line_height + line_spacing

    return y - line_spacing


def calculate_image_top(text_bottom: int) -> int:
    """
    Mantém a imagem quase sempre na mesma posição.
    Só empurra um pouco para baixo se o texto encostar demais.
    """
    text_limit = BASE_IMAGE_TOP - MIN_TEXT_IMAGE_GAP

    if text_bottom > text_limit:
        overflow = text_bottom - text_limit
        image_top = BASE_IMAGE_TOP + overflow
    else:
        image_top = BASE_IMAGE_TOP

    max_image_top = HEIGHT - IMAGE_AREA_HEIGHT - BOTTOM_SAFE_MARGIN
    image_top = min(image_top, max_image_top)

    return image_top


def draw_footer(draw: ImageDraw.ImageDraw):
    footer_font = get_font(14, bold=False)
    bbox = draw.textbbox((0, 0), FOOTER_TEXT, font=footer_font)
    text_width = bbox[2] - bbox[0]
    x = (WIDTH - text_width) // 2
    draw.text((x, FOOTER_Y), FOOTER_TEXT, fill=WHITE, font=footer_font)


def render_placeholder_image():
    placeholder = Image.new("RGB", (WIDTH - 2 * IMAGE_AREA_MARGIN, IMAGE_AREA_HEIGHT), (220, 220, 220))
    draw = ImageDraw.Draw(placeholder)
    font = get_font(30, bold=True)
    text = "Imagem não disponível"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    draw.text(
        ((placeholder.width - text_w) // 2, (placeholder.height - text_h) // 2),
        text,
        fill=(110, 110, 110),
        font=font
    )
    return placeholder


def render_slide(slide: Slide, categoria: str, index: int) -> str:
    base = create_striped_gradient_background()
    draw = ImageDraw.Draw(base)

    draw_header(draw, categoria)
    draw_title_box(draw, slide.frase)

    text_bottom = draw_subtext_and_calculate_bottom(draw, slide.subtexto or "")
    image_top = calculate_image_top(text_bottom)

    target_w = WIDTH - 2 * IMAGE_AREA_MARGIN
    target_h = IMAGE_AREA_HEIGHT
    image_x = IMAGE_AREA_MARGIN

    content_img = load_image_from_url(slide.image_url) if slide.image_url else None
    if content_img is None:
        content_img = render_placeholder_image()
    else:
        content_img = fit_image_cover(content_img, target_w, target_h)

    paste_rounded_image(base, content_img, image_x, image_top, radius=18)

    draw_footer(draw)

    output_path = os.path.join(OUTPUT_DIR, f"slide_{index}_{uuid.uuid4().hex}.png")
    base.save(output_path, quality=95)
    return output_path


# ── Endpoints ──────────────────────────────────────────────────
@app.get("/")
def health():
    return {"status": "ok", "service": "CashHunters - Gerador de Slides"}


@app.post("/gerar")
def gerar_carrossel(payload: CarrosselRequest):
    if not payload.slides:
        raise HTTPException(status_code=400, detail="Nenhum slide enviado.")

    files = []
    for idx, slide in enumerate(payload.slides, start=1):
        try:
            file_path = render_slide(slide, payload.categoria or "Cashback e Liberdade Financeira", idx)
            files.append({
                "slide": idx,
                "file": file_path,
                "filename": os.path.basename(file_path)
            })
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao gerar slide {idx}: {str(e)}"
            )

    return {
        "success": True,
        "total_slides": len(files),
        "files": files
    }


@app.get("/slide/{filename}")
def baixar_slide(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    return FileResponse(
        file_path,
        media_type="image/png",
        filename=filename
    )
