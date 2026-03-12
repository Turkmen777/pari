import logging
import os
from flask import Flask, request, jsonify
import telegram
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, ConversationHandler
import re

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)

# Получаем токен и ID группы из переменных окружения (которые вы настроите в Bothost)
TOKEN = os.environ.get('TOKEN')
GROUP_ID = int(os.environ.get('GROUP_ID', '-1003759188641'))

# Проверяем, что токен получен
if not TOKEN:
    logger.error("Токен не найден! Добавьте TOKEN в переменные окружения Bothost.")
    TOKEN = "8607427844:AAEI-DnlKJs-iXIsr6XFjFsQjsYZCzwfOw0"  # временно для теста, но лучше использовать переменные окружения

# Инициализация бота
bot = telegram.Bot(token=TOKEN)

# Состояния для ConversationHandler
(PHONE_INPUT, AMOUNT_INPUT, WITHDRAW_PHONE_INPUT, 
 WITHDRAW_AMOUNT_INPUT, WITHDRAW_RECEIPT_INPUT) = range(5)

# Временное хранилище данных пользователей
user_data = {}

# ================ ФУНКЦИИ ДЛЯ ПРОВЕРКИ ВВОДА ================

def validate_parikara_id(text):
    """Проверяет, что введены только цифры"""
    return re.match(r'^\d+$', text) is not None

def validate_amount(text):
    """Проверяет сумму (минимум 30 TMT и только цифры)"""
    if re.match(r'^\d+$', text):
        amount = int(text)
        if amount >= 30:
            return True
    return False

def validate_phone(text):
    """Проверяет номер телефона (+993 и 8 цифр)"""
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    if re.match(r'^\+993\d{8}$', clean_text):  # +99365123456
        return True
    elif re.match(r'^993\d{8}$', clean_text):  # 99365123456
        return True
    elif re.match(r'^\d{8}$', clean_text):  # 65123456
        return True
    return False

def format_phone(text):
    """Приводит номер к единому формату +993XXXXXXXX"""
    clean_text = re.sub(r'[\s\-\(\)]', '', text)
    if re.match(r'^\d{8}$', clean_text):
        return f"+993{clean_text}"
    elif re.match(r'^993\d{8}$', clean_text):
        return f"+{clean_text}"
    elif re.match(r'^\+\d{11,}$', clean_text):
        return clean_text
    return text

# ================ ОБРАБОТЧИКИ КОМАНД ================

def start(update, context):
    """Обработчик команды /start"""
    user = update.effective_user
    keyboard = [
        [telegram.KeyboardButton("💰 Hasaby doldurmak")],
        [telegram.KeyboardButton("💸 Pul çykarmak")]
    ]
    reply_markup = telegram.ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    welcome_text = (
        f"Hoş geldiňiz, {user.first_name}! 🤖\n\n"
        "Astra Kassa botyna hoş geldiňiz.\n"
        "Hasaby doldurmak ýa-da pul çykarmak üçin aşakdaky düwmeleri ulanyň."
    )
    
    update.message.reply_text(welcome_text, reply_markup=reply_markup)
    return ConversationHandler.END

def deposit_start(update, context):
    """Начало процесса пополнения"""
    user_id = update.effective_user.id
    user_data[user_id] = {'action': 'deposit'}
    update.message.reply_text("🔑 Parikara ID-nizi ýazyň:\n(Diňe sanlar)")
    return PHONE_INPUT

def deposit_phone(update, context):
    """Получение ID Parikara для пополнения"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_parikara_id(text):
        user_data[user_id]['parikara_id'] = text
        update.message.reply_text(
            f"✅ ID kabul edildi: {text}\n\n"
            "💵 Näçe TMT doldurmaly?\n"
            "(Iň az 30 TMT, diňe san)"
        )
        return AMOUNT_INPUT
    else:
        update.message.reply_text("❌ Ýalňyş! Diňe san giriziň.\nParikara ID-nizi täzeden ýazyň:")
        return PHONE_INPUT

def deposit_amount(update, context):
    """Получение суммы пополнения"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_amount(text):
        amount = text
        user_data[user_id]['amount'] = amount
        
        # Отправляем заявку в группу администраторов
        user = update.effective_user
        username = user.username or "ýok"
        
        group_message = (
            f"🟢 TÄZE HAÝYŞ: HASABY DOLDURMAK\n\n"
            f"Ulanyjy: @{username}\n"
            f"ID: {user_data[user_id]['parikara_id']}\n"
            f"Summa: {amount} TMT"
        )
        
        bot.send_message(chat_id=GROUP_ID, text=group_message)
        
        update.message.reply_text(
            "✅ Haýyşyňyz kabul edildi!\n\n"
            "📞 Töleg maglumatlary 10 minudyň içinde ugradylar.\n"
            "Tölegiňizi geçireniňizden soň, skrinşoty ugratmagy unutmaň."
        )
        
        # Очищаем данные пользователя
        del user_data[user_id]
        return ConversationHandler.END
    else:
        update.message.reply_text("❌ Ýalňyş summa! Iň az 30 TMT bolmaly.\nTäzeden ýazyň:")
        return AMOUNT_INPUT

