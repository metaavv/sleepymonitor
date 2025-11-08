import logging
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from database import Database
import config

# Настройка логирования с уменьшением спама
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, config.LOGGING_LEVEL)
)
# Уменьшаем логирование httpx
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database(config.DATABASE_NAME)

# Русские названия месяцев
MONTH_NAMES = {
    1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
    7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
}

def format_date_russian(target_date: date) -> str:
    """Форматирование даты на русском"""
    day = target_date.day
    month = MONTH_NAMES[target_date.month]
    return f"{day} {month}"

def get_day_name(target_date: date) -> str:
    """Получение названия дня (Сегодня/Вчера/Позавчера/Дата)"""
    today = date.today()
    
    if target_date == today:
        return "Сегодня"
    elif target_date == today - timedelta(days=1):
        return "Вчера"
    elif target_date == today - timedelta(days=2):
        return "Позавчера"
    else:
        return format_date_russian(target_date)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    try:
        user = update.effective_user
        db.add_user(user.id, user.username, user.first_name, user.last_name)
        
        welcome_text = """
🌙 Sleepy Monitor Bot.

Привет! Sleepy Tracker поможет записать свои данные сна. Бот записывает в вашу статистику из базы данных:
• 💤 Время засыпания и пробуждения
• ⏱️ Общая продолжительность сна строится на времени основного и дополнительного сна
• 🤒 Симптомы и самочувствие в течение дня

Доступные действия:
• Уснул - записать время засыпания
• Проснулся - записать время пробуждения  
• Симптом - добавить симптом/заметку о самочувствии
• Не спал - отметить день, как без сна
• История - просмотр всех записей
• Последние дни - быстрый доступ к недавним записям

Начните с записи времени засыпания или пробуждения!
        """
        
        await update.message.reply_text(
            welcome_text, 
            reply_markup=main_menu_keyboard(user.id)
            # Убрал parse_mode='Markdown' чтобы избежать ошибок разметки
        )
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при запуске бота")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на инлайн кнопки"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        if data == "sleep":
            await handle_sleep_time_request(query, context)
        elif data == "wake":
            await handle_wake_time_request(query, context)
        elif data == "sleep_now":
            await handle_sleep_now(query, user_id, context)
        elif data == "wake_now":
            await handle_wake_now(query, user_id, context)
        elif data == "sleep_confirm":
            await handle_sleep_confirm(query, user_id, context)
        elif data == "wake_confirm":
            await handle_wake_confirm(query, user_id, context)
        elif data == "no_sleep_confirm":
            await handle_no_sleep_confirm(query, user_id, context)
        elif data == "sleep_cancel":
            await handle_cancel(query, user_id, "засыпания")
        elif data == "wake_cancel":
            await handle_cancel(query, user_id, "пробуждения")
        elif data == "no_sleep_cancel":
            await handle_cancel(query, user_id, "отметки 'не спал'")
        elif data == "symptom":
            await handle_symptom_request(query, context)
        elif data == "no_sleep":
            await handle_no_sleep_request(query, context)
        elif data == "history":
            await show_history(query, user_id)
        elif data.startswith("recent_"):
            await handle_recent_day(query, user_id, data)
        elif data.startswith("day_"):
            await handle_day_details(query, user_id, data)
        elif data.startswith("delete_day_"):
            await handle_delete_day(query, user_id, data)
        elif data.startswith("delete_symptom_"):
            await handle_delete_symptom(query, user_id, data)
        elif data.startswith("add_sleep_"):
            await handle_add_sleep_request(query, context, data)
        elif data.startswith("edit_date_"):
            await handle_edit_date_request(query, context, data)
        elif data == "back_to_main":
            await show_main_menu(query, user_id)
        elif data == "back_to_history":
            await show_history(query, user_id)
            
    except Exception as e:
        logger.error(f"Error in button handler: {e}")
        try:
            await query.edit_message_text("❌ Произошла ошибка при обработке запроса")
        except:
            pass

