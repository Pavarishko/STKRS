import os
import tempfile
import subprocess
import logging
import asyncio
import ffmpeg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from config import TOKEN

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()


class Form(StatesGroup):
    waiting_photo = State()
    waiting_video_gif = State()
    waiting_video_sticker = State()


basic_sticker_button_name = "🖼 Обычный стикер"
anime_sticker_button_name = "✨ Анимированный стикер"
gif_button_name = "📸 GIF"
help_button_name = "ℹ️ Помощь"
back_button_name = "🔙 Назад"


def main_menu_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text=basic_sticker_button_name),
        types.KeyboardButton(text=anime_sticker_button_name)
    )
    builder.row(
        types.KeyboardButton(text=gif_button_name),
        types.KeyboardButton(text=help_button_name)
    )
    return builder.as_markup(resize_keyboard=True)


def back_button():
    return types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text=back_button_name)]],
        resize_keyboard=True
    )


@dp.message(F.text == back_button_name)
@dp.message(Command("start"))
async def return_to_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard()
    )
    logger.info(f"User {message.from_user.id} returned to main menu")


@dp.message(F.text == help_button_name)
@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📚 Доступные команды:\n\n"
        "/start - Главное меню\n"
        "/help - Эта справка\n\n"
        "Выберите действие:\n"
        "🖼 Обычный стикер\n"
        "✨ Анимированный стикер\n"
        "📸 GIF"
    )
    await message.answer(help_text, reply_markup=main_menu_keyboard())


@dp.message(F.text == gif_button_name)
async def create_gif_handler(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_video_gif)
    await message.answer(
        "📤 Отправьте видео для GIF (до 15 секунд)",
        reply_markup=back_button()
    )
    logger.info(f"User {message.from_user.id} selected GIF creation")


@dp.message(F.text == basic_sticker_button_name)
async def create_sticker_handler(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_photo)
    await message.answer(
        "📸 Отправьте фото для стикера",
        reply_markup=back_button()
    )
    logger.info(f"User {message.from_user.id} selected static sticker")


@dp.message(F.text == anime_sticker_button_name)
async def create_animated_sticker_handler(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_video_sticker)
    await message.answer(
        "🎥 Отправьте видео для стикера (до 3 секунд)",
        reply_markup=back_button()
    )
    logger.info(f"User {message.from_user.id} selected animated sticker")


async def cleanup_temp_files(*paths):
    """Удаляет временные файлы"""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Удален временный файл: {path}")
            except Exception as e:
                logger.error(f"Ошибка удаления файла {path}: {str(e)}")


@dp.message(Form.waiting_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    try:
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, 'photo.jpg')
            output_path = os.path.join(tmp_dir, 'sticker.webp')

            await bot.download_file(file.file_path, input_path)

            subprocess.run([
                'ffmpeg', '-i', input_path,
                '-vf', 'scale=512:512:force_original_aspect_ratio=increase,crop=512:512',
                '-y', output_path
            ], check=True)

            with open(output_path, 'rb') as f:
                await message.answer_sticker(BufferedInputFile(f.read(), 'sticker.webp'))

        await message.answer("✅ Стикер успешно создан!", reply_markup=main_menu_keyboard())
        logger.info(f"User {message.from_user.id} created static sticker")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown error"
        logger.error(f"FFmpeg error: {error_msg}")
        await message.answer("❌ Ошибка при создании стикера", reply_markup=main_menu_keyboard())

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=main_menu_keyboard())

    finally:
        await state.clear()


@dp.message(Form.waiting_video_gif, F.video | F.document)
async def handle_video_gif(message: Message, state: FSMContext):
    try:
        if message.video:
            file_id = message.video.file_id
        else:
            file_id = message.document.file_id

        file = await bot.get_file(file_id)

        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, 'video.mp4')
            output_path = os.path.join(tmp_dir, 'animation.gif')
            palette_path = os.path.join(tmp_dir, 'palette.png')

            await bot.download_file(file.file_path, input_path)

            subprocess.run([
                'ffmpeg', '-i', input_path,
                '-vf', 'fps=18,scale=480:-1:flags=lanczos,palettegen',
                '-y', palette_path
            ], check=True)

            subprocess.run([
                'ffmpeg', '-i', input_path, '-i', palette_path,
                '-filter_complex', 'fps=18,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse',
                '-t', '10', '-loop', '0', '-y', output_path
            ], check=True)

            with open(output_path, 'rb') as f:
                await message.answer_animation(BufferedInputFile(f.read(), 'animation.gif'))

            logger.info(f"User {message.from_user.id} created GIF")

        await message.answer("✅ GIF успешно создан!", reply_markup=main_menu_keyboard())

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else "Unknown error"
        logger.error(f"FFmpeg error: {error_msg}")
        await message.answer("❌ Ошибка при создании GIF", reply_markup=main_menu_keyboard())

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=main_menu_keyboard())

    finally:
        await state.clear()


