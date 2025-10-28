#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram-бот для управления командой трейдеров
Использует python-telegram-bot версии 20+
"""

import sqlite3
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
import logging
from datetime import datetime, timedelta
import asyncio
import os

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота (замените на реальный токен)
TOKEN = "7080432982:AAEgzJx0Ac3wywbUc1uNpKR6-3HTjePOTZY"

# ID администратора
ADMIN_ID = 844012884

# Пути к изображениям
LOGO_PATH = "logo.png"
PROFILE_PATH = "profil.png"
PROFIT_PATH = "profit.png"

# Словарь для хранения пользователей, ожидающих ввода имени
waiting_for_name = {}

# Словарь для хранения текущего состояния пользователей (menu_state)
# Возможные значения: 'main_menu', 'stats_menu', 'rating_menu', 'bots_menu', 'team_menu', 'settings_menu', 'admin_menu', 'admin_teams_menu', 'admin_workers_menu', 'admin_action', 'waiting_worker_selection'
user_states = {}

# Словарь для хранения выбранного периода статистики
# Формат: {telegram_id: 'day'/'week'/'month'/'all'}
selected_period = {}

# Словарь для хранения выбранного типа рейтинга
# Формат: {telegram_id: 'workers'/'teams'}
rating_type = {}

# Словарь для хранения временных данных при работе админ-панели
# Формат: {telegram_id: {'action': '...', 'data': {...}}}
admin_temp_data = {}


def init_database():
    """
    Инициализация базы данных SQLite
    Создает все необходимые таблицы
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            name TEXT,
            role TEXT DEFAULT 'worker',
            team_id INTEGER,
            direction TEXT
        )
    ''')
    
    # Таблица команд
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            team_leader_id INTEGER,
            stats TEXT
        )
    ''')
    
    # Таблица прибыли
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            direction TEXT,
            amount REAL,
            date TEXT,
            comment TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Таблица ботов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            link TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")


def get_user_role(telegram_id):
    """
    Получить роль пользователя из базы данных
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        Роль пользователя или None, если пользователь не найден
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_user_id_by_telegram_id(telegram_id):
    """
    Получить внутренний ID пользователя из базы данных
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        Внутренний ID пользователя или None
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_user_team_id(telegram_id):
    """
    Получить ID команды пользователя
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        ID команды или None
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT team_id FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_user_by_telegram_id(telegram_id):
    """
    Проверить существование пользователя в базе данных
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        True, если пользователь существует, иначе False
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def register_user(telegram_id, name):
    """
    Зарегистрировать нового пользователя в базе данных
    
    Args:
        telegram_id: Telegram ID пользователя
        name: Имя пользователя
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Определить роль: admin для указанного ID, иначе worker
    role = 'admin' if telegram_id == ADMIN_ID else 'worker'
    
    cursor.execute(
        'INSERT INTO users (telegram_id, name, role, team_id, direction) VALUES (?, ?, ?, ?, ?)',
        (telegram_id, name, role, None, None)
    )
    conn.commit()
    conn.close()
    logger.info(f"Пользователь зарегистрирован: {telegram_id}, {name}, роль: {role}")


def get_stats_menu_keyboard(telegram_id):
    """
    Создать клавиатуру меню статистики
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        ReplyKeyboardMarkup с кнопками меню статистики
    """
    role = get_user_role(telegram_id)
    keyboard = [
        ['📅 День', '📅 Неделя'],
        ['📅 Месяц', '📅 Все время'],
        ['🛠 По направлениям', '🔄 Обновить'],
        ['⬅️ Назад']
    ]
    
    # Для тимлидеров добавить дополнительные кнопки
    if role in ['team_leader', 'admin']:
        keyboard.insert(3, ['📈 Статистика команды', '👤 Детализация по воркеру'])
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_worker_stats_by_period(user_id, period):
    """
    Получить статистику воркера за указанный период
    
    Args:
        user_id: Внутренний ID пользователя
        period: Период ('day', 'week', 'month', 'all')
        
    Returns:
        Словарь с суммами по направлениям
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Определить дату начала периода
    now = datetime.now()
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:  # all
        start_date = datetime.min
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    query = '''
        SELECT direction, SUM(amount) as total
        FROM profits
        WHERE user_id = ? AND date >= ?
        GROUP BY direction
    '''
    
    cursor.execute(query, (user_id, start_date_str))
    results = cursor.fetchall()
    conn.close()
    
    stats = {}
    total = 0
    for direction, amount in results:
        stats[direction] = amount
        total += amount
    
    stats['total'] = total
    return stats


def get_team_stats_by_period(team_id, period):
    """
    Получить статистику команды за указанный период
    
    Args:
        team_id: ID команды
        period: Период ('day', 'week', 'month', 'all')
        
    Returns:
        Словарь с суммами по воркерам
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Определить дату начала периода
    now = datetime.now()
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:  # all
        start_date = datetime.min
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    query = '''
        SELECT u.name, SUM(p.amount) as total
        FROM profits p
        JOIN users u ON p.user_id = u.id
        WHERE u.team_id = ? AND p.date >= ?
        GROUP BY u.id, u.name
        ORDER BY total DESC
    '''
    
    cursor.execute(query, (team_id, start_date_str))
    results = cursor.fetchall()
    conn.close()
    
    return results


def get_team_workers(team_id):
    """
    Получить список воркеров команды
    
    Args:
        team_id: ID команды
        
    Returns:
        Список кортежей (telegram_id, name)
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT telegram_id, name FROM users WHERE team_id = ?', (team_id,))
    results = cursor.fetchall()
    conn.close()
    return results


def get_worker_detailed_stats(user_id, period):
    """
    Получить детальную статистику воркера по направлениям
    
    Args:
        user_id: Внутренний ID пользователя
        period: Период
        
    Returns:
        Словарь с детальной статистикой
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Определить дату начала периода
    now = datetime.now()
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:
        start_date = datetime.min
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    query = '''
        SELECT direction, SUM(amount) as total, COUNT(*) as count
        FROM profits
        WHERE user_id = ? AND date >= ?
        GROUP BY direction
    '''
    
    cursor.execute(query, (user_id, start_date_str))
    results = cursor.fetchall()
    conn.close()
    
    return results


def get_main_menu_keyboard(telegram_id):
    """
    Создать клавиатуру главного меню в зависимости от роли пользователя
    
    Args:
        telegram_id: Telegram ID пользователя
        
    Returns:
        ReplyKeyboardMarkup с кнопками меню
    """
    # Базовые кнопки для всех пользователей
    keyboard = [
        ['📊 Моя статистика', '🏆 Рейтинг'],
        ['🤖 Боты', '👥 Моя команда'],
        ['⚙️ Настройки', '🏠 Главное меню'],
        ['❓ Справка']
    ]
    
    # Получить роль пользователя
    role = get_user_role(telegram_id)
    
    # Добавить кнопку админ-панели для тимлидеров и админов
    if role in ['team_leader', 'admin']:
        keyboard.append(['🛠 Админ-панель'])
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_rating_menu_keyboard():
    """
    Создать клавиатуру меню рейтинга
    
    Returns:
        ReplyKeyboardMarkup с кнопками меню рейтинга
    """
    keyboard = [
        ['👤 Воркеры', '👥 Команды'],
        ['📅 День', '📅 Неделя'],
        ['📅 Месяц', '📅 Все время'],
        ['⬅️ Назад']
    ]
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_workers_rating_by_period(period):
    """
    Получить рейтинг воркеров за указанный период
    
    Args:
        period: Период ('day', 'week', 'month', 'all')
        
    Returns:
        Список кортежей (name, total)
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Определить дату начала периода
    now = datetime.now()
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:  # all
        start_date = datetime.min
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    query = '''
        SELECT u.name, SUM(p.amount) as total
        FROM profits p
        JOIN users u ON p.user_id = u.id
        WHERE p.date >= ? AND u.role = 'worker'
        GROUP BY u.id, u.name
        ORDER BY total DESC
    '''
    
    cursor.execute(query, (start_date_str,))
    results = cursor.fetchall()
    conn.close()
    
    return results