async def handle_sleep_time_request(query, context):
    """Запрос времени засыпания с проверкой существующих данных"""
    user_id = query.from_user.id
    target_date = date.today()
    
    # Проверяем существующие данные
    existing_data = db.check_existing_sleep_data(user_id, target_date)
    
    context.user_data['awaiting_sleep_time'] = True
    context.user_data['action'] = 'sleep'
    context.user_data['existing_data'] = existing_data
    context.user_data['target_date'] = target_date
    
    message_text = "Введите время засыпания в формате ЧЧ:ММ (например, 23:30):\n\n"
    message_text += "Или введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ (например, 08.11.2025 23:30):\n\n"
    message_text += "Можно просто нажать '✅ Сейчас' для записи текущего времени\n\n"
    
    # Добавляем информацию о существующих данных
    if existing_data['exists']:
        message_text += "⚠️ **Существующие данные:**\n"
        if existing_data['sleep_time']:
            sleep_time = datetime.fromisoformat(existing_data['sleep_time']).strftime('%H:%M')
            message_text += f"• Засыпание: {sleep_time}\n"
        if existing_data['wake_time']:
            wake_time = datetime.fromisoformat(existing_data['wake_time']).strftime('%H:%M')
            message_text += f"• Пробуждение: {wake_time}\n"
        if existing_data['no_sleep']:
            message_text += "• День отмечен как 'Не спал'\n"
        if existing_data['total_sleep_minutes']:
            hours = existing_data['total_sleep_minutes'] // 60
            minutes = existing_data['total_sleep_minutes'] % 60
            message_text += f"• Время сна: {hours}ч {minutes}м\n"
        
        message_text += "\n⚠️ **Новая запись заменит существующие данные!**\n"
    
    keyboard = [
        [InlineKeyboardButton("✅ Сейчас", callback_data="sleep_now")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_wake_time_request(query, context):
    """Запрос времени пробуждения с проверкой существующих данных"""
    user_id = query.from_user.id
    target_date = date.today()
    
    # Проверяем существующие данные
    existing_data = db.check_existing_sleep_data(user_id, target_date)
    
    context.user_data['awaiting_wake_time'] = True
    context.user_data['action'] = 'wake'
    context.user_data['existing_data'] = existing_data
    context.user_data['target_date'] = target_date
    
    message_text = "Введите время пробуждения в формате ЧЧ:ММ (например, 07:00):\n\n"
    message_text += "Или введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ (например, 09.11.2025 07:00):\n\n"
    message_text += "Можно просто нажать '✅ Сейчас' для записи текущего времени\n\n"
    
    # Добавляем информацию о существующих данных
    if existing_data['exists']:
        message_text += "⚠️ **Существующие данные:**\n"
        if existing_data['sleep_time']:
            sleep_time = datetime.fromisoformat(existing_data['sleep_time']).strftime('%H:%M')
            message_text += f"• Засыпание: {sleep_time}\n"
        if existing_data['wake_time']:
            wake_time = datetime.fromisoformat(existing_data['wake_time']).strftime('%H:%M')
            message_text += f"• Пробуждение: {wake_time}\n"
        if existing_data['no_sleep']:
            message_text += "• День отмечен как 'Не спал'\n"
        if existing_data['total_sleep_minutes']:
            hours = existing_data['total_sleep_minutes'] // 60
            minutes = existing_data['total_sleep_minutes'] % 60
            message_text += f"• Время сна: {hours}ч {minutes}м\n"
        
        message_text += "\n⚠️ **Новая запись заменит существующие данные!**\n"
    
    keyboard = [
        [InlineKeyboardButton("✅ Сейчас", callback_data="wake_now")],
        [InlineKeyboardButton("↩️ Назад", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_no_sleep_request(query, context):
    """Запрос подтверждения для отметки 'не спал'"""
    user_id = query.from_user.id
    target_date = date.today()
    
    # Проверяем существующие данные
    existing_data = db.check_existing_sleep_data(user_id, target_date)
    
    context.user_data['action'] = 'no_sleep'
    context.user_data['existing_data'] = existing_data
    context.user_data['target_date'] = target_date
    
    message_text = "🚫 **Отметить день как 'Не спал'**\n\n"
    
    # Добавляем информацию о существующих данных
    if existing_data['exists']:
        message_text += "⚠️ **Существующие данные:**\n"
        if existing_data['sleep_time']:
            sleep_time = datetime.fromisoformat(existing_data['sleep_time']).strftime('%H:%M')
            message_text += f"• Засыпание: {sleep_time}\n"
        if existing_data['wake_time']:
            wake_time = datetime.fromisoformat(existing_data['wake_time']).strftime('%H:%M')
            message_text += f"• Пробуждение: {wake_time}\n"
        if existing_data['no_sleep']:
            message_text += "• День уже отмечен как 'Не спал'\n"
        if existing_data['total_sleep_minutes']:
            hours = existing_data['total_sleep_minutes'] // 60
            minutes = existing_data['total_sleep_minutes'] % 60
            message_text += f"• Время сна: {hours}ч {minutes}м\n"
        
        message_text += "\n⚠️ **Это действие удалит все существующие данные о сне!**\n\n"
    
    message_text += "Вы уверены, что хотите отметить день как 'Не спал'?"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, отметить", callback_data="no_sleep_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="no_sleep_cancel")
        ]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_sleep_now(query, user_id, context):
    """Подтверждение записи текущего времени засыпания"""
    current_time = datetime.now()
    existing_data = context.user_data.get('existing_data', {})
    
    message_text = f"🕐 **Новое время засыпания:** {current_time.strftime('%H:%M %d.%m.%Y')}\n\n"
    
    if existing_data.get('exists'):
        message_text += "⚠️ **Существующие данные:**\n"
        if existing_data.get('sleep_time'):
            sleep_time = datetime.fromisoformat(existing_data['sleep_time']).strftime('%H:%M')
            message_text += f"• Засыпание: {sleep_time}\n"
        if existing_data.get('wake_time'):
            wake_time = datetime.fromisoformat(existing_data['wake_time']).strftime('%H:%M')
            message_text += f"• Пробуждение: {wake_time}\n"
        if existing_data.get('no_sleep'):
            message_text += "• День отмечен как 'Не спал'\n"
        
        message_text += "\n⚠️ **Новая запись заменит существующие данные!**\n\n"
    
    message_text += "Подтвердите запись:"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="sleep_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="sleep_cancel")
        ]
    ]
    
    context.user_data['pending_time'] = current_time
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_wake_now(query, user_id, context):
    """Подтверждение записи текущего времени пробуждения"""
    current_time = datetime.now()
    existing_data = context.user_data.get('existing_data', {})
    
    message_text = f"🕐 **Новое время пробуждения:** {current_time.strftime('%H:%M %d.%m.%Y')}\n\n"
    
    if existing_data.get('exists'):
        message_text += "⚠️ **Существующие данные:**\n"
        if existing_data.get('sleep_time'):
            sleep_time = datetime.fromisoformat(existing_data['sleep_time']).strftime('%H:%M')
            message_text += f"• Засыпание: {sleep_time}\n"
        if existing_data.get('wake_time'):
            wake_time = datetime.fromisoformat(existing_data['wake_time']).strftime('%H:%M')
            message_text += f"• Пробуждение: {wake_time}\n"
        if existing_data.get('no_sleep'):
            message_text += "• День отмечен как 'Не спал'\n"
        
        message_text += "\n⚠️ **Новая запись заменит существующие данные!**\n\n"
    
    message_text += "Подтвердите запись:"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="wake_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="wake_cancel")
        ]
    ]
    
    context.user_data['pending_time'] = current_time
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_sleep_confirm(query, user_id, context):
    """Подтверждение записи засыпания"""
    sleep_time = context.user_data.get('pending_time')
    target_date = context.user_data.get('target_date', sleep_time.date() if sleep_time else date.today())
    
    success = db.record_sleep(user_id, sleep_time, target_date)
    
    if success:
        time_str = sleep_time.strftime('%H:%M %d.%m.%Y')
        await query.edit_message_text(
            f"✅ Записал время засыпания: {time_str}",
            reply_markup=main_menu_keyboard(user_id)
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка при записи засыпания",
            reply_markup=main_menu_keyboard(user_id)
        )
    
    # Очищаем временные данные
    context.user_data.pop('pending_time', None)
    context.user_data.pop('existing_data', None)
    context.user_data.pop('target_date', None)

