# HARLEY-AI 🔨

**Dr. Harleen Quinzel** — психолог-психиатр Аркхэма, превратившийся в AI-ассистента.  
Multi-agent система с распознаванием файлов, голоса и авто-роутингом задач.

> ✅ Production-ready | One-command deploy | Полностью offline (Ollama + Whisper)

---

## Быстрый старт

```bash
chmod +x deploy.sh && ./deploy.sh
```

Открой браузер: **http://localhost:8000**  
Логин: `admin` / `HarleyQ!2026`

---

## Возможности

### 🎙️ Голосовые сообщения
- Запись прямо в браузере (кнопка микрофона)
- Загрузка аудио-файлов (MP3, WAV, OGG, FLAC, M4A, WebM)
- Локальная транскрипция через **OpenAI Whisper** (без интернета)
- Авто-определение языка

### 📁 Распознавание любых файлов
| Формат | Что делает |
|--------|-----------|
| PDF | Извлекает текст из всех страниц |
| DOCX/DOC | Читает параграфы Word |
| XLSX/XLS | Парсит все листы и строки |
| PPTX/PPT | Извлекает текст из слайдов |
| CSV | Анализирует структуру данных |
| Images | Описывает через llava vision |
| Code (.py .js .ts …) | Читает и анализирует код |
| ZIP | Показывает содержимое архива |
| Audio | Транскрибирует через Whisper |

### 🤖 Авто-переключение агентов
Система определяет тип задачи и автоматически выбирает агента:

| Агент | Триггер | Режим |
|-------|---------|-------|
| 🧠 Dr. Quinzel | психология, эмоции, поведение | клинический психолог |
| 💻 Code Goblin | code:, баг, python, debug | разработчик |
| 🔍 File Detective | файл, документ, PDF, Excel | аналитик документов |
| 👁️ Vision Harley | изображение, фото | vision AI |
| 🎨 Chaos Creative | напиши, придумай, brainstorm | творческий режим |
| 🃏 Harley | всё остальное | общий хаос |

### 💬 Персонаж
Харли Квинн: бывший психиатр Аркхэма — умная, непредсказуемая, дерзкая.  
Реальные знания психологии + театральный хаос = уникальный опыт.

---

## Стек

```
App:      FastAPI + Python 3.12
LLM:      Ollama (llama3.2 / llava для vision)
STT:      OpenAI Whisper (local, offline)
Files:    pypdf + python-docx + openpyxl + python-pptx + pandas + Pillow
Cache:    Redis
Frontend: Vanilla HTML/CSS/JS (no framework)
Deploy:   Docker Compose
```

---

## GPU (NVIDIA)

Раскомментируй секцию `deploy.resources` в `docker-compose.yml` для ollama.

---

## Смена модели

```bash
# Быстрая (рекомендуется для CPU):
curl http://localhost:11434/api/pull -d '{"name":"llama3.2"}'

# Умнее (нужно 8GB RAM):
curl http://localhost:11434/api/pull -d '{"name":"mistral"}'

# С vision (нужно 8GB):
curl http://localhost:11434/api/pull -d '{"name":"llava"}'
```

Потом измени `OLLAMA_MODEL` в `.env` и перезапусти.

---

## Логи

```bash
docker compose logs -f app      # Harley app
docker compose logs -f ollama   # LLM
```
