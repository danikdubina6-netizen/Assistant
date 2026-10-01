import asyncio
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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

class SolverStates(StatesGroup):
    choosing_subject = State()
    waiting_for_task = State()

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
async def cmd_start(message: Message, state: FSMContext):
    await state.set_state(SolverStates.choosing_subject)
    await message.answer(
        "Привет! 🤖 Какой предмет решить тебе?",
        reply_markup=subjects_kb()
    )

@router.callback_query(SolverStates.choosing_subject, F.data.startswith("sub_"))
async def process_subject(callback: CallbackQuery, state: FSMContext):
    sub_key = callback.data.split("_")[1]
    subject_name = SUBJECTS.get(sub_key, "Предмет")
    
    await state.update_data(subject=subject_name)
    await state.set_state(SolverStates.waiting_for_task)
    
    await callback.message.edit_text(
        f"✅ Выбран предмет: **{subject_name}**\n\n"
        "Выбор зафиксирован! Кидай фото или текст - решим вместе успешно задачу 🚀",
        parse_mode="Markdown"
    )
    await callback.answer()

async def ask_gemini(subject: str, prompt_content):
    system_instruction = (
        "Ты — строгий и точный школьный репетитор-помощник. "
        "ТВОЕ ЕДИНСТВЕННОЕ ПРАВИЛО: ты решаешь исключительно школьные задачи и объясняешь учебный материал. "
        "Никаких посторонних тем, светских разговоров, шуток или обсуждений не по делу. "
        "Если пользователь отправляет что-то не связанное с учебой или школьной задачей, "
        "кратко откажись отвечать. "
        "Выдавай решение структурировано: Дано / Ответ / Пошаговое объяснение."
    )
    
    for attempt in range(3):
        try:
            response = ai_client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
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

@router.message(SolverStates.waiting_for_task, F.text)
async def solve_text_task(message: Message, state: FSMContext):
    data = await state.get_data()
    subject = data.get("subject", "Общий")
    task_text = message.text
    
    processing_msg = await message.answer("🔍 Решаю задачу...")
    
    full_prompt = f"Предмет: {subject}\nЗадача: {task_text}"
    solution = await ask_gemini(subject, full_prompt)
    
    await processing_msg.delete()
    
    await message.answer(
        f"📚 **Предмет:** {subject}\n\n{solution}\n\n--- \nХочешь решить еще задачу? Нажми /start",
        parse_mode="Markdown"
    )
    await state.set_state(SolverStates.choosing_subject)

@router.message(SolverStates.waiting_for_task, F.photo)
async def solve_photo_task(message: Message, state: FSMContext):
    data = await state.get_data()
    subject = data.get("subject", "Общий")
    
    processing_msg = await message.answer("📸 Читаю фото и решаю...")
    
    try:
        photo = message.photo[-1]
        file_info = await bot.get_file(photo.file_id)
        photo_bytes_io = await bot.download_file(file_info.file_path)
        photo_bytes = photo_bytes_io.read()
        
        image_part = types.Part.from_bytes(
            data=photo_bytes,
            mime_type='image/jpeg',
        )
        
        prompt = f"Предмет: {subject}. Реши эту задачу с картинки, объясни ход решения."
        solution = await ask_gemini(subject, [image_part, prompt])
        
        await processing_msg.delete()
        
        await message.answer(
            f"📚 **Предмет:** {subject}\n\n{solution}\n\n--- \nРешить еще что-то? Нажми /start",
            parse_mode="Markdown"
        )
    except Exception as e:
        await processing_msg.edit_text(
            f"⚠️ Не удалось обработать фото: {e}\nПопробуй отправить текстом или скинуть другое фото."
        )
        
    await state.set_state(SolverStates.choosing_subject)

async def main():
    dp.include_router(router)
    print("Бот запущен и готов решать задачи!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
