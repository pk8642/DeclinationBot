from telegram.ext import Updater, CallbackQueryHandler
from telegram.ext import MessageHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import requests
import lxml.html
from tabulate import tabulate
import os
import logging

try:
    TOKEN = os.environ['TOKEN_D']
except KeyError:
    TOKEN = open('/home/pk864/tokens/test_bot').read().strip()
updater = Updater(token=TOKEN, use_context=True)


def log_exceptions(f):
    def send_exception_message(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            update, context = args[0], args[1]
            p = update.effective_chat
            if update.callback_query:
                upd = update.callback_query
                text = upd.data
            else:
                upd = update.message
                text = upd.text
            upd.bot.send_message(
                chat_id=-1001304092645,
                text=f'{p.username}({p.first_name} {p.last_name}): '
                     f'"{text}"\nError: {e}'
            )

    return send_exception_message


def send_hello(update, context):
    welcome = 'Hello, type here some czech word, except adjectives and' \
              ' adverbs. Also type just 1 word, without particles'
    update.message.reply_text(text=welcome)


def get_el_text(e):
    if type(e) is str:
        return e
    elif e.text:
        if type(e.text) is str and len(e.text) > 0:
            return e.text
    else:
        try:
            t = e.getchildren()[0].text
            if type(t) is str and len(t) > 0:
                return t
        except IndexError:
            pass
    return ' '


def assembly_message(table, start, end, keys=()):
    a = []
    for i in range(start, end):
        b = []
        for j in range(len(table[i])):
            e = get_el_text(table[i][j])
            b.append(e)
            b[j] = b[j].replace('. pád', '')
            b[j] = b[j].replace('. osoba', '')
            b[j] = b[j].replace('rozkazovací způsob', 'imperativ')
            b[j] = b[j].replace('příčestí činné', 'minulý č.')
            b[j] = b[j].replace('příčestí trpné', 'participium')
            b[j] = b[j].replace('přechodník přítomný', 'př.přít.')
            b[j] = b[j].replace('verbální substantivum', 'verb. subs.')
            b[j] = b[j].replace('přechodník minulý', 'př.min.')
            if start != 1 and j == 0:
                b[j] += ':'
            elif j != 0:
                b[j] = b[j].replace(', ', '\n')
        a.append(b)
    if not keys:
        keys = "firstrow"
    result = tabulate(a, headers=keys)
    if start == 1:
        return result + '\n\n'
    return result + '\n'


def find_gender(page):
    vars = page.find_class('polozky')
    genders = ['m. neživ.', 'm. živ.', 's.', 'ž.']
    for var in vars:
        for gender in genders:
            if gender in var.text:
                return var.text
    return ''


def form_message(page):
    table = page.xpath('//tr')
    keys = [' ', 'sing', 'plur']
    try:
        if 'pád' in table[1][0].text:  # noun nebo zaimeno

            gender = find_gender(page)
            message = gender + '\n\n'
            return message + assembly_message(table, 1, len(table), keys)
        elif 'osoba' in table[1][0].text:
            message = assembly_message(table, 1, 4, keys)  # verb
            for i in range(4, len(table) - 1):
                message += assembly_message(table, i, i + 1)
            return message
    except IndexError:
        pass


@log_exceptions
def send_message(update, context, message):
    if message:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f'`{message}`', parse_mode='MarkdownV2')
    else:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Didn\'t find anything about this :-(')


@log_exceptions
def get_links_by_id(update, next_links):
    keyboard = []
    links = next_links.xpath('//table/tr/td//a')
    for link in links:
        text = ''
        try:
            if link.tail:
                text += link.tail
            else:
                try:
                    text += link[0].tail
                except IndexError:
                    pass
        except TypeError:
            pass
        try:
            text = f'{get_el_text(link[0])}{text}'
        except IndexError:
            text = f'{get_el_text(link)}{text}'
            lines = link.getparent().getparent().getnext()
            for line in lines:
                try:
                    text += ' ' + line.text
                except IndexError:
                    text += ' ' + line[0].text
        keyboard.append([InlineKeyboardButton(
            text,
            callback_data=link.get('href'))])
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        next_links.getparent().text + '\n',
        reply_markup=reply_markup)


@log_exceptions
def get_links_by_class(update, next_links):
    keyboard = []
    for link in next_links:
        keyboard.append([InlineKeyboardButton(
            f"{link.xpath('a')[0].text}{link[0].tail}",
            callback_data=link.xpath('a')[0].get('href'))])
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        update.message.reply_text(
            next_links[0].getparent().text + '\n',
            reply_markup=reply_markup)
    except (AttributeError, IndexError):
        pass


@log_exceptions
def try_form_table(update, context, word, cb=None):
    target = 'https://prirucka.ujc.cas.cz'
    if cb:
        params = word.split('&')[0][(len(target)) + 2:]
    else:
        params = f'slovo={word.lower()}'
    request = requests.get(target, params=params)
    page = lxml.html.document_fromstring(request.text.split('<hr')[0])
    next_links = []
    try:
        next_links = page.find_class('odsazeno')
        get_links_by_class(update, next_links)
    except (KeyError, IndexError):
        try:
            next_links = page.get_element_by_id('dalsiz')
            get_links_by_id(update, next_links)
        except KeyError:
            pass
    finally:
        if len(next_links) == 0:
            message = ''
            try:
                message += page.find_class('ks')[0].getchildren()[
                               0].text + '\n'
            except IndexError:
                send_message(update, context, '')
                return
            try:
                message += form_message(page)
            except TypeError:
                pass
            send_message(update, context, message)


@log_exceptions
def callback_query_handler(bot, update):
    bot.effective_message.delete()
    try_form_table(bot, update, bot.callback_query.data, True)


@log_exceptions
def handle_message(update, context):
    message = update.effective_message.text
    if message == '/start':
        send_hello(update, context)
    elif update.effective_message.text != '/start' and \
            update.effective_message.text.startswith('/'):
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='You can start this bot by comand /start')
    elif len(message.split()) > 1:
        context.bot.send_message(
            chat_id=update.effective_chat.id,
            text='Please, type 1 word')
    else:
        try_form_table(update, context, message)


def main():
    message_handler = MessageHandler(Filters.text, handle_message)
    updater.dispatcher.add_handler(message_handler)
    command_handler = MessageHandler(Filters.command, handle_message)
    updater.dispatcher.add_handler(command_handler)
    updater.dispatcher.add_handler(
        CallbackQueryHandler(callback_query_handler))
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