async def handle_wake_confirm(query, user_id, context):
    """Подтверждение записи пробуждения"""
    wake_time = context.user_data.get('pending_time')
    target_date = context.user_data.get('target_date', wake_time.date() if wake_time else date.today())
    
    success = db.record_wake(user_id, wake_time, target_date)
    
    if success:
        time_str = wake_time.strftime('%H:%M %d.%m.%Y')
        await query.edit_message_text(
            f"✅ Записал время пробуждения: {time_str}",
            reply_markup=main_menu_keyboard(user_id)
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка при записи пробуждения",
            reply_markup=main_menu_keyboard(user_id)
        )
    
    # Очищаем временные данные
    context.user_data.pop('pending_time', None)
    context.user_data.pop('existing_data', None)
    context.user_data.pop('target_date', None)

async def handle_no_sleep_confirm(query, user_id, context):
    """Подтверждение отметки 'не спал'"""
    target_date = context.user_data.get('target_date', date.today())
    
    success = db.record_no_sleep(user_id, target_date)
    
    if success:
        await query.edit_message_text(
            "✅ День отмечен как 'Не спал'",
            reply_markup=main_menu_keyboard(user_id)
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка при отметке дня без сна",
            reply_markup=main_menu_keyboard(user_id)
        )
    
    # Очищаем временные данные
    context.user_data.pop('existing_data', None)
    context.user_data.pop('target_date', None)