def get_teams_rating_by_period(period):
    """
    Получить рейтинг команд за указанный период
    
    Args:
        period: Период ('day', 'week', 'month', 'all')
        
    Returns:
        Список кортежей (team_name, total)
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Определить дату начала периода
    now = datetime.now()
    if period == 'day':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == 'week':
        start_date = now - timedelta(days=7)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    else:  # all
        start_date = datetime.min
    
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    query = '''
        SELECT t.name, COALESCE(SUM(p.amount), 0) as total
        FROM teams t
        LEFT JOIN users u ON t.id = u.team_id
        LEFT JOIN profits p ON u.id = p.user_id AND p.date >= ?
        GROUP BY t.id, t.name
        HAVING total > 0
        ORDER BY total DESC
    '''
    
    cursor.execute(query, (start_date_str,))
    results = cursor.fetchall()
    conn.close()
    
    return results


def get_bots_from_database():
    """
    Получить список всех ботов из базы данных
    
    Returns:
        Список кортежей (name, description, link)
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, description, link FROM bots')
    results = cursor.fetchall()
    conn.close()
    return results


def get_bot_by_name(bot_name):
    """
    Получить информацию о боте по имени
    
    Args:
        bot_name: Название бота
        
    Returns:
        Кортеж (name, description, link) или None
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, description, link FROM bots WHERE name = ?', (bot_name,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_bots_menu_keyboard():
    """
    Создать клавиатуру со списком ботов
    
    Returns:
        ReplyKeyboardMarkup с кнопками ботов
    """
    bots = get_bots_from_database()
    
    if not bots:
        # Если ботов нет, показать только кнопку "Назад"
        keyboard = [['⬅️ Назад']]
    else:
        # Создать кнопки для каждого бота
        keyboard = []
        row = []
        for name, _, _ in bots:
            row.append(name)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append(['⬅️ Назад'])
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_team_info(team_id):
    """
    Получить информацию о команде
    
    Args:
        team_id: ID команды
        
    Returns:
        Кортеж (team_name, leader_id) или None
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, team_leader_id FROM teams WHERE id = ?', (team_id,))
    result = cursor.fetchone()
    conn.close()
    return result


def get_team_leader_name(leader_id):
    """
    Получить имя тимлидера по его ID
    
    Args:
        leader_id: ID тимлидера
        
    Returns:
        Имя тимлидера или None
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM users WHERE id = ?', (leader_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_team_total_stats(team_id):
    """
    Получить общую статистику команды за все время
    
    Args:
        team_id: ID команды
        
    Returns:
        Общая сумма профитов команды
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    query = '''
        SELECT COALESCE(SUM(p.amount), 0) as total
        FROM profits p
        JOIN users u ON p.user_id = u.id
        WHERE u.team_id = ?
    '''
    cursor.execute(query, (team_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0


def get_team_menu_keyboard():
    """
    Создать клавиатуру меню команды для тимлидеров
    
    Returns:
        ReplyKeyboardMarkup с кнопками меню команды
    """
    keyboard = [
        ['📊 Статистика команды', '👤 Список воркеров'],
        ['⬅️ Назад']
    ]
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_settings_menu_keyboard():
    """
    Создать клавиатуру меню настроек
    
    Returns:
        ReplyKeyboardMarkup с кнопками меню настроек
    """
    keyboard = [
        ['✏️ Выбрать направление'],
        ['⬅️ Назад']
    ]
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def update_user_direction(telegram_id, direction):
    """
    Обновить направление работы пользователя
    
    Args:
        telegram_id: Telegram ID пользователя
        direction: Название направления
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET direction = ? WHERE telegram_id = ?',
        (direction, telegram_id)
    )
    conn.commit()
    conn.close()
    logger.info(f"Направление обновлено для пользователя {telegram_id}: {direction}")


def get_settings_directions_keyboard():
    """
    Создать клавиатуру с направлениями из таблицы bots
    
    Returns:
        ReplyKeyboardMarkup с кнопками направлений
    """
    bots = get_bots_from_database()
    
    if not bots:
        # Если ботов нет, показать только кнопку "Назад"
        keyboard = [['⬅️ Назад']]
    else:
        # Создать кнопки для каждого направления (используем name бота как направление)
        keyboard = []
        row = []
        for name, _, _ in bots:
            row.append(name)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append(['⬅️ Назад'])
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_all_workers():
    """
    Получить список всех воркеров
    
    Returns:
        Список кортежей (name, telegram_id)
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name, telegram_id FROM users WHERE role = "worker"')
    results = cursor.fetchall()
    conn.close()
    return results


def get_all_teams():
    """
    Получить список всех команд
    
    Returns:
        Список кортежей (id, name)
    """
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM teams')
    results = cursor.fetchall()
    conn.close()
    return results


def create_profit(user_id, direction, amount, comment):
    """
    Создать запись профита в базе данных
    
    Args:
        user_id: ID пользователя
        direction: Направление
        amount: Сумма
        comment: Комментарий
        
    Returns:
        True если успешно
    """
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            'INSERT INTO profits (user_id, direction, amount, date, comment) VALUES (?, ?, ?, ?, ?)',
            (user_id, direction, amount, today, comment)
        )
        conn.commit()
        conn.close()
        logger.info(f"Профит добавлен: user_id={user_id}, direction={direction}, amount={amount}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении профита: {e}")
        return False


def create_team(team_name, leader_id):
    """
    Создать команду в базе данных
    
    Args:
        team_name: Название команды
        leader_id: ID тимлидера
        
    Returns:
        ID созданной команды или None
    """
    try:
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO teams (name, team_leader_id) VALUES (?, ?)',
            (team_name, leader_id)
        )
        conn.commit()
        team_id = cursor.lastrowid
        conn.close()
        logger.info(f"Команда создана: {team_name}, team_id={team_id}")
        return team_id
    except Exception as e:
        logger.error(f"Ошибка при создании команды: {e}")
        return None


async def start_handler(update, context):
    """
    Обработчик команды /start
    
    Проверяет регистрацию пользователя и запрашивает имя, если это новый пользователь
    """
    telegram_id = update.effective_user.id
    
    # Проверить, есть ли пользователь в базе
    if get_user_by_telegram_id(telegram_id):
        # Пользователь уже зарегистрирован
        user_states[telegram_id] = 'main_menu'
        keyboard = get_main_menu_keyboard(telegram_id)
        await send_image_with_text(
            update, context, LOGO_PATH,
            "Добро пожаловать обратно!",
            "<b>Добро пожаловать обратно!</b>\n\nВыберите действие из меню ниже."
        )
        # Отправить главное меню отдельно
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=keyboard
        )
    else:
        # Новый пользователь - запросить имя
        await send_image_with_text(
            update, context, LOGO_PATH,
            "Добро пожаловать! Введите ваше имя для регистрации.",
            "<b>Добро пожаловать!</b>\n\nВведите ваше имя для регистрации."
        )
        # Добавить пользователя в список ожидающих ввода имени
        waiting_for_name[telegram_id] = True


