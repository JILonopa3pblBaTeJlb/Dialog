import logging
import random
import time
import asyncio
import langdetect
import requests
import os
import re
import xml.etree.ElementTree as ET
import textwrap
from aiogram import Bot, Dispatcher
from ollama import chat, ChatResponse
from collections import deque

# Конфигурация
TOKEN_BOT_1 = 'tokenbot1' #токен бота
NEWS_URL = 'https://news.google.com/rss?hl=ru&gl=RU&ceid=RU:ru' #RSS источник новостей
NEWS_FETCH_INTERVAL = 3600  # Интервал обновления новостей
MIN_WAIT_TIME = 5 #ограничение минимума времени ожидания перед ответом ответа
MAX_WAIT_TIME = 10 #ограничение максимума времени ожидания перед ответом ответа
MAX_TELEGRAM_MESSAGE_SIZE = 4096  # Максимальный размер сообщения Telegram
latest_news = "" # Инициализация переменной
last_news_append_time = 0 # Инициализация другой переменной
OLD_NEWS_FILE = "oldnews.txt"  # Файл для хранения использованных новостей
RECENT_LINKS_QUEUE_SIZE = 100  # Настраиваемый размер очереди
recent_links = deque(maxlen=RECENT_LINKS_QUEUE_SIZE)
last_news_fetch_time = 0 # Инициализация таймера кулдауна для новостей
recent_jokes = deque(maxlen=1)  # Храним только последнюю шутку
jokes = []  # Инициализация пустого списка


# Логирование
logging.basicConfig(level=logging.DEBUG)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN_BOT_1)
dp = Dispatcher()

# Загрузка данных
logging.debug("Загружаем файлы denial.txt и goodrespond_jovan.txt")
with open("denial.txt", "r", encoding="utf-8") as denial_file:
    denial_lines = [line.strip() for line in denial_file.readlines()]
with open("goodrespond_jovan.txt", "r", encoding="utf-8") as goodrespond_file:
    good_respond_lines = [line.strip() for line in goodrespond_file.readlines()]

# Функция вызова локальной модели
def call_local_model(prompt):
    try:
        logging.debug(f"Вызов локальной модели с prompt: {prompt}")
        response: ChatResponse = chat(
            model='command-r',
            messages=[
                {'role': 'user', 'content': prompt}
            ]
        )
        raw_response = response.message.content
        logging.debug(f"Сырой ответ от локальной модели: {raw_response}")

        # Удаление кавычек, если они есть в начале и в конце
        if raw_response.startswith('"') and raw_response.endswith('"'):
            raw_response = raw_response[1:-1]

        # Замена имён сразу после получения текста
        processed_response = replace_names(raw_response)
        logging.debug(f"Обработанный ответ: {processed_response}")
        return processed_response
    except Exception as e:
        logging.error(f"Ошибка при работе с локальной моделью: {e}")
        return "Ошибка: не удалось получить ответ от локальной модели."

# Вспомогательные функции
def create_full_prompt(bot_prompt_file, previous_response_file):
    logging.debug(f"Создание полного prompt из файлов: {bot_prompt_file}, {previous_response_file}")

    # Чтение previous_response_file, начиная со второй строки
    with open(previous_response_file, 'r') as file:
        lines = file.readlines()
        previous_response = "".join(lines[1:])  # Пропускаем первую строку

    # Чтение bot_prompt_file полностью
    with open(bot_prompt_file, "r") as file:
        bot_prompt = file.read()

    # Формируем полный prompt
    full_prompt = bot_prompt + previous_response
    logging.debug(f"Сформированный prompt: {full_prompt}")
    return full_prompt

def load_jokes(file_path="jovan_jokes.txt"):
    """Загружает шутки из файла."""
    if not os.path.exists(file_path):
        logging.error(f"Файл {file_path} не найден.")
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            jokes = [line.strip() for line in file if line.strip()]
        logging.debug(f"Загружено {len(jokes)} шуток.")
        return jokes
    except Exception as e:
        logging.error(f"Ошибка при чтении файла {file_path}: {e}")
        return []
    
jokes = load_jokes("jovan_jokes.txt")

