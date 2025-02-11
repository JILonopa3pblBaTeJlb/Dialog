import logging
import random
import time
import asyncio
import requests
import os
import re
import json
import textwrap
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from bs4 import BeautifulSoup
from difflib import SequenceMatcher
from ollama import chat, ChatResponse
from aiogram.types import FSInputFile

# Конфигурация
TOKEN_BOT_2 = 'tokenbot2' #токен бота
PROXY_FILE = 'proxy.txt' #необходим, если вместо Ollama применяется g4f
CHANNEL_URL = 'https://t.me/YOURCHANNELNAME'#канал для хранения медиа (картинок)
LAST_POST_ID = 4 #Последний пост на канале
MEDIA_POST_PROBABILITY = 0.1 #Вероятность прицепления к посту медиа из канала
FRAGMENT_PROBABILITY = 0.2 #Вероятность прицепления к посту цитаты из романа
FRAGMENT_LENGTH = 1800 #длина цитаты
MIN_WAIT_TIME = 5 #ограничение минимума времени ожидания перед ответом ответа
MAX_WAIT_TIME = 10 #ограничение максимума времени ожидания перед ответом ответа
MAX_MESSAGE_LENGTH = 4096 #ограничение длины сообщения в Телеграме
SENT_FRAGMENTS_FILE = "sent_fragments.json" #учет посланных цитат романа
SENT_ARTICLES_FILE = "sent_articles.json" #учет посланных статей

# Логирование
logging.basicConfig(level=logging.DEBUG)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN_BOT_2)
dp = Dispatcher()

# Загрузка данных
with open("denial.txt", "r", encoding="utf-8") as denial_file:
    denial_lines = [line.strip() for line in denial_file.readlines()]
with open("goodrespond_ejik.txt", "r", encoding="utf-8") as goodrespond_file:
    good_respond_lines = [line.strip() for line in goodrespond_file.readlines()]
with open("great_russian_novell.txt", "r", encoding="utf-8") as novel_file:
    novel_text = novel_file.read()
with open("coarse.txt", "r", encoding="utf-8") as coarse_file:
    coarse_lines = [line.strip() for line in coarse_file.readlines()]

# Функция замены имён и существительных
def replace_names(text):

    # Словарь замен
    replacements = {
        r"\bиван\b|\bиован\b": "Йован",  # Заменяем "Иван" и "Иован" на "Йован"
        r"Иоvan": "Йован",
        r"\bнылить\b": "ныть",
        r"\bИду на вы\b": "Лолкек",
        r"\bИду на ты\b": "Пфффф",
        r"\bСвиноколбас Просвирнин\b": "интернет-деятель",
        r"\bИов": "Йован"
    }

    # Применяем замены
    for pattern, replacement in replacements.items():
        # Заменяем с учётом регистра и возможных знаков препинания
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text

# Вспомогательные функции
def call_local_model(prompt):
    """Вызов локальной модели для генерации текста."""
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
        
        # Замена имён сразу после получения ответа
        processed_response = replace_names(raw_response)
        logging.debug(f"Обработанный ответ: {processed_response}")
        return processed_response
    except Exception as e:
        logging.error(f"Ошибка при работе с локальной моделью: {e}")
        return None

def get_proxy_from_file():
    try:
        with open(PROXY_FILE, 'r') as file:
            proxy = file.read().strip()
            if proxy:
                logging.info(f"Using proxy: {proxy}")
                return proxy
            else:
                logging.info("Proxy file is empty, no proxy will be used.")
    except Exception as e:
        logging.warning(f"Failed to read proxy file: {e}")
    return None

def set_proxy(proxy):
    if proxy:
        os.environ['http_proxy'] = proxy
        os.environ['https_proxy'] = proxy
        logging.info(f"Proxy set: {proxy}")
    else:
        os.environ.pop('http_proxy', None)
        os.environ.pop('https_proxy', None)
        logging.info("No proxy is set.")

def initialize_sent_fragments_file():
    """Создаёт файл JSON для хранения последних отправленных фрагментов, если он не существует."""
    if not os.path.exists(SENT_FRAGMENTS_FILE):
        with open(SENT_FRAGMENTS_FILE, "w", encoding="utf-8") as file:
            json.dump([], file)
        logging.info(f"{SENT_FRAGMENTS_FILE} создан.")

