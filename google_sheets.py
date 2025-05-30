import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds_dict = json.loads(os.getenv("GOOGLE_CREDS_JSON", "{}"))
spreadsheet_id = os.getenv("SPREADSHEET_ID", "")

def add_to_google_sheet(name, surname, phone, procedure, date, time):
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(spreadsheet_id).sheet1
        sheet.append_row([name, surname, phone, procedure, date, time])
    except Exception as e:
        print(f"Google Sheets Error: {e}")
