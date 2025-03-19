import logging
import datetime
import os
import pandas as pd
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from aiogram.utils.exceptions import ChatNotFound

load_dotenv()

# Настройки бота
TOKEN = os.getenv("TOKEN")
ADMIN_IDS = {1331149682, 5303672650} # Список админов в виде множества {123456789, 987654321}
NOTIFICATION_CHAT_ID = os.getenv("NOTIFICATION_CHAT_ID")

event_date = "5 апреля"
event_price = 2300  # Установи свою цену билета
# Конфиг логирования
logging.basicConfig(level=logging.INFO)

db_file = "tickets.xlsx"

bot = Bot(token=TOKEN, timeout=30)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

accept_message = message = f"""
🎉 Оплата успешно подтверждена! 🎉

📍 Ждём тебя 5 апреля с 19:00 по адресу:  
Ольховская ул. 14с5 🏠🔥

🔹 Что взять с собой?  
   - 📌 Студенческий билет – для входа  
   - 📌 Паспорт – на всякий случай  
   - 📌 Отличное настроение – без него не пустим! 😉🎊  

💃 Будет много музыки, драйва и крутых впечатлений!  
🚀 Готовься к самой жаркой студенческой тусовке! 🔥  
"""


promo_codes = {
    "PROMO10": 10,
    "PROMO20": 20,
    "PROMO30": 30
}

# Определение состояний
class TicketOrder(StatesGroup):
    full_name = State()
    university = State()
    promo_code = State()
    confirm = State()
    age_confirmation = State() 

class AdminSetEvent(StatesGroup):
    date = State()
    price = State()
    confirmation = State()
    cancel_confirmation = State()
    deny_payment = State()
    cancel = State()

class AdminAddClient(StatesGroup):
    full_name = State()
    university = State()
    telegram_username = State()
    amount_paid = State()
    cancel = State()

# Клавиатуры
main_menu = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Купить билет"))
admin_menu = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("Изменить событие"),
    KeyboardButton("Получить таблицу"),
    KeyboardButton("Подтвердить заказ"),
    KeyboardButton("Отменить подтверждение"),
    KeyboardButton("Опровергнуть оплату"),
    KeyboardButton("Добавить клиента")
)
cancel_button = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Отмена"))

# Функции работы с Excel
def load_data():
    if not os.path.exists(db_file) or os.stat(db_file).st_size == 0:
        return pd.DataFrame(columns=["ФИО", "Учебное заведение", "Дата регистрации", "Подтверждение", "Оплачено", "Сумма", "Telegram Username", "Telegram ID"])
    return pd.read_excel(db_file, engine="openpyxl")

def save_data(df):
    df.to_excel(db_file, index=False)

# Функция для создания кнопок с именами пользователей
def create_user_buttons(users, page=0, per_page=5):
    markup = InlineKeyboardMarkup(row_width=1)
    start = page * per_page
    end = start + per_page
    for user in users[start:end]:
        markup.add(InlineKeyboardButton(user, callback_data=f"confirm_{user}"))
    if start > 0:
        markup.add(InlineKeyboardButton("⬅️ Назад", callback_data=f"page_{page-1}"))
    if end < len(users):
        markup.add(InlineKeyboardButton("➡️ Вперед", callback_data=f"page_{page+1}"))
    return markup

# Старт бота
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("Привет, Админ!", reply_markup=admin_menu)
    else:
        await message.answer(f"Привет! Ближайшая вечеринка {event_date}. Билет: {event_price}₽", reply_markup=main_menu)

# Обработка покупки билета
@dp.message_handler(lambda message: message.text == "Купить билет")
async def buy_ticket(message: types.Message):
    await message.answer("Введите ваше ФИО (три слова, каждое не длиннее 15 символов)")
    await TicketOrder.full_name.set()

@dp.message_handler(state=TicketOrder.full_name)
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    words = full_name.split()
    
    if len(words) != 3 or any(len(word) > 15 for word in words):
        await message.answer("Некорректный формат ФИО. Введите три слова, каждое не длиннее 15 символов.")
        return
    
    await state.update_data(full_name=full_name)
    await message.answer("Введите название вашего учебного заведения")
    await TicketOrder.university.set()