def load_sent_fragments():
    """Загружает список отправленных фрагментов из JSON файла."""
    initialize_sent_fragments_file()
    with open(SENT_FRAGMENTS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def save_sent_fragments(sent_fragments):
    """Сохраняет обновлённый список отправленных фрагментов в JSON файл."""
    with open(SENT_FRAGMENTS_FILE, "w", encoding="utf-8") as file:
        json.dump(sent_fragments, file, ensure_ascii=False, indent=2)
def get_random_novel_fragment():
    """Выбирает случайный фрагмент романа, исключая недавно отправленные, и обновляет файл JSON."""
    novel_length = len(novel_text)
    total_fragments = novel_length // FRAGMENT_LENGTH
    if total_fragments == 0:
        logging.warning("Текст романа слишком короткий для разделения на фрагменты.")
        return "Роман недоступен."

    # Загружаем список отправленных фрагментов
    sent_fragments = load_sent_fragments()

    # Генерируем список доступных фрагментов
    available_fragments = [i for i in range(total_fragments) if i not in sent_fragments]

    if not available_fragments:
        logging.info("Все фрагменты были отправлены недавно. Сбрасываем историю.")
        sent_fragments = []
        save_sent_fragments(sent_fragments)
        available_fragments = list(range(total_fragments))

    # Выбираем случайный индекс фрагмента
    selected_index = random.choice(available_fragments)

    # Добавляем отправленный фрагмент в историю
    sent_fragments.append(selected_index)
    if len(sent_fragments) > 20:  # Ограничиваем длину истории
        sent_fragments.pop(0)

    save_sent_fragments(sent_fragments)

    # Извлекаем текст фрагмента
    start_index = selected_index * FRAGMENT_LENGTH
    end_index = min(start_index + FRAGMENT_LENGTH, novel_length)
    fragment = novel_text[start_index:end_index]

    # Обрезаем текст до границ предложений
    first_period = fragment.find(".") + 1
    last_period = fragment.rfind(".")
    if first_period > 0 and last_period > first_period:
        fragment = fragment[first_period:last_period].strip()

    return f"Вот, почитай мой роман:\n{fragment}"

def create_full_prompt(bot_prompt_file, previous_response_file):
    """Создает промпт с добавлением случайной строки из coarse.txt и фразой 'он сказал тебе:'."""
    with open(previous_response_file, 'r', encoding='utf-8') as file:
        previous_response = file.read()
    with open(bot_prompt_file, 'r', encoding='utf-8') as file:
        bot_prompt = file.read()
    
    # Выбор случайной строки из coarse.txt
    random_coarse_line = random.choice(coarse_lines)
    logging.debug(f"Random coarse line selected: {random_coarse_line}")
    
    # Формирование полного промпта
    return bot_prompt + "\n" + random_coarse_line + "\nон сказал тебе:" + previous_response

def load_articles():
    with open("egor.txt", "r", encoding="utf-8") as file:
        content = file.read()
    return content.split('&')

def initialize_sent_articles_file():
    """
    Создаёт файл JSON для хранения последних 20 отправленных номеров статей, если файла ещё нет.
    """
    if not os.path.exists(SENT_ARTICLES_FILE):
        with open(SENT_ARTICLES_FILE, "w", encoding="utf-8") as file:
            json.dump([], file)
        logging.info(f"{SENT_ARTICLES_FILE} создан.")

def load_sent_articles():
    """
    Загружает список последних отправленных номеров статей из файла JSON.
    """
    initialize_sent_articles_file()
    with open(SENT_ARTICLES_FILE, "r", encoding="utf-8") as file:
        return json.load(file)

def save_sent_articles(sent_articles):
    """
    Сохраняет обновлённый список последних отправленных номеров статей в файл JSON.
    """
    with open(SENT_ARTICLES_FILE, "w", encoding="utf-8") as file:
        json.dump(sent_articles, file, ensure_ascii=False, indent=2)

def get_random_article():
    """
    Выбирает случайный номер статьи, исключая последние 20 отправленных, и обновляет JSON-файл.
    Возвращает последние 1800 символов текста для `respond.txt` и путь к готовому файлу для Telegram.
    """
    articles = load_articles()
    total_articles = len(articles)
    if total_articles == 0:
        logging.warning("Список статей пуст. Нечего отправлять.")
        return "Нет доступных статей."

    # Загружаем список отправленных статей
    sent_articles = load_sent_articles()

    # Генерируем список доступных номеров статей
    available_numbers = [i for i in range(total_articles) if i not in sent_articles]

    if not available_numbers:
        logging.info("Все статьи отправлялись недавно. Сбрасываем историю.")
        sent_articles = []
        save_sent_articles(sent_articles)
        available_numbers = list(range(total_articles))

    # Выбираем случайный номер статьи
    selected_index = random.choice(available_numbers)

    # Обновляем JSON по принципу FIFO
    sent_articles.append(selected_index)
    if len(sent_articles) > 20:
        sent_articles.pop(0)  # Удаляем самый старый номер

    save_sent_articles(sent_articles)

    # Генерируем путь к файлу статьи
    article_number = f"{selected_index + 1:03d}"  # Форматируем номер статьи как 001, 002, ...
    article_file_path = f"articles/{article_number}.txt"

    # Читаем полный текст статьи из файла
    with open(article_file_path, "r", encoding="utf-8") as file:
        full_article = file.read().strip()

    # Для `respond.txt` берем последние 1800 символов
    last_respond_part = full_article[-1800:].strip()

    return last_respond_part, article_file_path

def get_random_channel_post():
    attempt = 0
    max_attempts = 20
    max_media_retries = 5  # Количество попыток для загрузки медиа
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
    }

    while attempt < max_attempts:
        post_number = random.randint(2, LAST_POST_ID)
        url = f"{CHANNEL_URL}/{post_number}"

        logging.info(f"Attempt {attempt + 1}: checking URL {url}")

        try:
            response = requests.get(url, headers=headers, proxies={'http': None, 'https': None})
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                meta_image = soup.find("meta", property="twitter:image")
                if meta_image and meta_image.get("content"):
                    media_url = meta_image["content"]
                    logging.info(f"Found media URL: {media_url}")

                    # Попытки загрузки медиа
                    for media_attempt in range(1, max_media_retries + 1):
                        try:
                            media_response = requests.get(media_url, timeout=10)
                            if media_response.status_code == 200:
                                logging.info(f"Media successfully fetched on attempt {media_attempt}")
                                return media_url  # Или media_response.content, если нужно вернуть данные
                            else:
                                logging.warning(f"Media fetch failed with status {media_response.status_code} on attempt {media_attempt}")
                        except Exception as e:
                            logging.error(f"Error fetching media on attempt {media_attempt}: {e}")
                        
                        if media_attempt < max_media_retries:
                            time.sleep(2)  # Задержка между попытками

                    logging.error(f"Failed to fetch media after {max_media_retries} attempts")
        except Exception as e:
            logging.error(f"Error fetching post: {e}")

        attempt += 1

    logging.error("Failed to fetch a valid post after max attempts")
    return None

