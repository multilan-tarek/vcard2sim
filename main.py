import codecs
import sys

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

                        contacts, max_contacts, contact_length = self.get_contacts()
                        print(f"Used {len(contacts)} of {max_contacts} entries")
                        for contact in contacts:
                            print(f"({contact['slot']}/{max_contacts}) {contact['name']} - {contact['number']}")

                        export_contacts = input("Do you want to export the existing contact list? (y/N) ")
                        if export_contacts.lower() == "y":
                            pass

                        clear_contacts = input("Do you want to clear the contact list? (y/N) ")
                        if clear_contacts.lower() == "y":
                            self.clear_contacts()
                        else:
                            print("New contacts will be appended to the list")

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
        iccid = self.get_file([0x3F, 0x00], [0x2F, 0xE2])
        return self.hex_to_string(iccid)

    def get_spn(self):
        return bytearray.fromhex(toHexString(self.get_file([0x7F, 0x20], [0x6F, 0x46])[1:])).decode()

    def get_imsi(self):
        imsi = self.get_file([0x7F, 0x20], [0x6F, 0x07])
        return self.hex_to_string(imsi)[3:]

    def get_contacts(self):
        filtered_contacts = []
        contacts, size, record_length = self.get_file([0x7F, 0x10], [0x6F, 0x3A], record_mode=True)
        max_contacts = size // record_length

        for contact in contacts:
            name_length = record_length - 14
            name_str = ""
            name = contact[:name_length]
            bcd = contact[name_length:name_length + 1]
            ton_npi = contact[name_length + 1:name_length + 2]
            number = contact[name_length + 2:name_length + 1 + int(bcd[0])]
            number = self.hex_to_string(number)
            for bit in name:
                if bit != 0xff:
                    name_str += bytes.fromhex(str(hex(bit)).replace("0x", "")).decode('utf-8')
            if name_str != "":
                filtered_contacts.append({"slot": contacts.index(contact) + 1, "name": name_str, "number": number})

        return filtered_contacts, max_contacts, record_length

    def clear_contacts(self):
        contacts, size, record_length = self.get_file([0x7F, 0x10], [0x6F, 0x3A], record_mode=True)

        empty_data = []
        for i in range(record_length):
            empty_data.append(0xFF)

        for contact in range(len(contacts)):
            _, sw1, sw2 = self.write_record(contact + 1, empty_data)
            if sw1 != 0x90:
                print("Error: An error occurred while clearing contact list")
                exit()

            progress = round(((contact + 1) / len(contacts)) * 100, 1)
            sys.stdout.write(f"\rClearing list: {progress}%")
            sys.stdout.flush()

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
                            record, sw1, sw2 = self.read_record(record_length, i + 1)
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

    def read_record(self, record_le, record):
        return self.card_service.connection.transmit([0xA0, 0xB2, record, 0x04, record_le])

    def write_record(self, record, data):
        return self.card_service.connection.transmit([0xA0, 0xDC, record, 0x04, len(data)] + data)

    def select(self, addr, with_length=True):
        if with_length:
            addr = [min(len(addr), 255)] + addr

        return self.card_service.connection.transmit([0xA0, 0xA4, 0x00, 0x00] + addr)

    @staticmethod
    def hex_to_string(hex_list, reverse=True):
        result_string = ""
        for hex_val in hex_list:
            hex_string = str(hex(hex_val)).replace("0x", "")
            if len(hex_string) == 1:
                hex_string = f"0{hex_string}"

            if reverse:
                result_string += hex_string[1] + hex_string[0]
            else:
                result_string += hex_string

        return result_string.replace("f", "")

    @staticmethod
    def to_hex(decimal):
        print(decimal)
        new_hex = hex(decimal)[2:-1]
        print(new_hex)


Main()
