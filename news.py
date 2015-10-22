from datetime import datetime

class News:
    """This class represents a news item and is initialized with
    data in text format

    """

    def __init__(self, data):
        info = data.split('|')

        self.id         = info[0]
        self.link       = info[1]
        self.time       = datetime.fromtimestamp(int(info[2]))
        self.text       = info[3]

    def __str__(self):
        """Returns a string with the description of the news item

        """

        return '[{} ago]: [{}]({})'.format(self.get_elapsed_time(),
                                              self.text, self.link)

    def get_elapsed_time(self):
        """Returns a string containing the time that has passed since
        the news item was published

        """

        seconds = int((datetime.now() - self.time).total_seconds())
        time_string = ''

        if seconds >= 86400:        # Seconds in a day
            time_string = "{0}d"
        elif seconds >= 3600:
            time_string = "{1}h {2}m"
        else:
            time_string = "{2}m"

        return time_string.format(seconds // 86400, seconds // 3600, (seconds % 3600) // 60)
