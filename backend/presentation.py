# presentation.py - ПОЛНОСТЬЮ ИСПРАВЛЕННЫЙ
from __future__ import annotations

import os
import random
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

logger = logging.getLogger(__name__)


# ------------------------------
# Helpers / Options
# ------------------------------
def _rgb_from_hex(hex_color: str, fallback: RGBColor) -> RGBColor:
    try:
        h = hex_color.strip().lstrip("#")
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return RGBColor(r, g, b)
    except Exception:
        return fallback


class DesignOptions:
    """
    Набор всех пользовательских опций дизайна.
    """
    def __init__(
        self,
        font_family: str = "Arial",
        title_size: int = 44,
        text_size: int = 24,
        bold_titles: bool = True,
        upper_titles: bool = False,
        text_color: RGBColor = RGBColor(232, 238, 252),
        accent_color: RGBColor = RGBColor(78, 124, 255),

        layout: str = "photo_right",
        photo_radius: int = 0,

        show_numbers: bool = True,
        custom_button_path: Optional[str] = None,

        bg_mode: str = "solid",
        bg_color: RGBColor = RGBColor(18, 27, 47),
        bg_grad_from: RGBColor = RGBColor(26, 35, 64),
        bg_grad_to: RGBColor = RGBColor(15, 22, 35),
        bg_image_path: Optional[str] = None,
    ) -> None:
        self.font_family = font_family
        self.title_size = int(title_size)
        self.text_size = int(text_size)
        self.bold_titles = bool(bold_titles)
        self.upper_titles = bool(upper_titles)
        self.text_color = text_color
        self.accent_color = accent_color

        self.layout = layout
        self.photo_radius = int(photo_radius)

        self.show_numbers = bool(show_numbers)
        self.custom_button_path = custom_button_path

        self.bg_mode = bg_mode
        self.bg_color = bg_color
        self.bg_grad_from = bg_grad_from
        self.bg_grad_to = bg_grad_to
        self.bg_image_path = bg_image_path

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "DesignOptions":
        logger.info(f"🎨 DesignOptions.from_dict вызван")
    
        if not data:
            logger.info("🎨 Используются настройки по умолчанию")
            return cls()

        # Обрабатываем background
        background_data = data.get("background", {})
        logger.info(f"🎨 BACKGROUND DATA: {background_data}")

        # Цвета могут приходиться строками #RRGGBB
        text_color = _rgb_from_hex(data.get("text_color", data.get("textColor", "#E8EEFC")), RGBColor(232, 238, 252))
        accent_color = _rgb_from_hex(data.get("accent_color", data.get("accentColor", "#4E7CFF")), RGBColor(78, 124, 255))
        bg_color = _rgb_from_hex(data.get("bg_color", data.get("background_color", background_data.get("color", "#121B2F"))), RGBColor(18, 27, 47))
        grad_from = _rgb_from_hex(data.get("grad_from", data.get("bg_gradient_from", background_data.get("gradFrom", "#1A2340"))), RGBColor(26, 35, 64))
        grad_to = _rgb_from_hex(data.get("grad_to", data.get("bg_gradient_to", background_data.get("gradTo", "#0F1623"))), RGBColor(15, 22, 35))

        # Получаем custom_button_path
        custom_button_url = data.get("custom_button_path")
        custom_button_path = None

        if custom_button_url:
            try:
                logger.info(f"🔍 Обработка custom_button_url: {custom_button_url}")
                base_dir = os.path.dirname(os.path.dirname(__file__))
                
                # Если это относительный путь
                if custom_button_url.startswith('assets/custom_buttons/'):
                    filename = custom_button_url.replace('assets/custom_buttons/', '')
                    custom_buttons_dir = os.path.join(base_dir, "assets", "custom_buttons")
                    primary_path = os.path.join(custom_buttons_dir, filename)
                    
                    if os.path.exists(primary_path):
                        custom_button_path = primary_path
                        logger.info(f"✅ Кастомная кнопка найдена: {primary_path}")
                    else:
                        logger.warning(f"⚠️ Файл кнопки не найден: {primary_path}")
    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки custom_button_path: {e}")

        # Получаем bg_image_path - ИСПРАВЛЕННАЯ ЧАСТЬ
        bg_image_path = None
        bg_mode = background_data.get("mode", "solid")
        
        if bg_mode == "image":
            image_url = background_data.get("imageURL")
            logger.info(f"🔍 Поиск фонового изображения: {image_url}")
            
            if image_url:
                try:
                    base_dir = os.path.dirname(os.path.dirname(__file__))
                    
                    # Если это относительный путь
                    if image_url.startswith('assets/backgrounds/'):
                        filename = image_url.replace('assets/backgrounds/', '')
                        bg_image_path = os.path.join(base_dir, "assets", "backgrounds", filename)
                    
                    # Если это полный путь или имя файла
                    elif 'background_' in image_url and ('.png' in image_url or '.jpg' in image_url or '.jpeg' in image_url):
                        # Извлекаем имя файла из URL
                        if '/' in image_url:
                            filename = image_url.split('/')[-1].split('?')[0]
                        else:
                            filename = image_url
                        bg_image_path = os.path.join(base_dir, "assets", "backgrounds", filename)
                    
                    # Если это data URL (из превью), игнорируем
                    elif image_url.startswith('data:'):
                        logger.info("ℹ️ Пропускаем data URL из превью")
                        bg_mode = "solid"  # Fallback to solid color
                    
                    # Проверяем существование файла
                    if bg_image_path and os.path.exists(bg_image_path):
                        logger.info(f"✅ Фоновое изображение найдено: {bg_image_path}")
                    else:
                        logger.warning(f"⚠️ Фоновое изображение не найдено: {bg_image_path}")
                        bg_mode = "solid"  # Fallback to solid color
                        
                        # Поиск по всем файлам в backgrounds
                        backgrounds_dir = os.path.join(base_dir, "assets", "backgrounds")
                        if os.path.exists(backgrounds_dir):
                            for file in os.listdir(backgrounds_dir):
                                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                                    potential_path = os.path.join(backgrounds_dir, file)
                                    if os.path.exists(potential_path):
                                        bg_image_path = potential_path
                                        bg_mode = "image"
                                        logger.info(f"✅ Найдено альтернативное фоновое изображение: {bg_image_path}")
                                        break
                               
                except Exception as e:
                    logger.error(f"❌ Ошибка поиска фонового изображения: {e}")
                    bg_mode = "solid"  # Fallback to solid color

        result = cls(
            font_family=str(data.get("font_family", data.get("fontFamily", "Arial"))),
            title_size=int(data.get("title_size", data.get("titleSize", 44))),
            text_size=int(data.get("text_size", data.get("textSize", 24))),
            bold_titles=bool(data.get("bold_titles", data.get("boldTitles", True))),
            upper_titles=bool(data.get("upper_titles", data.get("upperTitles", False))),
            text_color=text_color,
            accent_color=accent_color,

            layout=str(data.get("layout", "photo_right")),
            photo_radius=int(data.get("photo_radius", data.get("photoRadius", 0))),

            show_numbers=bool(data.get("show_numbers", data.get("showNumbers", True))),
            custom_button_path=custom_button_path,

            bg_mode=str(bg_mode),  # Используем переменную bg_mode
            bg_color=bg_color,
            bg_grad_from=grad_from,
            bg_grad_to=grad_to,
            bg_image_path=bg_image_path,
        )

        logger.info(f"🎨 СОЗДАН DesignOptions:")
        logger.info(f"   bg_mode: {result.bg_mode}")
        logger.info(f"   bg_image_path: {result.bg_image_path}")
        logger.info(f"   bg_image_exists: {os.path.exists(result.bg_image_path) if result.bg_image_path else False}")

        return result

