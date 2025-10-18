# backend/presentation.py
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
import os

class PresentationGenerator:
    def generate(self, tracks):
        """Сгенерировать презентацию"""
        prs = Presentation()
        
        # Титульный слайд
        title_slide = prs.slides.add_slide(prs.slide_layouts[0])
        title_slide.shapes.title.text = "Музыкальное Лото"
        title_slide.placeholders[1].text = f"Всего треков: {len(tracks)}"
        
        # Слайды для каждого трека
        for i, track in enumerate(tracks, 1):
            self.add_track_slide(prs, track, i)
        
        # Сохраняем
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "presentation.pptx")
        prs.save(output_path)
        
        return output_path
    
    def add_track_slide(self, prs, track, number):
        """Добавить слайд для трека"""
        # Пустой слайд
        slide_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(slide_layout)
        
        # Заголовок
        title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
        title_frame = title_box.text_frame
        title_frame.text = f"Трек #{number}"
        
        title_paragraph = title_frame.paragraphs[0]
        title_paragraph.font.size = Pt(24)
        title_paragraph.font.bold = True
        title_paragraph.alignment = PP_ALIGN.LEFT
        
        # Исполнитель
        artist_box = slide.shapes.add_textbox(Inches(1), Inches(1.5), Inches(8), Inches(1))
        artist_frame = artist_box.text_frame
        artist_frame.text = f"Исполнитель: {track.get('artist', 'Неизвестно')}"
        artist_frame.paragraphs[0].font.size = Pt(18)
        
        # Название трека
        title_text_box = slide.shapes.add_textbox(Inches(1), Inches(2.2), Inches(8), Inches(1))
        title_text_frame = title_text_box.text_frame
        title_text_frame.text = f"Трек: {track.get('title', 'Без названия')}"
        title_text_frame.paragraphs[0].font.size = Pt(18)
        
        # Информация об аудио
        audio_box = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(1))
        audio_frame = audio_box.text_frame
        audio_frame.text = "🎵 Музыкальный отрывок 30 секунд"
        audio_frame.paragraphs[0].font.size = Pt(16)
        audio_frame.paragraphs[0].font.color.rgb = RGBColor(0, 100, 200)
        
        # Номер слайда
        footer_box = slide.shapes.add_textbox(Inches(8.5), Inches(6.5), Inches(1.5), Inches(0.5))
        footer_frame = footer_box.text_frame
        footer_frame.text = f"{number}/{len(prs.slides)}"
        footer_frame.paragraphs[0].font.size = Pt(12)
        footer_frame.paragraphs[0].font.color.rgb = RGBColor(128, 128, 128)