async def handle_cancel(query, user_id, action_name):
    """Отмена действия"""
    await query.edit_message_text(
        f"❌ Действие ({action_name}) отменено",
        reply_markup=main_menu_keyboard(user_id)
    )

async def handle_symptom_request(query, context):
    """Запрос симптома"""
    context.user_data['awaiting_symptom'] = True
    await query.edit_message_text(
        "Опишите симптом или самочувствие:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="back_to_main")]])
    )

async def handle_recent_day(query, user_id, data):
    """Обработка просмотра recent дня"""
    day_index = int(data.split("_")[1])
    recent_days = db.get_recent_days(user_id, days_count=3)
    
    if day_index >= len(recent_days):
        await query.edit_message_text(
            "❌ Нет данных за этот день",
            reply_markup=main_menu_keyboard(user_id)
        )
        return
    
    day_data = recent_days[day_index]
    await show_day_summary(query, user_id, day_data['date'], day_data['summary'])

async def handle_day_details(query, user_id, data):
    """Обработка просмотра деталей дня"""
    day_str = data[4:]  # format: YYYY-MM-DD
    try:
        target_date = datetime.strptime(day_str, '%Y-%m-%d').date()
        summary = db.get_day_summary(user_id, target_date)
        await show_day_summary(query, user_id, target_date, summary)
    except ValueError:
        await query.edit_message_text(
            "❌ Ошибка формата даты",
            reply_markup=main_menu_keyboard(user_id)
        )

async def handle_delete_day(query, user_id, data):
    """Обработка удаления дня"""
    day_str = data[11:]  # format: YYYY-MM-DD
    try:
        target_date = datetime.strptime(day_str, '%Y-%m-%d').date()
        success = db.delete_day(user_id, target_date)
        
        if success:
            await query.edit_message_text(
                f"✅ Все данные за {format_date_russian(target_date)} удалены",
                reply_markup=main_menu_keyboard(user_id)
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка при удалении данных",
                reply_markup=main_menu_keyboard(user_id)
            )
    except ValueError:
        await query.edit_message_text(
            "❌ Ошибка формата даты",
            reply_markup=main_menu_keyboard(user_id)
        )

async def handle_delete_symptom(query, user_id, data):
    """Обработка удаления симптома"""
    symptom_id = int(data[15:])  # format: delete_symptom_123
    success = db.delete_symptom(symptom_id)
    
    if success:
        await query.edit_message_text(
            "✅ Симптом удален",
            reply_markup=main_menu_keyboard(user_id)
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка при удалении симптома",
            reply_markup=main_menu_keyboard(user_id)
        )

