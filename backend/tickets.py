# backend/tickets.py
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

logger = logging.getLogger(__name__)


class TicketGenerator:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self._register_cyrillic_fonts()
        logger.info(f"TicketGenerator initialized with output_dir: {output_dir}")

    def _register_cyrillic_fonts(self):
        """Регистрирует кириллические шрифты (Arial на Windows)."""
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
        """Возвращает безопасный шрифт (Arial или Helvetica)."""
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
        avg = size * 0.6
        wide = set('WMДЖЩФ')
        narrow = set('il1ft.,;:! ')
        w = 0
        for ch in text:
            if ch in wide:
                w += size * 0.8
            elif ch in narrow:
                w += size * 0.3
            else:
                w += avg
        return w

    def _get_centered_x(self, text, font, size, x, width):
        return x + (width - self._get_text_width(text, font, size)) / 2

    def _wrap_text(self, text, font, size, max_width):
        if not text:
            return [""]
        if self._get_text_width(text, font, size) <= max_width:
            return [text]
        words = text.split()
        if len(words) == 1:
            approx_chars = max(1, int(max_width / (size * 0.6)) - 3)
            return [text[:approx_chars] + ("..." if len(text) > approx_chars else "")]
        lines, current = [], words[0]
        for w in words[1:]:
            if self._get_text_width(current + " " + w, font, size) <= max_width:
                current += " " + w
            else:
                lines.append(current)
                current = w
            if len(lines) == 2:
                break
        lines.append(current)
        result = []
        for ln in lines[:2]:
            if self._get_text_width(ln, font, size) > max_width:
                approx_chars = max(1, int(max_width / (size * 0.6)) - 3)
                result.append(ln[:approx_chars] + ("..." if len(ln) > approx_chars else ""))
            else:
                result.append(ln)
        return result

    def generate_modern_tickets(self, tracks, count=10, design=None):
        if not tracks:
            raise ValueError("Нет треков для генерации билетов")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = os.path.join(self.output_dir, f"tickets_{timestamp}")
        os.makedirs(folder, exist_ok=True)

        d = design or {}
        f_family = d.get("font_family", "Helvetica")
        t_size = int(d.get("title_size", 8))
        a_size = int(d.get("artist_size", 6))
        text_color = d.get("text_color", "#000000")
        accent_color = d.get("accent_color", "#2563eb")
        bold = d.get("bold", False)
        upper = d.get("uppercase", False)
        pad = int(d.get("vertical_padding", 5))
        title_pos = int(d.get("title_position", 30)) / 100.0
        artist_pos = int(d.get("artist_position", 70)) / 100.0

        title_font = self._get_safe_font(f_family, bold)
        artist_font = self._get_safe_font(f_family, False)

        ticket_sets = self._generate_random_ticket_sets(tracks, count, 36)
        generated_files = []

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

        self._merge_in_groups(folder, generated_files)
        return folder

    def _generate_single_ticket(self, path, num, tracks, t_font, a_font,
                               t_size, a_size, text_color, accent_color,
                               upper, pad, title_pos, artist_pos):
        c = canvas.Canvas(path, pagesize=A4)
        w, h = A4
        m = 5 * mm
        t_h = 190 * mm
        t_w = w - 2 * m
        stripe_h = 12 * mm
        x = m
        y = h - m - t_h

        # фон билета
        c.setFillColor(HexColor("#f8fafc"))
        c.rect(x, y, t_w, t_h, fill=1, stroke=0)

        # зелёная полоса
        stripe_col = HexColor("#009956")
        c.setFillColor(stripe_col)
        c.rect(x, y + t_h - stripe_h, t_w, stripe_h, fill=1, stroke=0)

        # разделительная линия под полосой
        c.setStrokeColor(HexColor("#dfeee6"))
        c.setLineWidth(0.6)
        c.line(x + 1 * mm, y + t_h - stripe_h - 0.5 * mm, x + t_w - 1 * mm, y + t_h - stripe_h - 0.5 * mm)

        # надпись "Билет №N"
        header_font = self._get_safe_font("Arial", True)
        c.setFont(header_font, 16)
        c.setFillColor(black)
        c.drawCentredString(x + t_w / 2, y + t_h - stripe_h / 2 - 4, f"Билет №{num}")

        # сетка
        grid_y = y
        grid_h = t_h - stripe_h - (4 * mm)
        self._draw_ticket_grid(c, x, grid_y, t_w, grid_h, tracks, t_font, a_font,
                               t_size, a_size, text_color, accent_color, upper, pad,
                               title_pos, artist_pos)

        # линия отреза
        cut_y = y - 5 * mm
        c.setStrokeColor(HexColor("#666666"))
        c.setLineWidth(0.5)
        c.setDash([2, 2])
        c.line(x, cut_y, x + t_w, cut_y)
        c.setDash()
        c.setFont(a_font, 6)
        c.setFillColor(HexColor("#666666"))
        c.drawCentredString(x + t_w / 2, cut_y - 2 * mm, "Отрежьте по линии")

        c.save()

    def _draw_ticket_grid(self, c, x, y, w, h, tracks, t_font, a_font,
                         t_size, a_size, t_col, a_col, upper, pad,
                         title_pos, artist_pos):
        rows, cols = 6, 6
        cw, ch = w / cols, h / rows
        pad_pt = pad * 0.75
        max_w = cw - pad_pt * 2

        for r in range(rows):
            for col in range(cols):
                cx = x + col * cw
                cy = y + (rows - r - 1) * ch
                c.setStrokeColor(black)
                c.setLineWidth(0.4)
                c.rect(cx, cy, cw, ch, stroke=1, fill=0)

                idx = r * cols + col
                if idx >= len(tracks):
                    continue

                t = tracks[idx]
                title = (t.get("title") or "Без названия").strip()
                artist = (t.get("artist") or "Неизвестный исполнитель").strip()
                if upper:
                    title, artist = title.upper(), artist.upper()

                title_lines = self._wrap_text(title, t_font, t_size, max_w)
                artist_lines = self._wrap_text(artist, a_font, a_size, max_w)
                title_lines, artist_lines = title_lines[:2], artist_lines[:2]

                title_h = len(title_lines) * (t_size + 2)
                artist_h = len(artist_lines) * (a_size + 2)

                # корректное направление (0% сверху, 100% снизу)
                title_base_y = cy + ch * (1 - title_pos) - title_h / 2
                artist_base_y = cy + ch * (1 - artist_pos) - artist_h / 2

                # трек
                c.setFont(t_font, t_size)
                c.setFillColor(HexColor(a_col))
                for i, ln in enumerate(title_lines):
                    line_y = title_base_y + (len(title_lines) - 1 - i) * (t_size + 2)
                    line_x = self._get_centered_x(ln, t_font, t_size, cx, cw)
                    c.drawString(line_x, line_y, ln)

                # артист
                c.setFont(a_font, a_size)
                c.setFillColor(HexColor(t_col))
                for i, ln in enumerate(artist_lines):
                    line_y = artist_base_y + (len(artist_lines) - 1 - i) * (a_size + 2)
                    line_x = self._get_centered_x(ln, a_font, a_size, cx, cw)
                    c.drawString(line_x, line_y, ln)

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

    def _merge_in_groups(self, folder, files):
        if not files:
            return
        files = sorted(files, key=lambda f: os.path.basename(f))
        group_size = 50
        groups = []
        for i in range(0, len(files), group_size):
            g = files[i:i + group_size]
            m = PdfMerger()
            for f in g:
                m.append(f)
            name = os.path.join(folder, f"all_tickets_{i+1}_{i+len(g)}.pdf")
            m.write(name)
            m.close()
            groups.append(name)
        m_all = PdfMerger()
        for g in groups:
            m_all.append(g)
        m_all.write(os.path.join(folder, "all_tickets.pdf"))
        m_all.close()
