import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2")
GEMINI_API_KEY_3 = os.getenv("GEMINI_API_KEY_3")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("❌ Ошибка: Не найден TELEGRAM_TOKEN или основной GEMINI_API_KEY!")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
router = Router()

keys = [k for k in [GEMINI_API_KEY, GEMINI_API_KEY_2, GEMINI_API_KEY_3] if k]
current_key_idx = 0

SUBJECTS = {
    "math": "📐 Математика",
    "algebra": "📊 Алгебра",
    "geometry": "🧬 Геометрия",
    "physics": "⚡ Физика",
    "chemistry": "🧪 Химия",
    "biology": "🌿 Биология",
    "history": "📜 История",
    "social": "🏛 Обществознание",
    "russian": "🇷🇺 Русский язык",
    "english": "🇬🇧 Английский язык",
    "inf": "💻 Информатика",
    "geo": "🌍 География"
}

SUBJECT_PROMPTS = {
    "math": "Решай математические задачи быстро и по шагам.",
    "algebra": "Объясняй алгебраические преобразования кратко.",
    "geometry": "Давай четкий ход решения геометрических задач.",
    "physics": "Пиши формулы и быстрый расчет в СИ.",
    "chemistry": "Балансируй реакции и давай быстрый ответ.",
    "biology": "Объясняй биологические процессы кратко.",
    "history": "Называй даты и суть событий без воды.",
    "social": "Разбирай термины и ситуации коротко.",
    "russian": "Объясняй правила орфографии и пунктуации тезисно.",
    "english": "Переводи и поясняй грамматику быстро.",
    "inf": "Пиши код и алгоритмы без лишних слов.",
    "geo": "Отвечай по географии четко и по делу."
}

user_subjects = {}
user_histories = {}
user_steps = {}
user_trains = {}

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

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Тренировка (/train)", callback_data="menu_train"),
         InlineKeyboardButton(text="📖 Шпаргалка", callback_data="menu_glossary")],
        [InlineKeyboardButton(text="🔄 Сменить предмет", callback_data="menu_subjects")]
    ])

async def ask_gemini_fast(subject_key: str, text_prompt: str, history=None):
    global current_key_idx
    specific_instruction = SUBJECT_PROMPTS.get(subject_key, "Помогай по учебе.")
    system_text = (
        f"Ты — быстрый школьный репетитор. {specific_instruction} "
        "Отвечай строго по делу, без воды. Без LaTeX (никаких $, \\). Выделяй главное жирным шрифтом."
    )
    
    contents = []
    if history:
        for h in history:
            contents.append({"role": "user" if h['role'] == 'user' else "model", "parts": [{"text": h['text']}]})
            
    contents.append({"role": "user", "parts": [{"text": text_prompt}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_text}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 800
        }
    }

    url_template = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={}"

    async with aiohttp.ClientSession() as session:
        for _ in range(len(keys) * 2):
            key = keys[current_key_idx]
            url = url_template.format(key)
            try:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                return parts[0]["text"].strip()
                    else:
                        print(f"Ошибка HTTP {resp.status}: {await resp.text()}")
            except Exception as e:
                print(f"Ошибка API на ключе #{current_key_idx}: {e}")
            
            if len(keys) > 1:
                current_key_idx = (current_key_idx + 1) % len(keys)
                
    return "⚠️ Перегруз серверов. Повтори запрос."

def split_text(text: str, limit: int = 3500):
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_idx = text.rfind('\n', 0, limit)
        if split_idx == -1:
            split_idx = limit
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    return chunks

async def transcribe_audio_groq(file_path: str) -> str:
    if not GROQ_API_KEY:
        return ""
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    
    async with aiohttp.ClientSession() as session:
        with open(file_path, "rb") as f:
            form = aiohttp.FormData()
            form.add_field('file', f, filename='voice.ogg', content_type='audio/ogg')
            form.add_field('model', 'whisper-large-v3')
            async with session.post(url, headers=headers, data=form) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    return res_json.get("text", "")
    return ""

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_subjects[message.from_user.id] = "math"
    await message.answer(
        "⚡ Бот запущен на молниеносном API! Выбери предмет:",
        reply_markup=subjects_kb()
    )

@router.message(Command("train"))
async def cmd_train(message: Message):
    user_id = message.from_user.id
    subject_key = user_subjects.get(user_id, "math")
    subject_name = SUBJECTS.get(subject_key, "Математика")
    
    prompt = f"Дай 1 короткую задачу по предмету {subject_name}. Внизу напиши ОТВЕТ: [ответ]."
    res = await ask_gemini_fast(subject_key, prompt)
    
    parts = res.split("ОТВЕТ:")
    task_text = parts[0].strip()
    correct_ans = parts[1].strip() if len(parts) > 1 else "решение"
    
    user_trains[user_id] = {"answer": correct_ans.lower()}
    
    await message.answer(
        f"🎯 **Тренажер ({subject_name})**\n\n{task_text}\n\n*Напиши ответ в чат:*",
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("sub_"))
async def process_subject(callback: CallbackQuery):
    sub_key = callback.data.split("_")[1]
    subject_name = SUBJECTS.get(sub_key, "Предмет")
    user_subjects[callback.from_user.id] = sub_key
    user_histories[callback.from_user.id] = []
    
    await callback.message.edit_text(
        f"✅ Предмет: **{subject_name}**\n\nЖду задачу или вопрос 👇",
        parse_mode="Markdown",
        reply_markup=main_menu_kb()
    )

