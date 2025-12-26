from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import simpleSplit
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
        """Регистрирует Open Sans с поддержкой кириллицы."""
        font_paths = [
            "./fonts/OpenSans-Regular.ttf",
            "./fonts/OpenSans-Bold.ttf",
        ]
        registered = False
        for path in font_paths:
            if os.path.exists(path):
                try:
                    if "Bold" in path:
                        pdfmetrics.registerFont(TTFont("OpenSans-Bold", path))
                        logger.info(f"✅ Зарегистрирован OpenSans-Bold: {path}")
                    else:
                        pdfmetrics.registerFont(TTFont("OpenSans", path))
                        logger.info(f"✅ Зарегистрирован OpenSans: {path}")
                    registered = True
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось зарегистрировать шрифт {path}: {e}")
        if not registered:
            logger.warning("⚠️ Шрифты OpenSans не найдены, используем Helvetica")

    def _get_safe_font(self, bold=False):
        """Возвращает OpenSans или Helvetica."""
        try:
            if bold:
                if pdfmetrics.getFont("OpenSans-Bold"):
                    return "OpenSans-Bold"
            else:
                if pdfmetrics.getFont("OpenSans"):
                    return "OpenSans"
        except Exception:
            pass
        return "Helvetica-Bold" if bold else "Helvetica"

    def _wrap_text_centered(self, text, font_name, font_size, max_width):
        if not text:
            return [""]
        try:
            words = text.split()
            lines = []
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                test_width = pdfmetrics.stringWidth(test_line, font_name, font_size)
                if test_width <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
                    if pdfmetrics.stringWidth(word, font_name, font_size) > max_width:
                        chars = list(word)
                        part = ""
                        for char in chars:
                            test_part = part + char
                            if pdfmetrics.stringWidth(test_part, font_name, font_size) <= max_width:
                                part = test_part
                            else:
                                if part:
                                    lines.append(part)
                                part = char
                        if part:
                            current_line = [part]
            if current_line:
                lines.append(' '.join(current_line))
            return lines[:4]
        except Exception:
            words = text.split()
            lines = []
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if len(test_line) * font_size * 0.5 <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
                    if len(lines) == 3:
                        break
            if current_line and len(lines) < 4:
                lines.append(current_line)
            return lines[:4]

    def generate_modern_tickets(self, tracks, count=10, design=None, progress_callback=None, rounds=3):
        if not tracks:
            raise ValueError("Нет треков для генерации билетов")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(self.output_dir, f"tickets_{timestamp}")
        os.makedirs(folder, exist_ok=True)

        font_size = 20
        text_color = "#000000"
        bold = True
        upper = True
        font_name = self._get_safe_font(bold=bold)

        logger.info(f"🎫 === НАЧАЛО ГЕНЕРАЦИИ БИЛЕТОВ ===")
        logger.info(f"🎫 Параметры: {count} билетов, {len(tracks)} треков, {rounds} раунда(ов)")
        logger.info(f"🎫 Используемый шрифт: {font_name}, размер: {font_size}, верхний регистр: {upper}")

        if progress_callback:
            progress_callback(0, count, "Подготовка к генерации...")

        # Определяем размер таблицы в зависимости от количества раундов
        if rounds == 2:
            rows, cols = 3, 5  # 3 строки, 5 столбцов (3x5)
            slots_per_ticket = rows * cols  # 15 ячеек
        else:
            rows, cols = 6, 6  # 6 строк, 6 столбцов (6x6)
            slots_per_ticket = rows * cols  # 36 ячеек
            
        ticket_sets = self._generate_random_ticket_sets(tracks, count, slots_per_ticket)
        generated_files = []

        for i in range(count):
            filename = f"ticket_{i+1:03d}.pdf"
            path = os.path.join(folder, filename)
            logger.info(f"🎫 🔄 Генерация билета {i+1}/{count}: {filename} (раундов: {rounds}, таблица: {rows}x{cols})")
            if progress_callback:
                progress_callback(i + 1, count, f"Генерация билета {i + 1} из {count}")
            self._generate_single_ticket(
                path, ticket_sets[i], font_name, font_size, text_color, upper, rounds, rows, cols
            )
            generated_files.append(path)
            logger.info(f"🎫 ✅ Билет {i+1}/{count} создан: {filename}")

        if progress_callback:
            progress_callback(count, count, "Создание объединенного PDF...")
        logger.info(f"🎫 Объединение {len(generated_files)} PDF файлов...")
        merged_pdf_path = os.path.join(folder, "all_tickets.pdf")
        self._merge_pdfs(generated_files, merged_pdf_path)

        if progress_callback:
            progress_callback(count, count, "Создание ZIP архива...")
        logger.info(f"🎫 Создание ZIP архива...")
        zip_filename = f"tickets_{timestamp}.zip"
        zip_path = os.path.join(self.output_dir, zip_filename)
        self._create_zip_archive(folder, zip_path)

        if progress_callback:
            progress_callback(count, count, "Генерация завершена!")

        logger.info(f"🎫 ✅ === ГЕНЕРАЦИЯ ЗАВЕРШЕНА ===")
        logger.info(f"🎫 ✅ Сгенерировано билетов: {count}")
        logger.info(f"🎫 ✅ Использовано треков: {len(tracks)}")
        logger.info(f"🎫 ✅ Количество раундов: {rounds}")
        logger.info(f"🎫 ✅ Таблица: {rows}x{cols}")
        logger.info(f"🎫 ✅ ZIP архив: {zip_path}")

        return {
            "success": True,
            "message": f"Сгенерировано {count} билетов ({rounds} раунда)",
            "zip_file": zip_filename,
            "folder": f"tickets_{timestamp}",
            "download_url": f"/api/tickets/download/{zip_filename}",
            "file_path": zip_path,
            "tickets_count": count,
            "tracks_used": len(tracks),
            "rounds": rounds,
            "table_size": f"{rows}x{cols}"
        }

    def _generate_single_ticket(self, path, tracks, font_name, font_size, text_color, upper, rounds=3, rows=6, cols=6):
        # Размер страницы для билета (горизонтальный A4)
        page_width = 67.742 * cm
        page_height = 38.1 * cm
        c = canvas.Canvas(path, pagesize=(page_width, page_height))
        w, h = page_width, page_height

        # Размеры таблицы - оставляем те же для обоих вариантов
        table_width = 36.95 * cm  # Такая же ширина как для 6x6
        rules_width = 27.0 * cm
        
        # Высота таблицы - увеличиваем для 2 раундов для больших ячеек
        if rounds == 2:
            # Для 2 раундов: таблица 3x5 - делаем ячейки выше
            table_height = 22.0 * cm  # Хорошая высота для 3 строк
        else:
            # Для 3 раундов: таблица 6x6
            table_height = 37.4 * cm

        total_content_width = table_width + rules_width + 0.5 * cm
        table_x = (w - total_content_width) / 2
        
        # ОБНОВЛЕНО: Для 2 раундов центрируем таблицу по вертикали
        if rounds == 2:
            # Центрируем таблицу по вертикали
            table_y = (h - table_height) / 2 + 0.5 * cm
            # Правила прижимаем к низу
            rules_y = 1.5 * cm  # Немного выше от края
        else:
            # Для 3 раундов оставляем центрирование
            table_y = (h - table_height) / 2 + 0.5 * cm
            rules_y = table_y  # Правила на той же высоте что и таблица
            
        rules_x = table_x + table_width + 0.5 * cm

        c.setFillColor(HexColor("#ffffff"))
        c.rect(0, 0, w, h, fill=1, stroke=0)

        self._draw_centered_table(
            c, table_x, table_y, table_width, table_height,
            tracks, font_name, font_size, text_color, upper, rows, cols
        )

        # ВЫБОР ФАЙЛА ПРАВИЛ В ЗАВИСИМОСТИ ОТ КОЛИЧЕСТВА РАУНДОВ
        rules_image_path = f"tickerts_rule_{'2' if rounds == 2 else ''}.png"
        if not os.path.exists(rules_image_path):
            rules_image_path = "tickerts_rule.png"
        
        logger.info(f"🎫 Используем файл правил: {rules_image_path} (раундов: {rounds})")
        
        if os.path.exists(rules_image_path):
            try:
                # Для 2 раундов прижимаем правила к низу, для 3 - на уровне таблицы
                c.drawImage(rules_image_path, rules_x, rules_y, width=rules_width, preserveAspectRatio=True, anchor='sw', mask='auto')
            except Exception as e:
                logger.exception(f"Ошибка при вставке изображения правил: {e}")
        else:
            logger.warning(f"⚠️ Файл правил не найден: {rules_image_path}")

        brand_image_path = "Brand.png"
        if os.path.exists(brand_image_path):
            try:
                brand_width = 8.55 * cm
                brand_height = 5.72 * cm
                brand_x = w - brand_width
                brand_y = h - brand_height
                c.drawImage(brand_image_path, brand_x, brand_y, width=brand_width, height=brand_height, preserveAspectRatio=False, mask='auto')
            except Exception as e:
                logger.exception(f"Ошибка при вставке логотипа Brand.png: {e}")

        c.save()

    def _draw_centered_table(self, c, x, y, w, h, tracks, font_name, font_size, text_color, upper, rows=6, cols=6):
        cell_width = w / cols
        cell_height = h / rows
        padding_x = 8
        padding_y = 8  # Увеличили вертикальный паддинг

        # Увеличиваем шрифт для 2 раундов (большие ячейки)
        if rows == 3 and cols == 5:
            font_size = 24  # Еще больше увеличили шрифт для 2 раундов

        for r in range(rows):
            for col in range(cols):
                cx = x + col * cell_width
                cy = y + (rows - r - 1) * cell_height

                c.setStrokeColor(black)
                c.setLineWidth(2.0)
                c.rect(cx, cy, cell_width, cell_height, stroke=1, fill=0)

                idx = r * cols + col
                if idx >= len(tracks):
                    continue

                t = tracks[idx]
                title = (t.get("title") or "Без названия").strip()
                artist = (t.get("artist") or "Неизвестный исполнитель").strip()

                if upper:
                    artist = artist.upper()
                    title = title.upper()

                text = f'{artist} "{title}"'
                max_text_width = cell_width - 2 * padding_x
                lines = self._wrap_text_centered(text, font_name, font_size, max_text_width)

                c.setFont(font_name, font_size)
                c.setFillColor(black)

                line_height = font_size * 1.2
                total_text_height = len(lines) * line_height
                cell_center_y = cy + cell_height / 2
                first_line_baseline_y = cell_center_y + (total_text_height / 2) - (line_height / 2)

                for i, line in enumerate(lines):
                    if not line.strip():
                        continue

                    text_width = pdfmetrics.stringWidth(line, font_name, font_size)
                    line_x = cx + (cell_width - text_width) / 2
                    min_x = cx + padding_x
                    max_x = cx + cell_width - padding_x - text_width
                    if line_x < min_x: line_x = min_x
                    elif line_x > max_x: line_x = max_x

                    line_y = first_line_baseline_y - i * line_height
                    min_y = cy + padding_y
                    max_y = cy + cell_height - padding_y

                    if line_y > max_y and i == 0:
                        shift = line_y - max_y
                        first_line_baseline_y -= shift
                        line_y = first_line_baseline_y - i * line_height
                    if line_y < min_y and i == len(lines) - 1:
                        shift = min_y - line_y
                        first_line_baseline_y += shift
                        line_y = first_line_baseline_y - i * line_height

                    if line_y < min_y: line_y = min_y
                    elif line_y > max_y: line_y = max_y

                    c.drawString(line_x, line_y, line)

    def _generate_random_ticket_sets(self, tracks, count, slots_per_ticket=36):
        if not tracks:
            return [[] for _ in range(count)]
        if len(tracks) < slots_per_ticket:
            pool = tracks * ((slots_per_ticket // len(tracks)) + 1)
        else:
            pool = tracks[:]
        result = []
        for i in range(count):
            s = random.sample(pool, slots_per_ticket) if len(pool) >= slots_per_ticket else pool[:]
            while len(s) < slots_per_ticket:
                s.append(random.choice(tracks))
            result.append(s)
        return result

    def _merge_pdfs(self, input_files, output_file):
        merger = PdfMerger()
        for pdf_file in input_files:
            merger.append(pdf_file)
        merger.write(output_file)
        merger.close()

    def _create_zip_archive(self, folder_path, zip_path):
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)
        return zip_path