def withdraw_start(update, context):
    """Начало процесса вывода средств"""
    user_id = update.effective_user.id
    user_data[user_id] = {'action': 'withdraw'}
    update.message.reply_text("🔑 Parikara ID-nizi ýazyň:\n(Diňe sanlar)")
    return WITHDRAW_PHONE_INPUT

def withdraw_phone(update, context):
    """Получение ID Parikara для вывода"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_parikara_id(text):
        user_data[user_id]['parikara_id'] = text
        update.message.reply_text(
            f"✅ ID kabul edildi: {text}\n\n"
            "💵 Näçe TMT çykarmaly?\n(Diňe san)"
        )
        return WITHDRAW_AMOUNT_INPUT
    else:
        update.message.reply_text("❌ Ýalňyş! Diňe san giriziň.\nParikara ID-nizi täzeden ýazyň:")
        return WITHDRAW_PHONE_INPUT

def withdraw_amount(update, context):
    """Получение суммы вывода"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if re.match(r'^\d+$', text):
        amount = text
        user_data[user_id]['amount'] = amount
        update.message.reply_text(
            f"✅ Summa kabul edildi: {amount} TMT\n\n"
            "📞 Telefon nomeriňizi ýazyň:\n"
            "(Mysal: +99365123456 ýa-da 65123456)"
        )
        return WITHDRAW_RECEIPT_INPUT
    else:
        update.message.reply_text("❌ Ýalňyş! Diňe san giriziň.\nTäzeden ýazyň:")
        return WITHDRAW_AMOUNT_INPUT

def withdraw_receipt(update, context):
    """Получение номера телефона для вывода"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if validate_phone(text):
        phone = format_phone(text)
        user = update.effective_user
        username = user.username or "ýok"
        
        group_message = (
            f"🔴 TÄZE HAÝYŞ: PUL ÇYKARMAK\n\n"
            f"Ulanyjy: @{username}\n"
            f"ID: {user_data[user_id]['parikara_id']}\n"
            f"Summa: {user_data[user_id]['amount']} TMT\n"
            f"Telefon: {phone}"
        )
        
        bot.send_message(chat_id=GROUP_ID, text=group_message)
        
        update.message.reply_text(
            "✅ Haýyşyňyz kabul edildi!\n\n"
            "💸 Pul çykarmak haýyşyňyz işlenilýär.\n"
            "Administratorlar tizara habarlaşarlar."
        )
        
        # Очищаем данные пользователя
        del user_data[user_id]
        return ConversationHandler.END
    else:
        update.message.reply_text(
            "❌ Ýalňyş telefon nomeri!\n"
            "Dogry format: +99365123456 ýa-da 65123456\n"
            "Täzeden ýazyň:"
        )
        return WITHDRAW_RECEIPT_INPUT

def cancel(update, context):
    """Отмена действия"""
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
    update.message.reply_text("❌ Amal ýatyryldy.\nTäzeden başlamak üçin /start basyň.")
    return ConversationHandler.END

def handle_screenshot(update, context):
    """Обрабатывает получение скриншотов"""
    if update.message.photo:
        photo = update.message.photo[-1]
        file_id = photo.file_id
        user = update.effective_user
        username = user.username or "ýok"
        
        bot.send_photo(
            chat_id=GROUP_ID, 
            photo=file_id,
            caption=f"🖼 TÄZE SKRINŞOT\n\nUlanyjy: @{username}"
        )
        update.message.reply_text("✅ Skrinşot kabul edildi!")
    else:
        update.message.reply_text("❌ Surat ugradyň!")

# ================ НАСТРОЙКА ОБРАБОТЧИКОВ ================

def setup_dispatcher():
    """Создаёт и настраивает диспетчер"""
    dispatcher = Dispatcher(bot, None, workers=0)
    
    # Обработчик диалога пополнения
    deposit_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^💰 Hasaby doldurmak$'), deposit_start)],
        states={
            PHONE_INPUT: [MessageHandler(Filters.text & ~Filters.command, deposit_phone)],
            AMOUNT_INPUT: [MessageHandler(Filters.text & ~Filters.command, deposit_amount)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Обработчик диалога вывода
    withdraw_conv = ConversationHandler(
        entry_points=[MessageHandler(Filters.regex('^💸 Pul çykarmak$'), withdraw_start)],
        states={
            WITHDRAW_PHONE_INPUT: [MessageHandler(Filters.text & ~Filters.command, withdraw_phone)],
            WITHDRAW_AMOUNT_INPUT: [MessageHandler(Filters.text & ~Filters.command, withdraw_amount)],
            WITHDRAW_RECEIPT_INPUT: [MessageHandler(Filters.text & ~Filters.command, withdraw_receipt)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(deposit_conv)
    dispatcher.add_handler(withdraw_conv)
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_screenshot))
    
    return dispatcher

dispatcher = setup_dispatcher()

# ================ ВЕБХУК ================

@app.route('/webhook', methods=['POST'])
def webhook():
    """Точка входа для вебхуков Telegram"""
    try:
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/')
def index():
    return 'Astra Kassa Bot is running!'

# Для локального тестирования
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
