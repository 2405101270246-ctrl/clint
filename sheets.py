import logging
import gspread
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEETS_CREDS, SPREADSHEET_NAME

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
HEADERS = ["Name", "Phone", "Email", "Address", "Website", "Source", "Message", "Status"]

_sheet = None


def _get_sheet():
    global _sheet
    if _sheet:
        return _sheet
    creds = Credentials.from_service_account_file(GOOGLE_SHEETS_CREDS, scopes=SCOPES)
    client = gspread.authorize(creds)
    try:
        wb = client.open(SPREADSHEET_NAME)
    except gspread.SpreadsheetNotFound:
        wb = client.create(SPREADSHEET_NAME)
        wb.share(None, perm_type="anyone", role="writer")
    ws = wb.sheet1
    if ws.row_count == 0 or ws.cell(1, 1).value != "Name":
        ws.insert_row(HEADERS, 1)
    _sheet = ws
    return _sheet


def save_lead(lead: dict):
    try:
        ws = _get_sheet()
        # Check duplicate by scanning Name+Phone column (lightweight)
        existing = ws.col_values(1)   # all names
        if lead.get("name") in existing:
            return False
        row = [
            lead.get("name", ""),
            lead.get("phone", ""),
            lead.get("email", ""),
            lead.get("address", ""),
            lead.get("website", ""),
            lead.get("source", ""),
            lead.get("message", ""),
            "Sent",
        ]
        ws.append_row(row)
        return True
    except Exception as e:
        logger.error(f"Sheets error: {e}")
        return False
