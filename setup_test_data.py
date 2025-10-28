#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для добавления тестовых данных в базу
"""

import sqlite3

# Подключиться к базе данных
conn = sqlite3.connect('bot_database.db')
cursor = conn.cursor()

# Добавить тестовые боты (направления)
print("Добавляю тестовые боты...")
bots = [
    ('eToro', 'Платформа для социального трейдинга', 'https://etoro.com'),
    ('Binance', 'Крупнейшая криптовалютная биржа', 'https://binance.com'),
    ('Forex', 'Валютный рынок Forex', 'https://forex.com'),
    ('Crypto', 'Криптовалютные активы', 'https://crypto.com'),
]

for name, description, link in bots:
    try:
        cursor.execute('INSERT INTO bots (name, description, link) VALUES (?, ?, ?)',
                       (name, description, link))
        print(f"  ✓ Бот '{name}' добавлен")
    except sqlite3.IntegrityError:
        print(f"  ⚠ Бот '{name}' уже существует")

conn.commit()

# Добавить тестового тимлидера
print("\nДобавляю тестового тимлидера...")
try:
    cursor.execute('''
        INSERT INTO users (telegram_id, name, role, team_id, direction)
        VALUES (?, ?, 'team_leader', NULL, NULL)
    ''', (999999999, 'Тестовый Тимлидер'))
    print("  ✓ Тимлидер добавлен")
except sqlite3.IntegrityError:
    print("  ⚠ Тимлидер уже существует")

conn.commit()

# Создать тестовую команду
print("\nСоздаю тестовую команду...")
cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (999999999,))
leader_result = cursor.fetchone()

if leader_result:
    leader_id = leader_result[0]
    try:
        cursor.execute('INSERT INTO teams (name, team_leader_id) VALUES (?, ?)',
                       ('Команда Альфа', leader_id))
        team_id = cursor.lastrowid
        print(f"  ✓ Команда 'Команда Альфа' создана (ID: {team_id})")
    except sqlite3.IntegrityError:
        print("  ⚠ Команда уже существует")
        cursor.execute('SELECT id FROM teams WHERE name = ?', ('Команда Альфа',))
        team_id = cursor.fetchone()[0]
        print(f"  ℹ️ Используется существующая команда (ID: {team_id})")
    
    conn.commit()
    
    # Добавить тестовых воркеров
    print("\nДобавляю тестовых воркеров...")
    workers = [
        (111111111, 'Воркер 1', 'eToro'),
        (222222222, 'Воркер 2', 'Binance'),
        (333333333, 'Воркер 3', 'Forex'),
    ]
    
    for tg_id, name, direction in workers:
        try:
            cursor.execute('''
                INSERT INTO users (telegram_id, name, role, team_id, direction)
                VALUES (?, ?, 'worker', ?, ?)
            ''', (tg_id, name, team_id, direction))
            print(f"  ✓ Воркер '{name}' добавлен")
        except sqlite3.IntegrityError:
            print(f"  ⚠ Воркер '{name}' уже существует")
    
    conn.commit()

# Добавить тестовые профиты
print("\nДобавляю тестовые профиты...")
cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (111111111,))
worker_result = cursor.fetchone()

if worker_result:
    worker_id = worker_result[0]
    import datetime
    
    profits = [
        (worker_id, 'eToro', 100.50, datetime.datetime.now().strftime('%Y-%m-%d'), 'Тестовый профит 1'),
        (worker_id, 'Binance', 250.00, datetime.datetime.now().strftime('%Y-%m-%d'), 'Тестовый профит 2'),
    ]
    
    for user_id, direction, amount, date, comment in profits:
        try:
            cursor.execute('''
                INSERT INTO profits (user_id, direction, amount, date, comment)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, direction, amount, date, comment))
            print(f"  ✓ Профит ${amount} добавлен")
        except Exception as e:
            print(f"  ✗ Ошибка при добавлении профита: {e}")
    
    conn.commit()

conn.close()

print("\n✅ Тестовые данные успешно добавлены!")
print("\nДля использования:")
print("1. Запустите бота: python bot.py")
print("2. Войдите в бота с Telegram ID: 844012884 (для админа)")
print("3. Или используйте любой из тестовых ID воркеров")

