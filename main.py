import os
import logging
import random
import json
from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv("BOT_TOKEN", "7936749972:AAHuSjSWqmkPpoR3fI5EtH3PH2IrCJd1Vo8")  # ЗАМЕНИТЕ НА РЕАЛЬНЫЙ ТОКЕН
BASE_URL = "https://tcos-by-velda.up.railway.app"
WEBAPP_URL = f"{BASE_URL}/webapp.html"

# Состояния игры
MAIN_MENU, SET_BET, SET_COLOR, SET_NUMBER = range(4)

# Цвета и коэффициенты
COLORS = {
    "red": {"name": "🔴 Красное", "emoji": "🔴"},
    "black": {"name": "⚫ Черное", "emoji": "⚫"},
    "white": {"name": "⚪ Белое", "emoji": "⚪"}
}
COLOR_VALUES = list(COLORS.keys())
NUMBERS = [1, 2, 3, 4, 5, 6]

# Создаем Flask приложение
app = Flask(__name__)

# Хранилище данных пользователя
user_data_store = {}

@app.route('/webapp', methods=['POST'])
def webapp_handler():
    data = request.json
    user_id = data['user_id']
    action = data.get('action')
    
    # Инициализация данных пользователя
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            'balance': 1000,
            'credit_taken': False
        }
    
    user_data = user_data_store[user_id]
    
    if action == 'get_data':
        # Отправляем данные пользователя в WebApp
        return jsonify({
            'balance': user_data['balance'],
            'credit_taken': user_data['credit_taken'],
            'colors': COLORS,
            'numbers': NUMBERS
        })
    
    elif action == 'spin':
        bet = data['bet']
        color = data['color']
        number = data['number']
        
        # Проверка ставки
        if bet <= 0:
            return jsonify({'error': 'Ставка должна быть больше 0!'})
        
        if user_data['balance'] < bet and not (user_data['balance'] <= 0 and user_data['credit_taken']):
            return jsonify({'error': 'Недостаточно средств!'})
        
        # Генерация результата
        result_color = random.choice(COLOR_VALUES)
        result_number = random.choice(NUMBERS)
        
        # Проверка выигрыша
        if color == result_color and number == result_number:
            user_data['balance'] += bet
            win = True
        else:
            user_data['balance'] -= bet
            win = False
        
        return jsonify({
            'result': {
                'color': result_color,
                'number': result_number,
                'color_name': COLORS[result_color]['name'],
                'emoji': COLORS[result_color]['emoji']
            },
            'win': win,
            'new_balance': user_data['balance']
        })
    
    elif action == 'take_credit':
        user_data['credit_taken'] = True
        return jsonify({'message': 'Кредит одобрен!', 'new_balance': user_data['balance']})
    
    return jsonify({'error': 'Неизвестное действие'})

@app.route('/webapp.html')
def serve_webapp():
    return send_from_directory('.', 'webapp.html')

# Telegram бот часть
def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка команды /start"""
    user = update.effective_user
    user_id = user.id
    
    # Инициализация данных пользователя
    if 'balance' not in context.user_data:
        context.user_data['balance'] = 1000
        context.user_data['credit_taken'] = False
    
    # Сохраняем в глобальное хранилище
    user_data_store[user_id] = {
        'balance': context.user_data['balance'],
        'credit_taken': context.user_data['credit_taken']
    }
    
    balance = context.user_data['balance']
    
    keyboard = [
        [InlineKeyboardButton("🎮 Новая игра", callback_data='new_game')],
        [InlineKeyboardButton("🕹 Играть в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}?user_id={user_id}"))]
    ]
    
    if balance <= 0 and not context.user_data['credit_taken']:
        keyboard.append([InlineKeyboardButton("🛎 Взять кредит", callback_data='take_credit')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n"
        "🎰 Добро пожаловать в казино!\n"
        f"💰 Ваш баланс: {balance} монет\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )
    return MAIN_MENU

def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало новой игры"""
    query = update.callback_query
    query.answer()
    
    context.user_data['current_bet'] = None
    context.user_data['current_color'] = None
    context.user_data['current_number'] = None
    
    query.edit_message_text(
        f"💰 Текущий баланс: {context.user_data['balance']} монет\n"
        "➡️ Введите сумму ставки:"
    )
    return SET_BET

def handle_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ставки от пользователя"""
    try:
        bet = int(update.message.text)
        balance = context.user_data['balance']
        credit_taken = context.user_data.get('credit_taken', False)
        
        # Проверка валидности ставки
        if bet <= 0:
            update.message.reply_text("❌ Ставка должна быть больше 0!")
            return SET_BET
            
        if balance >= bet or (balance <= 0 and credit_taken):
            context.user_data['current_bet'] = bet
            return select_color(update, context)
        else:
            # Предлагаем взять кредит, если баланс = 0
            if balance <= 0 and not credit_taken:
                keyboard = [
                    [InlineKeyboardButton("🛎 Взять кредит", callback_data='take_credit')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                update.message.reply_text(
                    "❌ Недостаточно средств! Хотите взять кредит?",
                    reply_markup=reply_markup
                )
                return MAIN_MENU
            else:
                update.message.reply_text(f"❌ Недостаточно средств! Максимальная ставка: {balance}")
                return SET_BET
    except ValueError:
        update.message.reply_text("❌ Пожалуйста, введите число!")
        return SET_BET

def select_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор цвета"""
    keyboard = []
    for color_key, color_info in COLORS.items():
        keyboard.append(
            [InlineKeyboardButton(color_info['name'], callback_data=f'color_{color_key}')]
        )
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        query = update.callback_query
        query.answer()
        query.edit_message_text(
            f"Ставка: {context.user_data['current_bet']} монет\n"
            "➡️ Выберите цвет:",
            reply_markup=reply_markup
        )
    else:
        update.message.reply_text(
            f"Ставка: {context.user_data['current_bet']} монет\n"
            "➡️ Выберите цвет:",
            reply_markup=reply_markup
        )
    return SET_COLOR