@dp.message_handler(state=TicketOrder.university)
async def process_university(message: types.Message, state: FSMContext):
    if len(message.text) > 25:
        await message.answer("Название учебного заведения должно быть не длиннее 25 символов. Попробуйте снова.")
        return
    
    await state.update_data(university=message.text)
    await message.answer("Введите промокод, если он у вас есть. Если нет, введите 'нет'.")
    await TicketOrder.promo_code.set()


@dp.message_handler(state=TicketOrder.promo_code)
async def process_promo_code(message: types.Message, state: FSMContext):
    promo_code = message.text.strip().upper()
    data = await state.get_data()
    full_name = data['full_name']
    university = data['university']
    timestamp = datetime.datetime.now().isoformat()

    discount = promo_codes.get(promo_code, 0)
    final_price = event_price - discount

    await state.update_data(promo_code=promo_code, final_price=final_price, discount=discount, timestamp=timestamp)

    # Отправляем пользователю данные для подтверждения
    await message.answer(
        "🔍 **Проверьте введенные данные:**\n\n"
        f"👤 **ФИО:** {full_name}\n"
        f"🏫 **Учебное заведение:** {university}\n"
        f"🎟 **Промокод:** {promo_code}\n"
        f"💰 **Скидка:** {discount}₽\n"
        f"🤑 **Итоговая цена:** {final_price}₽\n\n"
        "✅ Все верно?",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("Да", callback_data="confirm_yes"),
            InlineKeyboardButton("Изменить", callback_data="confirm_no")
        )
    )
    await TicketOrder.confirm.set()

@dp.callback_query_handler(lambda c: c.data == 'confirm_yes', state=TicketOrder.confirm)
async def confirm_data(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.send_message(
        callback_query.from_user.id,
        "Покупая билет, вы подтверждаете своё совершеннолетие. Продолжить?",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("Да", callback_data="age_confirm_yes"),
            InlineKeyboardButton("Отмена", callback_data="age_confirm_no")
        )
    )
    await TicketOrder.age_confirmation.set()

