"""
inventory.py
-------------
ابزار خط‌فرمان مدیریت موجودی انبارهای کارگاه روی Google Sheets.

این ابزار base را برای Workflow «مدیریت موجودی انبارها»
(workflows/inventory-management.md) فراهم می‌کند: ثبت ورود/خروج کالا،
انتقال بین انبارها، جستجوی کالا در همه‌ی انبارها، گزارش موجودی کم، و
درخواست خرید با چک خودکار انبارهای دیگر قبل از خرید جدید.

محل نگهداری پیش‌فرض «انبار شماره ۱» است: هر دستوری که --warehouse نگیرد،
روی همین انبار ثبت می‌شود.

Usage:
    python tools/inventory.py setup
    python tools/inventory.py add-warehouse --name "انبار مرکزی" --location "..." --contact "..."
    python tools/inventory.py add-item --name "پیچ ۸ میل" --unit "عدد" --min-stock 50 --category "یراق"
    python tools/inventory.py stock-in --item "پیچ ۸ میل" --qty 100 --note "بازگشت از کارگاه ۲"
    python tools/inventory.py stock-out --item "پیچ ۸ میل" --qty 10 --note "مصرف کارگاه ۱"
    python tools/inventory.py transfer --to "انبار ۲" --item "پیچ ۸ میل" --qty 20
    python tools/inventory.py check --item "پیچ"
    python tools/inventory.py low-stock
    python tools/inventory.py request-purchase --item "پیچ ۸ میل" --qty 30
    python tools/inventory.py list-requests --status pending
"""

import argparse
import sys
from datetime import datetime