def get_random_joke(jokes):
    """Выбирает случайную шутку, избегая повторов подряд."""
    if not jokes:
        return None

    available_jokes = [joke for joke in jokes if joke not in recent_jokes]

    if not available_jokes:  # Если все шутки уже использованы
        logging.debug("Все шутки использованы, сбрасываем очередь.")
        recent_jokes.clear()  # Очищаем историю
        available_jokes = jokes  # Снова делаем все доступными

    selected_joke = random.choice(available_jokes)
    recent_jokes.append(selected_joke)  # Добавляем в историю
    return selected_joke

def split_message_into_chunks(message, chunk_size=MAX_TELEGRAM_MESSAGE_SIZE):
    logging.debug(f"Разделение сообщения на чанки размером {chunk_size} символов")
    chunks = textwrap.wrap(message, width=chunk_size)
    logging.debug(f"Чанков создано: {len(chunks)}")
    return chunks

def is_russian(text):
    logging.debug("Проверка языка текста")
    try:
        lang = langdetect.detect(text)
        is_ru = lang == 'ru'
        logging.debug(f"Результат: {is_ru}")
        return is_ru
    except Exception as e:
        logging.error(f"Ошибка при определении языка: {e}")
        return False

def replace_names(text):

    # Словарь замен
    replacements = {
        r"\bиван\b|\bиован\b|\bИоvan": "Йован",      
        r"\bигорь\b": "Егор",
        r"\bнылить\b": "ныть",
        r"\bЖорж\b": "Егор",          
        r"\bсвиноколбас просвирнин\b": "Свиноколбас Просвирнин[x]",
        r"\bИду на вы\b": "Ахпха!",
        r"\bИду на ты\b": "Ахах!",
        r"Йован Савович:": "Кек!",
        r"Йован:": "Кек!",
        r"\bжирный опять ноет": "жирный опять ноет[x]"
    }

    # Применяем замены
    for pattern, replacement in replacements.items():
        # Заменяем с учётом регистра и возможных знаков препинания
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    
    # Удаляем последовательности " " (кавычки, пробел, кавычки)
    text = re.sub(r'" "', '', text)

    # Убираем лишние пробелы
    text = " ".join(text.split())

    return text

def get_random_link(file_path="jovan_links.txt"):
    """Выбирает случайную ссылку из файла, избегая повторов."""
    if not os.path.exists(file_path):
        logging.error(f"Файл {file_path} не найден.")
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            links = [line.strip() for line in file if line.strip()]
        
        # Отфильтровываем недавно использованные ссылки
        available_links = [link for link in links if link not in recent_links]

        if not available_links:  # Если все ссылки уже были использованы
            logging.debug("Все ссылки были использованы, сбрасываем очередь.")
            recent_links.clear()  # Очищаем историю
            available_links = links  # Вновь делаем все ссылки доступными
        
        selected_link = random.choice(available_links)
        recent_links.append(selected_link)  # Добавляем в историю
        return selected_link
    except Exception as e:
        logging.error(f"Ошибка при чтении файла {file_path}: {e}")
        return None
    
def generate_telegram_post_link():
    """Генерирует случайное число для создания Telegram-ссылки, избегая повторов."""
    global recent_links
    max_posts = 2646  # Максимальное количество постов в канале
    available_posts = [num for num in range(1, max_posts + 1) if num not in recent_links]

    if not available_posts:  # Если все посты уже были использованы
        logging.debug("Все посты использованы, сбрасываем очередь.")
        recent_links.clear()  # Очищаем историю
        available_posts = list(range(1, max_posts + 1))  # Снова делаем все доступными

    selected_post = random.choice(available_posts)
    recent_links.append(selected_post)  # Добавляем в историю
    return f"https://t.me/jovanstuff/{selected_post}"

def load_old_news():
    """Загружает список использованных новостей из файла."""
    if not os.path.exists(OLD_NEWS_FILE):
        return set()
    with open(OLD_NEWS_FILE, "r", encoding="utf-8") as file:
        return {line.strip() for line in file.readlines()}

def save_old_news(news):
    """Перезаписывает файл oldnews.txt, заменяя старую новость на новую."""
    with open(OLD_NEWS_FILE, "w", encoding="utf-8") as file:
        file.write(news + "\n")