@dp.callback_query_handler(lambda c: c.data == 'age_confirm_yes', state=TicketOrder.age_confirmation)
async def age_confirm_yes(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    full_name = data['full_name']
    university = data['university']
    promo_code = data['promo_code']
    final_price = data['final_price']
    timestamp = data['timestamp']

    df = load_data()
    new_row = pd.DataFrame([{
        "ФИО": full_name,
        "Учебное заведение": university,
        "Дата регистрации": timestamp,
        "Подтверждение": "Ожидание",
        "Оплачено": "Нет",
        "Сумма": final_price,
        "Telegram Username": f"@{callback_query.from_user.username}" if callback_query.from_user.username else "N/A",
        "Telegram ID": callback_query.from_user.id
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    save_data(df)

    # Отправляем уведомление в чат
    total_tickets_sold = len(df[df["Оплачено"] == "Да"])
    total_earned = df[df["Оплачено"] == "Да"]["Сумма"].sum()
    await bot.send_message(
        NOTIFICATION_CHAT_ID,
        f"Новый заказ: {full_name} ({university}). Ожидает оплаты. Промокод: {promo_code}, Скидка: {data['discount']}₽, Итоговая цена: {final_price}₽.\n"
        f"Всего продано билетов: {total_tickets_sold}\n"
        f"Общая сумма заработка: {total_earned}₽"
    )
    await bot.send_document(NOTIFICATION_CHAT_ID, types.InputFile(db_file))

    await bot.send_message(callback_query.from_user.id, f"Переведите {final_price}₽ на реквизиты: 1234567890. После перевода сообщите админу.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'age_confirm_no', state=TicketOrder.age_confirmation)
async def age_confirm_no(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await bot.send_message(callback_query.from_user.id, "Действие отменено.", reply_markup=main_menu)

@dp.callback_query_handler(lambda c: c.data == 'confirm_no', state=TicketOrder.confirm)
async def change_data(callback_query: types.CallbackQuery):
    await bot.send_message(
        callback_query.from_user.id,
        "Что вы хотите изменить?",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("ФИО", callback_data="change_full_name"),
            InlineKeyboardButton("Учебное заведение", callback_data="change_university"),
            InlineKeyboardButton("Промокод", callback_data="change_promo_code")
        )
    )

@dp.callback_query_handler(lambda c: c.data.startswith('change_'), state=TicketOrder.confirm)
async def process_change_data(callback_query: types.CallbackQuery, state: FSMContext):
    change_field = callback_query.data.split('_')[1]
    if change_field == "full_name":
        await bot.send_message(callback_query.from_user.id, "Введите ваше ФИО (три слова, каждое не длиннее 15 символов)")
        await TicketOrder.full_name.set()
    elif change_field == "university":
        await bot.send_message(callback_query.from_user.id, "Введите название вашего учебного заведения")
        await TicketOrder.university.set()
    elif change_field == "promo_code":
        await bot.send_message(callback_query.from_user.id, "Введите промокод, если он у вас есть. Если нет, введите 'нет'.")
        await TicketOrder.promo_code.set()
@dp.message_handler(lambda message: message.text == "Подтвердить заказ" and message.from_user.id in ADMIN_IDS)
async def ask_for_order_confirmation(message: types.Message):
    df = load_data()
    pending_users = df[df["Подтверждение"] == "Ожидание"]["ФИО"].tolist()
    if not pending_users:
        await message.answer("Нет заказов, ожидающих подтверждения.")
        return
    markup = create_user_buttons(pending_users)
    await message.answer("Выберите заказ для подтверждения:", reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('page_'))
async def process_page_callback(callback_query: types.CallbackQuery):
    page = int(callback_query.data.split('_')[1])
    df = load_data()
    pending_users = df[df["Подтверждение"] == "Ожидание"]["ФИО"].tolist()
    markup = create_user_buttons(pending_users, page=page)
    await callback_query.message.edit_reply_markup(reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('confirm_'))
async def process_confirm_callback(callback_query: types.CallbackQuery):
    full_name = callback_query.data.split('_')[1]
    df = load_data()
    if full_name not in df["ФИО"].values:
        await callback_query.message.answer("Человек не найден в базе. Проверьте ФИО и попробуйте снова.")
        return
    
    df.loc[df["ФИО"] == full_name, ["Подтверждение", "Оплачено", "Сумма"]] = [
        datetime.datetime.now().isoformat(),
        "Да",
        event_price
    ]
    save_data(df)

    # Отправляем пользователю сообщение о подтверждении
    user_id = df.loc[df["ФИО"] == full_name, "Telegram ID"].values[0]
    try:
        await bot.send_message(user_id, f"{full_name}, {accept_message}")
        await bot.send_location(user_id, latitude=55.775170, longitude=37.669693)
    except ChatNotFound:
        await callback_query.message.answer(f"Не удалось отправить сообщение пользователю {full_name}. Чат не найден.")

    await callback_query.message.answer(f"Заказ для {full_name} подтвержден.", reply_markup=admin_menu)
    await callback_query.message.delete()

@dp.message_handler(lambda message: message.text == "Опровергнуть оплату" and message.from_user.id in ADMIN_IDS)
async def ask_for_payment_denial(message: types.Message, state: FSMContext):
    await message.answer("Введите ФИО участника, чей платеж хотите опровергнуть:", reply_markup=cancel_button)
    await AdminSetEvent.deny_payment.set()

@dp.message_handler(state=AdminSetEvent.deny_payment)
async def deny_order_payment(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.finish()
        await message.answer("Действие отменено.", reply_markup=admin_menu)
        return

    full_name = message.text.strip()

    df = load_data()
    if full_name not in df["ФИО"].values:
        await message.answer("Человек не найден в базе. Проверьте ФИО и попробуйте снова.", reply_markup=cancel_button)
        return
    
    df.loc[df["ФИО"] == full_name, ["Оплачено", "Сумма"]] = [
        "Нет",
        0
    ]
    save_data(df)

    # Отправляем пользователю сообщение об опровержении оплаты
    user_id = df.loc[df["ФИО"] == full_name, "Telegram ID"].values[0]
    await bot.send_message(user_id, f"{full_name}, ваш платеж был опровергнут.")

    await message.answer(f"Оплата заказа для {full_name} опровергнута.", reply_markup=admin_menu)

# Изменение события
@dp.message_handler(lambda message: message.text == "Изменить событие" and message.from_user.id in ADMIN_IDS)
async def change_event(message: types.Message):
    await message.answer("Введите новую дату мероприятия (пример: 5 апреля)", reply_markup=cancel_button)
    await AdminSetEvent.date.set()

@dp.message_handler(state=AdminSetEvent.date)
async def set_event_date(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.finish()
        await message.answer("Действие отменено.", reply_markup=admin_menu)
        return

    global event_date
    event_date = message.text
    await state.update_data(date=event_date)
    await message.answer("Введите новую цену билета", reply_markup=cancel_button)
    await AdminSetEvent.price.set()

@dp.message_handler(state=AdminSetEvent.price)
async def set_event_price(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.finish()
        await message.answer("Действие отменено.", reply_markup=admin_menu)
        return

    global event_price
    event_price = int(message.text)
    await state.finish()
    await message.answer(f"Дата мероприятия: {event_date}, цена билета: {event_price}₽", reply_markup=admin_menu)

# Получение Excel таблицы
@dp.message_handler(lambda message: message.text == "Получить таблицу" and message.from_user.id in ADMIN_IDS)
async def get_table(message: types.Message):
    db_file = "tickets.xlsx"

    # Проверяем, существует ли файл и не пуст ли он
    if not os.path.exists(db_file) or os.path.getsize(db_file) == 0:
        await message.answer("Файл с билетами пуст или не создан. Попробуйте добавить хотя бы одну запись.")
        return

    await message.answer_document(types.InputFile(db_file))

# Добавление клиента
@dp.message_handler(lambda message: message.text == "Добавить клиента" and message.from_user.id in ADMIN_IDS)
async def add_client(message: types.Message):
    await message.answer("Введите ФИО клиента (три слова, каждое не длиннее 15 символов)", reply_markup=cancel_button)
    await AdminAddClient.full_name.set()

@dp.message_handler(state=AdminAddClient.full_name)
async def process_client_full_name(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.finish()
        await message.answer("Действие отменено.", reply_markup=admin_menu)
        return

    full_name = message.text.strip()
    words = full_name.split()
    
    if len(words) != 3 or any(len(word) > 15 for word in words):
        await message.answer("Некорректный формат ФИО. Введите три слова, каждое не длиннее 15 символов.", reply_markup=cancel_button)
        return
    
    await state.update_data(full_name=full_name)
    await message.answer("Введите название учебного заведения клиента", reply_markup=cancel_button)
    await AdminAddClient.university.set()

@dp.message_handler(state=AdminAddClient.university)
async def process_client_university(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.finish()
        await message.answer("Действие отменено.", reply_markup=admin_menu)
        return

    if len(message.text) > 25:
        await message.answer("Название учебного заведения должно быть не длиннее 25 символов. Попробуйте снова.", reply_markup=cancel_button)
        return
    
    await state.update_data(university=message.text)
    await message.answer("Введите ник в Telegram клиента (например, @username)", reply_markup=cancel_button)
    await AdminAddClient.telegram_username.set()

@dp.message_handler(state=AdminAddClient.telegram_username)
async def process_client_telegram_username(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.finish()
        await message.answer("Действие отменено.", reply_markup=admin_menu)
        return

    telegram_username = message.text.strip()
    if telegram_username.startswith('@'):
        telegram_username = telegram_username[1:]
    await state.update_data(telegram_username=telegram_username)
    await message.answer("Введите сумму, которую клиент заплатил", reply_markup=cancel_button)
    await AdminAddClient.amount_paid.set()

@dp.message_handler(state=AdminAddClient.amount_paid)
async def process_client_amount_paid(message: types.Message, state: FSMContext):
    if message.text == "Отмена":
        await state.finish()
        await message.answer("Действие отменено.", reply_markup=admin_menu)
        return

    amount_paid = message.text.strip()
    data = await state.get_data()
    full_name = data['full_name']
    university = data['university']
    telegram_username = data['telegram_username']
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    df = load_data()
    new_row = pd.DataFrame([{
        "ФИО": full_name,
        "Учебное заведение": university,
        "Дата регистрации": timestamp,
        "Подтверждение": "Да",
        "Оплачено": "Да",

        "Сумма": amount_paid,
        "Telegram Username": f"@{telegram_username}",
        "Telegram ID": message.from_user.id
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    save_data(df)

    await message.answer(f"Клиент {full_name} добавлен в базу.", reply_markup=admin_menu)
    await state.finish()

# Запуск бота
if __name__ == '__main__':
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)