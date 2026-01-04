import logging
import asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from threading import Thread
import time

from config import *

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# В памяти
deposits = []
next_id = 1000

# Состояния
WAITING_ID, WAITING_AMOUNT = range(2)

# ========== КЛИЕНТСКАЯ ЧАСТЬ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("💰 Пополнить счет")]]
    await update.message.reply_text(
        "Привет! Нажмите кнопку:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_deposit_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите ваш ID:")
    return WAITING_ID

async def handle_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['client_id'] = update.message.text
    await update.message.reply_text("Введите сумму (мин. 50 TMT):")
    return WAITING_AMOUNT

async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(',', '.'))
        
        if amount < MIN_AMOUNT:
            await update.message.reply_text(f"❌ Минимум {MIN_AMOUNT} TMT")
            return WAITING_AMOUNT
        
        global next_id, deposits
        
        # Создаем заявку
        deposit = {
            'id': next_id,
            'user_id': update.effective_user.id,
            'user_name': update.effective_user.first_name,
            'client_id': context.user_data['client_id'],
            'amount': amount,
            'time': datetime.now().strftime("%H:%M %d.%m.%Y"),
            'status': 'waiting'
        }
        
        deposits.append(deposit)
        
        # Клиенту
        await update.message.reply_text(
            f"✅ Заявка #{next_id} принята!\nОжидайте реквизиты..."
        )
        
        # ========== ОТПРАВКА В ГРУППУ ==========
        try:
            group_text = f"""
🆕 <b>НОВАЯ ЗАЯВКА #{next_id}</b>

👤 Клиент: {update.effective_user.first_name}
📞 ID: {context.user_data['client_id']}
💰 Сумма: {amount} TMT
⏰ Время: {deposit['time']}

<b>Отправьте номер телефона для клиента:</b>
(8 цифр, например: 65656565)
            """
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=group_text,
                parse_mode='HTML'
            )
            
            logger.info(f"✅ Заявка #{next_id} отправлена в группу {GROUP_CHAT_ID}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки в группу: {e}")
            await update.message.reply_text(f"Ошибка: {e}")
        
        next_id += 1
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите число!")
        return WAITING_AMOUNT