async def attach_random_post(chat_id):
    post_url = get_random_channel_post()
    if post_url:
        await bot.send_photo(chat_id=chat_id, photo=post_url)
        logging.info(f"Post '{post_url}' was sent.")
    else:
        logging.info("Failed to fetch post.")

def normalize_text(text):
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def contains_denial(response):
    normalized_response = normalize_text(response)
    for denial in denial_lines:
        normalized_denial = normalize_text(denial)
        if normalized_denial in normalized_response or SequenceMatcher(None, normalized_denial, normalized_response).ratio() > 0.8:
            logging.info(f"Detected undesirable message: {denial.strip()}")
            return True
    return False



async def send_to_telegram(chat_id, response, add_content=True):
    # Убираем лишние пробелы
    response = response.strip()

    article_file_path = None  # Переменная для пути к файлу статьи
    if add_content and random.random() < FRAGMENT_PROBABILITY:
        if random.random() < 0.5:
            response += "\n" + get_random_novel_fragment()
        else:
            # Получаем текст для respond.txt и путь к файлу статьи
            last_respond_part, article_file_path = get_random_article()
            # Текст статьи больше не добавляем в response

    try:
        # Отправка чанков текста в Telegram
        for chunk in textwrap.wrap(response, MAX_MESSAGE_LENGTH, replace_whitespace=False):
            chunk = replace_names(chunk)  # Обработка текста перед отправкой
            try:
                await bot.send_message(chat_id=chat_id, text=chunk)
                logging.info(f"Chunk sent: {chunk[:50]}...")  # Логируем часть отправленного чанка
            except Exception as e:
                logging.error(f"Error sending chunk: {e}")
                await asyncio.sleep(5)  # Ждём перед повторной попыткой
                try:
                    await bot.send_message(chat_id=chat_id, text=chunk)
                except Exception as retry_error:
                    logging.critical(f"Retry failed for chunk: {retry_error}")
                    break  # Прекращаем отправку, если повторная попытка тоже не удалась

        # Если была выбрана статья, прикрепляем файл к сообщению
        if article_file_path:
            try:
                await bot.send_message(chat_id, "Вот, почитай мою статью:")
                input_file = FSInputFile(article_file_path)  # Используем FSInputFile для отправки файла
                await bot.send_document(chat_id, input_file)  # Отправляем файл как документ
                logging.info(f"Article file {article_file_path} sent to Telegram.")
            except Exception as e:
                logging.error(f"Failed to send article file: {e}")

        # Отправка случайного поста из канала с вероятностью
        if random.random() < MEDIA_POST_PROBABILITY:
            await attach_random_post(chat_id)
            logging.info("Random media post attached.")

    finally:
        if article_file_path:
            respond_content = last_respond_part  # Если статья была выбрана, используем ее текст
        else:
            respond_content = response[-2000:]  # В остальных случаях берем конец ответа

        with open("respond.txt", "w", encoding="utf-8") as respond_file:
            respond_file.write(f"bot2\n{respond_content}")
            logging.info("Queue switched to bot1 in respond.txt")
        
