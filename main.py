import logging
import random
import json
from flask import Flask, request, jsonify
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

# Создаем Flask приложение для WebApp
app = Flask(__name__)

# Хранилище данных пользователя (в реальном проекте используйте БД)
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

# Telegram бот часть
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        [InlineKeyboardButton("🕹 Играть в приложении", web_app=WebAppInfo(url=f"https://{context.bot.username.lower().replace('_', '-')}.replit.app/webapp.html?user_id={user_id}"))]
    ]

    if balance <= 0 and not context.user_data['credit_taken']:
        keyboard.append([InlineKeyboardButton("🛎 Взять кредит", callback_data='take_credit')])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n"
        "🎰 Добро пожаловать в казино!\n"
        f"💰 Ваш баланс: {balance} монет\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )
    return MAIN_MENU

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало новой игры"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "💰 Введите размер ставки (число):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='back_to_menu')]])
    )
    return SET_BET

async def handle_bet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ставки"""
    try:
        bet = int(update.message.text)
        if bet <= 0:
            await update.message.reply_text("❌ Ставка должна быть больше 0! Попробуйте снова:")
            return SET_BET

        context.user_data['current_bet'] = bet

        keyboard = [
            [InlineKeyboardButton("🔴 Красное", callback_data='color_red')],
            [InlineKeyboardButton("⚫ Черное", callback_data='color_black')],
            [InlineKeyboardButton("⚪ Белое", callback_data='color_white')],
            [InlineKeyboardButton("🔙 Назад", callback_data='new_game')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"💰 Ставка: {bet} монет\n"
            "🎨 Выберите цвет:",
            reply_markup=reply_markup
        )
        return SET_COLOR

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число!")
        return SET_BET

async def select_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор числа после выбора цвета"""
    query = update.callback_query
    await query.answer()

    color = query.data.split('_')[1]
    context.user_data['current_color'] = color

    keyboard = []
    for i in range(0, len(NUMBERS), 3):
        row = []
        for j in range(i, min(i+3, len(NUMBERS))):
            number = NUMBERS[j]
            row.append(InlineKeyboardButton(str(number), callback_data=f'number_{number}'))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Назад к цветам", callback_data='back_to_color')])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"💰 Ставка: {context.user_data['current_bet']} монет\n"
        f"🎨 Цвет: {COLORS[color]['name']}\n"
        "🔢 Выберите число:",
        reply_markup=reply_markup
    )
    return SET_NUMBER

async def back_to_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возврат к выбору цвета"""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🔴 Красное", callback_data='color_red')],
        [InlineKeyboardButton("⚫ Черное", callback_data='color_black')],
        [InlineKeyboardButton("⚪ Белое", callback_data='color_white')],
        [InlineKeyboardButton("🔙 Назад", callback_data='new_game')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"💰 Ставка: {context.user_data['current_bet']} монет\n"
        "🎨 Выберите цвет:",
        reply_markup=reply_markup
    )
    return SET_COLOR

async def spin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка вращения (для чат-версии)"""
    query = update.callback_query
    await query.answer()

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
        [InlineKeyboardButton("🕹 Играть в приложении", web_app=WebAppInfo(url=f"https://{update.get_bot().username.lower().replace('_', '-')}.replit.app/webapp.html?user_id={user_id}"))]
    ]

    if context.user_data['balance'] <= 0 and not context.user_data['credit_taken']:
        keyboard.insert(0, [InlineKeyboardButton("🛎 Взять кредит", callback_data='take_credit')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(result_message, reply_markup=reply_markup)
    return MAIN_MENU

async def take_credit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка взятия кредита"""
    query = update.callback_query
    await query.answer()

    context.user_data['credit_taken'] = True
    user_id = update.effective_user.id

    # Обновляем глобальное хранилище
    if user_id in user_data_store:
        user_data_store[user_id]['credit_taken'] = True

    keyboard = [
        [InlineKeyboardButton("🎮 Новая игра", callback_data='new_game')],
        [InlineKeyboardButton("🕹 Играть в приложении", web_app=WebAppInfo(url=f"https://{update.get_bot().username.lower().replace('_', '-')}.replit.app/webapp.html?user_id={user_id}"))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🛎 Кредит одобрен! Теперь вы можете играть с отрицательным балансом.\n"
        f"💰 Ваш баланс: {context.user_data['balance']} монет\n"
        "Можете начать новую игру!",
        reply_markup=reply_markup
    )
    return MAIN_MENU

async def main() -> None:
    """Запуск бота"""
    TOKEN = "8085277321:AAHemZPBgSSzOb9Q_He4QJ10zKKWcd0iY3w"
    application = Application.builder().token(TOKEN).build()

    # Запускаем Flask в отдельном потоке
    from threading import Thread
    Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 5000}).start()

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
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())