# ========== ОБРАБОТКА ГРУППЫ ==========
async def handle_group_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений в группе"""
    
    # Проверяем, что это наша группа
    if update.effective_chat.id != GROUP_CHAT_ID:
        return
    
    # Проверяем, что это админ
    if update.effective_user.id not in ADMIN_IDS:
        logger.info(f"Сообщение от не-админа: {update.effective_user.id}")
        return
    
    text = update.message.text.strip()
    logger.info(f"Сообщение в группе от админа: {text}")
    
    # Проверяем, 8 ли это цифр
    if text.isdigit() and len(text) == 8:
        logger.info(f"Распознан номер: {text}")
        
        # Ищем последнюю заявку без номера
        last_deposit = None
        for deposit in deposits:
            if deposit['status'] == 'waiting' and 'phone' not in deposit:
                last_deposit = deposit
                break
        
        if not last_deposit:
            await update.message.reply_text("❌ Нет заявок, ожидающих номер")
            logger.info("Нет заявок для номера")
            return
        
        logger.info(f"Найдена заявка для номера: {last_deposit['id']}")
        
        # Форматируем номер
        phone = f"+993 {text[:2]} {text[2:5]} {text[5:]}"
        last_deposit['phone'] = phone
        
        # Отправляем клиенту
        try:
            await context.bot.send_message(
                chat_id=last_deposit['user_id'],
                text=f"💳 <b>РЕКВИЗИТЫ ДЛЯ ОПЛАТЫ</b>\n\n"
                     f"📱 Номер: <code>{phone}</code>\n"
                     f"💰 Сумма: {last_deposit['amount']} TMT\n\n"
                     f"После оплаты отправьте скриншот!",
                parse_mode='HTML'
            )
            
            logger.info(f"✅ Номер отправлен клиенту {last_deposit['user_id']}")
            
            # В группе подтверждаем
            await update.message.reply_text(
                f"✅ <b>Реквизиты отправлены клиенту #{last_deposit['id']}</b>\n\n"
                f"👤 Клиент: {last_deposit['user_name']}\n"
                f"📱 Номер: {phone}\n"
                f"💰 Сумма: {last_deposit['amount']} TMT",
                parse_mode='HTML'
            )
            
            # Создаем кнопку для подтверждения оплаты
            keyboard = [[
                InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{last_deposit['id']}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"⏳ Ожидаем скриншот от клиента #{last_deposit['id']}",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки клиенту: {e}")
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    # Команда для админа
    elif text == "/list":
        waiting = [d for d in deposits if d['status'] == 'waiting' and 'phone' not in d]
        
        if not waiting:
            await update.message.reply_text("⏳ Нет ожидающих заявок")
            return
        
        msg = "⏳ <b>Ожидают номер:</b>\n\n"
        for d in waiting:
            msg += f"🆔 #{d['id']} - {d['user_name']} - {d['amount']} TMT\n"
        
        await update.message.reply_text(msg, parse_mode='HTML')

# ========== СКРИНШОТЫ ==========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото (скриншотов)"""
    
    user_id = update.effective_user.id
    
    # Ищем заявку пользователя
    user_deposit = None
    for deposit in deposits:
        if deposit['user_id'] == user_id and deposit.get('phone') and deposit['status'] == 'waiting':
            user_deposit = deposit
            break
    
    if not user_deposit:
        await update.message.reply_text("❌ Нет активной заявки")
        return
    
    await update.message.reply_text("✅ Скриншот получен! Ожидайте подтверждения")
    
    # Пересылаем в группу
    try:
        photo = update.message.photo[-1]
        
        # Отправляем фото
        await context.bot.send_photo(
            chat_id=GROUP_CHAT_ID,
            photo=photo.file_id,
            caption=f"📸 Скриншот оплаты #{user_deposit['id']}"
        )
        
        # Создаем кнопку для подтверждения
        keyboard = [[
            InlineKeyboardButton("✅ Подтвердить оплату", callback_data=f"confirm_{user_deposit['id']}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"✅ Скриншот получен от клиента #{user_deposit['id']}",
            reply_markup=reply_markup
        )
        
        logger.info(f"✅ Скриншот от клиента #{user_deposit['id']} отправлен в группу")
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки скриншота: {e}")

# ========== ПОДТВЕРЖДЕНИЕ ОПЛАТЫ ==========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("confirm_"):
        deposit_id = int(query.data.split("_")[1])
        
        # Проверяем админа
        if query.from_user.id not in ADMIN_IDS:
            await query.answer("❌ Только администратор", show_alert=True)
            return
        
        # Ищем заявку
        deposit = None
        for d in deposits:
            if d['id'] == deposit_id:
                deposit = d
                break
        
        if not deposit:
            await query.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        # Обновляем статус
        deposit['status'] = 'completed'
        deposit['confirmed_by'] = query.from_user.first_name
        deposit['confirmed_time'] = datetime.now().strftime("%H:%M:%S")
        
        # Обновляем сообщение в группе
        await query.edit_message_text(
            f"✅ <b>ПЛАТЕЖ ПОДТВЕРЖДЕН #{deposit_id}</b>\n\n"
            f"👤 Клиент: {deposit['user_name']}\n"
            f"💰 Сумма: {deposit['amount']} TMT\n"
            f"👨‍💼 Подтвердил: {query.from_user.first_name}",
            parse_mode='HTML'
        )
        
        # Сообщаем клиенту
        try:
            await context.bot.send_message(
                chat_id=deposit['user_id'],
                text=f"🎉 <b>Счет пополнен!</b>\n\n"
                     f"💰 Сумма: {deposit['amount']} TMT\n"
                     f"🆔 Заявка: #{deposit_id}",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки клиенту: {e}")

# ========== ОТМЕНА ==========
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено")
    return ConversationHandler.END

# ========== ЗАПУСК ТЕЛЕГРАМ БОТА ==========
def run_bot():
    """Запуск Telegram бота"""
    print("🤖 Начинаем запуск бота...")
    
    # Создаем новый event loop для этого потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        # ConversationHandler для клиента
        conv_handler = ConversationHandler(
            entry_points=[
                MessageHandler(filters.Regex("^💰 Пополнить счет$"), handle_deposit_button)
            ],
            states={
                WAITING_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_id)
                ],
                WAITING_AMOUNT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount)
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel)]
        )
        
        # Обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(conv_handler)
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Обработчик группы
        application.add_handler(MessageHandler(
            filters.TEXT & filters.Chat(chat_id=GROUP_CHAT_ID) & ~filters.COMMAND,
            handle_group_text
        ))
        
        print("=" * 70)
        print("🤖 БОТ ЗАПУЩЕН НА RENDER!")
        print("=" * 70)
        print(f"Токен: {BOT_TOKEN[:15]}...")
        print(f"Группа ID: {GROUP_CHAT_ID}")
        print(f"Админ ID: {ADMIN_IDS}")
        print("=" * 70)
        
        # Запускаем бота
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ Ошибка запуска бота: {e}")
        logger.error(f"Ошибка запуска бота: {e}")

# ========== HTTP СЕРВЕР ДЛЯ PING ==========
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Telegram Bot is running on Render!"

@app.route('/health')
def health():
    return "✅ OK"

@app.route('/ping')
def ping():
    return "🏓 Pong!"

def run_flask():
    """Запуск Flask сервера"""
    app.run(host='0.0.0.0', port=10000, debug=False, use_reloader=False)

# ========== ОСНОВНОЙ ЗАПУСК ==========
def main():
    """Главная функция запуска"""
    print("🚀 Запуск приложения...")
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Небольшая задержка для запуска Flask
    time.sleep(2)
    
    # Запускаем бота в основном потоке
    run_bot()

if __name__ == '__main__':
    main()
