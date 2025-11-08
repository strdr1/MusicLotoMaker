from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import random
import os
import logging
from datetime import datetime
from PyPDF2 import PdfMerger
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)


class TicketGenerator:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self._register_fonts()
        logger.info(f"TicketGenerator initialized with output_dir: {output_dir}")

    def _register_fonts(self):
        """Регистрирует шрифты."""
        try:
            for path in ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
                if os.path.exists(path):
                    name = "Arial-Bold" if "bd" in path.lower() else "Arial"
                    try:
                        pdfmetrics.registerFont(TTFont(name, path))
                    except Exception:
                        pass
        except Exception:
            pass

    def _get_safe_font(self, font_family, bold=False):
        """Возвращает безопасный шрифт."""
        try:
            if pdfmetrics.getFont("Arial"):
                if bold and pdfmetrics.getFont("Arial-Bold"):
                    return "Arial-Bold"
                return "Arial"
        except Exception:
            pass
        return "Helvetica-Bold" if bold else "Helvetica"

    def _get_text_width(self, text, font, size):
        if not text:
            return 0
        avg = size * 0.5
        wide = set('WMДЖЩФ')
        narrow = set('il1ft.,;:! ')
        w = 0
        for ch in text:
            if ch in wide:
                w += size * 0.7
            elif ch in narrow:
                w += size * 0.2
            else:
                w += avg
        return w

    def _wrap_text_smart(self, text, font, size, max_width):
        """Очень агрессивный перенос текста с учетом границ ячейки."""
        if not text:
            return [""]
        
        # Если текст помещается в одну строку
        if self._get_text_width(text, font, size) <= max_width:
            return [text]
        
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            
            # ОЧЕНЬ АГРЕССИВНЫЙ ПЕРЕНОС - разбиваем при 60% ширины
            if self._get_text_width(test_line, font, size) <= max_width * 0.6:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
                
                # Если текущее слово уже не помещается, разбиваем его
                if self._get_text_width(word, font, size) > max_width * 0.5:
                    # Разбиваем слово на части посимвольно
                    chars = list(word)
                    part = ""
                    for char in chars:
                        test_part = part + char
                        if self._get_text_width(test_part, font, size) <= max_width * 0.8:
                            part = test_part
                        else:
                            if part:
                                lines.append(part)
                            part = char
                    if part:
                        current_line = part
                else:
                    current_line = word
                
                if len(lines) == 3:  # Максимум 4 строки
                    break
        
        if current_line and len(lines) < 4:
            lines.append(current_line)
        
        return lines[:4]

    def generate_modern_tickets(self, tracks, count=10, design=None):
        """Генерирует билеты и возвращает путь к ZIP архиву для скачивания"""
        if not tracks:
            raise ValueError("Нет треков для генерации билетов")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(self.output_dir, f"tickets_{timestamp}")
        os.makedirs(folder, exist_ok=True)

        # ФИКСИРОВАННЫЕ НАСТРОЙКИ - РАЗМЕР 11
        t_size = 11  # РАЗМЕР 11
        a_size = 11
        text_color = "#000000"
        accent_color = "#000000"
        bold = True
        upper = False
        pad = 3
        title_pos = 0.5
        artist_pos = 0.5

        title_font = self._get_safe_font("Arial", bold)
        artist_font = self._get_safe_font("Arial", bold)

        ticket_sets = self._generate_random_ticket_sets(tracks, count, 36)
        generated_files = []

        # Генерируем отдельные PDF файлы
        for i in range(count):
            filename = f"ticket_{i+1:03d}.pdf"
            path = os.path.join(folder, filename)
            self._generate_single_ticket(
                path, i + 1, ticket_sets[i],
                title_font, artist_font,
                t_size, a_size,
                text_color, accent_color,
                upper, pad, title_pos, artist_pos
            )
            generated_files.append(path)

        # Создаем объединенный PDF
        merged_pdf_path = os.path.join(folder, "all_tickets.pdf")
        self._merge_pdfs(generated_files, merged_pdf_path)

        # Создаем ZIP архив со всеми файлами
        zip_filename = f"tickets_{timestamp}.zip"
        zip_path = os.path.join(self.output_dir, zip_filename)
        self._create_zip_archive(folder, zip_path)

        logger.info(f"✅ Билеты сгенерированы: {zip_path}")
        
        return {
            "success": True,
            "message": f"Сгенерировано {count} билетов",
            "zip_file": zip_filename,
            "folder": f"tickets_{timestamp}",
            "download_url": f"/api/tickets/download/{zip_filename}",
            "file_path": zip_path
        }

    def _generate_single_ticket(self, path, num, tracks, t_font, a_font,
                               t_size, a_size, text_color, accent_color,
                               upper, pad, title_pos, artist_pos):
        # 📄 Оригинальный A4 горизонтальный (297x210 мм)
        page_width, page_height = A4
        c = canvas.Canvas(path, pagesize=(page_height, page_width))
        w, h = page_height, page_width

        m = 5 * mm

        # Квадратные ячейки: 6x6 - 60% ширины
        table_width = (w - 2 * m) * 0.6  # 60% ширины страницы
        cell_size = table_width / 6
        grid_width = 6 * cell_size
        grid_height = 6 * cell_size

        # Позиционируем таблицу по центру слева
        left_x = m
        left_y = m + ((h - 2 * m) - grid_height) / 2

        # Правая часть: отступ после таблицы
        right_x = left_x + grid_width + 3 * mm

        # Фон
        c.setFillColor(HexColor("#ffffff"))
        c.rect(0, 0, w, h, fill=1, stroke=0)

        # --- ТАБЛИЦА ТРЕКОВ ---
        self._draw_ticket_grid_proper(
            c, left_x, left_y, grid_width, grid_height,
            tracks, t_font, a_font, t_size, a_size,
            text_color, accent_color, upper, pad
        )

        # --- БРЕНД (ЛОГОТИП) В ПРАВОМ ВЕРХНЕМ УГЛУ ---
        brand_image_path = "Brand.png"
        if os.path.exists(brand_image_path):
            try:
                brand_width = 50 * mm
                brand_height = 20 * mm
            
                brand_x = w - brand_width - m
                brand_y = h - brand_height - m
            
                c.drawImage(
                    brand_image_path,
                    brand_x,
                    brand_y,
                    width=brand_width,
                    height=brand_height,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception as e:
                logger.exception(f"Ошибка при вставке бренда: {e}")
        else:
            logger.warning(f"Файл бренда не найден: {brand_image_path}")

        # --- ИЗОБРАЖЕНИЕ С ПРАВИЛАМИ В ПРАВОМ НИЖНЕМ УГЛУ ---
        rules_image_path = "tickerts_rule.png"
        if os.path.exists(rules_image_path):
            try:
                max_img_width = w - right_x - m
                rules_x = w - max_img_width
                rules_y = 0
            
                c.drawImage(
                    rules_image_path,
                    rules_x,
                    rules_y,
                    width=max_img_width,
                    height=None,
                    preserveAspectRatio=True,
                    anchor='sw',
                    mask='auto'
                )
            except Exception as e:
                logger.exception(f"Ошибка при вставке изображения: {e}")
        else:
            logger.warning(f"Файл не найден: {rules_image_path}")

        c.save()

    def _draw_ticket_grid_proper(self, c, x, y, w, h, tracks, t_font, a_font,
                                t_size, a_size, t_col, a_col, upper, pad):
        """Правильная отрисовка таблицы с размером 11 и выравниванием по левому краю."""
        rows, cols = 6, 6
        cell_size = min(w / cols, h / rows)
        cw = ch = cell_size
        
        # Отступы внутри ячейки
        pad_pt = 3
        max_w = cw - pad_pt * 2

        for r in range(rows):
            for col in range(cols):
                cx = x + col * cw
                cy = y + (rows - r - 1) * ch

                # Рамка ячейки
                c.setStrokeColor(black)
                c.setLineWidth(1.0)
                c.rect(cx, cy, cw, ch, stroke=1, fill=0)

                idx = r * cols + col
                if idx >= len(tracks):
                    continue

                t = tracks[idx]
                title = (t.get("title") or "Без названия").strip()
                artist = (t.get("artist") or "Неизвестный исполнитель").strip()
                
                if upper:
                    artist, title = artist.upper(), title.upper()
                
                full_text = f'{artist} "{title}"'

                # Разбиваем текст на строки с ОЧЕНЬ ЧАСТЫМИ переносами
                text_lines = self._wrap_text_smart(full_text, t_font, t_size, max_w)
                text_lines = text_lines[:4]  # Максимум 4 строки

                # Вычисляем общую высоту текста
                line_height = t_size + 1
                total_text_height = len(text_lines) * line_height
                
                # Начальная позиция текста - ОПУСКАЕМ ОТ ВЕРХНЕГО КРАЯ
                top_margin = 6  # Отступ от верхнего края ячейки
                text_start_y = cy + ch - top_margin - line_height

                # Выводим текст - ВЫРАВНИВАЕМ ПО ЛЕВОМУ КРАЮ
                c.setFont(t_font, t_size)
                c.setFillColor(black)
                
                for i, line in enumerate(text_lines):
                    line_y = text_start_y - i * line_height
                    
                    # Проверяем, чтобы не вышли за нижнюю границу
                    if line_y < cy + pad_pt:
                        continue
                    
                    # ВЫРАВНИВАЕМ ПО ЛЕВОМУ КРАЮ с небольшим отступом
                    left_margin = 4  # Небольшой отступ от левого края
                    line_x = cx + left_margin
                    
                    # Проверяем, чтобы текст не выходил за правую границу
                    text_width = self._get_text_width(line, t_font, t_size)
                    if line_x + text_width > cx + cw - pad_pt:
                        # Если не помещается, немного сдвигаем влево
                        line_x = cx + cw - pad_pt - text_width
                        if line_x < cx + left_margin:
                            line_x = cx + left_margin
                    
                    c.drawString(line_x, line_y, line)

    def _generate_random_ticket_sets(self, tracks, count, slots_per_ticket=36):
        if not tracks:
            return [[] for _ in range(count)]
        if len(tracks) < slots_per_ticket:
            pool = tracks * ((slots_per_ticket // len(tracks)) + 1)
        else:
            pool = tracks[:]
        result = []
        for _ in range(count):
            s = random.sample(pool, slots_per_ticket) if len(pool) >= slots_per_ticket else pool[:]
            while len(s) < slots_per_ticket:
                s.append(random.choice(tracks))
            result.append(s)
        return result

    def _merge_pdfs(self, input_files, output_file):
        """Объединяет PDF файлы в один"""
        try:
            merger = PdfMerger()
            for pdf_file in input_files:
                merger.append(pdf_file)
            merger.write(output_file)
            merger.close()
            logger.info(f"✅ PDF файлы объединены: {output_file}")
        except Exception as e:
            logger.error(f"❌ Ошибка объединения PDF: {e}")
            raise

    def _create_zip_archive(self, folder_path, zip_path):
        """Создает ZIP архив с билетами"""
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, folder_path)
                        zipf.write(file_path, arcname)
            logger.info(f"✅ ZIP архив создан: {zip_path}")
            return zip_path
        except Exception as e:
            logger.error(f"❌ Ошибка создания ZIP архива: {e}")
            raise   