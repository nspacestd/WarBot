from datetime import datetime

class Deal:
    """This class represents a daily deal and is initialized with
    data in JSON format

    """

    def __init__(self, data):
        self.id              = data['_id']
        self.item            = data['StoreItem']
        self.expiry          = datetime.fromtimestamp(data['Expiry']['sec'])
        self.original_price  = data['OriginalPrice']
        self.sale_price      = data['SalePrice']
        self.total           = data['AmountTotal']
        self.sold            = data['AmountSold']

    def __str__(self):
        """Returns a string with all the information about this alert

        """

        deal_string = ('{0}\n'
                       '{1}p (original {2}p)\n'
                       '{3} / {4} sold\n'
                       'Expires in {5}')

        return deal_string.format(self.item, self.sale_price,
                                  self.original_price, self.sold,
                                  self.total, self.get_eta_string())

    def get_eta_string(self):
        """Returns a string containing the deal's ETA

        """
        seconds = int((self.expiry - datetime.now()).total_seconds())
        return '{} hrs, {} mins'.format(seconds // 3600,
                                        (seconds % 3600) // 60)

