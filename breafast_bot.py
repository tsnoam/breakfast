#!/usr/bin/env python

from telegram import ReplyKeyboardMarkup, ReplyKeyboardHide, TelegramError
from telegram.ext import Updater, MessageHandler, Filters, CommandHandler, Job
import argparse
from configparser import ConfigParser
from datetime import datetime
from FunnyMessagesBucketToml import MessagesBucket

WILL_JOIN_OPTIONS = ['Here', '7:30', '8:00', '8:30', '9:00', '9:30']
WONT_MAKE_IT = ['Won\'t make it']


class EtaChat(object):
    token = None
    chat_id = None
    timeout = None
    custom_keyboard = None
    reply_markup = None

    def __init__(self,
                 messages_toml,
                 token,
                 chat_id,
                 admin_chat_id,
                 start_time,
                 end_time,
                 active_days,
                 reject_users):
        self.token = token
        self.chat_id = chat_id
        self.admin_chat_id = admin_chat_id
        self.start_time = start_time.split(':')
        self.end_time = end_time.split(':')
        self.active_days = [int(n) for n in active_days.split(',')]
        self.reject_users = reject_users

        self._startTimeInt = int(self.start_time[0]) * 60 + int(self.start_time[1])
        self._endTimeInt = int(self.end_time[0]) * 60 + int(self.end_time[1])

        self.funny_message_bucket = MessagesBucket(messages_toml)

        self.eta_collection_on = False
        _now = datetime.now()
        _nowTimeInt = int(_now.hour) * 60 + int(_now.minute)
        self.is_active_time_interval = False
        if self._startTimeInt <= _nowTimeInt <= self._endTimeInt:
            self.is_active_time_interval = True
            self.eta_collection_on = True

        self.eta_dict = dict()

        self.updater = Updater(self.token)

        self.custom_keyboard = [WILL_JOIN_OPTIONS[:1],
                                WILL_JOIN_OPTIONS[1:4],
                                WILL_JOIN_OPTIONS[4:],
                                WONT_MAKE_IT]
        self.reply_markup = ReplyKeyboardMarkup(self.custom_keyboard,
                                                one_time_keyboard=True)

        self.updater.dispatcher.add_handler(CommandHandler('start', self.command_start))
        self.updater.dispatcher.add_handler(CommandHandler('help', self.command_help))
        self.updater.dispatcher.add_handler(CommandHandler('begin', self.command_begin))
        self.updater.dispatcher.add_handler(CommandHandler('end', self.command_end))
        self.updater.dispatcher.add_handler(CommandHandler('send', self.command_send))
        self.updater.dispatcher.add_handler(MessageHandler([Filters.text], self.message_received))
        self.updater.dispatcher.add_handler(MessageHandler([Filters.sticker, Filters.photo], self.sticker_received))

    @staticmethod
    def _send_message(bot,
                      chat_id,
                      message_content):
        try:
            bot.send_message(chat_id,
                             text=message_content,
                             parse_mode='Markdown')
        except TelegramError:
            # should do a log here
            pass

    @staticmethod
    def _send_sticker(bot,
                      chat_id,
                      sticker_id):
        try:
            bot.send_sticker(chat_id,
                             sticker_id)
        except TelegramError:
            # Log should go here
            pass

    @staticmethod
    def _time_string_to_int(_time_string):
        _split_time = _time_string.split(':')
        return int(_split_time[0]) * 60 + int(_split_time[1])

    @staticmethod
    def _time_int_to_string(_time_int):
        _hours = _time_int / 60
        _minutes = _time_int % 60

        return '{:02d}:{:02d}'.format(_hours, _minutes)

    def send_funny_message(self, bot, chat_id, funny_message):
        message_type, message_content = self.funny_message_bucket.get_random_message(funny_message)
        if message_type == 'text':
            self._send_message(bot,
                               chat_id,
                               message_content)
        elif message_type == 'sticker':
            self._send_sticker(bot,
                               chat_id,
                               message_content)
        elif message_type == 'error':
            self._send_message(bot,
                               self.admin_chat_id,
                               message_content)

    def do_begin_eta_collection(self):
        if not self.eta_collection_on:
            try:
                self.updater.bot.send_message(self.chat_id,
                                              text=self.funny_message_bucket.get_random_message('ask_for_eta')[1],
                                              reply_markup=self.reply_markup)
            except TelegramError:
                pass

        self.eta_collection_on = True

    def do_end_eta_collection(self):
        _message_to_display = ''
        if self.eta_collection_on:
            _wont_make_it = dict()
            _will_make_it = dict()

            for key, value in self.eta_dict.iteritems():
                if value['text'] in WONT_MAKE_IT:
                    _wont_make_it[key] = value
                else:
                    _will_make_it[key] = value

            if len(_will_make_it) > 1:
                _recommended_time_for_breakfast = 0
                _format_string = '*{}* ({})\n'
                _message_to_display += self.funny_message_bucket.get_random_message('done_collecting_eta')[1] + '\n'
                for key, value in _will_make_it.iteritems():
                    _recommended_time_for_breakfast += EtaChat._time_string_to_int(_time_string=
                                                                                   '07:30' if value['text'] == 'Here'
                                                                                   else value['text'])
                    _message_to_display += _format_string.format(value['first_name'] + ' ' + value['last_name'],
                                                                 value['text'])

                # Let's check if the recommended time is before now, and if so say now :)
                _recommended_time_string = 'NOW!'
                _recommended_time_for_breakfast /= len(_will_make_it)
                if _recommended_time_for_breakfast > self._endTimeInt:
                    _recommended_time_string = self._time_int_to_string(_recommended_time_for_breakfast)

                    # Set a reminder for breakfast
                    def breakfast_alarm(bot):
                        self.send_funny_message(bot=bot,
                                                chat_id=self.chat_id,
                                                funny_message='time_for_breakfast')

                    _set_timer_for = (_recommended_time_for_breakfast - self._endTimeInt) * 60
                    self.updater.job_queue.put(breakfast_alarm,
                                               _set_timer_for,
                                               repeat=False)

                _message_to_display += '\n*Recommended Breakfast time: {}*'.format(_recommended_time_string)
            elif len(_will_make_it) == 1:
                _message_to_display += self.funny_message_bucket.get_random_message('only_one_answered')[1] + '\n'
                _message_to_display += '*{}*, they could still join later :)'.format(_will_make_it
                                                                                     .itervalues()
                                                                                     .next()
                                                                                     ['first_name'])
            else:
                _message_to_display += self.funny_message_bucket.get_random_message('no_one_answered')[1]

            if len(_wont_make_it) > 0:
                _message_to_display += '\n\n{}:\n'.format(self.funny_message_bucket.get_random_message('wont_make_it_and_voted')[1])
                for key, value in _wont_make_it.iteritems():
                    _message_to_display += '*{} {}*\n'.format(value['first_name'], value['last_name'])
            try:
                self.updater.bot.send_message(chat_id=self.chat_id,
                                              text=_message_to_display,
                                              parse_mode='Markdown',
                                              reply_markup=ReplyKeyboardHide())
            except TelegramError:
                pass

        self.eta_collection_on = False
        self.eta_dict.clear()

    def do_help(self, update):
        if update.message.chat.id == self.admin_chat_id:
            _help_message = '*/help* - _Display this help message_\n' \
                            '*/begin* - _Start collecting ETA_\n' \
                            '*/end* - _End ETA collection and display results_\n' \
                            '*/send <message>* - _Send a message to group_'

            try:
                self.updater.bot.send_message(chat_id=update.message.chat.id,
                                              text=_help_message,
                                              parse_mode='Markdown')
            except TelegramError:
                pass
        else:
            self.send_funny_message(self.updater.bot,
                                    update.message.chat.id,
                                    'you_are_not_my_master')

    def command_start(self, bot, update):
        _funny_message = None
        if update.message.chat.id == self.admin_chat_id:
            _funny_message = 'welcome_master'
        else:
            # is this Noam?
            if update.message.chat.username == 'tsnoam':
                _funny_message = 'respect_previous_creators'
            else:
                _funny_message = 'you_are_not_my_master'

            try:
                self.updater.bot.send_message(chat_id=self.admin_chat_id,
                                              text='Username ({} {} - @{}, chat_id = {}), '
                                                   'tried to contact me'.format(update.message.chat.first_name,
                                                                                update.message.chat.last_name,
                                                                                update.message.chat.username,
                                                                                update.message.chat_id))
            except TelegramError:
                pass

        if _funny_message is not None:
            self.send_funny_message(self.updater.bot,
                                    update.message.chat.id,
                                    _funny_message)

    def command_help(self, bot, update):
        self.do_help(update)

    def command_begin(self, bot, update):
        if update.message.chat.id == self.admin_chat_id:
            self.do_begin_eta_collection()

    def command_send(self, bot, update):
        if update.message.chat.id == self.admin_chat_id:
            self._send_message(bot,
                               self.chat_id,
                               update.message.text[5:])

    def command_end(self, bot, update):
        if update.message.chat.id == self.admin_chat_id:
            self.do_end_eta_collection()

    def message_received(self, bot, update):
        if update.message.chat_id == self.chat_id:
            if self.eta_collection_on:
                if update.message.from_user.id in self.eta_dict:
                    self.send_funny_message(self.updater.bot,
                                            self.chat_id,
                                            'no_double_votes')
                else:
                    # check if user is a rejected user
                    from_user = update.message.from_user
                    if from_user.username != '' and from_user.username in self.reject_users:
                        self.send_funny_message(self.updater.bot,
                                                update.message.chat.id,
                                                'you_can_not_vote')
                    elif update.message.text in WILL_JOIN_OPTIONS or update.message.text in WONT_MAKE_IT:
                        self.eta_dict[from_user.id] = {'id': from_user.id,
                                                       'first_name': from_user.first_name,
                                                       'last_name': from_user.last_name,
                                                       'text': update.message.text}
                    else:
                        self.send_funny_message(self.updater.bot,
                                                self.chat_id,
                                                'invalid_eta_input')
            else:
                self.send_funny_message(self.updater.bot,
                                        self.chat_id,
                                        'not_collecting_eta')

    def sticker_received(self, bot, update):
        if update.message.chat.id == self.admin_chat_id:
            _message_to_send = 'got a sticker: {}'.format(update.message.sticker.file_id)
            self._send_message(bot,
                               self.admin_chat_id,
                               _message_to_send)

    def run(self):
        def beep(bot, job):
            _now = datetime.now()
            _nowTimeInt = int(_now.hour) * 60 + int(_now.minute)

            if _now.isoweekday() not in self.active_days:
                # Not in the active day period
                return

            if self.is_active_time_interval:
                if self._startTimeInt <= _nowTimeInt <= self._endTimeInt:
                    pass
                else:
                    self.do_end_eta_collection()
                    self.is_active_time_interval = False
            else:
                if self._startTimeInt <= _nowTimeInt <= self._endTimeInt:
                    self.do_begin_eta_collection()
                    self.is_active_time_interval = True
                else:
                    pass

        job = Job(beep, 1, repeat=True, context=None)
        self.updater.job_queue.put(job)
        # Start the Bot
        self.updater.start_polling()

        self.send_funny_message(self.updater.bot,
                                self.admin_chat_id,
                                'bot_is_now_online')

        # Run the bot until the user presses Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT
        self.updater.idle()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--conf",
                        help="Configuration file")
    args = parser.parse_args()

    cfg = ConfigParser()
    cfg.read(args.conf)

    eta_chat = EtaChat(cfg.get('global', 'messages_toml'),
                       cfg.get('bot', 'token_id'),
                       cfg.getint('bot', 'chat_id'),
                       cfg.getint('bot', 'admin_chat_id'),
                       cfg.get('breakfast', 'start_time'),
                       cfg.get('breakfast', 'end_time'),
                       cfg.get('breakfast', 'active_days'),
                       cfg.get('breakfast', 'reject_users'))

    eta_chat.run()


if __name__ == '__main__':
    main()