async def append_news_or_joke(response, current_news):
    """Добавляет новость или шутку к ответу, если это необходимо."""
    global last_news_append_time
    logging.debug("Проверка необходимости добавления новости или шутки")
    current_time = time.time()

    # Читаем последнюю новость из oldnews.txt
    old_news = load_old_news()

    # Вероятность добавить шутку
    if random.random() <= 0.05:
        joke = get_random_joke(jokes)
        if joke:
            response += f'\nСлушай анекдот: {joke}'
            logging.debug(f"Добавлена шутка: {joke}")
        return response

    # Добавление новости
    if (
        current_time - last_news_append_time > NEWS_FETCH_INTERVAL  # Интервал обновления новостей
        and current_news.lower() not in old_news  # Новость должна быть новой
        and current_news and current_news != "Новость недоступна"  # Проверка валидности новости
    ):
        response += f'\nКстати, слышал новость? {current_news}'
        last_news_append_time = current_time  # Обновляем время только при добавлении новости
        save_old_news(current_news)  # Перезаписываем файл с новой новостью
        logging.debug("Файл oldnews.txt перезаписан с новой новостью")
    
    return response

async def fetch_news_headline():
    """Получает заголовок последней новости из RSS-ленты."""
    logging.debug("Получение заголовка новости")
    try:
        response = requests.get(NEWS_URL)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        first_item = root.find('./channel/item/title').text
        logging.debug(f"Полученный заголовок новости: {first_item}")
        return first_item
    except Exception as e:
        logging.error(f"Ошибка при получении новостей: {e}")
        return None


# Основной процесс
async def bot1_process():
    global last_news_append_time

    # Добавляем переменную для отслеживания времени последней проверки новостей
    last_news_fetch_time = 0  # Время последней проверки новостей
    current_news = "Новость недоступна"  # Инициализируем текущую новость

    try:
        with open("chatid.txt", "r") as file:
            chat_id = int(file.read().strip())
    except Exception as e:
        logging.error(f"Ошибка при чтении chat_id: {e}")
        return

    logging.debug("bot1_process запущен")
    while True:
        logging.debug("Начало цикла обработки сообщений")
        current_time = time.time()

        # Проверяем, нужно ли обновить заголовок новости
        if current_time - last_news_fetch_time > NEWS_FETCH_INTERVAL:
            logging.debug("Проверяем RSS-ленту для обновления новости")
            current_news = await fetch_news_headline() or "Новость недоступна"
            last_news_fetch_time = current_time

        try:
            with open('respond.txt', 'r') as file:
                lines = file.readlines()
        except FileNotFoundError:
            logging.error("Файл respond.txt не найден")
            await asyncio.sleep(10)
            continue

        if not lines or lines[0].strip() != "bot2":
            logging.debug("Сейчас не очередь bot1, ждем...")
            await asyncio.sleep(random.randint(MIN_WAIT_TIME, MAX_WAIT_TIME))
            continue

        await asyncio.sleep(random.randint(MIN_WAIT_TIME, MAX_WAIT_TIME))
        full_prompt = create_full_prompt('bot1prompt.txt', 'respond.txt')
        response = call_local_model(full_prompt)

        if is_russian(response):
            response = await append_news_or_joke(response, current_news)

            if random.random() <= 0.1:
                if random.random() < 0.5:  # 50% вероятность выбрать ссылку из файла
                    random_link = get_random_link("jovan_links.txt")
                    if random_link:
                        response += f"\n\nВот почитай мой пост: {random_link}"
                else:  # 50% вероятность сгенерировать Telegram-ссылку
                    telegram_post_link = generate_telegram_post_link()
                    response += f"\n\nВот еще посмотри: {telegram_post_link}"

            # Запись ответа в файлы
            with open('respond.txt', 'w', encoding="utf-8") as respond_file:
                respond_file.write(f"bot1\n{response}")

            # Дописывание ответа в opera.txt
            # with open('opera.txt', 'a', encoding="utf-8") as opera_file:
            #     opera_file.write(f"\nЙован\n\n{response}\n\n")

            # Отправка ответа чанками в Telegram
            response_chunks = split_message_into_chunks(response)
            for chunk in response_chunks:
                logging.debug(f"Отправка чанка сообщения: {chunk}")
                await bot.send_message(chat_id=chat_id, text=chunk)

        # Убедиться, что цикл не продолжает после отправки сообщения
        await asyncio.sleep(random.randint(MIN_WAIT_TIME, MAX_WAIT_TIME))

async def main():
    """Запускает основной цикл бота."""
    logging.debug("Запуск основного цикла")
    asyncio.create_task(bot1_process())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
    