# ------------------------------
# Generator
# ------------------------------
class ModernPresentationGenerator:
    """
    Генератор презентации «Большое музыкальное лото».
    """

    def __init__(self) -> None:
        self._opts = DesignOptions()

    def generate_presentation_by_template(
        self,
        tracks: List[dict],
        output_path: str,
        design: Optional[dict] = None,
    ) -> Tuple[str | None, List[Dict]]:
        """
        Генерирует .pptx по структуре
        """
        logger.info("🚀 НАЧАЛО ГЕНЕРАЦИИ ПРЕЗЕНТАЦИИ")
        logger.info(f"📊 Треков: {len(tracks)}")
        logger.info(f"📁 Выходной файл: {output_path}")
        
        try:
            # применяем пользовательские опции
            self._opts = DesignOptions.from_dict(design or {})

            prs = Presentation()
            prs.slide_width = Inches(13.333)  # 1280x720 (16:9)
            prs.slide_height = Inches(7.5)

            # 1) титульный + правила
            self._slide_title(prs)
            self._slide_rules(prs)

            # 2) подготовка треков: минимум 120
            tracks_120 = self._pad_to_120(tracks)
            rounds = self._split_into_rounds(tracks_120, num_rounds=3, per_round=40)

            track_slide_map: List[Dict] = []

            # 3) раунды
            for rnd_idx, round_tracks in enumerate(rounds, start=1):
                self._slide_round_title(prs, rnd_idx)
                menu_slide = self._slide_round_menu(prs, rnd_idx)

                # создаём 40 карточек и линкуем кнопки из меню
                card_slides = []
                for i, tr in enumerate(round_tracks, start=1):
                    s = self._slide_track(
                        prs=prs,
                        track=tr,
                        track_num=i,
                        round_num=rnd_idx,
                        menu_slide=menu_slide,
                    )
                    if s:
                        card_slides.append(s)
                        track_slide_map.append(
                            {
                                "round": rnd_idx,
                                "num": i,
                                "artist": tr.get("artist", ""),
                                "title": tr.get("title", ""),
                            }
                        )

                # привязка кнопок меню к карточкам
                if hasattr(menu_slide, '_round_menu_buttons'):
                    self._wire_menu_buttons_to_cards(menu_slide, card_slides)

                # пауза после 1 и 2 раунда
                if rnd_idx < 3:
                    self._slide_pause(prs, rnd_idx)

            # 4) финальный
            self._slide_final(prs)

            # 5) сохранить
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            prs.save(output_path)
            logger.info("✅ PPTX создан: %s", output_path)
            return output_path, track_slide_map

        except Exception as e:
            logger.exception("❌ Ошибка генерации презентации: %s", e)
            return None, []

    # ---------- INTERNAL ----------

    def _pad_to_120(self, tracks: List[dict]) -> List[dict]:
        if not tracks:
            return []
        if len(tracks) >= 120:
            return tracks[:120]
        need = 120 - len(tracks)
        extra = [self._clone_track_random(tracks) for _ in range(need)]
        out = list(tracks) + extra
        random.shuffle(out)
        return out[:120]

    def _clone_track_random(self, tracks: List[dict]) -> dict:
        base = dict(random.choice(tracks))
        base["id"] = f"dup_{base.get('id', '')}_{random.randint(1000,9999)}"
        return base

    def _split_into_rounds(self, tracks: List[dict], num_rounds: int, per_round: int) -> List[List[dict]]:
        return [tracks[i * per_round : (i + 1) * per_round] for i in range(num_rounds)]

    # ---------- BG / TEXT utilities ----------

    def _apply_background(self, slide, prs) -> None:
        """
        Применяет фон согласно опциям.
        """
        try:
            slide_width = prs.slide_width
            slide_height = prs.slide_height
        
            if self._opts.bg_mode == "image" and self._opts.bg_image_path:
                if os.path.exists(self._opts.bg_image_path):
                    try:
                        logger.info(f"🖼️ Загрузка фонового изображения: {self._opts.bg_image_path}")
                    
                        # Просто добавляем изображение - оно будет фоном
                        pic = slide.shapes.add_picture(
                            self._opts.bg_image_path,
                            Inches(0), Inches(0), slide_width, slide_height
                        )
                        logger.info("✅ Фоновое изображение установлено")
                    
                    except Exception as e:
                        logger.error(f"❌ Ошибка установки фонового изображения: {e}")
                        self._apply_solid_background(slide, self._opts.bg_color)
                else:
                    logger.warning(f"⚠️ Фоновое изображение не найдено: {self._opts.bg_image_path}")
                    self._apply_solid_background(slide, self._opts.bg_color)
                
            elif self._opts.bg_mode == "gradient":
                try:
                    background = slide.background
                    fill = background.fill
                    fill.solid()
                    fill.fore_color.rgb = self._opts.bg_grad_from
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось установить градиент: {e}")
                    self._apply_solid_background(slide, self._opts.bg_grad_from)
                
            else:
                self._apply_solid_background(slide, self._opts.bg_color)
            
        except Exception as e:
            logger.error(f"❌ Ошибка применения фона: {e}")
            try:
                background = slide.background
                fill = background.fill
                fill.solid()
                fill.fore_color.rgb = RGBColor(18, 27, 47)
            except:
                pass

    def _apply_solid_background(self, slide, color):
        """Применяет сплошной цвет фона"""
        try:
            background = slide.background
            fill = background.fill
            fill.solid()
            fill.fore_color.rgb = color
        except Exception as e:
            logger.error(f"❌ Ошибка установки сплошного фона: {e}")

    def _add_text(
        self,
        slide,
        text: str,
        left,
        top,
        width,
        height,
        size: int,
        bold: bool = False,
        align=PP_ALIGN.LEFT,
        color: Optional[RGBColor] = None,
        force_upper: bool = False,
    ):
        try:
            if force_upper:
                text = text.upper()
            tb = slide.shapes.add_textbox(left, top, width, height)
            tf = tb.text_frame
            tf.clear()
            p = tf.paragraphs[0]
            p.text = text
            p.font.name = self._opts.font_family
            p.font.size = Pt(size)
            p.font.bold = bold
            p.font.color.rgb = color or self._opts.text_color
            p.alignment = align
            return tb
        except Exception as e:
            logger.error(f"❌ Ошибка добавления текста: {e}")
            return None

    def _add_artist_photo(self, slide, img_path: str, left, top, width, height):
        """Добавляет фото артиста"""
        try:
            if img_path and os.path.exists(img_path):
                return slide.shapes.add_picture(img_path, left, top, width, height)
            return None
        except Exception as e:
            logger.warning(f"Не удалось вставить фото '{img_path}': {e}")
            return None

    # ---------- Slides ----------

    def _slide_title(self, prs):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        self._apply_background(s, prs)
        self._add_text(
            s,
            "БОЛЬШОЕ\nМУЗЫКАЛЬНОЕ ЛОТО",
            Inches(0.8),
            Inches(1.6),
            Inches(11.5),
            Inches(3.5),
            size=self._opts.title_size if self._opts.title_size > 34 else 60,
            bold=self._opts.bold_titles,
            align=PP_ALIGN.CENTER,
            force_upper=self._opts.upper_titles,
        )
        self._add_text(
            s,
            "Музыкальная викторина в стиле PowerPoint",
            Inches(2.5),
            Inches(5.3),
            Inches(8.3),
            Inches(1.0),
            size=max(self._opts.text_size, 18),
            align=PP_ALIGN.CENTER,
            color=self._opts.accent_color,
        )

    def _slide_rules(self, prs):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        self._apply_background(s, prs)  
        self._add_text(
            s,
            "ПРАВИЛА",
            Inches(0.8),
            Inches(0.7),
            Inches(11.5),
            Inches(0.9),
            max(self._opts.title_size - 4, 28),
            True,
            PP_ALIGN.CENTER,
            force_upper=self._opts.upper_titles,
        )
        rules = [
            "1) Собери комбинацию и крикни «БИНГО» первым.",
            "2) Пой и получай удовольствие.",
            "3) В каждом раунде — 40 номеров.",
            "4) При выборе номера звучит 30с отрывок трека.",
        ]
        for i, line in enumerate(rules):
            self._add_text(
                s,
                line,
                Inches(1.0),
                Inches(2.0 + i * 0.8),
                Inches(11.0),
                Inches(0.7),
                max(self._opts.text_size, 20),
                False,
                PP_ALIGN.LEFT,
                color=self._opts.text_color,
            )

    def _slide_round_title(self, prs, round_num: int):
        roman = ["I", "II", "III"][round_num - 1]
        s = prs.slides.add_slide(prs.slide_layouts[6])
        self._apply_background(s, prs)
        self._add_text(
            s,
            f"{roman} РАУНД — выбор номера",
            Inches(0.8),
            Inches(2.8),
            Inches(11.5),
            Inches(1.2),
            max(self._opts.title_size - 2, 32),
            self._opts.bold_titles,
            PP_ALIGN.CENTER,
            force_upper=self._opts.upper_titles,
        )

    def _slide_round_menu(self, prs, round_num: int):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        self._apply_background(s, prs)

        # создаём 40 кнопок-шейпов
        buttons = []
        custom_btn_ok = (
            self._opts.custom_button_path
            and os.path.exists(self._opts.custom_button_path)
        )

        # сетка 4x10
        start_x, start_y = Inches(0.9), Inches(1.4)
        w, h = Inches(1.2), Inches(0.8)
        gap_x, gap_y = Inches(0.2), Inches(0.25)

        for r in range(4):
            for c in range(10):
                num = r * 10 + c + 1
                left = start_x + c * (w + gap_x)
                top = start_y + r * (h + gap_y)

                if custom_btn_ok:
                    try:
                        shape = s.shapes.add_picture(self._opts.custom_button_path, left, top, w, h)
                        # Нумерация поверх
                        if self._opts.show_numbers:
                            self._add_text(
                                s,
                                str(num),
                                left,
                                top,
                                w,
                                h,
                                size=max(self._opts.text_size, 20),
                                bold=True,
                                align=PP_ALIGN.CENTER,
                                color=self._opts.text_color,
                            )
                        buttons.append(shape)
                    except Exception as e:
                        logger.error(f"❌ Ошибка загрузки кастомной кнопки: {e}")
                        # Fallback to default button
                        shape = self._create_default_button(s, left, top, w, h, num)
                        if shape:
                            buttons.append(shape)
                else:
                    shape = self._create_default_button(s, left, top, w, h, num)
                    if shape:
                        buttons.append(shape)

        s._round_menu_buttons = buttons
        return s

    def _create_default_button(self, slide, left, top, width, height, number):
        """Создает стандартную кнопку"""
        try:
            shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, left, top, width, height)
            fill = shape.fill
            fill.solid()
            fill.fore_color.rgb = self._opts.accent_color
            line = shape.line
            line.color.rgb = self._opts.accent_color
            
            # текст
            if self._opts.show_numbers:
                tf = shape.text_frame
                tf.clear()
                p = tf.paragraphs[0]
                p.text = str(number)
                p.font.name = self._opts.font_family
                p.font.size = Pt(max(self._opts.text_size, 20))
                p.font.bold = True
                p.font.color.rgb = self._opts.text_color
                p.alignment = PP_ALIGN.CENTER
            
            return shape
        except Exception as e:
            logger.error(f"❌ Ошибка создания кнопки: {e}")
            # Создаем простую кнопку как запасной вариант
            try:
                shape = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, left, top, width, height)
                shape.fill.solid()
                shape.fill.fore_color.rgb = RGBColor(78, 124, 255)
                return shape
            except:
                return None

    def _wire_menu_buttons_to_cards(self, menu_slide, card_slides: List):
        try:
            if not hasattr(menu_slide, '_round_menu_buttons'):
                return
                
            for i, (shape, target) in enumerate(zip(menu_slide._round_menu_buttons, card_slides)):
                if shape and target and i < len(card_slides):
                    try:
                        shape.click_action.target_slide = target
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось связать кнопку {i+1} со слайдом: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка связывания кнопок: {e}")

    def _slide_track(self, prs, track: dict, track_num: int, round_num: int, menu_slide):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        self._apply_background(s, prs)

        # номер / заголовки
        subtitle_color = self._opts.text_color
        self._add_text(
            s,
            f"Раунд {round_num}, №{track_num}",
            Inches(0.8),
            Inches(0.5),
            Inches(5.0),
            Inches(0.7),
            max(self._opts.text_size - 6, 16),
            False,
            PP_ALIGN.LEFT,
            subtitle_color,
        )
        artist = track.get("artist", "Неизвестный исполнитель")
        title = track.get("title", "Без названия")
        if self._opts.upper_titles:
            artist = artist.upper()
            title = title.upper()

        # ФИКСИРОВАННЫЙ РАЗМЕР ФОТО
        PHOTO_WIDTH = Inches(4.0)
        PHOTO_HEIGHT = Inches(4.0)

        # Позиции зависят от пресета
        if self._opts.layout == "photo_left":
            # фото слева, текст справа
            img_left, img_top = Inches(0.8), Inches(1.2)
            text_left, text_top, text_w = Inches(5.0), Inches(1.2), Inches(7.8)
        elif self._opts.layout == "photo_top":
            img_left, img_top = Inches(4.5), Inches(0.9)
            text_left, text_top, text_w = Inches(0.8), Inches(5.1), Inches(11.5)
        elif self._opts.layout == "photo_only":
            img_left, img_top = Inches(4.6), Inches(1.0)
            text_left, text_top, text_w = Inches(0.8), Inches(5.6), Inches(11.5)
        else:  # photo_right (дефолт)
            img_left, img_top = Inches(8.5), Inches(1.2)
            text_left, text_top, text_w = Inches(0.8), Inches(1.2), Inches(8.0)

        # Заголовки
        self._add_text(
            s, artist, text_left, text_top, text_w, Inches(1.2),
            max(self._opts.title_size, 28), self._opts.bold_titles, PP_ALIGN.LEFT, self._opts.text_color
        )
        self._add_text(
            s, f"«{title}»", text_left, text_top + Inches(1.1), text_w, Inches(1.0),
            max(self._opts.text_size, 20), False, PP_ALIGN.LEFT, self._opts.accent_color
        )

        # Фото артиста
        img_path = track.get("image_path")
        if img_path and os.path.exists(img_path):
            try:
                self._add_artist_photo(s, img_path, img_left, img_top, PHOTO_WIDTH, PHOTO_HEIGHT)
            except Exception as e:
                logger.warning("Не удалось вставить фото '%s': %s", img_path, e)

        # кнопка «назад в меню»
        try:
            btn = s.shapes.add_shape(
                MSO_AUTO_SHAPE_TYPE.ACTION_BUTTON_BACK_OR_PREVIOUS, Inches(12.2), Inches(0.35), Inches(0.8), Inches(0.6)
            )
            btn.fill.solid()
            btn.fill.fore_color.rgb = self._opts.accent_color
            btn.line.color.rgb = self._opts.accent_color
            if menu_slide:
                btn.click_action.target_slide = menu_slide
        except Exception as e:
            logger.error(f"❌ Ошибка создания кнопки назад: {e}")

        return s

    def _slide_pause(self, prs, after_round: int):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        self._apply_background(s, prs)
        self._add_text(s, "ПАУЗА", Inches(4.5), Inches(3.0), Inches(4.3), Inches(1.2),
                       max(self._opts.title_size + 16, 48), True, PP_ALIGN.CENTER)

    def _slide_final(self, prs):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        self._apply_background(s, prs)
        self._add_text(
            s, "СПАСИБО, ЧТО БЫЛИ С НАМИ!", Inches(1.0), Inches(1.4), Inches(11.3), Inches(1.0),
            max(self._opts.title_size - 4, 28), True, PP_ALIGN.CENTER
        )


class TicketGenerator:
    def generate_modern_tickets(self, tracks: List[dict], count: int = 24) -> str | None:
        """Заглушка генерации билетов"""
        try:
            out = f"/tmp/musical_loto_tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            with open(out, "w", encoding="utf-8") as f:
                f.write("Tickets placeholder")
            return out
        except Exception as e:
            logger.error("❌ Ошибка генерации билетов: %s", e)
            return None


# ------------------------------
# small color util
# ------------------------------
def _dim(rgb: RGBColor, k: float) -> RGBColor:
    """
    Сделать цвет темнее/прозрачнее
    """
    r = max(0, min(255, int(rgb[0] * (1 - (1 - k)))))
    g = max(0, min(255, int(rgb[1] * (1 - (1 - k)))))
    b = max(0, min(255, int(rgb[2] * (1 - (1 - k)))))
    return RGBColor(r, g, b)