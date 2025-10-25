import os
import zipfile
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from pydub import AudioSegment
import json
import logging
import random
from PIL import Image, ImageOps
from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class ModernPresentationGenerator:
    """
    Современный генератор презентации:
    - заменяет треки по номерам слайдов;
    - добавляет фото артистов (до 14×14 дюймов) в нижний левый угол;
    - подставляет {{ARTIST}} и {{TRACK}} с сохранением стиля;
    - поддерживает ч/б режим и RGBA;
    - гарантирует совпадение mp3, фото и названий по одному слайду;
    - рандомно окрашивает отдельные слова текста (красный или чёрный).
    """

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        if not self.base_path.exists():
            raise FileNotFoundError(f"❌ Шаблон не найден: {self.base_path}")

        self.skip_slides = {1, 2, 3, 4, 45, 46, 47, 88, 89, 90, 131}
        self.buffer_ms = 5000
        self.default_ms = 35_000

    # === служебное ===
    def _load_tracks_from_json(self):
        json_path = Path.cwd() / "tracks.json"
        if not json_path.exists():
            logger.warning("⚠️ tracks.json не найден — треки не загружены")
            return []
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("tracks", [])

    def _get_rels_list_sorted(self, slides_rels_dir: Path):
        rels = list(slides_rels_dir.glob("slide*.xml.rels"))

        def slide_num(p: Path):
            s = p.stem
            num = ''.join(ch for ch in s if ch.isdigit())
            return int(num) if num else 0

        return sorted(rels, key=slide_num)

    # === вставка текста и фото ===
    def _replace_placeholders_and_photos(self, prs, slide_track_map, make_bw: bool):
        """Заменяет {{ARTIST}}, {{TRACK}} и вставляет фото в те слайды, где реально лежит mp3."""
        for slide in prs.slides:
            slide_part = slide.part.partname
            slide_num = int(''.join(ch for ch in slide_part if ch.isdigit()) or 0)

            if slide_num not in slide_track_map:
                continue

            track = slide_track_map[slide_num]
            artist = track.get("artist", "Неизвестный исполнитель")
            title = track.get("title", "Без названия")
            image_path = Path(track.get("image_path", ""))

            # === текст ===
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                text_frame = shape.text_frame

                for paragraph in text_frame.paragraphs:
                    for run in paragraph.runs:
                        font_name = run.font.name
                        font_size = run.font.size
                        font_bold = run.font.bold
                        font_italic = run.font.italic

                        # --- для {{ARTIST}} ---
                        if "{{ARTIST}}" in run.text:
                            paragraph.clear()
                            for word in artist.split():
                                run_artist = paragraph.add_run()
                                run_artist.text = word + " "
                                if font_name:
                                    run_artist.font.name = font_name
                                if font_size:
                                    run_artist.font.size = font_size
                                run_artist.font.bold = font_bold
                                run_artist.font.italic = font_italic
                                # случайный цвет для каждого слова
                                run_artist.font.color.rgb = (
                                    RGBColor(255, 0, 0)
                                    if random.random() < 0.5
                                    else RGBColor(0, 0, 0)
                                )

                        # --- для {{TRACK}} ---
                        elif "{{TRACK}}" in run.text:
                            paragraph.clear()
                            for word in title.split():
                                run_title = paragraph.add_run()
                                run_title.text = word + " "
                                if font_name:
                                    run_title.font.name = font_name
                                if font_size:
                                    run_title.font.size = font_size
                                run_title.font.bold = font_bold
                                run_title.font.italic = font_italic
                                run_title.font.color.rgb = (
                                    RGBColor(255, 0, 0)
                                    if random.random() < 0.5
                                    else RGBColor(0, 0, 0)
                                )

            # === фото ===
            if image_path.exists():
                try:
                    with Image.open(image_path) as img:
                        img = img.convert("RGBA")

                        if make_bw:
                            grayscale = ImageOps.grayscale(img.convert("RGB"))
                            alpha = img.split()[3]
                            img = Image.merge("RGBA", (grayscale, grayscale, grayscale, alpha))

                        # Масштабируем с сохранением пропорций (до 14×14 дюймов)
                        max_dim = Inches(14)
                        dpi = 96  # стандарт PowerPoint
                        target_px = int(max_dim.inches * dpi)
                        img.thumbnail((target_px, target_px), Image.LANCZOS)

                        temp_img_path = Path(tempfile.gettempdir()) / f"temp_photo_{slide_num}.png"
                        img.save(temp_img_path, "PNG", optimize=True)

                        width = Inches(img.width / dpi)
                        height = Inches(img.height / dpi)
                        left = Inches(0)  # без отступов
                        top = prs.slide_height - height  # прижать к нижнему краю

                        slide.shapes.add_picture(str(temp_img_path), left, top, width=width, height=height)
                        temp_img_path.unlink(missing_ok=True)

                        logger.info(
                            f"🖼️ Фото добавлено на слайд {slide_num}: {image_path.name} "
                            f"({width.inches:.2f}×{height.inches:.2f} дюйма)"
                        )

                except Exception as e:
                    logger.error(f"❌ Ошибка вставки фото {image_path}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

        logger.info("✅ Замена текста и добавление фото завершены")

    # === генерация ===
    def generate(self, game_title: str, tracks: list = None, make_bw: bool = False):
        if not tracks:
            tracks = self._load_tracks_from_json()

        if not tracks:
            raise ValueError("❌ Нет треков — генерация невозможна")

        logger.info(f"🎵 Загружено треков: {len(tracks)}")

        tmp = Path(tempfile.mkdtemp(prefix="pptx_work_"))
        extract_dir = tmp / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(self.base_path, "r") as z:
                z.extractall(extract_dir)

            slides_dir = extract_dir / "ppt" / "slides"
            slides_rels_dir = slides_dir / "_rels"
            media_dir = extract_dir / "ppt" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_root = Path.cwd() / "output" / f"presentation_{timestamp}"
            out_root.mkdir(parents=True, exist_ok=True)

            # --- заменяем TITLE ---
            slide1 = slides_dir / "slide1.xml"
            if slide1.exists():
                txt = slide1.read_text(encoding="utf-8")
                if "{{TITLE}}" in txt:
                    txt = txt.replace("{{TITLE}}", game_title)
                    slide1.write_text(txt, encoding="utf-8")
                    logger.info(f"📝 Заголовок заменен на: {game_title}")

            # --- заменяем аудио и формируем карту слайд->трек ---
            rels_list = self._get_rels_list_sorted(slides_rels_dir)
            slide_track_map = {}
            processed_tracks = 0

            for rels_path in rels_list:
                slide_num = int(''.join(ch for ch in rels_path.stem if ch.isdigit()) or 0)
                if slide_num in self.skip_slides:
                    continue
                if processed_tracks >= len(tracks):
                    break

                track = tracks[processed_tracks]
                track_path = track.get("file_path") or track.get("path", "")
                if not track_path:
                    continue

                real_path = next(
                    (p for p in [
                        Path(track_path),
                        Path.cwd() / "downloads" / Path(track_path).name,
                        Path.cwd() / "uploads" / Path(track_path).name
                    ] if p.exists()),
                    None
                )
                if not real_path:
                    logger.warning(f"⚠️ Не найден трек для слайда {slide_num}")
                    continue

                try:
                    tree = ET.parse(rels_path)
                    root = tree.getroot()
                    targets = [
                        rel.attrib.get("Target", "")
                        for rel in root.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
                        if rel.attrib.get("Target", "").lower().endswith(".mp3")
                    ]
                    if not targets:
                        continue

                    audio = AudioSegment.from_file(real_path)
                    seg_start = int(float(track.get("segment_start", 0)) * 1000)
                    seg_dur = int(float(track.get("segment_duration", self.default_ms / 1000)) * 1000)
                    end_ms = min(len(audio), seg_start + seg_dur + self.buffer_ms)
                    clip = audio[seg_start:end_ms]

                    out_media_path = media_dir / os.path.basename(targets[0])
                    clip.export(out_media_path, format="mp3")

                    slide_track_map[slide_num] = track
                    processed_tracks += 1

                    logger.info(f"🎵 Трек {processed_tracks}: {track.get('title', 'Unknown')} → слайд {slide_num}")

                except Exception as e:
                    logger.error(f"❌ Ошибка обработки аудио: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # --- собираем pptx ---
            final_pptx = out_root / f"presentation_{timestamp}.pptx"
            with zipfile.ZipFile(final_pptx, "w", zipfile.ZIP_DEFLATED) as zip_out:
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        fp = Path(root) / file
                        arcname = os.path.relpath(fp, extract_dir)
                        zip_out.write(fp, arcname)

            # --- вставляем тексты и фото по реальной карте ---
            prs = Presentation(final_pptx)
            self._replace_placeholders_and_photos(prs, slide_track_map, make_bw)
            prs.save(final_pptx)

            logger.info(f"✅ Презентация готова: {final_pptx}")
            return str(out_root)

        finally:
            shutil.rmtree(tmp, ignore_errors=True)
