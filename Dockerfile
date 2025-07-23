# Используем официальный Python-образ
FROM python:3.11-slim

# Создаём рабочую директорию
WORKDIR /app

# Копируем файлы requirements.txt и устанавливаем зависимости
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем всё остальное
COPY ./backend ./backend
COPY ./static ./static

# Открываем порт (обычно 8000)
EXPOSE 8000

# Запускаем приложение
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]