@router.callback_query(F.data.startswith("menu_"))
async def process_menu(callback: CallbackQuery):
    action = callback.data.split("_")[1]
    user_id = callback.from_user.id
    subject_key = user_subjects.get(user_id, "math")
    subject_name = SUBJECTS.get(subject_key, "Предмет")
    
    if action == "subjects":
        await callback.message.edit_text("Выбери предмет:", reply_markup=subjects_kb())
    elif action == "train":
        fake_msg = callback.message
        fake_msg.from_user = callback.from_user
        await cmd_train(fake_msg)
    elif action == "glossary":
        prompt = f"Дай топ-3 коротких термина по предмету {subject_name} с определениями."
        res = await ask_gemini_fast(subject_key, prompt)
        await callback.message.answer(f"📖 **Шпаргалка: {subject_name}**\n\n{res}", parse_mode="Markdown")

@router.callback_query(F.data == "quiz_test")
async def process_quiz(callback: CallbackQuery):
    user_id = callback.from_user.id
    subject_key = user_subjects.get(user_id, "math")
    history = user_histories.get(user_id, [])
    
    last_context = ""
    if history:
        last_context = f"Основываясь на последнем вопросе ученика: '{history[-1].get('text', '')}',"

    prompt = f"{last_context} Составь мини-тест из 1 вопроса с 3 вариантами ответа строго по этой же теме."
    res = await ask_gemini_fast(subject_key, prompt)
    await callback.message.answer(f"🧠 **Проверка по теме:**\n\n{res}", parse_mode="Markdown")

@router.callback_query(F.data == "next_chunk")
async def process_next_chunk(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = user_steps.get(user_id)
    if not data:
        await callback.answer("Готово.")
        return
    chunks = data["chunks"]
    idx = data["index"] + 1
    if idx < len(chunks):
        user_steps[user_id]["index"] = idx
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Дальше ➡️", callback_data="next_chunk")]]) if idx < len(chunks) - 1 else None
        await callback.message.answer(chunks[idx], reply_markup=kb, parse_mode="Markdown")

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message):
    user_id = message.from_user.id
    subject_key = user_subjects.get(user_id, "math")
    subject_name = SUBJECTS.get(subject_key, "Общий")
    
    if user_id in user_trains:
        correct = user_trains[user_id]["answer"]
        user_ans = message.text.strip().lower()
        del user_trains[user_id]
        if correct in user_ans or user_ans in correct:
            await message.answer("🎉 Верно!")
        else:
            await message.answer("❌ Неверно. Попробуй еще через /train")
        return

    if user_id not in user_histories:
        user_histories[user_id] = []
    
    history = user_histories[user_id]
    
    full_prompt = f"Предмет: {subject_name}\nВопрос: {message.text}"
    solution = await ask_gemini_fast(subject_key, full_prompt, history=history)
    
    history.append({"role": "user", "text": message.text})
    history.append({"role": "assistant", "text": solution})
    if len(history) > 6:
        history.pop(0)
        history.pop(0)
    
    chunks = split_text(solution)
    user_steps[user_id] = {"chunks": chunks, "index": 0}
    
    first_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Дальше ➡️", callback_data="next_chunk")]
    ]) if len(chunks) > 1 else None
    
    quiz_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧠 Проверить себя", callback_data="quiz_test")]
    ])
    
    await message.answer(
        f"📚 **{subject_name}**\n\n{chunks[0]}",
        parse_mode="Markdown",
        reply_markup=first_kb
    )
    if len(chunks) == 1:
        await message.answer("Закрепим?", reply_markup=quiz_kb)

@router.message(F.voice | F.audio)
async def handle_voice(message: Message):
    user_id = message.from_user.id
    subject_key = user_subjects.get(user_id, "math")
    subject_name = SUBJECTS.get(subject_key, "Общий")
    
    try:
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_info = await bot.get_file(file_id)
        file_path = file_info.file_path
        
        local_audio = f"voice_{user_id}.ogg"
        await bot.download_file(file_path, local_audio)
        
        transcribed_text = await transcribe_audio_groq(local_audio)
        if os.path.exists(local_audio):
            os.remove(local_audio)
            
        if not transcribed_text:
            await message.answer("⚠️ Не распознано.")
            return
            
        full_prompt = f"Предмет: {subject_name}\nВопрос: {transcribed_text}"
        solution = await ask_gemini_fast(subject_key, full_prompt)
        
        await message.answer(
            f"📚 **{subject_name}** (из голоса: {transcribed_text})\n\n{solution}",
            parse_mode="Markdown",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        await message.answer("⚠️ Ошибка аудио.")

async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Старт"),
        BotCommand(command="train", description="🎯 Тренажер")
    ])
    
    print(f"Бот на прямом API запущен! Ключей: {len(keys)}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
