import codecs

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

    def get_iccid(self):
        return self.get_file([0x3F, 0x00], [0x2F, 0xE2])

    def get_spn(self):
        return bytearray.fromhex(toHexString(self.get_file([0x7F, 0x20], [0x6F, 0x46])[1:])).decode()

    def get_imsi(self):
        return self.get_file([0x7F, 0x20], [0x6F, 0x07])

    def get_contacts(self):
        contacts, size, record_length = self.get_file([0x7F, 0x10], [0x6F, 0x3A], record_mode=True)
        record_count = size // record_length
        for contact in contacts:
            name_str = ""
            name = contact[:record_length - 14]
            for bit in name:
                if bit != 0xff:
                    name_str += bytes.fromhex(str(hex(bit)).replace("0x", "")).decode('utf-8')

            if name_str != "":
                print(f"({contacts.index(contact) + 1}/{record_count}) {name_str}")

        return ""

    def get_file(self, folder, file, record_mode=False):
        df_gsm, sw1, sw2 = self.select(folder)
        if sw1 == 0x9F:
            file, sw1, sw2 = self.select(file)
            if sw1 == 0x9F:
                file_desc, sw1, sw2 = self.get(sw2)
                if sw1 == 0x90:
                    size = file_desc[2] * 0x100 + file_desc[3]
                    if record_mode:
                        record_length = file_desc[14]
                        records = []
                        for i in range(size // record_length):
                            record, sw1, sw2 = self.read_record(size, record_length, i + 1)
                            if sw1 == 0x90:
                                records.append(record)
                        return records, size, record_length

                    else:
                        content, sw1, sw2 = self.read_binary(size)
                        if sw1 == 0x90:
                            return content

    def get(self, le):
        return self.card_service.connection.transmit([0xA0, 0xC0, 0x00, 0x00, le])

    def read_binary(self, le):
        return self.card_service.connection.transmit([0xA0, 0xB0, 0x00, 0x00, le])

    def read_record(self, le, record_le, record):
        return self.card_service.connection.transmit([0xA0, 0xB2, record, 0x04, record_le])

    def select(self, addr, with_length=True):
        if with_length:
            addr = [min(len(addr), 255)] + addr

        return self.card_service.connection.transmit([0xA0, 0xA4, 0x00, 0x00] + addr)

    @staticmethod
    def to_hex(decimal):
        print(decimal)
        new_hex = hex(decimal)[2:-1]
        print(new_hex)


Main()
