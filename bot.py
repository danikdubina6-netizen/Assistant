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
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Ошибка: Не найден TELEGRAM_TOKEN или основной GEMINI_API_KEY!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
router = Router()

# Собираем список доступных клиентов ИИ
clients = []
if GEMINI_API_KEY:
    clients.append(genai.Client(api_key=GEMINI_API_KEY))
if GEMINI_API_KEY_2:
    clients.append(genai.Client(api_key=GEMINI_API_KEY_2))

current_client_idx = 0

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

SUBJECT_PROMPTS = {
    "math": "Ты помогаешь по математике. Решай уравнения, выстраивай логику вычислений, пиши формулы.",
    "algebra": "Ты помогаешь по алгебре. Объясняй преобразования выражений, графики и функции по шагам.",
    "geometry": "Ты помогаешь по геометрии. Расписывай теоремы, свойства фигур, построения и доказательства.",
    "physics": "Ты помогаешь по физике. Указывай законы, формулы, перевод единиц в СИ и подробный ход решения.",
    "chemistry": "Ты помогаешь по химии. Балансируй уравнения реакций, объясняй термины и расчеты по молям.",
    "biology": "Ты помогаешь по биологии. Четко и научно, но понятно объясняй процессы, анатомию и экосистемы.",
    "history": "Ты помогаешь по истории. Называй точные даты, причины, ключевые фигуры и исторические последствия.",
    "social": "Ты помогаешь по обществознанию. Разбирай термины, Конституцию, экономику и правовые ситуации.",
    "russian": "Ты помогаешь по русскому языку. Объясняй правила орфографии, пунктуации, разборы слов и предложений.",
    "english": "Ты помогаешь по английскому языку. Переводи тексты, объясняй грамматические времена и правила.",
    "inf": "Ты помогаешь по информатике. Объясняй программирование (Python, Scratch, алгоритмы), логику, софт и устройство ПК.",
    "geo": "Ты помогаешь по географии. Рассказывай про страны, климат, рельеф и экономическую географию."
}

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
    user_subjects[message.from_user.id] = "math"
    await message.answer(
        "Привет! 🤖 Выбери предмет для помощи:",
        reply_markup=subjects_kb()
    )

@router.callback_query(F.data.startswith("sub_"))
async def process_subject(callback: CallbackQuery):
    sub_key = callback.data.split("_")[1]
    subject_name = SUBJECTS.get(sub_key, "Предмет")
    
    user_subjects[callback.from_user.id] = sub_key
    
    await callback.message.edit_text(
        f"✅ Выбран предмет: **{subject_name}**\n\n"
        "Отлично! Теперь отправляй текст задачи или фото, я на связи 🚀",
        parse_mode="Markdown"
    )
    await callback.answer()

async def ask_gemini(subject_key: str, prompt_content):
    global current_client_idx
    specific_instruction = SUBJECT_PROMPTS.get(subject_key, "Помогай ученику по школьной программе.")
    system_instruction = (
        f"Ты — толковый школьный репетитор-помощник. {specific_instruction} "
        "Отвечай понятно, структурировано, без лишней воды. "
        "НЕ используй LaTeX-формулы (никаких $, \\, и т.д.), пиши математические знаки обычным текстом. "
        "НЕ используй заголовки с решеткой (###), выделяй главное жирным шрифтом."
    )
    
    # Пройдемся по всем доступным ключам по кругу (максимум столько попыток, сколько ключей)
    total_tries = len(clients)
    for i in range(total_tries):
        client = clients[current_client_idx]
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',  # Используем надежную быструю модель
                contents=prompt_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3,
                )
            )
            
            # Безопасно вытаскиваем текст ответа
            answer_text = None
            if response and hasattr(response, 'text') and response.text:
                answer_text = response.text
            elif response and hasattr(response, 'candidates') and response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if hasattr(part, 'text') and part.text:
                                answer_text = part.text
                                break
                    if answer_text:
                        break
            
            if answer_text and str(answer_text).strip():
                return str(answer_text).strip()
            
        except Exception as e:
            print(f"Ошибка на ключе #{current_client_idx}: {e}")
            
        # Если этот ключ не сработал или вернул пустоту — сразу переключаемся на следующий
        if len(clients) > 1:
            current_client_idx = (current_client_idx + 1) % len(clients)
            
    return "⚠️ В данный момент серверы перегружены или исчерпаны лимиты. Попробуй отправить запрос еще раз через пару секунд."

@router.message(F.text)
async def handle_text(message: Message):
    if message.text.startswith("/"):
        return
        
    user_id = message.from_user.id
    subject_key = user_subjects.get(user_id, "math")
    subject_name = SUBJECTS.get(subject_key, "Общий")
    
    processing_msg = await message.answer("🔍 Думаю над ответом...")
    
    full_prompt = f"Предмет: {subject_name}\nВопрос/Задача: {message.text}"
    solution = await ask_gemini(subject_key, full_prompt)
    
    try:
        await processing_msg.delete()
    except:
        pass
    
    await message.answer(
        f"📚 **Предмет:** {subject_name}\n\n{solution}\n\n--- \nХочешь выбрать другой предмет? Нажми /start",
        parse_mode="Markdown"
    )

@router.message(F.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    subject_key = user_subjects.get(user_id, "math")
    subject_name = SUBJECTS.get(subject_key, "Общий")
    
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
        
        prompt = f"Предмет: {subject_name}. Разбери задание с картинки, объясни ход решения или ответь на вопрос."
        solution = await ask_gemini(subject_key, [image_part, prompt])
        
        try:
            await processing_msg.delete()
        except:
            pass
        
        await message.answer(
            f"📚 **Предмет:** {subject_name}\n\n{solution}\n\n--- \nЗадать еще вопрос? Нажми /start",
            parse_mode="Markdown"
        )
    except Exception as e:
        try:
            await processing_msg.delete()
        except:
            pass
        await message.answer(
            f"⚠️ Не удалось обработать фото. Попробуй отправить текстом."
        )

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    print(f"Бот запущен! Активных API-ключей: {len(clients)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