@dp.message(Form.waiting_video_sticker, F.video | F.video_note | F.document)
async def handle_video_input(message: Message, state: FSMContext):
    """Обработка входящего видео"""
    temp_files = []
    try:
        # Определение типа входящего медиа
        if message.video_note:
            media = message.video_note
            media_type = "video_note"
        elif message.video:
            media = message.video
            media_type = "video"
        else:
            if not (message.document and message.document.mime_type.startswith('video/')):
                await message.answer("❌ Пожалуйста, отправьте видео файл")
                return
            media = message.document
            media_type = "document"

        logger.info(f"Получен {media_type} от пользователя {message.from_user.id}")

        # Проверка длительности
        if media.duration > 3:
            await message.answer("❌ Видео должно быть короче 3 секунд")
            return

        # Скачивание файла
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = os.path.join(tmp_dir, "input.mp4")
            output_path = os.path.join(tmp_dir, "output.webm")
            temp_files.extend([input_path, output_path])

            file = await bot.get_file(media.file_id)
            await bot.download_file(file.file_path, destination=input_path)
            logger.info(f"Файл сохранен в {input_path}")

            # Параметры FFmpeg
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # Перезапись без подтверждения
                '-i', input_path,
                '-t', '3',  # Ограничение длительности
                '-c:v', 'libvpx-vp9',  # Кодек для WebM
                '-b:v', '500k',  # Битрейт
                '-crf', '30',  # Качество
                '-an',  # Без звука
                '-loop', '0',  # Бесконечный цикл
            ]

            # Обработка видеокружков
            if media_type == "video_note":
                ffmpeg_cmd += [
                    '-vf', (
                        'scale=512:512:force_original_aspect_ratio=increase,'
                        'crop=512:512,'
                        'format=rgba,'
                        'geq=alpha=if(gt(sqrt((X-256)^2+(Y-256)^2),230),0,255)'
                    )
                ]
            else:
                ffmpeg_cmd += [
                    '-vf', 'scale=512:512:force_original_aspect_ratio=increase,crop=512:512'
                ]

            ffmpeg_cmd.append(output_path)

            # Запуск конвертации
            logger.info(f"Запуск FFmpeg: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30  # Таймаут 30 секунд
            )

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    ffmpeg_cmd,
                    output=result.stdout,
                    stderr=result.stderr
                )

            # Проверка размера файла
            file_size = os.path.getsize(output_path)
            logger.info(f"Размер выходного файла: {file_size} байт")
            if file_size > 256 * 1024:
                raise ValueError(f"Размер файла {file_size} байт превышает лимит Telegram")

            # Отправка стикера
            with open(output_path, 'rb') as f:
                await message.answer_sticker(
                    BufferedInputFile(f.read(), filename="sticker.webm")
                )
            logger.info("Стикер успешно отправлен")

    except subprocess.TimeoutExpired:
        logger.error("Таймаут обработки видео")
        await message.answer("⌛ Слишком долгая обработка, попробуйте более короткое видео")
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка FFmpeg: {e.stderr}")
        await message.answer("❌ Ошибка обработки видео. Проверьте формат файла")
    except ValueError as e:
        logger.error(f"Ошибка валидации: {str(e)}")
        await message.answer("❌ Слишком большой размер файла после конвертации")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {str(e)}", exc_info=True)
        await message.answer("❌ Произошла непредвиденная ошибка")
    finally:
        await cleanup_temp_files(*temp_files)
        await state.clear()


@dp.message()
async def handle_other_messages(message: Message):
    """Обработчик прочих сообщений"""
    await message.answer(
        "Используйте кнопки меню для взаимодействия с ботом",
        reply_markup=main_menu_keyboard()
    )


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())