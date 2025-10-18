# backend/presentation.py
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
import logging
import os
from datetime import datetime
import random

logger = logging.getLogger(__name__)

class ModernPresentationGenerator:
    def __init__(self):
        # Современная цветовая палитра для игрового дизайна
        self.colors = {
            'primary': RGBColor(41, 128, 185),    # Синий
            'secondary': RGBColor(231, 76, 60),   # Красный
            'accent': RGBColor(241, 196, 15),     # Желтый
            'success': RGBColor(46, 204, 113),    # Зеленый
            'dark': RGBColor(44, 62, 80),         # Темно-синий
            'light': RGBColor(236, 240, 241),     # Светло-серый
            'white': RGBColor(255, 255, 255),
            'purple': RGBColor(155, 89, 182),     # Фиолетовый
            'orange': RGBColor(230, 126, 34)      # Оранжевый
        }
    
    def generate_musical_loto_presentation(self, tracks, output_path):
        """Генерация современной презентации для музыкального лото"""
        try:
            logger.info(f"🎲 Генерация Musical Loto для {len(tracks)} треков")
            
            prs = Presentation()
            
            # Современное соотношение сторон 16:9
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)
            
            # 1. Титульный слайд (игровой стиль)
            self._create_title_slide(prs)
            
            # 2. Слайд с правилами
            self._create_rules_slide(prs)
            
            # 3. Раунды (разбиваем треки на 3 раунда по 40)
            rounds = self._split_tracks_into_rounds(tracks, 3, 40)
            
            for round_num, round_tracks in enumerate(rounds, 1):
                # Слайд начала раунда
                self._create_round_start_slide(prs, round_num, len(round_tracks))
                
                # Слайды с исполнителями раунда
                self._create_round_artists_slides(prs, round_tracks, round_num)
                
                # Слайд с кнопками для раунда
                self._create_round_buttons_slide(prs, round_num, len(round_tracks))
            
            # Финальный слайд
            self._create_final_slide(prs)
            
            prs.save(output_path)
            logger.info(f"✅ Musical Loto презентация создана: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации Musical Loto: {e}")
            return None

    def generate_modern_pptx(self, tracks, output_path):
        """Генерация современной презентации (альтернативный стиль)"""
        try:
            logger.info(f"🎨 Генерация современной презентации для {len(tracks)} треков")
            
            prs = Presentation()
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)
            
            # Титульный слайд
            self._create_modern_title_slide(prs, len(tracks))
            
            # Слайды с треками
            for i, track in enumerate(tracks, 1):
                self._create_modern_track_slide(prs, track, i, len(tracks))
            
            # Слайд статистики
            self._create_modern_stats_slide(prs, tracks)
            
            prs.save(output_path)
            logger.info(f"✅ Современная презентация создана: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации современной презентации: {e}")
            return None

    def generate_modern_pdf(self, tracks, output_path):
        """Генерация PDF версии (заглушка)"""
        try:
            logger.info(f"📊 Генерация PDF для {len(tracks)} треков")
            # Пока возвращаем тот же файл что и для PPTX
            pptx_path = output_path.replace('.pdf', '.pptx')
            result = self.generate_modern_pptx(tracks, pptx_path)
            return result
        except Exception as e:
            logger.error(f"❌ Ошибка генерации PDF: {e}")
            return None

    def _create_title_slide(self, prs):
        """Создание титульного слайда в игровом стиле"""
        slide_layout = prs.slide_layouts[6]  # Пустой слайд
        slide = prs.slides.add_slide(slide_layout)
        
        # Градиентный фон
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['dark']
        
        # Декоративные элементы - конфетти
        self._add_confetti(slide)
        
        # Главный заголовок
        title_box = slide.shapes.add_textbox(Inches(1), Inches(1.5), Inches(11), Inches(2))
        title_frame = title_box.text_frame
        title_frame.text = "БОЛЬШОЕ\nМУЗЫКАЛЬНОЕ\nЛОТО"
        
        title_paragraph = title_frame.paragraphs[0]
        title_paragraph.font.size = Pt(54)
        title_paragraph.font.color.rgb = self.colors['accent']
        title_paragraph.font.bold = True
        title_paragraph.alignment = PP_ALIGN.CENTER
        
        # Подзаголовок
        subtitle_box = slide.shapes.add_textbox(Inches(2), Inches(4), Inches(9), Inches(1))
        subtitle_frame = subtitle_box.text_frame
        subtitle_frame.text = "🎵 ИГРАЙ И УГАДЫВАЙ 🎵"
        
        subtitle_paragraph = subtitle_frame.paragraphs[0]
        subtitle_paragraph.font.size = Pt(28)
        subtitle_paragraph.font.color.rgb = self.colors['white']
        subtitle_paragraph.alignment = PP_ALIGN.CENTER
        
        # Кнопка "Начать игру"
        button = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Inches(5), Inches(5.5), Inches(3), Inches(0.8)
        )
        button.fill.solid()
        button.fill.fore_color.rgb = self.colors['primary']
        button.line.color.rgb = self.colors['white']
        button.line.width = Pt(3)
        
        button_text = slide.shapes.add_textbox(Inches(5.1), Inches(5.6), Inches(2.8), Inches(0.6))
        button_frame = button_text.text_frame
        button_frame.text = "🎮 НАЧАТЬ ИГРУ"
        button_frame.paragraphs[0].font.size = Pt(18)
        button_frame.paragraphs[0].font.color.rgb = self.colors['white']
        button_frame.paragraphs[0].font.bold = True
        button_frame.paragraphs[0].alignment = PP_ALIGN.CENTER

    def _create_modern_title_slide(self, prs, total_tracks):
        """Современный титульный слайд для обычной презентации"""
        slide_layout = prs.slide_layouts[0]  # Title Slide
        slide = prs.slides.add_slide(slide_layout)
        
        # Устанавливаем темный фон
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['dark']
        
        # Заголовок
        title_shape = slide.shapes.title
        title_shape.text = "Музыкальная Коллекция"
        title_shape.text_frame.paragraphs[0].font.color.rgb = self.colors['accent']
        title_shape.text_frame.paragraphs[0].font.size = Pt(44)
        title_shape.text_frame.paragraphs[0].font.bold = True
        
        # Подзаголовок
        subtitle_shape = slide.placeholders[1]
        subtitle_shape.text = f"Всего треков: {total_tracks}\nСовременная презентация"
        subtitle_shape.text_frame.paragraphs[0].font.color.rgb = self.colors['white']
        subtitle_shape.text_frame.paragraphs[0].font.size = Pt(20)
        
        # Добавляем дату генерации
        date_box = slide.shapes.add_textbox(Inches(0.5), Inches(6.5), Inches(4), Inches(0.5))
        date_frame = date_box.text_frame
        date_frame.text = f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        date_frame.paragraphs[0].font.size = Pt(12)
        date_frame.paragraphs[0].font.color.rgb = self.colors['white']

    def _create_modern_track_slide(self, prs, track, current_num, total_tracks):
        """Современный слайд с информацией о треке"""
        slide_layout = prs.slide_layouts[1]  # Title and Content
        slide = prs.slides.add_slide(slide_layout)
        
        # Темный фон
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['dark']
        
        # Заголовок слайда
        title_shape = slide.shapes.title
        title_shape.text = f"Трек #{current_num}"
        title_shape.text_frame.paragraphs[0].font.color.rgb = self.colors['accent']
        title_shape.text_frame.paragraphs[0].font.size = Pt(32)
        title_shape.text_frame.paragraphs[0].font.bold = True
        
        # Содержание - информация о треке
        content_shape = slide.placeholders[1]
        content_frame = content_shape.text_frame
        content_frame.clear()  # Очищаем стандартный текст
        
        # Исполнитель
        artist_p = content_frame.paragraphs[0]
        artist_p.text = "🎤 Исполнитель:"
        artist_p.font.bold = True
        artist_p.font.color.rgb = self.colors['white']
        artist_p.font.size = Pt(18)
        
        artist_name_p = content_frame.add_paragraph()
        artist_name_p.text = track.get('artist', 'Неизвестный исполнитель')
        artist_name_p.font.color.rgb = self.colors['primary']
        artist_name_p.font.size = Pt(20)
        artist_name_p.font.bold = True
        
        # Название трека
        title_p = content_frame.add_paragraph()
        title_p.text = "🎵 Название трека:"
        title_p.font.bold = True
        title_p.font.color.rgb = self.colors['white']
        title_p.font.size = Pt(18)
        
        track_title_p = content_frame.add_paragraph()
        track_title_p.text = track.get('title', 'Без названия')
        track_title_p.font.color.rgb = self.colors['white']
        track_title_p.font.size = Pt(16)
        
        # Информация о файле
        file_p = content_frame.add_paragraph()
        file_p.text = "📁 Оригинальный файл:"
        file_p.font.bold = True
        file_p.font.color.rgb = self.colors['light']
        file_p.font.size = Pt(14)
        
        filename_p = content_frame.add_paragraph()
        filename_p.text = track.get('original_filename', 'Неизвестно')
        filename_p.font.color.rgb = self.colors['light']
        filename_p.font.size = Pt(12)
        
        # Номер слайда
        slide_num = slide.shapes.add_textbox(Inches(11.5), Inches(6.8), Inches(1.5), Inches(0.4))
        slide_num_frame = slide_num.text_frame
        slide_num_frame.text = f"{current_num}/{total_tracks}"
        slide_num_frame.paragraphs[0].font.size = Pt(12)
        slide_num_frame.paragraphs[0].font.color.rgb = self.colors['light']
        slide_num_frame.paragraphs[0].alignment = PP_ALIGN.RIGHT

    def _create_modern_stats_slide(self, prs, tracks):
        """Современный слайд со статистикой"""
        slide_layout = prs.slide_layouts[1]
        slide = prs.slides.add_slide(slide_layout)
        
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['dark']
        
        # Заголовок
        title_shape = slide.shapes.title
        title_shape.text = "Статистика"
        title_shape.text_frame.paragraphs[0].font.color.rgb = self.colors['accent']
        title_shape.text_frame.paragraphs[0].font.size = Pt(32)
        
        # Статистика
        content_shape = slide.placeholders[1]
        content_frame = content_shape.text_frame
        content_frame.clear()
        
        artists = [track.get('artist', 'Неизвестно') for track in tracks]
        unique_artists = len(set(artists))
        
        stats_data = [
            f"📊 Всего треков: {len(tracks)}",
            f"🎤 Уникальных исполнителей: {unique_artists}",
            f"⏱️ Общая продолжительность: ~{len(tracks) * 0.5} минут",
            f"📅 Дата генерации: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        ]
        
        for stat in stats_data:
            p = content_frame.add_paragraph()
            p.text = stat
            p.font.size = Pt(16)
            p.font.color.rgb = self.colors['white']
            p.space_after = Pt(12)

    def _create_rules_slide(self, prs):
        """Создание слайда с правилами игры"""
        slide_layout = prs.slide_layouts[1]  # Title and Content
        slide = prs.slides.add_slide(slide_layout)
        
        # Фон
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['light']
        
        # Заголовок
        title_shape = slide.shapes.title
        title_shape.text = "🎯 ПРАВИЛА ИГРЫ"
        title_shape.text_frame.paragraphs[0].font.color.rgb = self.colors['primary']
        
        # Правила
        content_shape = slide.placeholders[1]
        content_frame = content_shape.text_frame
        content_frame.clear()
        
        rules = [
            "🎲 3 раунда по 40 исполнителей",
            "🎵 Каждый трек - 30 секунд",
            "🏆 Угадай исполнителя и название",
            "⭐ 1 балл за исполнителя, 2 балла за название",
            "🎯 Нажимай кнопки для прослушивания",
            "🏅 Победит самый музыкальный!"
        ]
        
        for rule in rules:
            p = content_frame.add_paragraph()
            p.text = rule
            p.font.size = Pt(20)
            p.font.color.rgb = self.colors['dark']
            p.space_after = Pt(12)
            
        # Декоративные элементы
        self._add_game_elements(slide)
    
    def _create_round_start_slide(self, prs, round_num, tracks_count):
        """Слайд начала раунда"""
        slide_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(slide_layout)
        
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['primary']
        
        # Номер раунда
        round_box = slide.shapes.add_textbox(Inches(2), Inches(1), Inches(9), Inches(2))
        round_frame = round_box.text_frame
        round_frame.text = f"РАУНД {round_num}"
        
        round_paragraph = round_frame.paragraphs[0]
        round_paragraph.font.size = Pt(48)
        round_paragraph.font.color.rgb = self.colors['white']
        round_paragraph.font.bold = True
        round_paragraph.alignment = PP_ALIGN.CENTER
        
        # Количество треков
        count_box = slide.shapes.add_textbox(Inches(3), Inches(3), Inches(7), Inches(1))
        count_frame = count_box.text_frame
        count_frame.text = f"{tracks_count} музыкальных треков"
        
        count_paragraph = count_frame.paragraphs[0]
        count_paragraph.font.size = Pt(24)
        count_paragraph.font.color.rgb = self.colors['accent']
        count_paragraph.alignment = PP_ALIGN.CENTER
        
        # Готовность
        ready_box = slide.shapes.add_textbox(Inches(4), Inches(4.5), Inches(5), Inches(1))
        ready_frame = ready_box.text_frame
        ready_frame.text = "🎧 ГОТОВЫ СЛУШАТЬ?"
        
        ready_paragraph = ready_frame.paragraphs[0]
        ready_paragraph.font.size = Pt(28)
        ready_paragraph.font.color.rgb = self.colors['white']
        ready_paragraph.alignment = PP_ALIGN.CENTER
    
    def _create_round_artists_slides(self, prs, tracks, round_num):
        """Создание слайдов с исполнителями раунда"""
        # Разбиваем на группы по 8 исполнителей на слайд
        chunk_size = 8
        for i in range(0, len(tracks), chunk_size):
            chunk = tracks[i:i + chunk_size]
            self._create_artists_chunk_slide(prs, chunk, round_num, i//chunk_size + 1, (len(tracks)-1)//chunk_size + 1)
    
    def _create_artists_chunk_slide(self, prs, tracks_chunk, round_num, chunk_num, total_chunks):
        """Создание слайда с группой исполнителей"""
        slide_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(slide_layout)
        
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['light']
        
        # Заголовок слайда
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.8))
        title_frame = title_box.text_frame
        title_frame.text = f"РАУНД {round_num} - ИСПОЛНИТЕЛИ ({chunk_num}/{total_chunks})"
        
        title_paragraph = title_frame.paragraphs[0]
        title_paragraph.font.size = Pt(20)
        title_paragraph.font.color.rgb = self.colors['primary']
        title_paragraph.font.bold = True
        
        # Сетка исполнителей
        artists_per_row = 2
        card_width = Inches(5.5)
        card_height = Inches(1.2)
        margin = Inches(0.3)
        
        for idx, track in enumerate(tracks_chunk):
            row = idx // artists_per_row
            col = idx % artists_per_row
            
            left = margin + col * (card_width + margin)
            top = Inches(1.5) + row * (card_height + margin)
            
            # Карточка исполнителя
            card = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                left, top, card_width, card_height
            )
            card.fill.solid()
            card.fill.fore_color.rgb = self.colors['white']
            card.line.color.rgb = self.colors['secondary']
            card.line.width = Pt(2)
            
            # Номер и информация
            num_text = slide.shapes.add_textbox(left + Inches(0.2), top + Inches(0.1), Inches(0.6), Inches(0.3))
            num_frame = num_text.text_frame
            num_frame.text = f"{idx + 1 + (chunk_num-1)*8}"
            num_frame.paragraphs[0].font.size = Pt(16)
            num_frame.paragraphs[0].font.color.rgb = self.colors['primary']
            num_frame.paragraphs[0].font.bold = True
            
            artist_text = slide.shapes.add_textbox(left + Inches(0.2), top + Inches(0.4), card_width - Inches(0.4), Inches(0.7))
            artist_frame = artist_text.text_frame
            artist_frame.text = f"{track.get('artist', 'Неизвестно')}\n«{track.get('title', 'Без названия')}»"
            
            for paragraph in artist_frame.paragraphs:
                paragraph.font.size = Pt(12)
                paragraph.font.color.rgb = self.colors['dark']
    
    def _create_round_buttons_slide(self, prs, round_num, tracks_count):
        """Создание слайда с кнопками для прослушивания"""
        slide_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(slide_layout)
        
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['dark']
        
        # Заголовок
        title_box = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(11), Inches(1))
        title_frame = title_box.text_frame
        title_frame.text = f"РАУНД {round_num} - ПРОСЛУШИВАНИЕ"
        
        title_paragraph = title_frame.paragraphs[0]
        title_paragraph.font.size = Pt(32)
        title_paragraph.font.color.rgb = self.colors['accent']
        title_paragraph.alignment = PP_ALIGN.CENTER
        
        # Сетка кнопок 8x5
        button_size = Inches(1.2)
        margin = Inches(0.2)
        start_x = Inches(1)
        start_y = Inches(2)
        
        for i in range(tracks_count):
            row = i // 8
            col = i % 8
            
            left = start_x + col * (button_size + margin)
            top = start_y + row * (button_size + margin)
            
            if top > Inches(6.5):  # Не выходить за пределы слайда
                continue
                
            # Кнопка
            button = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                left, top, button_size, button_size
            )
            button.fill.solid()
            button.fill.fore_color.rgb = self.colors['primary']
            button.line.color.rgb = self.colors['white']
            button.line.width = Pt(2)
            
            # Номер на кнопке
            num_text = slide.shapes.add_textbox(left + Inches(0.3), top + Inches(0.4), Inches(0.6), Inches(0.4))
            num_frame = num_text.text_frame
            num_frame.text = str(i + 1)
            num_frame.paragraphs[0].font.size = Pt(20)
            num_frame.paragraphs[0].font.color.rgb = self.colors['white']
            num_frame.paragraphs[0].font.bold = True
            num_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
            
            # Подпись "30 сек"
            time_text = slide.shapes.add_textbox(left, top + Inches(0.8), button_size, Inches(0.3))
            time_frame = time_text.text_frame
            time_frame.text = "30 сек"
            time_frame.paragraphs[0].font.size = Pt(10)
            time_frame.paragraphs[0].font.color.rgb = self.colors['accent']
            time_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    
    def _create_final_slide(self, prs):
        """Финальный слайд"""
        slide_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(slide_layout)
        
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = self.colors['success']
        
        # Благодарность
        thanks_box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(11), Inches(2))
        thanks_frame = thanks_box.text_frame
        thanks_frame.text = "СПАСИБО,\nЧТО ПРОВЕЛИ ЭТО ВРЕМЯ\nС НАМИ!"
        
        thanks_paragraph = thanks_frame.paragraphs[0]
        thanks_paragraph.font.size = Pt(36)
        thanks_paragraph.font.color.rgb = self.colors['white']
        thanks_paragraph.alignment = PP_ALIGN.CENTER
        
        # Финальный логотип
        logo_box = slide.shapes.add_textbox(Inches(3), Inches(4.5), Inches(7), Inches(1.5))
        logo_frame = logo_box.text_frame
        logo_frame.text = "БОЛЬШОЕ\nМУЗЫКАЛЬНОЕ\nЛОТО"
        
        for paragraph in logo_frame.paragraphs:
            paragraph.font.size = Pt(28)
            paragraph.font.color.rgb = self.colors['accent']
            paragraph.font.bold = True
            paragraph.alignment = PP_ALIGN.CENTER
        
        self._add_confetti(slide)
    
    def _split_tracks_into_rounds(self, tracks, num_rounds, tracks_per_round):
        """Разбивает треки на раунды"""
        # Если треков меньше чем нужно, дублируем случайные
        total_needed = num_rounds * tracks_per_round
        if len(tracks) < total_needed:
            # Дублируем случайные треки чтобы набрать нужное количество
            additional = total_needed - len(tracks)
            extra_tracks = random.choices(tracks, k=additional)
            all_tracks = tracks + extra_tracks
        else:
            all_tracks = tracks[:total_needed]
        
        # Разбиваем на раунды
        rounds = []
        for i in range(num_rounds):
            start_idx = i * tracks_per_round
            end_idx = start_idx + tracks_per_round
            rounds.append(all_tracks[start_idx:end_idx])
        
        return rounds
    
    def _add_confetti(self, slide):
        """Добавляет декоративные конфетти"""
        for i in range(15):
            shape = slide.shapes.add_shape(
                MSO_SHAPE.OVAL,
                Inches(random.uniform(0.5, 12)),
                Inches(random.uniform(0.5, 6)),
                Inches(0.1),
                Inches(0.1)
            )
            color = random.choice([self.colors['accent'], self.colors['secondary'], self.colors['success']])
            shape.fill.solid()
            shape.fill.fore_color.rgb = color
            shape.line.fill.background()
    
    def _add_game_elements(self, slide):
        """Добавляет игровые элементы"""
        # Ноты
        notes = ["♪", "♫", "♬", "🎵", "🎶"]
        for i in range(8):
            note_box = slide.shapes.add_textbox(
                Inches(random.uniform(0.5, 12)),
                Inches(random.uniform(1, 6)),
                Inches(0.5), Inches(0.5)
            )
            note_frame = note_box.text_frame
            note_frame.text = random.choice(notes)
            note_frame.paragraphs[0].font.size = Pt(20)
            note_frame.paragraphs[0].font.color.rgb = self.colors['primary']


class TicketGenerator:
    def generate_modern_tickets(self, tracks, count=24):
        """Генерация билетов в современном стиле"""
        try:
            logger.info(f"🎫 Генерация {count} билетов для {len(tracks)} треков")
            # Заглушка - возвращаем временный путь
            return f"/tmp/modern_tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        except Exception as e:
            logger.error(f"❌ Ошибка генерации билетов: {e}")
            return f"/tmp/tickets_error_{datetime.now().strftime('%H%M%S')}.pdf"