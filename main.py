from smartcard import System
from smartcard.CardRequest import CardRequest
from smartcard.CardType import AnyCardType
from smartcard.Exceptions import CardRequestTimeoutException, CardConnectionException
from smartcard.util import toHexString


class Main:
    def __init__(self):
        text = "vcard2sim - Save vCard contacts to SIM card"
        print(len(text) * "#")
        print(text)
        print(len(text) * "#")

        print("Select smart card reader:")
        readers = System.readers()
        for reader in readers:
            print(f"{readers.index(reader)} - {reader}")

        reader_select = input("?: ")
        if reader_select.isnumeric():
            reader_select = int(reader_select)
            if reader_select < len(readers):
                reader = readers[reader_select]

                print(len(text) * "#")
                print(f"Reading card using reader '{reader}'")

                self.card_type = AnyCardType()
                self.card_request = CardRequest(timeout=1, cardType=self.card_type, readers=[reader])

                try:
                    self.card_service = self.card_request.waitforcard()
                    print("Card found")
                    self.card_service.connection.connect()
                    print("Connected!")

                    df_gsm, sw1, sw2 = self.select([0x7F, 0x20])

                    if sw1 == 0x9F:
                        print(self.get_imsi())


                    else:
                        print("Error: Card is not a SIM card")

                except CardRequestTimeoutException:
                    print("Error: No card inserted")
                    exit()
                except CardConnectionException:
                    print("Error: Could not communicate with card")
                    exit()

            else:
                print("Error: Selection not in list")
        else:
            print("Error: Selection not in list")

    def select(self, addr, with_length=True):
        if with_length:
            addr = [min(len(addr), 255)] + addr

        return self.card_service.connection.transmit([0xA0, 0xA4, 0x00, 0x00] + addr)

    def get(self, le):
        return self.card_service.connection.transmit([0xA0, 0xC0, 0x00, 0x00, le])

    def read(self, le):
        return self.card_service.connection.transmit([0xA0, 0xB0, 0x00, 0x00, le])

    def get_imsi(self):
        df_gsm, sw1, sw2 = self.select([0x7F, 0x20])
        if sw1 == 0x9F:
            imsi, sw1, sw2 = self.select([0x6F, 0x07])
            if sw1 == 0x9F:
                imsi_file_desc, sw1, sw2 = self.get(sw2)
                if sw1 == 0x90:
                    imsi_content, sw1, sw2 = self.read(0x09)
                    if sw1 == 0x90:
                        return toHexString(imsi_content)

    @staticmethod
    def to_hex(decimal):
        print(decimal)
        new_hex = hex(decimal)[2:-1]
        print(new_hex)


Main()