def select_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор числа"""
    query = update.callback_query
    query.answer()
    
    # Сохраняем выбранный цвет
    color_key = query.data.split('_')[1]
    context.user_data['current_color'] = color_key
    
    keyboard = []
    row = []
    for number in NUMBERS:
        row.append(InlineKeyboardButton(str(number), callback_data=f'number_{number}'))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_color')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        f"Ставка: {context.user_data['current_bet']} монет\n"
        f"Цвет: {COLORS[context.user_data['current_color']]['name']}\n"
        "➡️ Выберите число:",
        reply_markup=reply_markup
    )
    return SET_NUMBER

def spin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка вращения (для чат-версии)"""
    query = update.callback_query
    query.answer()
    
    # Сохраняем выбранное число
    number = int(query.data.split('_')[1])
    context.user_data['current_number'] = number
    
    # Генерация результата
    result_color = random.choice(COLOR_VALUES)
    result_number = random.choice(NUMBERS)
    
    # Проверка выигрыша
    bet = context.user_data['current_bet']
    user_color = context.user_data['current_color']
    user_number = context.user_data['current_number']
    
    if user_color == result_color and user_number == result_number:
        context.user_data['balance'] += bet
        win_text = "🎉 Поздравляем! Вы выиграли!"
    else:
        context.user_data['balance'] -= bet
        win_text = "❌ К сожалению, вы проиграли."
    
    # Обновляем глобальное хранилище
    user_id = update.effective_user.id
    if user_id in user_data_store:
        user_data_store[user_id]['balance'] = context.user_data['balance']
    
    # Формируем результат
    result_message = (
        f"🎰 Результат: {COLORS[result_color]['name']} {result_number}\n"
        f"📌 Ваша ставка: {COLORS[user_color]['name']} {user_number}\n"
        f"{win_text}\n"
        f"💰 Новый баланс: {context.user_data['balance']} монет"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Играть снова", callback_data='new_game')],
        [InlineKeyboardButton("🕹 Играть в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}?user_id={user_id}"))]
    ]
    
    if context.user_data['balance'] <= 0 and not context.user_data['credit_taken']:
        keyboard.insert(0, [InlineKeyboardButton("🛎 Взять кредит", callback_data='take_credit')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(result_message, reply_markup=reply_markup)
    return MAIN_MENU

def take_credit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка взятия кредита"""
    query = update.callback_query
    query.answer()
    
    context.user_data['credit_taken'] = True
    user_id = update.effective_user.id
    
    # Обновляем глобальное хранилище
    if user_id in user_data_store:
        user_data_store[user_id]['credit_taken'] = True
    
    keyboard = [
        [InlineKeyboardButton("🎮 Новая игра", callback_data='new_game')],
        [InlineKeyboardButton("🕹 Играть в приложении", web_app=WebAppInfo(url=f"{WEBAPP_URL}?user_id={user_id}"))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        "🛎 Кредит одобрен! Теперь вы можете играть с отрицательным балансом.\n"
        f"💰 Ваш баланс: {context.user_data['balance']} монет\n"
        "Можете начать новую игру!",
        reply_markup=reply_markup
    )
    return MAIN_MENU

def back_to_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат к выбору цвета"""
    return select_color(update, context)

async def setup_bot():
    """Настройка и запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Сохраняем ссылку на бота для использования в WebApp
    app.bot = application.bot

    # Обработчики диалога
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(new_game, pattern='^new_game$'),
                CallbackQueryHandler(take_credit, pattern='^take_credit$')
            ],
            SET_BET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bet)
            ],
            SET_COLOR: [
                CallbackQueryHandler(select_number, pattern='^color_'),
                CallbackQueryHandler(back_to_color, pattern='^back_to_color$'),
                CallbackQueryHandler(new_game, pattern='^new_game$')
            ],
            SET_NUMBER: [
                CallbackQueryHandler(spin, pattern='^number_'),
                CallbackQueryHandler(back_to_color, pattern='^back_to_color$'),
                CallbackQueryHandler(new_game, pattern='^new_game$')
            ]
        },
        fallbacks=[],
        allow_reentry=True
    )
    
    application.add_handler(conv_handler)
    
    # Запуск бота
    await application.run_polling()
    return application

def run_app():
    """Запуск Flask приложения"""
    port = int(os.environ.get("PORT", 3000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    # Запускаем бота в отдельном потоке
    import threading
    import asyncio
    
    def run_bot():
        asyncio.run(setup_bot())
    
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    # Запускаем Flask приложение
    run_app()
