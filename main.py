import os
import random
import sqlite3
import asyncio
import logging
from dotenv import load_dotenv
from unidecode import unidecode
from telethon import TelegramClient, events
from datetime import datetime, time, timedelta

# Настройка логирования
def setup_logging():
    """Настройка системы логирования"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    log_formatter = logging.Formatter(log_format)

    # Логирование в файл
    file_handler = logging.FileHandler('bot.log', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG)

    # Логирование в консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.DEBUG)

    # Основной логгер
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # Логгеры библиотек
    logging.getLogger('telethon').setLevel(logging.ERROR)
    logging.getLogger('asyncio').setLevel(logging.ERROR)


    return logger

logger = setup_logging()

# Загрузка конфигурации
load_dotenv()
CONFIG = {
    'TOKEN': os.getenv('TOKEN'),
    'API_ID': int(os.getenv('API_ID')),
    'API_HASH': os.getenv('API_HASH'),
    'DB_NAME': os.getenv('DB_NAME', 'sqlite.db'),
    'DEFAULT_NAMES_FILE': 'default_names.txt',
    'DEFAULT_NAME': os.getenv('DEFAULT_NAME'),
    'TARGET_TIME': time(15, 30),  # Время отправки (15:30)
    'TARGET_CHAT_ID': int(os.getenv('TARGET_CHAT_ID')) if os.getenv('TARGET_CHAT_ID') else None,
}

# Глобальное состояние
STATE = {
    'current_date': None,
    'last_shay_ids': [],
    'current_shay_name': None
}

def init_db():
    """Инициализация базы данных"""
    try:
        with sqlite3.connect(CONFIG['DB_NAME']) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS shays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    normalized_name TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        try: # Add stat collumn
            conn.execute('ALTER TABLE shays ADD COLUMN stats INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

            if not conn.execute('SELECT 1 FROM shays LIMIT 1').fetchone():
                default_names = load_default_names()
                conn.executemany(
                    'INSERT INTO shays (name, normalized_name) VALUES (?, ?)',
                    [(name, normalize_name(name)) for name in default_names]
                )
            conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}", exc_info=True)
        raise

def normalize_name(name):
    """Нормализация имени для дедупликации"""
    return unidecode(name.lower().strip())

def load_default_names():
    """Загрузка стандартных имен из файла"""
    try:
        with open(CONFIG['DEFAULT_NAMES_FILE'], 'r', encoding='utf-8') as f:
            names = [line.strip() for line in f if line.strip()]
            if not names:
                names = [CONFIG['DEFAULT_NAME']]
            logger.info(f"Loaded {len(names)} default names from file")
            return names
    except FileNotFoundError:
        logger.warning(f"Default names file not found, using default name only")
        return [CONFIG['DEFAULT_NAME']]
    except Exception as e:
        logger.error(f"Error loading default names: {e}", exc_info=True)
        return [CONFIG['DEFAULT_NAME']]

async def save_names_to_file():
    """Сохраняет все имена из базы данных в файл с добавлением уникальности"""
    try:
        names = db_query('SELECT name FROM shays ORDER BY id ASC;')
        if not names:
            logger.info("Database is empty, nothing to save")
            return "База данных пуста, сохранять нечего."

        try:
            with open(CONFIG['DEFAULT_NAMES_FILE'], 'r', encoding='utf-8') as f:
                existing_names = {line.strip() for line in f if line.strip()}
        except FileNotFoundError:
            existing_names = set()

        # Добавляем новые имена к существующим
        new_names = {name[0] for name in names}
        all_names = existing_names | new_names  # Объединение множества без дубликатов

        # Записываем имена обратно в файл
        with open(CONFIG['DEFAULT_NAMES_FILE'], 'w', encoding='utf-8') as f:
            first = True
            for name in sorted(all_names):
                if not first:
                    f.write('\n')  # Пишем новую строку только перед не первой записью
                f.write(name)
                first = False  # Устанавливаем, что первая запись уже прошла

        logger.info(f"Appended {len(names)} names to {CONFIG['DEFAULT_NAMES_FILE']} with deduplication")
        return f"Имена ({len(new_names)}) успешно сохранены на сервере."
    except Exception as e:
        logger.error(f"Error saving names to file: {e}", exc_info=True)
        return "Произошла ошибка при сохранении имен в файл."

def db_query(query, params=(), fetch=False):
    """Универсальный запрос к БД"""
    try:
        with sqlite3.connect(CONFIG['DB_NAME']) as conn:
            cursor = conn.execute(query, params)
            if query.strip().upper().startswith('SELECT'):
                return cursor.fetchone() if fetch else cursor.fetchall()
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        logger.error(f"Database query failed: {query} with params {params}. Error: {e}", exc_info=True)
        raise

async def send_shay_list(event):
    """Отправка списка всех имен и их статистики"""
    try:
        rows = db_query('SELECT name, stats FROM shays ORDER BY created_at DESC;')
        if not rows:
            await event.reply("База данных пуста.")
            logger.info("Empty database response sent")
            return

        names_list = "\n".join(
            f"{i+1}. {name} — {count}" for i, (name, count) in enumerate(rows)
        )
        total = len(rows)
        total_sent = sum(count for _, count in rows)

        response = (
            f"**Список всех имен ({total}):**\n\n{names_list}\n\n"
            f"Всего имен: **{total}**\n"
            f"Всего отправок: **{total_sent}**"
        )
        await event.reply(response, parse_mode='md')
        logger.info(f"Sent list of {total} names to chat {event.chat_id}")
    except Exception as e:
        logger.error(f"Error sending shay list: {e}", exc_info=True)
        await event.reply("Произошла ошибка при получении списка имен.")

async def get_daily_shay():
    """Получение имени на сегодня"""
    try:
        today = datetime.now().date()

        if today == STATE.get('current_date') and STATE['current_shay_name']:
            return (
                f"__Я уже говорил__.\n\n**{STATE['current_shay_name']}** - сегодня величайшего зовут так.",
                STATE['current_shay_name']
            )

        STATE['current_date'] = today
        shay_id = select_random_shay_id()
        STATE['current_shay_name'] = db_query(
            'SELECT name FROM shays WHERE id = ?',
            (shay_id,),
            fetch=True
        )[0]

        db_query(
            'UPDATE shays SET stats = stats + 1 WHERE id = ?',
            (shay_id,)
        )

        response = (
            f"**Вот это да!**\nСегодня {CONFIG['DEFAULT_NAME']} и есть {CONFIG['DEFAULT_NAME']}. Удивительно."
            if shay_id == 1 else
            f"**{STATE['current_shay_name']}** - сегодня величайшего зовут так."
        )

        logger.info(f"Selected new shay for today: {STATE['current_shay_name']} (ID: {shay_id})")
        return response, STATE['current_shay_name']
    except Exception as e:
        logger.error(f"Error getting daily shay: {e}", exc_info=True)
        return "Произошла ошибка при выборе имени на сегодня.", None

async def reset_daily_shay():
    """Сброс ежедневного выбора в 00:00"""
    while True:
        now = datetime.now()
        next_day = now.replace(hour=4, minute=0, second=0) + timedelta(days=1)
        wait_seconds = (next_day - now).total_seconds()

        logger.info(f"Waiting {wait_seconds:.0f} seconds until midnight reset")
        await asyncio.sleep(wait_seconds)

        STATE['current_date'] = None
        STATE['current_shay_name'] = None
        logger.info("Daily shay reset at midnight")


async def send_daily_message(client):
    """Ежедневная отправка сообщения в указанное время"""
    while True:
        try:
            now = datetime.now()
            target_time = datetime.combine(now.date(), CONFIG['TARGET_TIME'])

            if now >= target_time:
                target_time = datetime.combine(
                    now.date() + timedelta(days=1),
                    CONFIG['TARGET_TIME']
                )

            wait_seconds = (target_time - now).total_seconds()
            logger.info(f"Waiting {wait_seconds:.0f} seconds until next message at {target_time}")
            await asyncio.sleep(wait_seconds)

            # >>> Do not send on weekend <<<
            today = datetime.now().weekday()
            if today in (5, 6):  # 5 = суббота, 6 = воскресенье
                logger.info("It is weekend, skipping message.")
                continue

            response, shay_name = await get_daily_shay()
            if not shay_name:
                logger.error("Failed to get shay name for daily message")
                continue

            if CONFIG['TARGET_CHAT_ID']:
                await client.send_message(CONFIG['TARGET_CHAT_ID'], response, parse_mode='md')
                logger.info(f"Sent daily message to target chat {CONFIG['TARGET_CHAT_ID']}")
            else:
                dialogs = await client.get_dialogs()
                for dialog in dialogs:
                    if dialog.is_group:
                        try:
                            await client.send_message(dialog.id, response, parse_mode='md')
                            logger.info(f"Sent daily message to group {dialog.id}")
                        except Exception as e:
                            logger.warning(f"Failed to send to group {dialog.id}: {str(e)}")
        except Exception as e:
            logger.error(f"Error in daily message loop: {e}", exc_info=True)
            await asyncio.sleep(60)  # Wait before retrying

def select_random_shay_id():
    """Выбор случайного ID исключая последние 5 использованных (если возможно)"""
    try:
        min_id, max_id = db_query('SELECT MIN(id), MAX(id) FROM shays', fetch=True)
        available_ids = [id for id in range(min_id, max_id + 1)
                         if id not in STATE['last_shay_ids'] or len(STATE['last_shay_ids']) >= (max_id - min_id + 1)]

        if not available_ids:
            available_ids = range(min_id, max_id + 1)

        selected_id = random.choice(available_ids)

        # Обновление списка последних ID
        if selected_id not in STATE['last_shay_ids']:
            STATE['last_shay_ids'].append(selected_id)
            if len(STATE['last_shay_ids']) > 5:
                STATE['last_shay_ids'].pop(0)

        logger.debug(f"Selected random shay ID: {selected_id} (available: {len(available_ids)})")
        return selected_id
    except Exception as e:
        logger.error(f"Error selecting random shay ID: {e}", exc_info=True)
        return 1  # Fallback to default ID

async def add_shay(event):
    """Добавление нового имени с автоматической капитализацией и дедупликацией"""
    try:
        name = event.raw_text[5:].strip()

        if not name or len(name.split()) != 2:
            await event.reply("Некорректное имя. Имя должно состоять из двух слов.")
            logger.warning(f"Invalid name format from {event.sender_id}: {name}")
            return

        capitalized_name = ' '.join(word.capitalize() for word in name.split())
        normalized_name = normalize_name(capitalized_name)
        logger.info(f"Attempting to add new name from {event.sender_id}: {capitalized_name} (normalized: {normalized_name})")

        # Проверка на дубликаты по нормализованному имени
        existing = db_query(
            'SELECT name FROM shays WHERE normalized_name = ?',
            (normalized_name,),
            fetch=True
        )

        if existing:
            await event.reply(f"Такое имя уже существует: **{existing[0]}**", parse_mode='md')
            logger.warning(f"Duplicate name attempt from {event.sender_id}: {capitalized_name} (existing: {existing[0]})")
            return

        try:
            db_query(
                'INSERT INTO shays (name, normalized_name) VALUES (?, ?)',
                (capitalized_name, normalized_name)
            )
            await event.reply(f"Добавлено новое имя: **{capitalized_name}**!", parse_mode='md')
            logger.info(f"Successfully added new name: {capitalized_name}")
        except sqlite3.IntegrityError:
            existing_name = db_query(
                'SELECT name FROM shays WHERE normalized_name = ?',
                (normalized_name,),
                fetch=True
            )
            await event.reply(f"Такое имя уже существует: **{existing_name[0]}**", parse_mode='md')
            logger.warning(f"Late duplicate detection for name: {capitalized_name}")
    except Exception as e:
        logger.error(f"Error in add_shay from {event.sender_id}: {e}", exc_info=True)
        await event.reply("Произошла ошибка при добавлении имени.")

async def log_info(client):
    try:
        bot_info = await client.get_me()
        logger.info(f"Bot logged as {bot_info.first_name} (@{bot_info.username}, id: {bot_info.id})")
    except Exception as e:
        logger.error(f"Error fetching bot or target chat info: {e}", exc_info=True)

# Инициализация и запуск бота
def run_bot():
    try:
        logger.info("Starting bot initialization")
        init_db()
        client = TelegramClient('bot', CONFIG['API_ID'], CONFIG['API_HASH'])

        @client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            logger.info(f"Help command from {event.sender_id} in chat {event.chat_id}")
            await event.reply(
                f"Для того, чтобы узнать, кто сегодня {CONFIG['DEFAULT_NAME']} введите\n"
                "`/get`\n\nДля добавления новой вариации имени введите\n"
                f"`/add <имя> <отчетсво>`.\n\n"
                f"Автоматически каждый день в {CONFIG['TARGET_TIME'].strftime('%H:%M')} "
                "будет отправляться результат.",
                parse_mode='md'
            )

        @client.on(events.NewMessage(pattern='/get'))
        async def get_handler(event):
            logger.info(f"Get command from {event.sender_id} in chat {event.chat_id}")
            response, _ = await get_daily_shay()
            await event.reply(response, parse_mode='md')

        @client.on(events.NewMessage(pattern='/add'))
        async def add_handler(event):
            logger.info(f"Add command from {event.sender_id} in chat {event.chat_id}")
            await add_shay(event)

        @client.on(events.NewMessage(pattern='/db'))
        async def db_handler(event):
            logger.info(f"DB command from {event.sender_id} in chat {event.chat_id}")
            await send_shay_list(event)

        @client.on(events.NewMessage(pattern='/save'))
        async def save_handler(event):
            logger.info(f"Save command from {event.sender_id} in chat {event.chat_id}")
            response = await save_names_to_file()
            await event.reply(response, parse_mode='md')

        if CONFIG['TARGET_CHAT_ID']:
            client.loop.create_task(send_daily_message(client))

        async def start_client():
            logger.info("Bot starting...")
            await client.start(bot_token=CONFIG['TOKEN'])
            await log_info(client)
            await client.run_until_disconnected()

        client.loop.run_until_complete(start_client())
    except Exception as e:
        logger.critical(f"Fatal error in bot: {e}", exc_info=True)
        raise

if __name__ == '__main__':
    try:
        run_bot()
    except Exception as e:
        logger.critical(f"Bot crashed: {e}", exc_info=True)
        raise