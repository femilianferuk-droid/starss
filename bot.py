import logging
import sqlite3
from typing import Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройки бота
BOT_TOKEN = "8576508096:AAG0AIzNghWipA1mDiUrLilFiZ_aeKr8k7Q"
ADMIN_CHAT_ID = 7973988177

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            balance INTEGER DEFAULT 0,
            referrer_id INTEGER DEFAULT NULL,
            invited_count INTEGER DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица каналов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT,
            channel_link TEXT
        )
    ''')
    
    # Добавляем тестовые каналы (замените на реальные)
    cursor.execute('''
        INSERT OR IGNORE INTO channels (channel_id, channel_name, channel_link) 
        VALUES 
        ('@testchannel1', 'Тестовый канал 1', 'https://t.me/testchannel1'),
        ('@testchannel2', 'Тестовый канал 2', 'https://t.me/testchannel2')
    ''')
    
    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_user(user_id: int) -> Dict:
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'last_name': user[3],
            'balance': user[4],
            'referrer_id': user[5],
            'invited_count': user[6],
            'registered_at': user[7]
        }
    return None

def add_user(user_id: int, username: str, first_name: str, last_name: str, referrer_id: int = None):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, referrer_id)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, referrer_id))
    
    # Если есть реферер, начисляем бонусы
    if referrer_id:
        cursor.execute('UPDATE users SET balance = balance + 5, invited_count = invited_count + 1 WHERE user_id = ?', (referrer_id,))
        cursor.execute('UPDATE users SET balance = balance + 4 WHERE user_id = ?', (user_id,))
    
    conn.commit()
    conn.close()

def update_balance(user_id: int, amount: int):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()
    return users

def get_channels():
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM channels')
    channels = cursor.fetchall()
    conn.close()
    return channels

def update_channels(channel_data: List[Tuple]):
    conn = sqlite3.connect('bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM channels')
    cursor.executemany('INSERT INTO channels (channel_id, channel_name, channel_link) VALUES (?, ?, ?)', channel_data)
    conn.commit()
    conn.close()

# Проверка подписки на каналы
async def check_subscriptions(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # Админ всегда имеет доступ
    if user_id == ADMIN_CHAT_ID:
        return True
        
    channels = get_channels()
    
    for channel in channels:
        channel_id = channel[0]
        try:
            member = await context.bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logger.error(f"Ошибка проверки подписки на канал {channel_id}: {e}")
            return False
    
    return True

# Главное меню
async def show_main_menu(user_id: int, context: ContextTypes.DEFAULT_TYPE, update: Update = None, query = None):
    user_data = get_user(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💎 Баланс", callback_data="balance")],
        [InlineKeyboardButton("🎁 Вывод", callback_data="withdraw")],
        [InlineKeyboardButton("👥 Реферальная система", callback_data="referral")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    
    if user_id == ADMIN_CHAT_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"🎉 Добро пожаловать!\n\n💫 Ваш баланс: {user_data['balance']} звезд\n👥 Приглашено друзей: {user_data['invited_count']}\n\nВыберите действие:"
    
    if user_id == ADMIN_CHAT_ID:
        text = f"👑 Добро пожаловать, Администратор!\n\n💫 Ваш баланс: {user_data['balance']} звезд\n👥 Приглашено друзей: {user_data['invited_count']}\n\nВыберите действие:"
    
    if update and update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif query:
        await query.edit_message_text(text, reply_markup=reply_markup)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Проверяем реферальную ссылку
    referrer_id = None
    if context.args:
        try:
            referrer_id = int(context.args[0])
        except ValueError:
            pass
    
    # Добавляем пользователя если его нет
    if not get_user(user_id):
        add_user(user_id, user.username, user.first_name, user.last_name, referrer_id)
    
    # Если пользователь - админ, сразу даем доступ
    if user_id == ADMIN_CHAT_ID:
        await show_main_menu(user_id, context, update=update)
        return
    
    # Для обычных пользователей проверяем подписки
    has_access = await check_subscriptions(user_id, context)
    
    if has_access:
        await show_main_menu(user_id, context, update=update)
    else:
        channels = get_channels()
        channel_links = "\n".join([f"• {channel[2]}" for channel in channels])
        
        await update.message.reply_text(
            f"🚫 Доступ ограничен!\n\n"
            f"Для доступа к боту необходимо подписаться на следующие каналы:\n\n"
            f"{channel_links}\n\n"
            f"После подписки нажмите /start",
            parse_mode='HTML'
        )

# Обработчик callback запросов
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    user_data = get_user(user_id)
    
    if data == "balance":
        await query.edit_message_text(
            f"💫 Ваш баланс: {user_data['balance']} звезд\n"
            f"👥 Приглашено друзей: {user_data['invited_count']}"
        )
    
    elif data == "withdraw":
        keyboard = [
            [
                InlineKeyboardButton("15 звезд", callback_data="withdraw_15"),
                InlineKeyboardButton("25 звезд", callback_data="withdraw_25")
            ],
            [
                InlineKeyboardButton("50 звезд", callback_data="withdraw_50"),
                InlineKeyboardButton("100 звезд", callback_data="withdraw_100")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🎁 Вывод звезд\n\n"
            "Выберите сумму для вывода:",
            reply_markup=reply_markup
        )
    
    elif data.startswith("withdraw_"):
        amount = int(data.split("_")[1])
        
        if user_data['balance'] >= amount:
            await query.edit_message_text(
                f"💎 Запрос на вывод {amount} звезд\n\n"
                f"Для вывода напишите: @nezeexsupp\n\n"
                f"В сообщении укажите:\n"
                f"• Сумму вывода: {amount} звезд\n"
                f"• Ваш ID: {user_id}\n"
                f"• Ваш баланс: {user_data['balance']} звезд"
            )
        else:
            await query.edit_message_text(
                f"❌ Недостаточно звезд для вывода!\n"
                f"💫 Ваш баланс: {user_data['balance']} звезд\n"
                f"💎 Требуется: {amount} звезд"
            )
    
    elif data == "referral":
        ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start={user_id}"
        
        await query.edit_message_text(
            f"👥 Реферальная система\n\n"
            f"💫 Приглашайте друзей и получайте бонусы!\n\n"
            f"🎁 За каждого приглашенного друга:\n"
            f"• Вам: 5 звезд\n"
            f"• Другу: 4 звезды\n\n"
            f"🔗 Ваша реферальная ссылка:\n"
            f"<code>{ref_link}</code>\n\n"
            f"👥 Приглашено друзей: {user_data['invited_count']}",
            parse_mode='HTML'
        )
    
    elif data == "help":
        help_text = (
            "ℹ️ Помощь\n\n"
            "💫 Звезды - это внутренняя валюта бота\n\n"
            "🎁 Как получить звезды:\n"
            "• Приглашайте друзей по реферальной ссылке\n"
            "• За каждого друга получаете 5 звезд\n\n"
            "💎 Вывод от 15 звезд\n\n"
            "👥 Для доступа к боту нужно быть подписанным на все каналы"
        )
        
        # Для админа добавляем информацию о привилегиях
        if user_id == ADMIN_CHAT_ID:
            help_text += "\n\n👑 Вы администратор и имеете доступ без подписок"
            
        await query.edit_message_text(help_text)
    
    elif data == "admin" and user_id == ADMIN_CHAT_ID:
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("✉️ Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton("💰 Изменить баланс", callback_data="admin_balance")],
            [InlineKeyboardButton("📢 Управление каналами", callback_data="admin_channels")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚙️ Админ панель\n\n"
            "Выберите действие:",
            reply_markup=reply_markup
        )
    
    elif data == "admin_stats" and user_id == ADMIN_CHAT_ID:
        users = get_all_users()
        total_users = len(users)
        total_balance = sum(user[4] for user in users)
        total_refs = sum(user[6] for user in users)
        
        await query.edit_message_text(
            f"📊 Статистика\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"💫 Общий баланс: {total_balance} звезд\n"
            f"👥 Всего приглашено: {total_refs} друзей"
        )
    
    elif data == "admin_balance" and user_id == ADMIN_CHAT_ID:
        context.user_data['awaiting_balance'] = True
        await query.edit_message_text(
            "💰 Изменение баланса\n\n"
            "Отправьте сообщение в формате:\n"
            "<code>user_id amount</code>\n\n"
            "Например: <code>123456789 10</code>\n"
            "Для добавления звезд используйте положительное число\n"
            "Для списания - отрицательное",
            parse_mode='HTML'
        )
    
    elif data == "admin_broadcast" and user_id == ADMIN_CHAT_ID:
        context.user_data['awaiting_broadcast'] = True
        await query.edit_message_text(
            "✉️ Рассылка сообщений\n\n"
            "Отправьте сообщение которое хотите разослать всем пользователям:"
        )
    
    elif data == "admin_channels" and user_id == ADMIN_CHAT_ID:
        channels = get_channels()
        channel_list = "\n".join([f"• {channel[1]} ({channel[0]})" for channel in channels])
        
        await query.edit_message_text(
            f"📢 Управление каналами\n\n"
            f"Текущие каналы:\n{channel_list}\n\n"
            f"Для изменения каналов отправьте сообщение в формате:\n"
            f"<code>channel_id channel_name channel_link</code>\n\n"
            f"Например:\n"
            f"<code>@channel1 Мой канал https://t.me/channel1</code>\n\n"
            f"Для нескольких каналов разделяйте их пустой строкой",
            parse_mode='HTML'
        )
        context.user_data['awaiting_channels'] = True
    
    elif data == "back_to_main":
        await show_main_menu(user_id, context, query=query)

# Обработчик текстовых сообщений для админских функций
async def handle_admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id != ADMIN_CHAT_ID:
        return
    
    # Изменение баланса
    if context.user_data.get('awaiting_balance'):
        try:
            parts = text.split()
            target_user_id = int(parts[0])
            amount = int(parts[1])
            
            update_balance(target_user_id, amount)
            user_data = get_user(target_user_id)
            
            await update.message.reply_text(
                f"✅ Баланс пользователя {target_user_id} изменен!\n"
                f"💫 Новый баланс: {user_data['balance']} звезд"
            )
            
            # Сбрасываем флаг
            context.user_data['awaiting_balance'] = False
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    # Рассылка
    elif context.user_data.get('awaiting_broadcast'):
        users = get_all_users()
        success_count = 0
        
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user[0],
                    text=text
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки пользователю {user[0]}: {e}")
        
        await update.message.reply_text(
            f"✉️ Рассылка завершена!\n"
            f"✅ Успешно отправлено: {success_count}/{len(users)}"
        )
        
        context.user_data['awaiting_broadcast'] = False
    
    # Управление каналами
    elif context.user_data.get('awaiting_channels'):
        try:
            channels_data = []
            lines = text.split('\n')
            
            for line in lines:
                if line.strip():
                    parts = line.split(' ', 2)
                    if len(parts) == 3:
                        channels_data.append((parts[0], parts[1], parts[2]))
            
            update_channels(channels_data)
            
            await update.message.reply_text(
                f"✅ Каналы обновлены!\n"
                f"📢 Добавлено каналов: {len(channels_data)}"
            )
            
            context.user_data['awaiting_channels'] = False
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")

def main():
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_commands))
    
    # Запуск бота
    application.run_polling()
    print("Бот запущен!")

if __name__ == '__main__':
    main()
