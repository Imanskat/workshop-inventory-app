"""
sheets_client.py
-----------------
لایه‌ی ارتباط با Google Sheets برای سیستم مدیریت موجودی انبارهای کارگاه.

این فایل خودش یک ابزار اجرایی نیست؛ توسط inventory.py ایمپورت می‌شود.

نکات کلیدی:
- احراز هویت با Service Account انجام می‌شود (نه OAuth کاربر)، چون این سیستم
  باید بدون لاگین مرورگری و در پس‌زمینه کار کند.
- Service Account فقط به Scope «spreadsheets» نیاز دارد، نه Drive؛ به همین
  دلیل شیت باید از قبل توسط کاربر ساخته و با ایمیل Service Account
  Share شده باشد (Editor) و آیدی آن در .env (INVENTORY_SPREADSHEET_ID) ثبت شود.
- ساختار شیت‌ها (تب‌ها و هدرها) idempotent ساخته می‌شود: اگر تب یا هدر از قبل
  وجود داشته باشد دوباره ساخته/بازنویسی نمی‌شود.
"""

from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# محل نگهداری پیش‌فرض: هر جا انبار مشخص نشده باشد، همین انبار در نظر گرفته می‌شود.
# این مقدار باید مو‌به‌مو با نام انبار در شیت و با DEFAULT_WAREHOUSE در
# webapp/Code.gs و docs/assets/app.js یکی باشد.
DEFAULT_WAREHOUSE = "انبار شماره ۱"

SHEET_SCHEMAS = {
    "Warehouses": ["warehouse_name", "location", "contact"],
    "Items": ["item_name", "unit", "min_stock", "category"],
    "Stock": ["warehouse_name", "item_name", "quantity", "last_updated"],
    "Transactions": [
        "timestamp",
        "type",
        "warehouse_name",
        "item_name",
        "quantity",
        "ref_warehouse",
        "note",
    ],
    "PurchaseRequests": [
        "timestamp",
        "warehouse_name",
        "item_name",
        "quantity_requested",
        "status",
        "note",
    ],
}


class InventoryError(Exception):
    pass


def load_env() -> dict:
    if not ENV_PATH.exists():
        raise InventoryError(f".env پیدا نشد: {ENV_PATH}")
    env = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()

    if not env.get("INVENTORY_SPREADSHEET_ID"):
        raise InventoryError(
            "INVENTORY_SPREADSHEET_ID در .env خالی است — اول شیت موجودی را بساز، "
            "با ایمیل Service Account شیر کن و آیدی آن را در .env بگذار."
        )
    sa_file = env.get("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
    if not (ROOT / sa_file).exists():
        raise InventoryError(
            f"فایل کلید Service Account پیدا نشد: {ROOT / sa_file} — "
            "آن را از Google Cloud Console دانلود و در ریشه پروژه قرار بده."
        )
    return env


def get_client(env: dict) -> gspread.Client:
    sa_file = ROOT / env.get("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
    creds = Credentials.from_service_account_file(str(sa_file), scopes=SCOPES)
    return gspread.authorize(creds)


def open_spreadsheet(env: dict) -> gspread.Spreadsheet:
    client = get_client(env)
    try:
        return client.open_by_key(env["INVENTORY_SPREADSHEET_ID"])
    except gspread.exceptions.APIError as exc:
        raise InventoryError(
            f"باز کردن شیت ناموفق بود — مطمئن شو آیدی درست است و شیت با ایمیل "
            f"Service Account شیر شده (Editor). جزئیات: {exc}"
        ) from exc


def ensure_sheet(spreadsheet: gspread.Spreadsheet, name: str) -> gspread.Worksheet:
    headers = SHEET_SCHEMAS[name]
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=200, cols=len(headers))
        ws.append_row(headers)
        return ws

    existing_header = ws.row_values(1)
    if existing_header != headers:
        ws.update(values=[headers], range_name="A1")
    return ws


def ensure_all_sheets(spreadsheet: gspread.Spreadsheet) -> dict:
    sheets = {name: ensure_sheet(spreadsheet, name) for name in SHEET_SCHEMAS}
    ensure_default_warehouse(sheets["Warehouses"])
    return sheets


def ensure_default_warehouse(ws: gspread.Worksheet) -> bool:
    """ثبت انبار پیش‌فرض در تب Warehouses اگر هنوز نباشد. True یعنی تازه ساخته شد."""
    existing = get_records(ws)
    if any((r.get("warehouse_name") or "").strip().casefold() == DEFAULT_WAREHOUSE.casefold() for r in existing):
        return False
    ws.append_row([DEFAULT_WAREHOUSE, "", ""])
    return True


def get_records(ws: gspread.Worksheet) -> list:
    return ws.get_all_records()
