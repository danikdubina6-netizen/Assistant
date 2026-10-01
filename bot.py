import asyncio
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    CallbackQuery
)
from google import genai
from google.genai import types

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Ошибка: Не найдены переменные окружения TELEGRAM_TOKEN или GEMINI_API_KEY!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
router = Router()

ai_client = genai.Client(api_key=GEMINI_API_KEY)

SUBJECTS = {
    "math": "📐 Математика",
    "algebra": "📊 Алгебра",
    "geometry": "📐 Геометрия",
    "physics": "⚡ Физика",
    "chemistry": "🧪 Химия",
    "biology": "🧬 Биология",
    "history": "📜 История",
    "social": "🏛 Обществознание",
    "russian": "🇷🇺 Русский язык",
    "english": "🇬🇧 Английский язык",
    "inf": "💻 Информатика",
    "geo": "🌍 География"
}

# Словарь для хранения выбранного предмета для каждого пользователя
user_subjects = {}

def subjects_kb():
    keyboard = []
    row = []
    for key, name in SUBJECTS.items():
        row.append(InlineKeyboardButton(text=name, callback_data=f"sub_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_subjects[message.from_user.id] = "Общий"
    await message.answer(
        "Привет! 🤖 Выбери предмет для помощи:",
        reply_markup=subjects_kb()
    )

@router.callback_query(F.data.startswith("sub_"))
async def process_subject(callback: CallbackQuery):
    sub_key = callback.data.split("_")[1]
    subject_name = SUBJECTS.get(sub_key, "Предмет")
    
    # Сохраняем предмет за конкретным пользователем
    user_subjects[callback.from_user.id] = subject_name
    
    await callback.message.edit_text(
        f"✅ Выбран предмет: **{subject_name}**\n\n"
        "Отлично! Теперь отправляй текст задачи или фото, я на связи 🚀",
        parse_mode="Markdown"
    )
    await callback.answer()

async def ask_gemini(subject: str, prompt_content):
    system_instruction = (
        "Ты — толковый школьный репетитор-помощник. "
        "Помогай ученику по школьным предметам: решай задачи, объясняй правила, "
        "а также подсказывай по учебным программам, технологиям и софту (например, по информатике, Скретчу и т.д.). "
        "Отвечай понятно, структурировано и по делу."
    )
    
    for attempt in range(3):
        try:
            response = ai_client.models.generate_content(
                model='gemini-3.5-flash',
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3,
                )
            )
            return response.text
        except Exception as e:
            error_str = str(e)
            if ("503" in error_str or "429" in error_str or "UNAVAILABLE" in error_str or "RESOURCE_EXHAUSTED" in error_str) and attempt < 2:
                await asyncio.sleep(5)
                continue
            if attempt == 2:
                return f"⚠️ Ошибка квот или обращения к ИИ: {e}"

@router.message(F.text)
async def handle_text(message: Message):
    # Игнорируем команды вроде /start
    if message.text.startswith("/"):
        return
        
    user_id = message.from_user.id
    subject = user_subjects.get(user_id, "Общий")
    
    processing_msg = await message.answer("🔍 Думаю над ответом...")
    
    full_prompt = f"Предмет: {subject}\nВопрос/Задача: {message.text}"
    solution = await ask_gemini(subject, full_prompt)
    
    await processing_msg.delete()
    
    await message.answer(
        f"📚 **Предмет:** {subject}\n\n{solution}\n\n--- \nХочешь выбрать другой предмет? Нажми /start",
        parse_mode="Markdown"
    )

@router.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    subject = user_subjects.get(user_id, "Общий")
    
    processing_msg = await message.answer("📸 Читаю фото...")
    
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes_io = await bot.download_file(file_info.file_path)
        photo_bytes = photo_bytes_io.read()
        
        image_part = types.Part.from_bytes(
            data=photo_bytes,
            mime_type='image/jpeg',
        )
        
        prompt = f"Предмет: {subject}. Разбери задание с картинки, объясни ход решения или ответь на вопрос."
        solution = await ask_gemini(subject, [image_part, prompt])
        
        await processing_msg.delete()
        
        await message.answer(
            f"📚 **Предмет:** {subject}\n\n{solution}\n\n--- \nЗадать еще вопрос? Нажми /start",
            parse_mode="Markdown"
        )
    except Exception as e:
        await processing_msg.edit_text(
            f"⚠️ Не удалось обработать фото: {e}\nПопробуй отправить текстом."
        )

async def main():
    dp.include_router(router)
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
