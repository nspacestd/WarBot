from datetime import datetime
import threading
import time
import shelve
import argparse
import os.path
import dbm

import requests

from invasion import Invasion
from alert import Alert
from deal import Deal


class WarBot:

    TOKEN = 'your token here'
    API_URL = 'https://api.telegram.org/bot' + TOKEN + '/'

    INVASION_URL = 'https://deathsnacks.com/wf/data/invasion.json'
    ALERT_URL = 'https://deathsnacks.com/wf/data/last15alerts_localized.json'
    DEAL_URL = 'http://deathsnacks.com/wf/data/daily_deals.json'

    NOTIFICATION_INTERVAL = 900
    TIMEOUT = 5

    USAGE = (
                'Warframe alert and invasion bot v0.2 by @nspacestd\n\n'
                'Usage:\n'
                '/help - Show this\n'
                '/alerts - Show current filtered alerts\n'
                '/alerts all - Show all current alerts\n'
                '/invasions - Show current filtered invasions\n'
                '/invasions all - Show all current invasions\n'
                '/darvo - Show current daily deals\n'
                '/notify [on|off] turn notifications on/off'
            )

    def __init__(self, reward_path, state_path):

        # Path to file containing rewards to filter
        self.reward_path = reward_path

        # IDs of chats with active notifications
        self.notification_chats = []
        
        # IDs of notified alerts and invasions
        self.notified_alerts = []
        self.notified_invasions = []

        # Read saved program state
        try:
            with shelve.open(state_path, flag='r') as f:
                self.notification_chats = f['chats']
                self.notified_alerts = f['alerts']
                self.notified_invasions = f['invasions']
        except dbm.error:
            print('State file not found, defaulting to empty')
            self.notification_chats = []
            self.notified_alerts = []
            self.notified_invasions = []
        except KeyError:
            print('Bad state file, defaulting to empty')
            self.notification_chats = []
            self.notified_alerts = []
            self.notified_invasions = []

        # Event that starts or stops notifications
        self.notifications = threading.Event()

        # Notifications are inactive by default
        self.notifications.clear()

        # Lock for notification_chats
        self.notification_lock = threading.Lock()

        # Lock for reward_filter
        self.reward_lock = threading.Lock()

        # Path to file for saving program state
        self.state_path = state_path

        # When set to True application closes
        self.close = False

        # Load reward filter from file
        self.load_rewards()

    def load_rewards(self):
        """ Load reward filter from file specified in self.reward_path

        """
        # Read rewards from file, one per line
        # Lines starting with '#' and blank lines are ignored
        with self.reward_lock:
            with open(self.reward_path) as f:
                self.reward_filter = list(filter(
                    lambda l: l and not l.startswith('#'),
                    (line.strip() for line in f)))

    def run(self):
        """ Run the bot and wait for user to manually stop it
        At exit save chats with active notifications

        """

        # Spawn new thread for main messaging loop
        threading.Thread(target=self.loop).start()

        # Spawn new thread for notifier, and set it to daemon mode
        t = threading.Thread(target=self.notifier)
        t.daemon = True
        t.start()

        if self.notification_chats:
            self.notifications.set()

        print('WarBot is running')
        print('[Q]: Quit [R]: Reload rewards file')

        s = ''

        try:
            while s.lower() != 'q':
                s = input()
                if s.lower() == 'r':
                    self.load_rewards()

        except EOFError:
            print('EOF received, quitting')

        self.close = True
        self.save_state()

    def loop(self):
        """ Main loop, polls telegram servers for updates

        """

        # offset should be one higher than the highest received update_id
        offset = 0

        # Main loop
        while not self.close:
            p = {'timeout': WarBot.TIMEOUT, 'offset': offset}
            r = None

            try:
                r = requests.post(WarBot.API_URL + 'getUpdates', params=p).json()
            except ValueError:
                print('Invalid JSON from Telegram API')
                time.sleep(2)
                continue
            except requests.ConnectionError as e:
                print('Error connecting to API server: ', e)
                time.sleep(2)
                continue

            if r and r['ok']:
                for update in r['result']:
                    if update['update_id'] >= offset:
                        offset = update['update_id'] + 1
                    if 'message' in update and 'text' in update['message']:
                        try:
                            self.bot(update['message'])
                        except RuntimeError as e:
                            print(e)

    def bot(self, message):
        """ Answers received messages

        Parameters
        ----------
        message : str
            Textual content of received message
        """

        text = message['text']
        chat_id = message['chat']['id']

        if '/help' in text:
            self.send(chat_id, WarBot.USAGE)

        elif '/alerts' in text:
            if '/alerts all' in text:
                self.send(chat_id, self.get_alert_string(True))
            else:
                self.send(chat_id, self.get_alert_string(False))

        elif '/invasions' in text:
            if '/invasions all' in text:
                self.send(chat_id, self.get_invasion_string(True))
            else:
                self.send(chat_id, self.get_invasion_string(False))
        
        elif '/darvo' in text:
            self.send(chat_id, self.get_deals_string())

        elif '/notify' in text:
            if '/notify on' in text:
                self.set_notifications(chat_id, True)
            elif '/notify off' in text:
                self.set_notifications(chat_id, False)

    def send(self, recipient, message):
        """Send a message to a specified user or group

        Parameters
        ----------

        recipient : int
            Id of recipient
        message : str
            Message to be sent

        """
        p = {'chat_id': recipient, 'text': message}
        requests.post(WarBot.API_URL + 'sendMessage', params=p)

    def get_alerts(self):
        """Returns a list of Alert objects containing the last 15 alerts
        Throws RuntimeError in case of a bad response

        """
        
        alert_data = None
        r = requests.get(WarBot.ALERT_URL)

        # Raise an exception in case of a bad response
        if not r.status_code == requests.codes.ok:
            raise RuntimeError('Bad response from ' + WarBot.ALERT_URL)

        # Response.json() might raise ValueError
        try:
            alert_data = r.json()
        except ValueError as e:
            raise RuntimeError('Bad JSON from ' + WarBor.ALERT_URL) from e

        # Raise an exception in case of an empty response
        if not alert_data:
            raise RuntimeError('Empty response from ' + WarBot.ALERT_URL)

        return [Alert(d) for d in alert_data]

    def get_invasions(self):
        """ Returns a list of Invasion objects containing all active
        invasions
        Throws RuntimeError in case of a bad response

        """
        invasion_data = None
        r = requests.get(WarBot.INVASION_URL)

        # Raise an exception in case of a bad response
        if not r.status_code == requests.codes.ok:
            raise RuntimeError('Bad response from ' + WarBot.INVASION_URL)

        # Response.json() might raise ValueError
        try:
            invasion_data = r.json()
        except ValueError as e:
            raise RuntimeError('Bad JSON from ' + WarBot.INVASION_URL) from e

        # Raise an exception in case of an empty response
        if not invasion_data:
            raise RuntimeError('Empty response from ' + WarBot.INVASION_URL)

        return [Invasion(d) for d in invasion_data]

    def get_deals(self):
        """ Returns a list of Deal objects containing all active
        daily deals
        Throws RuntimeError in case of a bad response

        """

        deal_data = None
        r = requests.get(WarBot.DEAL_URL)

        # Raise an exception in case of a bad response
        if not r.status_code == requests.codes.ok:
            raise RuntimeError('Bad response from ' + WarBot.DEAL_URL)

        # Response.json() might raise ValueError
        try:
            deal_data = r.json()
        except ValueError as e:
            raise RuntimeError('Bad JSON from ' + WarBot.DEAL_URL) from e

        # Raise an exception in case of an empty response
        if not deal_data:
            raise RuntimeError('Empty response from ' + WarBot.DEAL_URL)

        return [Deal(d) for d in deal_data]

    def get_alert_string(self, show_all):
        """ Returns a string with all current alerts

        Parameters
        ----------
        show_all : bool
            Whether or not to show all alerts or only filtered ones

        """

        alert_string = ''
        alerts = self.get_alerts()

        for a in alerts:

            # We only need current alerts
            if a.expiry < datetime.now():
                break

            if show_all or self.filter_rewards(a.get_rewards()):
                alert_string += str(a) + '\n\n'

        if not alert_string:
            if not show_all:
                alert_string = 'No filtered alerts'
            else:
                alert_string = 'No alerts'

        return alert_string

    def get_invasion_string(self, show_all):
        """ Returns a string with all current invasions

        Parameters
        ----------
        show_all : bool
            Whether or not to show all invasions or only filtered ones
        """

        invasion_string = ''
        invasions = self.get_invasions()

        for i in invasions:
            if show_all or self.filter_rewards(i.get_rewards()):
                invasion_string += str(i) + '\n\n'

        if not invasion_string:
            if not show_all:
                invasion_string = 'No filtered invasions'
            else:
                invasion_string = 'No invasions'

        return invasion_string

    def get_deals_string(self):
        """ Returns a string with all current daily deals

        """

        deal_string = ""
        deals = self.get_deals()

        for d in deals:
            deal_string += str(d) + '\n\n'

        if not deal_string:
            deal_string = 'No deals'

        return deal_string

    def filter_rewards(self, rewards):
        """ Returns True if at least one reward is contained in the
        filter

        Parameters
        ----------
        rewards : List of str objects
            List of rewards for an alert or invasion

        """
        with self.reward_lock:
            return any(i in self.reward_filter for i in rewards)

    def set_notifications(self, chat_id, enable):
        """ Enables or disables reward notifications for a specified
        chat

        Parameters
        ----------
        chat_id : int
            ID of specified chat
        enable : bool
            Whether to enable or disable notifications for the
            specified chat

        """

        if enable:
            if chat_id not in self.notification_chats:
                # Acquire lock on notification_chats and add new chat to it
                with self.notification_lock:
                    self.notification_chats.append(chat_id)

                # Start notifier if needed
                if not self.notifications.is_set():
                    self.notifications.set()

                # Send confirmation to user
                self.send(chat_id, 'Notifications enabled')
            else:
                self.send(chat_id, 'Notifications are already enabled')
        else:
            if chat_id in self.notification_chats:
                # Remove chat_id from notification_chats
                with self.notification_lock:
                    self.notification_chats.remove(chat_id)

                # Stop notifier if there are no chats with
                # active notifications
                if not self.notification_chats:
                    self.notifications.clear()

                # Send confirmation to user
                self.send(chat_id, 'Notifications disabled')
            else:
                self.send(chat_id, 'Notifications are already disabled')


    def notifier(self):
        """ Runs in a separate thread and checks alerts and invasions every
        NOTIFICATION_INTERVAL seconds. Those with rewards that are in the
        filter are notified to all chats in notification_chats

        """

        while not self.close:
            # Only run if notifications is set
            # i.e. notifications are active
            self.notifications.wait()

            try:
                alerts = self.get_alerts()
                invasions = self.get_invasions()

                notification_text = ''

                for a in alerts:
                    # Remove any expired alerts from list of
                    # notified alerts
                    if a.expiry < datetime.now():
                        if a.id in self.notified_alerts:
                            self.notified_alerts.remove(a.id)

                    # If alert has not been notified, send a message
                    elif a.id not in self.notified_alerts and \
                            self.filter_rewards(a.get_rewards()):
                                notification_text += str(a) + '\n\n'
                                # Add to list of notified alerts
                                self.notified_alerts.append(a.id)

                # Remove any expired invasions
                for n in self.notified_invasions:
                    if not any(n == i.id for i in invasions):
                        self.notified_invasions.remove(n)

                for i in invasions:
                    # If invasion has not been notified, send a message
                    if i.id not in self.notified_invasions and \
                            self.filter_rewards(i.get_rewards()):
                                notification_text += str(i) + '\n\n'
                                # Add to list of notified invasions
                                self.notified_invasions.append(i.id)

                if notification_text:
                    # Send message to all chats
                    with self.notification_lock:
                        for c in self.notification_chats:
                            self.send(c, notification_text)

            # If we get a bad response, just wait and try again
            except RuntimeError:
                pass
            time.sleep(WarBot.NOTIFICATION_INTERVAL)

    def save_state(self):
        """ Saves the state of the notifier thread at the path specified
        in statefile

        """
        with shelve.open(self.state_path, flag='n') as f:
            f['chats'] = self.notification_chats
            f['alerts'] = self.notified_alerts
            f['invasions'] = self.notified_invasions


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='WarBot, a Warframe alert telegram bot')

    parser.add_argument('--rewards', '-r', default='rewards',
                        dest='rewards_file')
    parser.add_argument('--statefile', '-s', default='state', dest='state_file')

    args = parser.parse_args()

    if os.path.isfile(args.rewards_file):
        w = WarBot(args.rewards_file, args.state_file)
        w.run()

    else:
        print('Error: reward file not found')