async def handle_add_sleep_request(query, context, data):
    """Запрос данных для добавления сна"""
    day_str = data[10:]  # format: add_sleep_YYYY-MM-DD
    context.user_data['adding_sleep_for'] = day_str
    context.user_data['awaiting_sleep_time'] = True
    context.user_data['action'] = 'additional_sleep'
    
    await query.edit_message_text(
        "Введите время засыпания в формате ЧЧ:ММ (например, 14:30):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="back_to_main")]])
    )

async def handle_edit_date_request(query, context, data):
    """Запрос даты для редактирования"""
    context.user_data['editing_date'] = True
    await query.edit_message_text(
        "Введите дату в формате ДД.ММ.ГГГГ (например, 08.11.2025):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="back_to_main")]])
    )

async def show_history(query, user_id):
    """Показать историю дней"""
    days = db.get_user_days(user_id, limit=30)
    
    keyboard = []
    
    if not days:
        # Если история пуста, предлагаем добавить запись
        keyboard.extend([
            [InlineKeyboardButton("💤 Добавить сон за сегодня", callback_data="sleep")],
            [InlineKeyboardButton("🌅 Добавить пробуждение за сегодня", callback_data="wake")],
            [InlineKeyboardButton("🚫 Отметить 'не спал' за сегодня", callback_data="no_sleep")],
            [InlineKeyboardButton("✏️ Добавить запись за другую дату", callback_data="edit_date_")],
            [InlineKeyboardButton("↩️ Главное меню", callback_data="back_to_main")]
        ])
        
        await query.edit_message_text(
            "📊 История пуста\n\nЗаписей еще нет. Начните отслеживание сна!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Показываем существующие дни
    for day_date, has_data in days:
        if has_data:
            button_text = format_date_russian(day_date)
        else:
            button_text = f"{format_date_russian(day_date)} - Нет данных"
        
        callback_data = f"day_{day_date.strftime('%Y-%m-%d')}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    
    # Добавляем кнопки для добавления новых записей
    keyboard.extend([
        [InlineKeyboardButton("💤 Добавить сон за сегодня", callback_data="sleep")],
        [InlineKeyboardButton("🌅 Добавить пробуждение за сегодня", callback_data="wake")],
        [InlineKeyboardButton("✏️ Добавить запись за другую дату", callback_data="edit_date_")],
        [InlineKeyboardButton("↩️ Главное меню", callback_data="back_to_main")]
    ])
    
    await query.edit_message_text(
        "📊 История записей:\n\nВыберите день для просмотра деталей:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_day_summary(query, user_id, target_date, summary):
    """Отобразить сводку дня"""
    date_str = format_date_russian(target_date)
    
    text = f"🌙 **Сводка за {date_str}**\n\n"
    
    # Информация о сне
    if summary['no_sleep']:
        text += "🚫 **Не спал**\n"
        text += "⏱️ **Время сна:** 0ч 0м\n"
    else:
        if summary['sleep_time']:
            sleep_time = datetime.fromisoformat(summary['sleep_time'])
            text += f"💤 **Засыпание:** {sleep_time.strftime('%H:%M')}\n"
        else:
            text += f"💤 **Засыпание:** Нет данных\n"
        
        if summary['wake_time']:
            wake_time = datetime.fromisoformat(summary['wake_time'])
            text += f"🌅 **Пробуждение:** {wake_time.strftime('%H:%M')}\n"
        else:
            text += f"🌅 **Пробуждение:** Нет данных\n"
        
        # Показываем общее время сна (основной + дополнительные сны)
        if summary['total_sleep_all_minutes'] > 0:
            total_hours = summary['total_sleep_all_minutes'] // 60
            total_minutes = summary['total_sleep_all_minutes'] % 60
            text += f"⏱️ **Общее время сна:** {total_hours}ч {total_minutes}м\n"
            
            # Если есть основной сон, показываем его отдельно
            if summary['total_sleep_minutes']:
                main_hours = summary['total_sleep_minutes'] // 60
                main_minutes = summary['total_sleep_minutes'] % 60
                text += f"🌙 **Основной сон:** {main_hours}ч {main_minutes}м\n"
        elif summary['total_sleep_minutes']:
            hours = summary['total_sleep_minutes'] // 60
            minutes = summary['total_sleep_minutes'] % 60
            text += f"⏱️ **Время сна:** {hours}ч {minutes}м\n"
        else:
            text += f"⏱️ **Время сна:** Нет данных\n"
    
    # Дополнительные сны
    if summary['additional_sleeps']:
        text += f"\n😴 **Дополнительные сны:**\n"
        total_additional = 0
        for i, sleep in enumerate(summary['additional_sleeps'], 1):
            sleep_time = datetime.fromisoformat(sleep['sleep_time']).strftime('%H:%M')
            wake_time = datetime.fromisoformat(sleep['wake_time']).strftime('%H:%M')
            hours = sleep['sleep_minutes'] // 60
            minutes = sleep['sleep_minutes'] % 60
            text += f"{i}. {sleep_time} - {wake_time} ({hours}ч {minutes}м)\n"
            total_additional += sleep['sleep_minutes']
        
        if total_additional > 0:
            total_hours = total_additional // 60
            total_minutes = total_additional % 60
            text += f"**Всего доп. сон:** {total_hours}ч {total_minutes}м\n"
    
    # Информация о симптомах
    if summary['symptoms']:
        text += f"\n🤒 **Симптомы:**\n"
        for i, symptom in enumerate(summary['symptoms'], 1):
            text += f"{i}. {symptom['text']}\n"
    else:
        text += f"\n🤒 **Симптомы:** Нет записей\n"
    
    keyboard = [
        [InlineKeyboardButton("😴 Добавить сон", callback_data=f"add_sleep_{target_date}")],
        [InlineKeyboardButton("🗑️ Удалить день", callback_data=f"delete_day_{target_date}")],
        [InlineKeyboardButton("📊 История", callback_data="back_to_history")],
        [InlineKeyboardButton("↩️ Главное меню", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_main_menu(query, user_id):
    """Показать главное меню"""
    await query.edit_message_text(
        get_main_menu_text(),
        reply_markup=main_menu_keyboard(user_id),
        parse_mode='Markdown'
    )

def main_menu_keyboard(user_id):
    """Клавиатура главного меню"""
    recent_days = db.get_recent_days(user_id, days_count=3)
    
    # Создаем кнопки для последних дней
    recent_buttons = []
    for i in range(3):
        if i < len(recent_days):
            day_data = recent_days[i]
            day_name = get_day_name(day_data['date'])
            recent_buttons.append(InlineKeyboardButton(day_name, callback_data=f"recent_{i}"))
        else:
            # Заглушки если дней нет
            day_names = ["Сегодня", "Вчера", "Позавчера"]
            recent_buttons.append(InlineKeyboardButton(day_names[i], callback_data=f"recent_{i}"))
    
    keyboard = [
        [InlineKeyboardButton("📊 История", callback_data="history")],
        recent_buttons,
        [
            InlineKeyboardButton("💤 Уснул", callback_data="sleep"),
            InlineKeyboardButton("🌅 Проснулся", callback_data="wake"),
            InlineKeyboardButton("🤒 Симптом", callback_data="symptom")
        ],
        [InlineKeyboardButton("🚫 Не спал", callback_data="no_sleep")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_menu_text():
    """Текст главного меню"""
    return """
😴 **Трекер сна и самочувствия**

Выберите действие:
• 📊 История - просмотр всех записей
• Последние дни - быстрый доступ к недавним записям  
• 💤 Уснул - записать время засыпания
• 🌅 Проснулся - записать время пробуждения
• 🤒 Симптом - добавить симптом
• 🚫 Не спал - отметить день без сна
    """

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    try:
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        
        if context.user_data.get('awaiting_symptom'):
            # Обработка симптома
            symptom_text = message_text
            success = db.add_symptom(user_id, symptom_text)
            
            if success:
                await update.message.reply_text(
                    f"✅ Симптом записан: {symptom_text}",
                    reply_markup=main_menu_keyboard(user_id)
                )
            else:
                await update.message.reply_text(
                    "❌ Ошибка при записи симптома",
                    reply_markup=main_menu_keyboard(user_id)
                )
            
            context.user_data['awaiting_symptom'] = False
        
        elif context.user_data.get('awaiting_sleep_time'):
            # Обработка времени засыпания
            action = context.user_data.get('action', 'sleep')
            
            try:
                # Пробуем распарсить как время ЧЧ:ММ
                if len(message_text) <= 5 and ':' in message_text:
                    # Формат ЧЧ:ММ
                    time_obj = datetime.strptime(message_text, '%H:%M').time()
                    if action == 'sleep':
                        target_datetime = datetime.combine(date.today(), time_obj)
                        await handle_sleep_manual(update, user_id, target_datetime, context)
                    elif action == 'wake':
                        target_datetime = datetime.combine(date.today(), time_obj)
                        await handle_wake_manual(update, user_id, target_datetime, context)
                    elif action == 'additional_sleep':
                        day_str = context.user_data.get('adding_sleep_for')
                        target_date = datetime.strptime(day_str, '%Y-%m-%d').date()
                        target_datetime = datetime.combine(target_date, time_obj)
                        context.user_data['sleep_time'] = target_datetime
                        context.user_data['awaiting_sleep_time'] = False
                        context.user_data['awaiting_wake_time'] = True
                        await update.message.reply_text(
                            "Теперь введите время пробуждения в формате ЧЧ:ММ:",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Отмена", callback_data="back_to_main")]])
                        )
                else:
                    # Пробуем распарсить как дату и время ДД.ММ.ГГГГ ЧЧ:ММ
                    target_datetime = datetime.strptime(message_text, '%d.%m.%Y %H:%M')
                    if action == 'sleep':
                        await handle_sleep_manual(update, user_id, target_datetime, context)
                    elif action == 'wake':
                        await handle_wake_manual(update, user_id, target_datetime, context)
                    
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат. Используйте:\n• ЧЧ:ММ (например, 23:30)\n• ДД.ММ.ГГГГ ЧЧ:ММ (например, 08.11.2025 23:30)",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Отмена", callback_data="back_to_main")]])
                )
        
        elif context.user_data.get('awaiting_wake_time'):
            # Обработка времени пробуждения для дополнительного сна
            wake_time_str = message_text
            sleep_datetime = context.user_data.get('sleep_time')
            day_str = context.user_data.get('adding_sleep_for')
            
            try:
                wake_time = datetime.strptime(wake_time_str, '%H:%M').time()
                target_date = datetime.strptime(day_str, '%Y-%m-%d').date()
                wake_datetime = datetime.combine(target_date, wake_time)
                
                if wake_datetime <= sleep_datetime:
                    wake_datetime += timedelta(days=1)  # Если пробуждение на следующий день
                
                success = db.add_additional_sleep(user_id, sleep_datetime, wake_datetime, target_date)
                
                if success:
                    sleep_minutes = int((wake_datetime - sleep_datetime).total_seconds() / 60)
                    hours = sleep_minutes // 60
                    minutes = sleep_minutes % 60
                    
                    await update.message.reply_text(
                        f"✅ Дополнительный сон записан: {sleep_datetime.strftime('%H:%M')} - {wake_datetime.strftime('%H:%M')} ({hours}ч {minutes}м)",
                        reply_markup=main_menu_keyboard(user_id)
                    )
                else:
                    await update.message.reply_text(
                        "❌ Ошибка при записи дополнительного сна",
                        reply_markup=main_menu_keyboard(user_id)
                    )
                
                # Очищаем временные данные
                context.user_data.pop('sleep_time', None)
                context.user_data.pop('awaiting_wake_time', None)
                context.user_data.pop('adding_sleep_for', None)
                context.user_data.pop('action', None)
                
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат времени. Используйте ЧЧ:ММ (например, 15:45):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Отмена", callback_data="back_to_main")]])
                )
        
        elif context.user_data.get('editing_date'):
            # Обработка ввода даты для редактирования
            date_str = message_text
            
            try:
                target_date = datetime.strptime(date_str, '%d.%m.%Y').date()
                summary = db.get_day_summary(user_id, target_date)
                
                if any([summary['sleep_time'], summary['wake_time'], summary['no_sleep'], summary['symptoms'], summary['additional_sleeps']]):
                    await update.message.reply_text(
                        f"📊 Найдены записи за {format_date_russian(target_date)}:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📋 Просмотреть сводку", callback_data=f"day_{target_date}")],
                            [InlineKeyboardButton("↩️ Главное меню", callback_data="back_to_main")]
                        ])
                    )
                else:
                    await update.message.reply_text(
                        f"📊 Нет записей за {format_date_russian(target_date)}. Хотите добавить?",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("💤 Добавить сон", callback_data="sleep")],
                            [InlineKeyboardButton("🌅 Добавить пробуждение", callback_data="wake")],
                            [InlineKeyboardButton("🚫 Не спал", callback_data="no_sleep")],
                            [InlineKeyboardButton("🤒 Симптом", callback_data="symptom")],
                            [InlineKeyboardButton("↩️ Главное меню", callback_data="back_to_main")]
                        ])
                    )
                
                context.user_data['editing_date'] = False
                
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например, 08.11.2025):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Отмена", callback_data="back_to_main")]])
                )
        
        else:
            await update.message.reply_text(
                "Используйте кнопки меню для взаимодействия с ботом",
                reply_markup=main_menu_keyboard(user_id)
            )
            
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке сообщения")