async def help_handler(update, context):
    """
    Обработчик команды /help
    
    Выводит краткую инструкцию по использованию бота
    """
    message = """Используйте кнопки для навигации.

Основные функции:
📊 Моя статистика - просмотр ваших профитов
🏆 Рейтинг - рейтинги воркеров и команд
🤖 Боты - список доступных ботов
👥 Моя команда - информация о команде
⚙️ Настройки - выбор направления работы

Для админов:
🛠 Админ-панель - управление системой
📊 Глобальная статистика - статистика по всем данным

Для команды:
/start - перезапуск бота
/help - эта справка"""
    
    await send_image_with_text(
        update, context, LOGO_PATH,
        message,
        "<b>Справка по использованию бота</b>\n\n" + message
    )


def format_period_name(period):
    """Преобразовать код периода в читаемое название"""
    periods = {
        'day': 'день',
        'week': 'неделю',
        'month': 'месяц',
        'all': 'все время'
    }
    return periods.get(period, period)


async def send_image_with_text(update, context, image_path, text, caption=None):
    """
    Отправить изображение с текстом в одном сообщении
    
    Args:
        update: Update объект
        context: Context объект
        image_path: Путь к изображению
        text: Текст сообщения
        caption: Подпись к изображению (опционально)
    """
    if os.path.exists(image_path):
        try:
            await update.message.reply_photo(
                photo=open(image_path, 'rb'),
                caption=caption or text,
                parse_mode='HTML'
            )
            # Если текст не совпадает с подписью, отправим его отдельно
            if caption and caption != text:
                await update.message.reply_text(text)
        except Exception as e:
            logger.error(f"Ошибка при отправке изображения {image_path}: {e}")
            # Если не удалось отправить изображение, отправим только текст
            await update.message.reply_text(text)
    else:
        # Если изображение не найдено, отправим только текст
        await update.message.reply_text(text)