from sheets_client import (
    DEFAULT_WAREHOUSE,
    InventoryError,
    ensure_all_sheets,
    ensure_default_warehouse,
    ensure_sheet,
    get_records,
    load_env,
    open_spreadsheet,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def norm(value: str) -> str:
    return (value or "").strip().casefold()


def find_row(ws, records: list, predicate) -> tuple:
    for idx, record in enumerate(records, start=2):  # row 1 = header
        if predicate(record):
            return idx, record
    return None, None


def get_stock_qty(record: dict) -> float:
    try:
        return float(record.get("quantity") or 0)
    except ValueError:
        return 0.0


def cmd_setup(env, args):
    spreadsheet = open_spreadsheet(env)
    ensure_all_sheets(spreadsheet)
    print("ساختار شیت موجودی (Warehouses, Items, Stock, Transactions, PurchaseRequests) آماده شد.")
    print(f"محل نگهداری پیش‌فرض: «{DEFAULT_WAREHOUSE}»")


def ensure_warehouse_registered(spreadsheet, warehouse: str) -> None:
    """انبار پیش‌فرض باید همیشه در تب Warehouses باشد تا در لیست‌ها و پنل وب دیده شود."""
    if norm(warehouse) != norm(DEFAULT_WAREHOUSE):
        return
    ensure_default_warehouse(ensure_sheet(spreadsheet, "Warehouses"))


def cmd_add_warehouse(env, args):
    spreadsheet = open_spreadsheet(env)
    ws = ensure_sheet(spreadsheet, "Warehouses")
    records = get_records(ws)
    if any(norm(r["warehouse_name"]) == norm(args.name) for r in records):
        raise InventoryError(f"انبار «{args.name}» از قبل ثبت شده است.")
    ws.append_row([args.name, args.location or "", args.contact or ""])
    print(f"انبار «{args.name}» ثبت شد.")


def cmd_list_warehouses(env, args):
    spreadsheet = open_spreadsheet(env)
    ws = ensure_sheet(spreadsheet, "Warehouses")
    records = get_records(ws)
    if not records:
        print("هیچ انباری ثبت نشده است.")
        return
    for r in records:
        print(f"- {r['warehouse_name']} | محل: {r.get('location') or '—'} | تماس: {r.get('contact') or '—'}")


def cmd_add_item(env, args):
    spreadsheet = open_spreadsheet(env)
    ws = ensure_sheet(spreadsheet, "Items")
    records = get_records(ws)
    if any(norm(r["item_name"]) == norm(args.name) for r in records):
        raise InventoryError(f"کالای «{args.name}» از قبل در کاتالوگ ثبت شده است.")
    ws.append_row([args.name, args.unit or "", args.min_stock or 0, args.category or ""])
    print(f"کالای «{args.name}» در کاتالوگ ثبت شد.")


def upsert_stock(ws, records: list, warehouse: str, item: str, delta: float) -> float:
    row_idx, record = find_row(
        ws, records, lambda r: norm(r["warehouse_name"]) == norm(warehouse) and norm(r["item_name"]) == norm(item)
    )
    if record is None:
        new_qty = delta
        if new_qty < 0:
            raise InventoryError(f"موجودی «{item}» در «{warehouse}» صفر است؛ نمی‌توان کاهش داد.")
        ws.append_row([warehouse, item, new_qty, now()])
        return new_qty

    current_qty = get_stock_qty(record)
    new_qty = current_qty + delta
    if new_qty < 0:
        raise InventoryError(f"موجودی ناکافی: «{item}» در «{warehouse}» فقط {current_qty} عدد دارد.")
    ws.update(values=[[new_qty, now()]], range_name=f"C{row_idx}:D{row_idx}")
    return new_qty


def cmd_stock_in(env, args):
    spreadsheet = open_spreadsheet(env)
    ensure_warehouse_registered(spreadsheet, args.warehouse)
    stock_ws = ensure_sheet(spreadsheet, "Stock")
    tx_ws = ensure_sheet(spreadsheet, "Transactions")
    records = get_records(stock_ws)
    new_qty = upsert_stock(stock_ws, records, args.warehouse, args.item, args.qty)
    tx_ws.append_row([now(), "IN", args.warehouse, args.item, args.qty, "", args.note or ""])
    print(f"ثبت شد: +{args.qty} «{args.item}» در «{args.warehouse}» — موجودی فعلی: {new_qty}")


def cmd_stock_out(env, args):
    spreadsheet = open_spreadsheet(env)
    ensure_warehouse_registered(spreadsheet, args.warehouse)
    stock_ws = ensure_sheet(spreadsheet, "Stock")
    tx_ws = ensure_sheet(spreadsheet, "Transactions")
    records = get_records(stock_ws)
    new_qty = upsert_stock(stock_ws, records, args.warehouse, args.item, -args.qty)
    tx_ws.append_row([now(), "OUT", args.warehouse, args.item, args.qty, "", args.note or ""])
    print(f"ثبت شد: -{args.qty} «{args.item}» از «{args.warehouse}» — موجودی فعلی: {new_qty}")


def cmd_transfer(env, args):
    if norm(args.from_wh) == norm(args.to_wh):
        raise InventoryError("انبار مبدا و مقصد نمی‌توانند یکسان باشند.")
    spreadsheet = open_spreadsheet(env)
    ensure_warehouse_registered(spreadsheet, args.from_wh)
    ensure_warehouse_registered(spreadsheet, args.to_wh)
    stock_ws = ensure_sheet(spreadsheet, "Stock")
    tx_ws = ensure_sheet(spreadsheet, "Transactions")

    records = get_records(stock_ws)
    upsert_stock(stock_ws, records, args.from_wh, args.item, -args.qty)
    records = get_records(stock_ws)  # رفرش بعد از تغییر ردیف‌ها
    new_qty_dest = upsert_stock(stock_ws, records, args.to_wh, args.item, args.qty)

    tx_ws.append_row([now(), "TRANSFER", args.from_wh, args.item, args.qty, args.to_wh, args.note or ""])
    print(
        f"انتقال شد: {args.qty} «{args.item}» از «{args.from_wh}» به «{args.to_wh}» "
        f"— موجودی جدید مقصد: {new_qty_dest}"
    )


def cmd_check(env, args):
    spreadsheet = open_spreadsheet(env)
    ws = ensure_sheet(spreadsheet, "Stock")
    records = get_records(ws)
    matches = [r for r in records if norm(args.item) in norm(r["item_name"])]
    if not matches:
        print(f"هیچ موجودی‌ای برای «{args.item}» در هیچ انباری پیدا نشد.")
        return
    print(f"موجودی «{args.item}» در انبارها:")
    for r in sorted(matches, key=lambda r: -get_stock_qty(r)):
        print(f"- {r['warehouse_name']}: {r['item_name']} → {get_stock_qty(r)}")


def cmd_low_stock(env, args):
    spreadsheet = open_spreadsheet(env)
    stock_ws = ensure_sheet(spreadsheet, "Stock")
    items_ws = ensure_sheet(spreadsheet, "Items")
    stock_records = get_records(stock_ws)
    if args.warehouse:
        stock_records = [r for r in stock_records if norm(r["warehouse_name"]) == norm(args.warehouse)]

    min_stock_by_item = {}
    for r in get_records(items_ws):
        try:
            min_stock_by_item[norm(r["item_name"])] = float(r.get("min_stock") or 0)
        except ValueError:
            min_stock_by_item[norm(r["item_name"])] = 0

    low = []
    for r in stock_records:
        threshold = min_stock_by_item.get(norm(r["item_name"]), 0)
        if threshold > 0 and get_stock_qty(r) < threshold:
            low.append((r, threshold))

    if not low:
        print("هیچ کالایی زیر حداقل موجودی تعریف‌شده نیست.")
        return
    print("کالاهای زیر حداقل موجودی:")
    for r, threshold in low:
        print(f"- {r['warehouse_name']}: {r['item_name']} → {get_stock_qty(r)} (حداقل: {threshold})")


def cmd_request_purchase(env, args):
    spreadsheet = open_spreadsheet(env)
    ensure_warehouse_registered(spreadsheet, args.warehouse)
    stock_ws = ensure_sheet(spreadsheet, "Stock")
    pr_ws = ensure_sheet(spreadsheet, "PurchaseRequests")

    stock_records = get_records(stock_ws)
    available_elsewhere = [
        r
        for r in stock_records
        if norm(r["item_name"]) == norm(args.item)
        and norm(r["warehouse_name"]) != norm(args.warehouse)
        and get_stock_qty(r) > 0
    ]

    if available_elsewhere and not args.force:
        print(f"قبل از خرید جدید، «{args.item}» در انبارهای دیگر موجود است:")
        for r in available_elsewhere:
            print(f"- {r['warehouse_name']}: {get_stock_qty(r)} عدد")
        print(
            "به‌جای خرید، انتقال داخلی پیشنهاد می‌شود "
            "(دستور transfer). اگر با این حال باید خرید جدید ثبت شود، با --force دوباره اجرا کن."
        )
        return

    pr_ws.append_row([now(), args.warehouse, args.item, args.qty, "pending", args.note or ""])
    print(f"درخواست خرید ثبت شد: {args.qty} «{args.item}» برای «{args.warehouse}» (وضعیت: pending)")


def cmd_list_requests(env, args):
    spreadsheet = open_spreadsheet(env)
    ws = ensure_sheet(spreadsheet, "PurchaseRequests")
    records = get_records(ws)
    if args.status:
        records = [r for r in records if norm(r["status"]) == norm(args.status)]
    if not records:
        print("درخواست خریدی پیدا نشد.")
        return
    for r in records:
        print(
            f"- [{r['status']}] {r['warehouse_name']}: {r['quantity_requested']} عدد «{r['item_name']}» "
            f"({r['timestamp']}) {r.get('note') or ''}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="مدیریت موجودی انبارهای کارگاه روی Google Sheets")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="ساخت/تضمین ساختار تب‌ها و هدرهای شیت").set_defaults(func=cmd_setup)

    p = sub.add_parser("add-warehouse", help="ثبت انبار جدید")
    p.add_argument("--name", required=True)
    p.add_argument("--location", default="")
    p.add_argument("--contact", default="")
    p.set_defaults(func=cmd_add_warehouse)

    sub.add_parser("list-warehouses", help="لیست انبارها").set_defaults(func=cmd_list_warehouses)

    p = sub.add_parser("add-item", help="ثبت کالا در کاتالوگ (برای تعریف واحد و حداقل موجودی)")
    p.add_argument("--name", required=True)
    p.add_argument("--unit", default="")
    p.add_argument("--min-stock", type=float, default=0, dest="min_stock")
    p.add_argument("--category", default="")
    p.set_defaults(func=cmd_add_item)

    p = sub.add_parser("stock-in", help="ثبت ورود کالا به انبار")
    p.add_argument("--warehouse", default=DEFAULT_WAREHOUSE, help=f"پیش‌فرض: {DEFAULT_WAREHOUSE}")
    p.add_argument("--item", required=True)
    p.add_argument("--qty", type=float, required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_stock_in)

    p = sub.add_parser("stock-out", help="ثبت خروج/مصرف کالا از انبار")
    p.add_argument("--warehouse", default=DEFAULT_WAREHOUSE, help=f"پیش‌فرض: {DEFAULT_WAREHOUSE}")
    p.add_argument("--item", required=True)
    p.add_argument("--qty", type=float, required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_stock_out)

    p = sub.add_parser("transfer", help="انتقال کالا بین دو انبار")
    p.add_argument("--from", default=DEFAULT_WAREHOUSE, dest="from_wh", help=f"پیش‌فرض: {DEFAULT_WAREHOUSE}")
    p.add_argument("--to", required=True, dest="to_wh")
    p.add_argument("--item", required=True)
    p.add_argument("--qty", type=float, required=True)
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_transfer)

    p = sub.add_parser("check", help="جستجوی موجودی یک کالا در همه‌ی انبارها")
    p.add_argument("--item", required=True)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("low-stock", help="گزارش کالاهای زیر حداقل موجودی")
    p.add_argument("--warehouse", default="")
    p.set_defaults(func=cmd_low_stock)

    p = sub.add_parser("request-purchase", help="ثبت درخواست خرید (با چک خودکار انبارهای دیگر)")
    p.add_argument("--warehouse", default=DEFAULT_WAREHOUSE, help=f"پیش‌فرض: {DEFAULT_WAREHOUSE}")
    p.add_argument("--item", required=True)
    p.add_argument("--qty", type=float, required=True)
    p.add_argument("--note", default="")
    p.add_argument("--force", action="store_true", help="حتی اگر کالا در انبار دیگری موجود است، درخواست خرید ثبت شود")
    p.set_defaults(func=cmd_request_purchase)

    p = sub.add_parser("list-requests", help="لیست درخواست‌های خرید")
    p.add_argument("--status", default="")
    p.set_defaults(func=cmd_list_requests)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        env = load_env()
        args.func(env, args)
    except InventoryError as exc:
        print(f"خطا: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