async def handle_sleep_manual(update, user_id, sleep_time, context):
    """Подтверждение ручного ввода времени засыпания"""
    existing_data = context.user_data.get('existing_data', {})
    target_date = sleep_time.date()
    
    message_text = f"🕐 **Новое время засыпания:** {sleep_time.strftime('%H:%M %d.%m.%Y')}\n\n"
    
    if existing_data.get('exists'):
        message_text += "⚠️ **Существующие данные:**\n"
        if existing_data.get('sleep_time'):
            existing_sleep = datetime.fromisoformat(existing_data['sleep_time']).strftime('%H:%M')
            message_text += f"• Засыпание: {existing_sleep}\n"
        if existing_data.get('wake_time'):
            existing_wake = datetime.fromisoformat(existing_data['wake_time']).strftime('%H:%M')
            message_text += f"• Пробуждение: {existing_wake}\n"
        if existing_data.get('no_sleep'):
            message_text += "• День отмечен как 'Не спал'\n"
        
        message_text += "\n⚠️ **Новая запись заменит существующие данные!**\n\n"
    
    message_text += "Подтвердите запись:"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="sleep_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="sleep_cancel")
        ]
    ]
    
    context.user_data['pending_time'] = sleep_time
    context.user_data['target_date'] = target_date
    
    if isinstance(update, Update):
        await update.message.reply_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def handle_wake_manual(update, user_id, wake_time, context):
    """Подтверждение ручного ввода времени пробуждения"""
    existing_data = context.user_data.get('existing_data', {})
    target_date = wake_time.date()
    
    message_text = f"🕐 **Новое время пробуждения:** {wake_time.strftime('%H:%M %d.%m.%Y')}\n\n"
    
    if existing_data.get('exists'):
        message_text += "⚠️ **Существующие данные:**\n"
        if existing_data.get('sleep_time'):
            existing_sleep = datetime.fromisoformat(existing_data['sleep_time']).strftime('%H:%M')
            message_text += f"• Засыпание: {existing_sleep}\n"
        if existing_data.get('wake_time'):
            existing_wake = datetime.fromisoformat(existing_data['wake_time']).strftime('%H:%M')
            message_text += f"• Пробуждение: {existing_wake}\n"
        if existing_data.get('no_sleep'):
            message_text += "• День отмечен как 'Не спал'\n"
        
        message_text += "\n⚠️ **Новая запись заменит существующие данные!**\n\n"
    
    message_text += "Подтвердите запись:"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="wake_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="wake_cancel")
        ]
    ]
    
    context.user_data['pending_time'] = wake_time
    context.user_data['target_date'] = target_date
    
    if isinstance(update, Update):
        await update.message.reply_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

def main():
    """Запуск бота"""
    try:
        application = Application.builder().token(config.BOT_TOKEN).build()
        
        # Обработчики команд
        application.add_handler(CommandHandler("start", start))
        
        # Обработчики кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик текстовых сообщений
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Запуск бота
        print("Бот запущен...")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

if __name__ == '__main__':
    main()