async def text_handler(update, context):
    """
    Обработчик текстовых сообщений
    
    Обрабатывает ввод имени для регистрации и нажатия кнопок меню
    """
    telegram_id = update.effective_user.id
    text = update.message.text
    
    # Проверить, ожидает ли бот ввода имени
    if telegram_id in waiting_for_name:
        name = update.message.text
        
        # Зарегистрировать пользователя
        register_user(telegram_id, name)
        
        # Удалить из списка ожидающих
        del waiting_for_name[telegram_id]
        
        # Получить роль пользователя для сообщения
        role = get_user_role(telegram_id)
        role_name = 'администратор' if role == 'admin' else 'воркер'
        
        # Установить состояние главного меню
        user_states[telegram_id] = 'main_menu'
        
        # Показать главное меню
        keyboard = get_main_menu_keyboard(telegram_id)
        await update.message.reply_text(
            f"Спасибо, {name}! Вы успешно зарегистрированы как {role_name}.",
            reply_markup=keyboard
        )
        return
    
    # Проверить состояние пользователя
    current_state = user_states.get(telegram_id, 'main_menu')
    
    # Обработка кнопки "📊 Моя статистика"
    if text == '📊 Моя статистика':
        keyboard = get_stats_menu_keyboard(telegram_id)
        user_states[telegram_id] = 'stats_menu'
        await update.message.reply_text(
            "Выберите период для отображения статистики:",
            reply_markup=keyboard
        )
        return
    
    # Обработка кнопок периода статистики
    if current_state == 'stats_menu' and text in ['📅 День', '📅 Неделя', '📅 Месяц', '📅 Все время']:
        period_map = {
            '📅 День': 'day',
            '📅 Неделя': 'week',
            '📅 Месяц': 'month',
            '📅 Все время': 'all'
        }
        period = period_map[text]
        selected_period[telegram_id] = period
        
        role = get_user_role(telegram_id)
        user_id = get_user_id_by_telegram_id(telegram_id)
        
        if role == 'worker':
            # Статистика для воркера
            stats = get_worker_stats_by_period(user_id, period)
            period_name = format_period_name(period)
            
            if stats['total'] == 0:
                message = f"Ваши профиты за {period_name}: нет данных."
            else:
                message = f"Ваши профиты за {period_name}:\n\n"
                for direction, amount in stats.items():
                    if direction != 'total':
                        message += f"{direction}: ${amount:.2f}\n"
                message += f"\nВсего: ${stats['total']:.2f}"
            
            await send_image_with_text(
                update, context, PROFILE_PATH,
                message,
                f"<b>📊 Статистика за {period_name}</b>\n\n" + message
            )
        
        elif role in ['team_leader', 'admin']:
            # Статистика команды для тимлидера
            team_id = get_user_team_id(telegram_id)
            if not team_id:
                await update.message.reply_text("У вас нет команды.")
                return
            
            team_stats = get_team_stats_by_period(team_id, period)
            period_name = format_period_name(period)
            
            if not team_stats:
                message = f"Статистика команды за {period_name}: нет данных."
            else:
                total_sum = sum(amount for _, amount in team_stats)
                message = f"Статистика команды за {period_name}:\n\nВсего: ${total_sum:.2f}\n\n"
                for name, amount in team_stats:
                    message += f"{name}: ${amount:.2f}\n"
            
            await send_image_with_text(
                update, context, PROFILE_PATH,
                message,
                f"<b>👥 Статистика команды за {period_name}</b>\n\n" + message
            )
        
        return
    
    # Обработка кнопки "🛠 По направлениям"
    if current_state == 'stats_menu' and text == '🛠 По направлениям':
        role = get_user_role(telegram_id)
        user_id = get_user_id_by_telegram_id(telegram_id)
        
        if role == 'worker':
            # Детальная статистика для воркера
            period = selected_period.get(telegram_id, 'all')
            detailed_stats = get_worker_detailed_stats(user_id, period)
            period_name = format_period_name(period)
            
            if not detailed_stats:
                message = f"Детализация по направлениям за {period_name}: нет данных."
            else:
                message = f"Детализация по направлениям за {period_name}:\n\n"
                total_sum = 0
                for direction, amount, count in detailed_stats:
                    message += f"{direction}:\n  Сумма: ${amount:.2f}\n  Записей: {count}\n\n"
                    total_sum += amount
                message += f"Всего: ${total_sum:.2f}"
            
            await send_image_with_text(
                update, context, PROFILE_PATH,
                message,
                f"<b>🛠 Детализация по направлениям за {period_name}</b>\n\n" + message
            )
        
        return
    
    # Обработка кнопки "👤 Детализация по воркеру" (для тимлидеров)
    if current_state == 'stats_menu' and text == '👤 Детализация по воркеру':
        team_id = get_user_team_id(telegram_id)
        if not team_id:
            await update.message.reply_text("У вас нет команды.")
            return
        
        workers = get_team_workers(team_id)
        if not workers:
            await update.message.reply_text("В вашей команде нет воркеров.")
            return
        
        # Создать клавиатуру с именами воркеров
        keyboard_buttons = []
        for worker_tg_id, worker_name in workers:
            keyboard_buttons.append([f'👤 {worker_name}'])
        keyboard_buttons.append(['⬅️ Назад'])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard_buttons,
            resize_keyboard=True,
            one_time_keyboard=False
        )
        
        user_states[telegram_id] = 'waiting_worker_selection'
        await update.message.reply_text(
            "Выберите воркера для детализации:",
            reply_markup=keyboard
        )
        return
    
    # Обработка выбора воркера для детализации
    if current_state == 'waiting_worker_selection' and text.startswith('👤'):
        # Извлечь имя воркера
        worker_name = text.replace('👤 ', '')
        team_id = get_user_team_id(telegram_id)
        
        # Получить telegram_id воркера по имени
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE name = ? AND team_id = ?', (worker_name, team_id))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            worker_id = result[0]
            period = selected_period.get(telegram_id, 'all')
            period_name = format_period_name(period)
            
            # Получить детальную статистику воркера
            detailed_stats = get_worker_detailed_stats(worker_id, period)
            
            if not detailed_stats:
                message = f"Детализация по воркеру {worker_name} за {period_name}: нет данных."
            else:
                message = f"Детализация по воркеру {worker_name} за {period_name}:\n\n"
                total_sum = 0
                for direction, amount, count in detailed_stats:
                    message += f"{direction}:\n  Сумма: ${amount:.2f}\n  Записей: {count}\n\n"
                    total_sum += amount
                message += f"Всего: ${total_sum:.2f}"
            
            # Вернуться в меню статистики
            user_states[telegram_id] = 'stats_menu'
            keyboard = get_stats_menu_keyboard(telegram_id)
            await send_image_with_text(
                update, context, PROFILE_PATH,
                message,
                f"<b>👤 Детализация по воркеру {worker_name} за {period_name}</b>\n\n" + message
            )
        else:
            await update.message.reply_text("Воркер не найден.")
        return
    
    # Обработка кнопки "📈 Статистика команды" (для тимлидеров)
    if current_state == 'stats_menu' and text == '📈 Статистика команды':
        team_id = get_user_team_id(telegram_id)
        if not team_id:
            await update.message.reply_text("У вас нет команды.")
            return
        
        # Показать статистику за последний выбранный период или за все время
        period = selected_period.get(telegram_id, 'all')
        period_name = format_period_name(period)
        
        team_stats = get_team_stats_by_period(team_id, period)
        
        if not team_stats:
            message = f"Статистика команды за {period_name}: нет данных."
        else:
            total_sum = sum(amount for _, amount in team_stats)
            message = f"Статистика команды за {period_name}:\n\nВсего: ${total_sum:.2f}\n\n"
            for name, amount in team_stats:
                message += f"{name}: ${amount:.2f}\n"
        
        await send_image_with_text(
            update, context, PROFILE_PATH,
            message,
            f"<b>👥 Статистика команды за {period_name}</b>\n\n" + message
        )
        return
    
    # Обработка кнопки "🔄 Обновить"
    if current_state == 'stats_menu' and text == '🔄 Обновить':
        role = get_user_role(telegram_id)
        user_id = get_user_id_by_telegram_id(telegram_id)
        period = selected_period.get(telegram_id, 'all')
        period_name = format_period_name(period)
        
        if role == 'worker':
            stats = get_worker_stats_by_period(user_id, period)
            
            if stats['total'] == 0:
                message = f"Ваши профиты за {period_name}: нет данных."
            else:
                message = f"Ваши профиты за {period_name}:\n\n"
                for direction, amount in stats.items():
                    if direction != 'total':
                        message += f"{direction}: ${amount:.2f}\n"
                message += f"\nВсего: ${stats['total']:.2f}"
            
            await send_image_with_text(
                update, context, PROFILE_PATH,
                message,
                f"<b>🔄 Обновление статистики за {period_name}</b>\n\n" + message
            )
        
        elif role in ['team_leader', 'admin']:
            team_id = get_user_team_id(telegram_id)
            if not team_id:
                await update.message.reply_text("У вас нет команды.")
                return
            
            team_stats = get_team_stats_by_period(team_id, period)
            
            if not team_stats:
                message = f"Статистика команды за {period_name}: нет данных."
            else:
                total_sum = sum(amount for _, amount in team_stats)
                message = f"Статистика команды за {period_name}:\n\nВсего: ${total_sum:.2f}\n\n"
                for name, amount in team_stats:
                    message += f"{name}: ${amount:.2f}\n"
            
            await send_image_with_text(
                update, context, PROFILE_PATH,
                message,
                f"<b>🔄 Обновление статистики команды за {period_name}</b>\n\n" + message
            )
        
        return
    
    # Обработка кнопки "🏆 Рейтинг"
    if text == '🏆 Рейтинг':
        keyboard = get_rating_menu_keyboard()
        user_states[telegram_id] = 'rating_menu'
        await update.message.reply_text(
            "Выберите тип рейтинга и период:",
            reply_markup=keyboard
        )
        return
    
    # Обработка кнопки "👤 Воркеры" в меню рейтинга
    if current_state == 'rating_menu' and text == '👤 Воркеры':
        rating_type[telegram_id] = 'workers'
        # Показать рейтинг за последний выбранный период или за все время
        period = selected_period.get(telegram_id, 'all')
        period_name = format_period_name(period)
        
        rating = get_workers_rating_by_period(period)
        
        if not rating:
            message = f"Рейтинг воркеров за {period_name}: нет данных."
        else:
            message = f"🏆 Рейтинг воркеров за {period_name}:\n\n"
            for i, (name, total) in enumerate(rating, 1):
                message += f"{i}. {name}: ${total:.2f}\n"
        
        await send_image_with_text(
            update, context, PROFILE_PATH,
            message,
            f"<b>🏆 Рейтинг воркеров за {period_name}</b>\n\n" + message
        )
        return
    
    # Обработка кнопки "👥 Команды" в меню рейтинга
    if current_state == 'rating_menu' and text == '👥 Команды':
        rating_type[telegram_id] = 'teams'
        # Показать рейтинг за последний выбранный период или за все время
        period = selected_period.get(telegram_id, 'all')
        period_name = format_period_name(period)
        
        rating = get_teams_rating_by_period(period)
        
        if not rating:
            message = f"Рейтинг команд за {period_name}: нет данных."
        else:
            message = f"🏆 Рейтинг команд за {period_name}:\n\n"
            for i, (team_name, total) in enumerate(rating, 1):
                message += f"{i}. {team_name}: ${total:.2f}\n"
        
        await send_image_with_text(
            update, context, PROFILE_PATH,
            message,
            f"<b>🏆 Рейтинг команд за {period_name}</b>\n\n" + message
        )
        return
    
    # Обработка кнопок периода в меню рейтинга
    if current_state == 'rating_menu' and text in ['📅 День', '📅 Неделя', '📅 Месяц', '📅 Все время']:
        period_map = {
            '📅 День': 'day',
            '📅 Неделя': 'week',
            '📅 Месяц': 'month',
            '📅 Все время': 'all'
        }
        period = period_map[text]
        selected_period[telegram_id] = period
        period_name = format_period_name(period)
        
        # Получить тип рейтинга
        rtype = rating_type.get(telegram_id, 'workers')
        
        message = "Неизвестная ошибка"
        
        if rtype == 'workers':
            rating = get_workers_rating_by_period(period)
            
            if not rating:
                message = f"Рейтинг воркеров за {period_name}: нет данных."
            else:
                message = f"🏆 Рейтинг воркеров за {period_name}:\n\n"
                for i, (name, total) in enumerate(rating, 1):
                    message += f"{i}. {name}: ${total:.2f}\n"
        
        elif rtype == 'teams':
            rating = get_teams_rating_by_period(period)
            
            if not rating:
                message = f"Рейтинг команд за {period_name}: нет данных."
            else:
                message = f"🏆 Рейтинг команд за {period_name}:\n\n"
                for i, (team_name, total) in enumerate(rating, 1):
                    message += f"{i}. {team_name}: ${total:.2f}\n"
        
        await send_image_with_text(
            update, context, PROFILE_PATH,
            message,
            f"<b>🏆 Рейтинг за {period_name}</b>\n\n" + message
        )
        return
    
    # Обработка кнопки "🤖 Боты"
    if text == '🤖 Боты':
        bots = get_bots_from_database()
        
        if not bots:
            await update.message.reply_text(
                "В базе пока нет доступных ботов.",
                reply_markup=get_bots_menu_keyboard()
            )
        else:
            keyboard = get_bots_menu_keyboard()
            user_states[telegram_id] = 'bots_menu'
            await update.message.reply_text(
                "Выберите бота:",
                reply_markup=keyboard
            )
        return
    
    # Обработка выбора бота в меню ботов
    if current_state == 'bots_menu':
        # Проверить, не является ли это кнопка "Назад"
        if text == '⬅️ Назад':
            user_states[telegram_id] = 'main_menu'
            keyboard = get_main_menu_keyboard(telegram_id)
            await update.message.reply_text(
                "Главное меню:",
                reply_markup=keyboard
            )
            return
        
        # Получить информацию о выбранном боте
        bot_info = get_bot_by_name(text)
        
        if bot_info:
            name, description, link = bot_info
            message = f"Бот: {name}\nОписание: {description or 'Нет описания'}\nСсылка: {link or 'Нет ссылки'}"
            await update.message.reply_text(message)
        else:
            await update.message.reply_text("Бот не найден.")
        return
    
    # Обработка кнопки "👥 Моя команда"
    if text == '👥 Моя команда':
        team_id = get_user_team_id(telegram_id)
        
        if not team_id:
            await update.message.reply_text("Вы не состоите в команде.")
            return
        
        role = get_user_role(telegram_id)
        
        if role == 'worker':
            # Для воркеров - показать информацию о команде и тимлидере
            team_info = get_team_info(team_id)
            
            if team_info:
                team_name, leader_id = team_info
                leader_name = get_team_leader_name(leader_id)
                
                if leader_name:
                    message = f"Ваша команда: {team_name}\nТимлидер: {leader_name}"
                else:
                    message = f"Ваша команда: {team_name}\nТимлидер: не назначен"
            else:
                message = "Информация о команде не найдена."
            
            await update.message.reply_text(message)
        
        elif role in ['team_leader', 'admin']:
            # Для тимлидеров - показать подменю
            team_info = get_team_info(team_id)
            total_stats = get_team_total_stats(team_id)
            workers = get_team_workers(team_id)
            
            if team_info:
                team_name, _ = team_info
                workers_names = [name for _, name in workers] if workers else []
                workers_str = ', '.join(workers_names) if workers_names else "нет воркеров"
                
                message = f"Команда: {team_name}\nСтатистика: ${total_stats:.2f}\nВоркеры: {workers_str}"
                await update.message.reply_text(message)
            
            keyboard = get_team_menu_keyboard()
            user_states[telegram_id] = 'team_menu'
            await update.message.reply_text("Выберите действие:", reply_markup=keyboard)
        
        return
    
    # Обработка меню команды для тимлидеров
    if current_state == 'team_menu':
        if text == '📊 Статистика команды':
            team_id = get_user_team_id(telegram_id)
            team_info = get_team_info(team_id)
            total_stats = get_team_total_stats(team_id)
            
            if team_info:
                team_name, _ = team_info
                message = f"📊 Статистика команды '{team_name}':\n\nОбщая сумма: ${total_stats:.2f}"
            else:
                message = "Информация о команде не найдена."
            
            await update.message.reply_text(message)
            return
        
        elif text == '👤 Список воркеров':
            team_id = get_user_team_id(telegram_id)
            workers = get_team_workers(team_id)
            
            if not workers:
                await update.message.reply_text("В команде нет воркеров.")
                return
            
            # Создать клавиатуру с именами воркеров
            keyboard_buttons = []
            for worker_tg_id, worker_name in workers:
                keyboard_buttons.append([f'👤 {worker_name}'])
            keyboard_buttons.append(['⬅️ Назад'])
            
            keyboard = ReplyKeyboardMarkup(
                keyboard_buttons,
                resize_keyboard=True,
                one_time_keyboard=False
            )
            
            user_states[telegram_id] = 'waiting_worker_selection'
            await update.message.reply_text(
                "Выберите воркера:",
                reply_markup=keyboard
            )
            return
        
        elif text == '⬅️ Назад':
            user_states[telegram_id] = 'main_menu'
            keyboard = get_main_menu_keyboard(telegram_id)
            await update.message.reply_text(
                "Главное меню:",
                reply_markup=keyboard
            )
            return
    
    # Обработка кнопки "⚙️ Настройки"
    if text == '⚙️ Настройки':
        keyboard = get_settings_menu_keyboard()
        user_states[telegram_id] = 'settings_menu'
        await update.message.reply_text(
            "Настройки:",
            reply_markup=keyboard
        )
        return
    
    # Обработка меню настроек
    if current_state == 'settings_menu':
        if text == '✏️ Выбрать направление':
            # Показать список направлений из таблицы bots
            bots = get_bots_from_database()
            
            if not bots:
                await update.message.reply_text("Нет доступных направлений.")
                return
            
            keyboard = get_settings_directions_keyboard()
            user_states[telegram_id] = 'waiting_direction_selection'
            await update.message.reply_text(
                "Выберите направление:",
                reply_markup=keyboard
            )
            return
        
        elif text == '⬅️ Назад':
            user_states[telegram_id] = 'main_menu'
            keyboard = get_main_menu_keyboard(telegram_id)
            await update.message.reply_text(
                "Главное меню:",
                reply_markup=keyboard
            )
            return
    
    # Обработка выбора направления
    if user_states.get(telegram_id) == 'waiting_direction_selection':
        if text == '⬅️ Назад':
            # Вернуться в меню настроек
            user_states[telegram_id] = 'settings_menu'
            keyboard = get_settings_menu_keyboard()
            await update.message.reply_text(
                "Настройки:",
                reply_markup=keyboard
            )
            return
        
        # Обновить направление пользователя
        direction = text
        bot_info = get_bot_by_name(direction)
        
        if bot_info:
            # Направление существует в таблице bots
            update_user_direction(telegram_id, direction)
            message = f"Вы выбрали направление: {direction}."
            
            # Вернуться в главное меню
            user_states[telegram_id] = 'main_menu'
            keyboard = get_main_menu_keyboard(telegram_id)
            await update.message.reply_text(message, reply_markup=keyboard)
        else:
            await update.message.reply_text("Направление не найдено.")
        
        return
    
    # Обработка кнопки "⬅️ Назад"
    if text == '⬅️ Назад' or text == '🏠 Главное меню':
        user_states[telegram_id] = 'main_menu'
        keyboard = get_main_menu_keyboard(telegram_id)
        await update.message.reply_text(
            "Главное меню:",
            reply_markup=keyboard
        )
        return
    
    # Обработка кнопки "🛠 Админ-панель"
    if text == '🛠 Админ-панель':
        role = get_user_role(telegram_id)
        if role != 'admin':
            await update.message.reply_text("Доступ запрещен.")
            return
        
        keyboard = [
            ['👥 Управление командами', '👤 Управление воркерами'],
            ['💰 Начислить профит', '📊 Глобальная статистика'],
            ['⬅️ Назад']
        ]
        keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        user_states[telegram_id] = 'admin_menu'
        await update.message.reply_text("Админ-панель:", reply_markup=keyboard)
        return
    
    # Обработка меню админ-панели
    if current_state == 'admin_menu':
        if text == '⬅️ Назад':
            user_states[telegram_id] = 'main_menu'
            keyboard = get_main_menu_keyboard(telegram_id)
            await update.message.reply_text("Главное меню:", reply_markup=keyboard)
            return
        elif text == '📊 Глобальная статистика':
            # Простая глобальная статистика
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute('SELECT COUNT(*) FROM users WHERE role = "worker"')
            workers_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM teams')
            teams_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM profits')
            profits_count = cursor.fetchone()[0]
            
            cursor.execute('SELECT SUM(amount) FROM profits')
            total_profit = cursor.fetchone()[0] or 0
            conn.close()
            
            message = f"📊 Глобальная статистика:\n\n"
            message += f"Воркеров: {workers_count}\n"
            message += f"Команд: {teams_count}\n"
            message += f"Записей профита: {profits_count}\n"
            message += f"Общий профит: ${total_profit:.2f}"
            
            await update.message.reply_text(message)
            return
        elif text == '💰 Начислить профит':
            # Показать список воркеров
            workers = get_all_workers()
            if not workers:
                await update.message.reply_text("Нет зарегистрированных воркеров.")
                return
            
            keyboard_buttons = []
            for name, _ in workers:
                keyboard_buttons.append([f'👤 {name}'])
            keyboard_buttons.append(['⬅️ Назад'])
            keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
            
            admin_temp_data[telegram_id] = {'action': 'add_profit', 'step': 'worker'}
            user_states[telegram_id] = 'admin_action'
            await update.message.reply_text("Выберите воркера:", reply_markup=keyboard)
            return
        elif text == '👥 Управление командами':
            keyboard = [
                ['➕ Создать команду', '✏️ Редактировать команду'],
                ['⬅️ Назад']
            ]
            keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
            user_states[telegram_id] = 'admin_teams_menu'
            await update.message.reply_text("Управление командами:", reply_markup=keyboard)
            return
        elif text == '👤 Управление воркерами':
            keyboard = [
                ['➕ Добавить воркера', '❌ Удалить воркера'],
                ['🔄 Переместить воркера', '⬅️ Назад']
            ]
            keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
            user_states[telegram_id] = 'admin_workers_menu'
            await update.message.reply_text("Управление воркерами:", reply_markup=keyboard)
            return
    
    # Обработка подменю "Управление командами"
    if current_state == 'admin_teams_menu':
        if text == '⬅️ Назад':
            keyboard = [
                ['👥 Управление командами', '👤 Управление воркерами'],
                ['💰 Начислить профит', '📊 Глобальная статистика'],
                ['⬅️ Назад']
            ]
            keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
            user_states[telegram_id] = 'admin_menu'
            await update.message.reply_text("Админ-панель:", reply_markup=keyboard)
            return
        elif text == '➕ Создать команду':
            admin_temp_data[telegram_id] = {'action': 'create_team', 'step': 'name'}
            user_states[telegram_id] = 'admin_action'
            await update.message.reply_text("Введите название команды:", reply_markup=ReplyKeyboardRemove())
            return
        elif text == '✏️ Редактировать команду':
            teams = get_all_teams()
            if not teams:
                await update.message.reply_text("Нет команд для редактирования.")
                return
            
            keyboard_buttons = []
            for team_id, team_name in teams:
                keyboard_buttons.append([f'👥 {team_name}'])
            keyboard_buttons.append(['⬅️ Назад'])
            keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
            
            admin_temp_data[telegram_id] = {'action': 'edit_team', 'step': 'select'}
            user_states[telegram_id] = 'admin_action'
            await update.message.reply_text("Выберите команду для редактирования:", reply_markup=keyboard)
            return
    
    # Обработка подменю "Управление воркерами"
    if current_state == 'admin_workers_menu':
        if text == '⬅️ Назад':
            keyboard = [
                ['👥 Управление командами', '👤 Управление воркерами'],
                ['💰 Начислить профит', '📊 Глобальная статистика'],
                ['⬅️ Назад']
            ]
            keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
            user_states[telegram_id] = 'admin_menu'
            await update.message.reply_text("Админ-панель:", reply_markup=keyboard)
            return
        elif text == '➕ Добавить воркера':
            admin_temp_data[telegram_id] = {'action': 'add_worker', 'step': 'name'}
            user_states[telegram_id] = 'admin_action'
            await update.message.reply_text("Введите имя воркера:", reply_markup=ReplyKeyboardRemove())
            return
        elif text == '❌ Удалить воркера':
            workers = get_all_workers()
            if not workers:
                await update.message.reply_text("Нет зарегистрированных воркеров.")
                return
            
            keyboard_buttons = []
            for name, _ in workers:
                keyboard_buttons.append([f'👤 {name}'])
            keyboard_buttons.append(['⬅️ Назад'])
            keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
            
            admin_temp_data[telegram_id] = {'action': 'delete_worker', 'step': 'select'}
            user_states[telegram_id] = 'admin_action'
            await update.message.reply_text("Выберите воркера для удаления:", reply_markup=keyboard)
            return
        elif text == '🔄 Переместить воркера':
            workers = get_all_workers()
            if not workers:
                await update.message.reply_text("Нет зарегистрированных воркеров.")
                return
            
            keyboard_buttons = []
            for name, _ in workers:
                keyboard_buttons.append([f'👤 {name}'])
            keyboard_buttons.append(['⬅️ Назад'])
            keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
            
            admin_temp_data[telegram_id] = {'action': 'move_worker', 'step': 'select_worker'}
            user_states[telegram_id] = 'admin_action'
            await update.message.reply_text("Выберите воркера для перемещения:", reply_markup=keyboard)
            return
    
    # Обработка действий админ-панели (начисление профита, создание команды и т.д.)
    if current_state == 'admin_action':
        temp_data = admin_temp_data.get(telegram_id, {})
        action = temp_data.get('action')
        step = temp_data.get('step')
        
        if text == '⬅️ Назад':
            # Возврат в админ-меню
            keyboard = [
                ['👥 Управление командами', '👤 Управление воркерами'],
                ['💰 Начислить профит', '📊 Глобальная статистика'],
                ['⬅️ Назад']
            ]
            keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
            user_states[telegram_id] = 'admin_menu'
            if telegram_id in admin_temp_data:
                del admin_temp_data[telegram_id]
            await update.message.reply_text("Админ-панель:", reply_markup=keyboard)
            return
        
        if action == 'add_profit' and step == 'worker':
            if text.startswith('👤'):
                worker_name = text.replace('👤 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id, telegram_id FROM users WHERE name = ? AND role = "worker"', (worker_name,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    worker_id, worker_tg_id = result
                    admin_temp_data[telegram_id] = {'action': 'add_profit', 'step': 'direction', 'worker_id': worker_id, 'worker_tg_id': worker_tg_id, 'worker_name': worker_name}
                    
                    # Показать направления
                    bots = get_bots_from_database()
                    if not bots:
                        await update.message.reply_text("Нет доступных направлений. Добавьте боты в базу данных.")
                        return
                    
                    keyboard_buttons = []
                    for name, _, _ in bots:
                        keyboard_buttons.append([name])
                    keyboard_buttons.append(['⬅️ Назад'])
                    keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
                    await update.message.reply_text("Выберите направление:", reply_markup=keyboard)
                else:
                    await update.message.reply_text("Воркер не найден.")
            return
        
        elif action == 'add_profit' and step == 'direction':
            direction = text
            bot_info = get_bot_by_name(direction)
            
            if bot_info:
                admin_temp_data[telegram_id]['direction'] = direction
                admin_temp_data[telegram_id]['step'] = 'amount'
                await update.message.reply_text("Введите сумму профита (только число, например: 100.50):")
                return
            else:
                await update.message.reply_text("Направление не найдено.")
            return
        
        elif action == 'add_profit' and step == 'amount':
            try:
                amount = float(text)
                admin_temp_data[telegram_id]['amount'] = amount
                admin_temp_data[telegram_id]['step'] = 'comment'
                await update.message.reply_text("Введите комментарий (или отправьте '-' чтобы пропустить):")
                return
            except ValueError:
                await update.message.reply_text("Неверный формат суммы. Введите число (например: 100.50)")
                return
        
        elif action == 'add_profit' and step == 'comment':
            comment = text if text != '-' else ""
            admin_temp_data[telegram_id]['comment'] = comment
            
            # Сохранить профит
            worker_id = admin_temp_data[telegram_id]['worker_id']
            direction = admin_temp_data[telegram_id]['direction']
            amount = admin_temp_data[telegram_id]['amount']
            worker_tg_id = admin_temp_data[telegram_id]['worker_tg_id']
            worker_name = admin_temp_data[telegram_id]['worker_name']
            
            if create_profit(worker_id, direction, amount, comment):
                # Отправить уведомление воркеру
                try:
                    notification = f"Вам начислен профит: ${amount:.2f} за {direction}."
                    if comment:
                        notification += f" Комментарий: {comment}."
                    await context.bot.send_message(chat_id=worker_tg_id, text=notification)
                    logger.info(f"Уведомление отправлено воркеру {worker_name} (ID: {worker_tg_id})")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления: {e}")
                
                # Вернуться в админ-меню
                del admin_temp_data[telegram_id]
                user_states[telegram_id] = 'admin_menu'
                keyboard = [
                    ['👥 Управление командами', '👤 Управление воркерами'],
                    ['💰 Начислить профит', '📊 Глобальная статистика'],
                    ['⬅️ Назад']
                ]
                keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                await update.message.reply_text(f"✅ Профит начислен воркеру {worker_name}!", reply_markup=keyboard)
            else:
                await update.message.reply_text("Ошибка при добавлении профита.")
            return
        
        elif action == 'create_team' and step == 'name':
            team_name = text
            admin_temp_data[telegram_id]['team_name'] = team_name
            admin_temp_data[telegram_id]['step'] = 'leader'
            
            # Получить список тимлидеров
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('SELECT telegram_id, name FROM users WHERE role = "team_leader"')
            leaders = cursor.fetchall()
            conn.close()
            
            if not leaders:
                await update.message.reply_text("Нет доступных тимлидеров. Сначала создайте пользователя с ролью team_leader.")
                return
            
            keyboard_buttons = []
            for leader_tg_id, leader_name in leaders:
                keyboard_buttons.append([f'👤 {leader_name}'])
            keyboard_buttons.append(['⬅️ Назад'])
            keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
            await update.message.reply_text("Выберите тимлидера:", reply_markup=keyboard)
            return
        
        elif action == 'create_team' and step == 'leader':
            if text.startswith('👤'):
                leader_name = text.replace('👤 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM users WHERE name = ? AND role = "team_leader"', (leader_name,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    leader_id = result[0]
                    team_name = admin_temp_data[telegram_id]['team_name']
                    
                    # Создать команду
                    team_id = create_team(team_name, leader_id)
                    
                    if team_id:
                        # Вернуться в админ-меню
                        del admin_temp_data[telegram_id]
                        user_states[telegram_id] = 'admin_menu'
                        keyboard = [
                            ['👥 Управление командами', '👤 Управление воркерами'],
                            ['💰 Начислить профит', '📊 Глобальная статистика'],
                            ['⬅️ Назад']
                        ]
                        keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                        await update.message.reply_text(f"✅ Команда '{team_name}' создана!", reply_markup=keyboard)
                    else:
                        await update.message.reply_text("Ошибка при создании команды.")
                else:
                    await update.message.reply_text("Тимлидер не найден.")
            return
        
        elif action == 'add_worker' and step == 'name':
            worker_name = text
            admin_temp_data[telegram_id]['worker_name'] = worker_name
            admin_temp_data[telegram_id]['step'] = 'telegram_id'
            await update.message.reply_text("Введите Telegram ID воркера:")
            return
        
        elif action == 'add_worker' and step == 'telegram_id':
            try:
                worker_tg_id = int(text)
                admin_temp_data[telegram_id]['worker_telegram_id'] = worker_tg_id
                admin_temp_data[telegram_id]['step'] = 'direction'
                
                bots = get_bots_from_database()
                if not bots:
                    await update.message.reply_text("Нет доступных направлений. Добавьте боты в базу данных.")
                    return
                
                keyboard_buttons = []
                for name, _, _ in bots:
                    keyboard_buttons.append([name])
                keyboard_buttons.append(['⬅️ Назад'])
                keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
                await update.message.reply_text("Выберите направление:", reply_markup=keyboard)
                return
            except ValueError:
                await update.message.reply_text("Неверный формат ID. Введите число.")
                return
        
        elif action == 'add_worker' and step == 'direction':
            direction = text
            bot_info = get_bot_by_name(direction)
            
            if bot_info:
                admin_temp_data[telegram_id]['direction'] = direction
                admin_temp_data[telegram_id]['step'] = 'team'
                
                teams = get_all_teams()
                if not teams:
                    await update.message.reply_text("Нет доступных команд.")
                    return
                
                keyboard_buttons = []
                for team_id, team_name in teams:
                    keyboard_buttons.append([f'👥 {team_name}'])
                keyboard_buttons.append(['⬅️ Назад'])
                keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
                await update.message.reply_text("Выберите команду:", reply_markup=keyboard)
                return
            else:
                await update.message.reply_text("Направление не найдено.")
                return
        
        elif action == 'add_worker' and step == 'team':
            if text.startswith('👥'):
                team_name = text.replace('👥 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM teams WHERE name = ?', (team_name,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    team_id = result[0]
                    worker_name = admin_temp_data[telegram_id]['worker_name']
                    worker_tg_id = admin_temp_data[telegram_id]['worker_telegram_id']
                    direction = admin_temp_data[telegram_id]['direction']
                    
                    # Добавить воркера
                    try:
                        conn = sqlite3.connect('bot_database.db')
                        cursor = conn.cursor()
                        cursor.execute(
                            'INSERT INTO users (telegram_id, name, role, team_id, direction) VALUES (?, ?, ?, ?, ?)',
                            (worker_tg_id, worker_name, 'worker', team_id, direction)
                        )
                        conn.commit()
                        conn.close()
                        
                        # Уведомить тимлидера
                        conn = sqlite3.connect('bot_database.db')
                        cursor = conn.cursor()
                        cursor.execute('SELECT team_leader_id FROM teams WHERE id = ?', (team_id,))
                        leader_result = cursor.fetchone()
                        conn.close()
                        
                        if leader_result:
                            leader_id = leader_result[0]
                            conn = sqlite3.connect('bot_database.db')
                            cursor = conn.cursor()
                            cursor.execute('SELECT telegram_id FROM users WHERE id = ?', (leader_id,))
                            leader_tg = cursor.fetchone()
                            conn.close()
                            
                            if leader_tg:
                                try:
                                    notification = f"В вашу команду '{team_name}' добавлен воркер: {worker_name}."
                                    await context.bot.send_message(chat_id=leader_tg[0], text=notification)
                                    logger.info(f"Уведомление отправлено тимлидеру (ID: {leader_tg[0]})")
                                except Exception as e:
                                    logger.error(f"Ошибка при отправке уведомления тимлидеру: {e}")
                        
                        # Вернуться в админ-меню
                        del admin_temp_data[telegram_id]
                        user_states[telegram_id] = 'admin_menu'
                        keyboard = [
                            ['👥 Управление командами', '👤 Управление воркерами'],
                            ['💰 Начислить профит', '📊 Глобальная статистика'],
                            ['⬅️ Назад']
                        ]
                        keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                        await update.message.reply_text(f"✅ Воркер {worker_name} добавлен!", reply_markup=keyboard)
                    except Exception as e:
                        logger.error(f"Ошибка при добавлении воркера: {e}")
                        await update.message.reply_text("Ошибка при добавлении воркера.")
                else:
                    await update.message.reply_text("Команда не найдена.")
            return
        
        elif action == 'delete_worker' and step == 'select':
            if text.startswith('👤'):
                worker_name = text.replace('👤 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('DELETE FROM users WHERE name = ? AND role = "worker"', (worker_name,))
                conn.commit()
                conn.close()
                
                del admin_temp_data[telegram_id]
                user_states[telegram_id] = 'admin_menu'
                keyboard = [
                    ['👥 Управление командами', '👤 Управление воркерами'],
                    ['💰 Начислить профит', '📊 Глобальная статистика'],
                    ['⬅️ Назад']
                ]
                keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                await update.message.reply_text(f"✅ Воркер {worker_name} удален!", reply_markup=keyboard)
            return
        
        elif action == 'move_worker' and step == 'select_worker':
            if text.startswith('👤'):
                worker_name = text.replace('👤 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id, team_id FROM users WHERE name = ? AND role = "worker"', (worker_name,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    worker_id, current_team_id = result
                    admin_temp_data[telegram_id]['worker_id'] = worker_id
                    admin_temp_data[telegram_id]['worker_name'] = worker_name
                    admin_temp_data[telegram_id]['step'] = 'select_team'
                    
                    teams = get_all_teams()
                    if not teams:
                        await update.message.reply_text("Нет доступных команд.")
                        return
                    
                    keyboard_buttons = []
                    for team_id, team_name in teams:
                        keyboard_buttons.append([f'👥 {team_name}'])
                    keyboard_buttons.append(['⬅️ Назад'])
                    keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
                    await update.message.reply_text("Выберите новую команду:", reply_markup=keyboard)
                else:
                    await update.message.reply_text("Воркер не найден.")
            return
        
        elif action == 'move_worker' and step == 'select_team':
            if text.startswith('👥'):
                team_name = text.replace('👥 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM teams WHERE name = ?', (team_name,))
                team_result = cursor.fetchone()
                
                if team_result:
                    new_team_id = team_result[0]
                    worker_id = admin_temp_data[telegram_id]['worker_id']
                    worker_name = admin_temp_data[telegram_id]['worker_name']
                    
                    cursor.execute('UPDATE users SET team_id = ? WHERE id = ?', (new_team_id, worker_id))
                    conn.commit()
                    conn.close()
                    
                    del admin_temp_data[telegram_id]
                    user_states[telegram_id] = 'admin_menu'
                    keyboard = [
                        ['👥 Управление командами', '👤 Управление воркерами'],
                        ['💰 Начислить профит', '📊 Глобальная статистика'],
                        ['⬅️ Назад']
                    ]
                    keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                    await update.message.reply_text(f"✅ Воркер {worker_name} перемещен в команду '{team_name}'!", reply_markup=keyboard)
                else:
                    await update.message.reply_text("Команда не найдена.")
            return
        
        elif action == 'edit_team' and step == 'select':
            if text.startswith('👥'):
                team_name = text.replace('👥 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM teams WHERE name = ?', (team_name,))
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    team_id = result[0]
                    admin_temp_data[telegram_id]['team_id'] = team_id
                    admin_temp_data[telegram_id]['team_name'] = team_name
                    admin_temp_data[telegram_id]['step'] = 'action'
                    
                    keyboard = [
                        ['👤 Сменить тимлидера', '🗑 Удалить команду'],
                        ['⬅️ Назад']
                    ]
                    keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                    await update.message.reply_text(f"Выберите действие для команды '{team_name}':", reply_markup=keyboard)
                else:
                    await update.message.reply_text("Команда не найдена.")
            return
        
        elif action == 'edit_team' and step == 'action':
            if text == '🗑 Удалить команду':
                team_id = admin_temp_data[telegram_id]['team_id']
                team_name = admin_temp_data[telegram_id]['team_name']
                
                try:
                    conn = sqlite3.connect('bot_database.db')
                    cursor = conn.cursor()
                    # Удалить воркеров из команды
                    cursor.execute('UPDATE users SET team_id = NULL WHERE team_id = ?', (team_id,))
                    # Удалить команду
                    cursor.execute('DELETE FROM teams WHERE id = ?', (team_id,))
                    conn.commit()
                    conn.close()
                    
                    del admin_temp_data[telegram_id]
                    user_states[telegram_id] = 'admin_menu'
                    keyboard = [
                        ['👥 Управление командами', '👤 Управление воркерами'],
                        ['💰 Начислить профит', '📊 Глобальная статистика'],
                        ['⬅️ Назад']
                    ]
                    keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                    await update.message.reply_text(f"✅ Команда '{team_name}' удалена!", reply_markup=keyboard)
                except Exception as e:
                    logger.error(f"Ошибка при удалении команды: {e}")
                    await update.message.reply_text("Ошибка при удалении команды.")
            elif text == '👤 Сменить тимлидера':
                admin_temp_data[telegram_id]['step'] = 'select_leader'
                
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT telegram_id, name FROM users WHERE role = "team_leader"')
                leaders = cursor.fetchall()
                conn.close()
                
                if not leaders:
                    await update.message.reply_text("Нет доступных тимлидеров.")
                    return
                
                keyboard_buttons = []
                for leader_tg_id, leader_name in leaders:
                    keyboard_buttons.append([f'👤 {leader_name}'])
                keyboard_buttons.append(['⬅️ Назад'])
                keyboard = ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)
                await update.message.reply_text("Выберите нового тимлидера:", reply_markup=keyboard)
            return
        
        elif action == 'edit_team' and step == 'select_leader':
            if text.startswith('👤'):
                leader_name = text.replace('👤 ', '')
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM users WHERE name = ? AND role = "team_leader"', (leader_name,))
                result = cursor.fetchone()
                
                if result:
                    new_leader_id = result[0]
                    team_id = admin_temp_data[telegram_id]['team_id']
                    team_name = admin_temp_data[telegram_id]['team_name']
                    
                    cursor.execute('UPDATE teams SET team_leader_id = ? WHERE id = ?', (new_leader_id, team_id))
                    conn.commit()
                    conn.close()
                    
                    del admin_temp_data[telegram_id]
                    user_states[telegram_id] = 'admin_menu'
                    keyboard = [
                        ['👥 Управление командами', '👤 Управление воркерами'],
                        ['💰 Начислить профит', '📊 Глобальная статистика'],
                        ['⬅️ Назад']
                    ]
                    keyboard = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
                    await update.message.reply_text(f"✅ Тимлидер команды '{team_name}' изменен на {leader_name}!", reply_markup=keyboard)
                else:
                    await update.message.reply_text("Тимлидер не найден.")
            return
    
    # Обработка кнопки "❓ Справка"
    if text == '❓ Справка':
        await help_handler(update, context)
        return
    
    # Обычное сообщение
    await update.message.reply_text("Выберите пункт из меню.")


async def main():
    """
    Основная функция запуска бота
    """
    # Инициализировать базу данных
    init_database()
    
    # Создать Application
    application = Application.builder().token(TOKEN).build()
    
    # Добавить обработчики команд
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # Добавить обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    # Запустить бота
    logger.info("Бот запущен")
    await application.run_polling()


if __name__ == '__main__':
    asyncio.run(main())