# Уточнение логики обработки ответа в процессе работы бота
async def bot2_process(chat_id):
    while True:
        proxy = get_proxy_from_file()
        set_proxy(proxy)

        # Ждём своей очереди
        while True:
            try:
                with open('respond.txt', 'r') as file:
                    lines = file.readlines()

                if lines[0].strip() == "bot1":
                    break
                else:
                    logging.info("Not bot2's turn, waiting...")
                    await asyncio.sleep(random.randint(30, 61))
            except Exception as e:
                logging.error(f"Error reading respond.txt: {e}")
                await asyncio.sleep(random.randint(30, 61))

        response = None
        start_time = time.time()
        full_prompt = create_full_prompt('bot2prompt.txt', 'respond.txt')

        while time.time() - start_time < 1800 and not response:
            try:
                response = call_local_model(full_prompt)
                if response and not contains_denial(response):
                    await send_to_telegram(chat_id, response, add_content=True)
                    break
                elif response and contains_denial(response):
                    response = random.choice(good_respond_lines)
                    await send_to_telegram(chat_id, response, add_content=True)
                    break
            except Exception as e:
                logging.error(f"Error generating response with local model: {e}")
                await asyncio.sleep(random.randint(30, 61))

        if not response:
            logging.info("No response from local model, using a good response.")
            response = random.choice(good_respond_lines)
            await send_to_telegram(chat_id, response, add_content=True)

        # Проверяем, действительно ли очередь переключена
        while True:
            try:
                with open('respond.txt', 'r') as file:
                    lines = file.readlines()

                if lines[0].strip() == "bot2":
                    logging.info("bot2 successfully switched to bot1, waiting for next turn.")
                    break
                else:
                    logging.warning("bot2 did not switch queue, retrying...")
                    await asyncio.sleep(5)
            except Exception as e:
                logging.error(f"Error verifying queue switch: {e}")
                await asyncio.sleep(5)

        # Пауза перед следующей итерацией
        await asyncio.sleep(random.randint(5, 10))
        
@dp.message(Command(commands=["start_bot2"]))
async def start(message: types.Message):
    saved_chat_id = get_saved_chat_id()
    if saved_chat_id:
        logging.info(f"Bot already started for chat_id: {saved_chat_id}")
        await message.reply("Бот уже запущен и работает.")
        asyncio.create_task(bot2_process(saved_chat_id))
    else:
        chat_id = message.chat.id
        logging.info(f"Received start command from chat_id: {chat_id}")
        await message.reply("Я Великий Русский Писатель!")

        with open("chatid.txt", "w") as file:
            file.write(str(chat_id))
        asyncio.create_task(bot2_process(chat_id))

def get_saved_chat_id():
    if os.path.exists("chatid.txt"):
        with open("chatid.txt", "r") as file:
            return int(file.read().strip())
    return None

async def main():
    saved_chat_id = get_saved_chat_id()
    if saved_chat_id:
        logging.info(f"Starting bot with saved chat_id: {saved_chat_id}")
        asyncio.create_task(bot2_process(saved_chat_id))
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
