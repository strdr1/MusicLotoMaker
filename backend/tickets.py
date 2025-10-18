
# backend/tickets.py
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import random
import os

class TicketGenerator:
    def generate(self, artists, count=24):
        """Сгенерировать билеты лото"""
        if not artists:
            raise ValueError("Нет артистов для генерации билетов")
        
        # Дублируем артистов если мало
        while len(artists) < 15:
            artists = artists + artists
        
        # Создаем PDF
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "tickets.pdf")
        c = canvas.Canvas(output_path, pagesize=A4)
        
        tickets_per_page = 2
        pages = (count + tickets_per_page - 1) // tickets_per_page
        
        for page in range(pages):
            if page > 0:
                c.showPage()
            
            # Заголовок страницы
            c.setFont("Helvetica-Bold", 16)
            c.drawString(100, 800, "Билеты Музыкального Лото")
            
            # Генерируем билеты для этой страницы
            start_idx = page * tickets_per_page
            end_idx = min(start_idx + tickets_per_page, count)
            
            for i in range(start_idx, end_idx):
                ticket_num = i + 1
                y_position = 700 - (i % tickets_per_page) * 350
                
                self.draw_ticket(c, ticket_num, artists, y_position)
        
        c.save()
        return output_path
    
    def draw_ticket(self, c, ticket_num, artists, y_position):
        """Нарисовать один билет"""
        # Рамка билета
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(1)
        c.rect(50, y_position - 280, 500, 250)
        
        # Заголовок билета
        c.setFont("Helvetica-Bold", 14)
        c.drawString(60, y_position - 30, f"БИЛЕТ №{ticket_num}")
        c.line(50, y_position - 40, 550, y_position - 40)
        
        # Сетка артистов 3x5
        c.setFont("Helvetica", 10)
        ticket_artists = random.sample(artists, 15)
        
        for row in range(3):
            for col in range(5):
                idx = row * 5 + col
                x_pos = 60 + col * 100
                y_pos = y_position - 80 - row * 40
                
                # Номер и артист
                c.drawString(x_pos, y_pos, f"{idx+1}.")
                c.drawString(x_pos + 15, y_pos, ticket_artists[idx][:20])  # Обрезаем длинные имена
        
        # Подпись
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(50, y_position - 290, "Музыкальное Лото - отметьте исполненные треки")