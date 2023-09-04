import os
import sys

from smartcard import System
from smartcard.CardRequest import CardRequest
from smartcard.CardType import AnyCardType
from smartcard.Exceptions import CardRequestTimeoutException, CardConnectionException
from smartcard.util import toHexString


class CardBlocked(Exception):
    pass


class CardPinLocked(Exception):
    pass


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

                    try:
                        self.get_imsi()
                    except CardPinLocked:
                        if not self.unlock_sim():
                            exit()
                    except CardBlocked:
                        print("Error: SIM card blocked")
                        exit()

                    if sw1 == 0x9F:
                        print("Detected card:")
                        print("ICCID:", self.get_iccid())
                        print("IMSI:", self.get_imsi())
                        print("Provider:", self.get_spn())
                        print(len(text) * "#")

                        print("Reading contacts from card...")
                        contacts, max_contacts, contact_length = self.get_contacts()
                        self.print_contacts(contacts, max_contacts)

                        append_mode = False
                        cleared = False
                        if len(contacts) != 0:
                            append_mode = True
                            export_contacts = input("Do you want to export the existing contact list? (y/N) ")
                            if export_contacts.lower() == "y":
                                export_fn = input("Enter a file name: ")
                                self.export_contacts(export_fn)

                            clear_contacts = input("Do you want to clear the contact list? (y/N) ")
                            if clear_contacts.lower() == "y":
                                self.clear_contacts()
                                cleared = True
                                append_mode = False

                        if append_mode:
                            continue_append = input("Contacts will be appended to existing contact list on card, "
                                                    "continue? (y/N) ")
                            if continue_append.lower() != "y":
                                exit()

                        vcard_file = input("Enter import vCard (.vcf) filename: ")
                        if os.path.exists(vcard_file):
                            print(f"Starting import of vCard file '{vcard_file}'")
                            start_entry = 0
                            if append_mode:
                                start_entry = len(contacts)
                                print(f"New contacts will be appended to the list after entry {len(contacts)}")

                            _, _, record_length = self.get_file([0x7F, 0x10], [0x6F, 0x3A], record_mode=True)
                            vcard_contacts = self.read_vcard(vcard_file)

                            if len(vcard_contacts) + len(contacts) > max_contacts and not cleared:
                                print("Error: Appending vCard contacts would exceed SIM card space")
                                exit()

                            for contact in vcard_contacts:
                                progress = round((vcard_contacts.index(contact) / len(vcard_contacts)) * 100, 1)
                                sys.stdout.flush()
                                sys.stdout.write(f"\rImporting {contact['name']}... {progress}%")
                                self.add_contact(contact["name"], contact["number"], record_length,
                                                 vcard_contacts.index(contact) + 1 + start_entry)

                            sys.stdout.flush()
                            sys.stdout.write(f"\rvCard contact list successfully imported from {vcard_file}\r\n")

                            print("Reading contact list from card...")
                            contacts, max_contacts, contact_length = self.get_contacts()
                            self.print_contacts(contacts, max_contacts)
                        else:
                            print("Error: File not found")
                    else:
                        print("Error: Card is not a SIM card")

                except CardRequestTimeoutException:
                    print("Error: No card inserted")
                    exit()
                except CardConnectionException:
                    print("\r\nError: Could not communicate with card")
                    exit()

            else:
                print("Error: Selection not in list")
        else:
            print("Error: Selection must be numeric")

    def unlock_sim(self):
        pin = input("SIM card is PIN locked! Enter SIM PIN1: ")
        if pin.isnumeric():
            if len(pin) == 4:
                cmd = [0xA0, 0x20, 0x00, 0x01, 0x08]
                for c in pin:
                    cmd.append(int(c) | 0x30)
                cmd += [0xff, 0xff, 0xff, 0xff]

                value, sw1, sw2 = self.card_service.connection.transmit(cmd)
                if sw1 == 0x90:
                    return True
                elif sw1 == 0x98 and sw2 == 0x04:
                    print("Error: SIM PIN invalid")
                elif sw1 == 0x98 and sw2 == 0x40:
                    print("Error: SIM PIN blocked, SIM needs to be unblocked using PUK first")
            else:
                print("Error: SIM PIN must be a 4 digit number")
        else:
            print("Error: SIM PIN must be numeric")
        return False

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

        slot = 0
        for contact in contacts:
            slot += 1
            name_length = record_length - 14
            name_str = ""
            name = contact[:name_length]
            bcd = contact[name_length:name_length + 1]
            ton = contact[name_length + 1:name_length + 2]
            number = contact[name_length + 2:name_length + 1 + int(bcd[0])]
            number = self.hex_to_string(number)
            if ton[0] == 0x91:
                number = "+" + number
            for bit in name:
                if bit != 0xff:
                    name_str += bytes.fromhex(str(hex(bit)).replace("0x", "")).decode('utf-8')
            if name_str != "":
                filtered_contacts.append({"slot": slot, "name": name_str, "number": number})

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

        sys.stdout.flush()
        sys.stdout.write("\rContact list successfully cleared\r\n")

    def add_contact(self, name, number, length, slot):
        data = []

        max_name_length = length - 14
        name = name.encode("utf-8").hex()
        name_chunks = [name[i:i + 2] for i in range(0, len(name), 2)]
        name_data = []

        for chunk in name_chunks:
            if len(name_data) <= max_name_length:
                chunk = int(f"0x{chunk}", 16)
                name_data.append(chunk)

        data = data + name_data

        for i in range(max_name_length - len(name_data)):
            data.append(0xFF)

        starts_with_plus = False
        number = number.replace("*", "A1").replace("#", "B2")
        if number.startswith("+"):
            number = number.strip("+")
            starts_with_plus = True
        number = number.replace(" ", "")

        number_chunks = [number[i:i + 2] for i in range(0, len(number), 2)]
        number_data = []

        for chunk in number_chunks:
            if len(chunk) == 2:
                chunk = chunk[1] + chunk[0]
            else:
                chunk = "F" + chunk

            chunk = int(f"0x{chunk}", 16)
            number_data.append(chunk)

        data.append(len(number_data) + 1)
        if starts_with_plus:
            data.append(0x91)
        else:
            data.append(0x81)
        data = data + number_data

        for i in range(length - len(data)):
            data.append(0xFF)

        _, sw1, sw2 = self.write_record(slot, data)
        if sw1 != 0x90:
            print("Error: An error occurred while communicating with card")
            exit()

    @staticmethod
    def print_contacts(contacts, max_contacts):
        print(f"Used {len(contacts)} of {max_contacts} entries")
        for contact in contacts:
            print(f"({contact['slot']}/{max_contacts}) {contact['name']} - {contact['number']}")

    def export_contacts(self, filename):
        start_export = True
        if not filename.endswith(".vcf"):
            filename += ".vcf"

        if os.path.exists(filename):
            replace = input(f"File already exists. Do you want to replace '{filename}'? (y/N) ")
            if replace.lower() != "y":
                start_export = False
                print("Export aborted")

        if start_export:
            sys.stdout.write(f"\rExporting list to {filename}...")
            contacts, _, _ = self.get_contacts()
            self.write_vcard(contacts, filename)
            sys.stdout.flush()
            sys.stdout.write(f"\rContact list successfully exported to {filename}\r\n")

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
                else:
                    print("Error: An error occurred while communicating with card")
                    exit()

    def get(self, le):
        value, sw1, sw2 = self.card_service.connection.transmit([0xA0, 0xC0, 0x00, 0x00, le])
        self.check_card_access(sw1, sw2)
        return value, sw1, sw2

    def read_binary(self, le):
        value, sw1, sw2 = self.card_service.connection.transmit([0xA0, 0xB0, 0x00, 0x00, le])
        self.check_card_access(sw1, sw2)
        return value, sw1, sw2

    def read_record(self, record_le, record):
        value, sw1, sw2 = self.card_service.connection.transmit([0xA0, 0xB2, record, 0x04, record_le])
        self.check_card_access(sw1, sw2)
        return value, sw1, sw2

    def write_record(self, record, data):
        value, sw1, sw2 = self.card_service.connection.transmit([0xA0, 0xDC, record, 0x04, len(data)] + data)
        self.check_card_access(sw1, sw2)
        return value, sw1, sw2

    def select(self, addr):
        addr = [min(len(addr), 255)] + addr
        value, sw1, sw2 = self.card_service.connection.transmit([0xA0, 0xA4, 0x00, 0x00] + addr)
        self.check_card_access(sw1, sw2)
        return value, sw1, sw2

    @staticmethod
    def check_card_access(sw1, sw2):
        if sw1 == 0x98 and sw2 == 0x04:
            raise CardPinLocked
        elif sw2 == 0x98:
            raise CardBlocked

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
    def write_vcard(data, filename):
        new_vcard = ""
        for item in data:
            new_vcard += "BEGIN:VCARD\rVERSION:4.0\r"
            new_vcard += f"FN:{item['name']}\r"
            new_vcard += f"TEL;TYPE=cell:{item['number']}\r"
            new_vcard += "END:VCARD\r"

        with open(filename, "w") as file:
            file.write(new_vcard)

    @staticmethod
    def read_vcard(filename):
        contacts = []
        with open(filename, "r") as file:
            vcard = file.read()

        name = None
        number = None
        for line in vcard.splitlines():
            if line == "BEGIN:VCARD":
                name = None
                number = None

            elif line == "END:VCARD":
                if name and number:
                    contacts.append({"number": number, "name": name})
                elif name and not number:
                    print(f"'{name} is missing a number'")
                else:
                    print("Error: vCard file has missing information or is corrupt")

            elif "TEL;" in line:
                number = line.rsplit(":", 1)[1]

            elif "FN:" in line:
                name = line.rsplit(":", 1)[1]

        return contacts


Main()
input("Press enter to exit...")