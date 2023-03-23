from smartcard import System

text = "vcard2sim - Save vCard Contacts to SIM Card"
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
    if reader_select <= len(readers):
        reader = readers[reader_select]
        con = reader.createConnection()
        con.connect()
        print(con)
    else:
        print("Error: Selection not in list")
else:
    print("Error: Selection not in list")


