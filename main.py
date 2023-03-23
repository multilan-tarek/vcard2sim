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
                    print("Connecting to card...")
                    self.card_service.connection.connect()

                    df_gsm, sw1, sw2 = self.select([0x7F, 0x20])

                    if sw1 == 0x9F:
                        print("Detected card:")
                        print("ICCID:", self.get_iccid())
                        print("IMSI:", self.get_imsi())
                        print("Provider:", self.get_spn())
                        print("Loading contacts...")
                        print(self.get_contacts())

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

    def read_binary(self, le):
        return self.card_service.connection.transmit([0xA0, 0xB0, 0x00, 0x00, le])

    def read_record(self, record, le):
        return self.card_service.connection.transmit([0xA0, 0xB2, 0x00, 0x01, le])

    def get_iccid(self):
        return self.get_file([0x3F, 0x00], [0x2F, 0xE2])

    def get_spn(self):
        return bytearray.fromhex(toHexString(self.get_file([0x7F, 0x20], [0x6F, 0x46])[1:])).decode()

    def get_imsi(self):
        return self.get_file([0x7F, 0x20], [0x6F, 0x07])

    def get_contacts(self):
        return self.get_file([0x7F, 0x10], [0x6F, 0x3A], record_mode=True)

    def get_file(self, folder, file, record_mode=False):
        df_gsm, sw1, sw2 = self.select(folder)
        if sw1 == 0x9F:
            file, sw1, sw2 = self.select(file)
            if sw1 == 0x9F:
                file_desc, sw1, sw2 = self.get(sw2)
                size = file_desc[3]
                if sw1 == 0x90:

                    if record_mode:
                        records, sw1, sw2 = self.read_record(0x01, size)
                        print(records, toHexString([sw1, sw2]))

                    else:

                        content, sw1, sw2 = self.read_binary(size)
                        if sw1 == 0x90:
                            return content



    @staticmethod
    def to_hex(decimal):
        print(decimal)
        new_hex = hex(decimal)[2:-1]
        print(new_hex)


Main()
