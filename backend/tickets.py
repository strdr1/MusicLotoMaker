# backend/tickets.py
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor
import random
import os
import logging

logger = logging.getLogger(__name__)

class TicketGenerator:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_modern_tickets(self, tracks, count=10, design=None):
        """
        Сгенерировать PDF с билетами.
        tracks: список словарей {'artist': '..', 'title': '..', ...}
        count: количество билетов
        design: словарь параметров дизайна:
            {
                "font_family": "Helvetica",
                "title_size": 14,
                "artist_size": 10,
                "text_color": "#000000",
                "accent_color": "#2563eb",
                "bold": True,
                "uppercase": False
            }
        Возвращает полный путь к PDF.
        """
        if not tracks or len(tracks) == 0:
            raise ValueError("Нет треков для генерации билетов")

        design = design or {}
        font_family = design.get("font_family", "Helvetica")
        title_size = int(design.get("title_size", 14))
        artist_size = int(design.get("artist_size", 10))
        text_color = design.get("text_color", "#111111")
        accent_color = design.get("accent_color", "#2563eb")
        bold = design.get("bold", True)
        uppercase = design.get("uppercase", False)

        # output
        filename = f"tickets_{len(tracks)}_{count}.pdf"
        output_path = os.path.join(self.output_dir, filename)

        # prepare canvas
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4

        # layout: 2 columns x 2 rows per page (4 tickets per page)
        tickets_per_page = 4
        pages = (count + tickets_per_page - 1) // tickets_per_page

        logger.info(f"TicketGenerator: start generate {count} tickets across {pages} pages")

        # Создаем случайные наборы треков для каждого билета (6x6 = 36 треков на билет)
        ticket_tracks_sets = self._generate_random_ticket_sets(tracks, count, slots_per_ticket=36)

        for page in range(pages):
            if page > 0:
                c.showPage()

            # page header
            c.setFont("Helvetica-Bold", 18)
            try:
                c.setFillColor(HexColor(accent_color))
            except Exception:
                c.setFillColor(HexColor("#2563eb"))
            c.drawString(60, height - 50, "🎵 Музыкальное Лото")

            # tickets for this page
            start_idx = page * tickets_per_page
            end_idx = min(start_idx + tickets_per_page, count)
            for i in range(start_idx, end_idx):
                # compute placement
                local_index = i - start_idx  # 0..3
                col = local_index % 2
                row = local_index // 2  # 0 or 1

                ticket_w = (width - 120) / 2  # margin left+right ~60
                ticket_h = (height - 140) / 2

                x = 60 + col * (ticket_w + 20)
                y_top = height - 80 - row * (ticket_h + 20)
                
                # Передаем уникальный набор треков для этого билета
                ticket_tracks = ticket_tracks_sets[i]
                self._draw_ticket(c, i + 1, ticket_tracks, x, y_top, ticket_w, ticket_h,
                                  font_family, title_size, artist_size,
                                  text_color, accent_color, bold, uppercase)

        c.save()
        logger.info(f"TicketGenerator: saved {output_path}")
        return output_path

    def _generate_random_ticket_sets(self, tracks, count, slots_per_ticket=36):
        """
        Генерирует случайные наборы треков для каждого билета.
        Каждый билет получает уникальный набор из 36 случайных треков (6x6).
        """
        if len(tracks) < slots_per_ticket:
            # Если треков меньше, чем нужно для одного билета - дублируем
            needed_multiplier = (slots_per_ticket // len(tracks)) + 1
            pool = tracks * needed_multiplier
            logger.warning(f"Треков ({len(tracks)}) меньше, чем слотов ({slots_per_ticket}). Дублируем треки.")
        else:
            pool = tracks[:]
        
        ticket_sets = []
        
        for i in range(count):
            # Для каждого билета выбираем случайные треки
            if len(pool) >= slots_per_ticket:
                # Если треков достаточно - берем случайную выборку
                chosen = random.sample(pool, slots_per_ticket)
            else:
                # Если все еще недостаточно - берем все что есть и дополняем случайными
                chosen = pool[:]
                while len(chosen) < slots_per_ticket:
                    chosen.append(random.choice(tracks))
            
            ticket_sets.append(chosen)
            logger.debug(f"Билет {i+1}: выбрано {len(chosen)} треков")
        
        logger.info(f"Сгенерировано {len(ticket_sets)} наборов треков для билетов")
        return ticket_sets

    def _draw_ticket(self, c, ticket_num, tracks, x, y_top, w, h,
                     font_family, title_size, artist_size,
                     text_color, accent_color, bold, uppercase):
        """
        Рисует один билет в прямоугольнике (x, y_top) верхняя-left.
        На билет помещаем 36 элементов (6 строк по 6).
        """
        # border
        try:
            c.setStrokeColor(HexColor(accent_color))
        except Exception:
            c.setStrokeColor(HexColor("#2563eb"))
        c.setLineWidth(1)
        c.rect(x, y_top - h, w, h, stroke=1, fill=0)

        # ticket header
        c.setFont("Helvetica-Bold", 12)
        try:
            c.setFillColor(HexColor(accent_color))
        except Exception:
            c.setFillColor(HexColor("#2563eb"))
        c.drawString(x + 8, y_top - 14, f"БИЛЕТ №{ticket_num}")

        # layout: 6 rows x 6 columns = 36 items
        rows = 6
        cols = 6
        left_padding = x + 8
        top_start = y_top - 30
        
        # Calculate cell dimensions
        cell_width = (w - 16) / cols
        cell_height = (h - 40) / rows
        
        # Draw grid and content
        for row in range(rows):
            for col in range(cols):
                idx = row * cols + col
                if idx >= len(tracks):
                    continue
                    
                item = tracks[idx]
                title = item.get("title") or ""
                artist = item.get("artist") or ""

                if uppercase:
                    title = title.upper()
                    artist = artist.upper()

                # Calculate cell position
                cell_x = left_padding + col * cell_width
                cell_y = top_start - row * cell_height

                # Draw cell border (optional)
                c.setStrokeColor(HexColor("#eeeeee"))
                c.setLineWidth(0.3)
                c.rect(cell_x, cell_y - cell_height + 5, cell_width - 2, cell_height - 8, stroke=1, fill=0)

                # title line
                set_font = font_family + ("-Bold" if bold else "")
                try:
                    c.setFont(set_font, title_size)
                except Exception:
                    # fallback
                    c.setFont("Helvetica-Bold" if bold else "Helvetica", title_size)
                try:
                    c.setFillColor(HexColor(text_color))
                except Exception:
                    c.setFillColor(HexColor("#111111"))
                
                # Trim long titles to fit cell
                max_title_chars = 15
                title_draw = (title[:max_title_chars-3] + "...") if len(title) > max_title_chars else title
                c.drawString(cell_x + 2, cell_y - 8, title_draw)

                # artist line (smaller, accent)
                try:
                    c.setFont(font_family, artist_size)
                except Exception:
                    c.setFont("Helvetica", artist_size)
                try:
                    c.setFillColor(HexColor(accent_color))
                except Exception:
                    c.setFillColor(HexColor("#2563eb"))
                
                max_artist_chars = 13
                artist_draw = (artist[:max_artist_chars-3] + "...") if len(artist) > max_artist_chars else artist
                c.drawString(cell_x + 2, cell_y - 20, artist_draw)

        # footer small note
        c.setFont("Helvetica-Oblique", 7)
        try:
            c.setFillColor(HexColor("#888888"))
        except Exception:
            c.setFillColor(HexColor("#888888"))
        c.drawString(x + 8, y_top - h + 8, "Музыкальное лото — отметьте сыгранные треки")