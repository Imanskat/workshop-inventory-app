/**
 * Code.gs
 * --------
 * بک‌اند JSON API مدیریت موجودی انبارهای کارگاه.
 * این اسکریپت باید به همان Google Sheet که tools/inventory.py استفاده می‌کند
 * متصل (Bound) باشد: از داخل شیت، منوی Extensions → Apps Script.
 *
 * فرانت‌اند (GitHub Pages، پوشه‌ی site/ همین پروژه) با fetch ساده (GET) به
 * این آدرس وصل می‌شود؛ همه‌ی عملیات (خواندن و نوشتن) از طریق doGet با
 * پارامتر action انجام می‌شود — عمداً همه چیز GET است تا مرورگر هیچ
 * CORS preflight (OPTIONS) نزند، چون Apps Script به OPTIONS پاسخ نمی‌دهد.
 * این همان الگویی است که در پروژه‌ی telegram daily workshop (GAS_URL با
 * action=list/get) استفاده شده.
 *
 * چون این اسکریپت Bound به شیت است، نیازی به Service Account یا کلید جداگانه
 * ندارد — با هویت خود کاربری که آن را Deploy کرده اجرا می‌شود و مستقیماً به
 * شیت دسترسی دارد.
 *
 * ساختار شیت‌ها دقیقاً همان ساختاری است که tools/sheets_client.py می‌سازد:
 * Warehouses, Items, Stock, Transactions, PurchaseRequests
 * (هر دو ابزار — این اپ و ابزار پایتون چت‌محور — روی یک شیت کار می‌کنند و
 * می‌توانند با هم به‌صورت موازی استفاده شوند.)
 */

var SHEET_NAMES = {
  WAREHOUSES: 'Warehouses',
  ITEMS: 'Items',
  STOCK: 'Stock',
  TRANSACTIONS: 'Transactions',
  PURCHASE_REQUESTS: 'PurchaseRequests'
};

function getSheet_(name) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    throw new Error('تب «' + name + '» در شیت پیدا نشد. ابتدا با tools/inventory.py دستور setup را اجرا کن.');
  }
  return sheet;
}

function norm_(v) {
  return (v || '').toString().trim().toLowerCase();
}

function nowIso_() {
  return new Date().toISOString();
}

/** خواندن همه‌ی ردیف‌های یک تب به‌صورت آرایه‌ای از آبجکت + شماره ردیف واقعی شیت (برای آپدیت بعدی) */
function readRows_(sheet) {
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];
  var headers = values[0];
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var obj = { _row: i + 1 };
    for (var c = 0; c < headers.length; c++) {
      obj[headers[c]] = values[i][c];
    }
    rows.push(obj);
  }
  return rows;
}

// ---------- Web App entry point (JSON API) ----------

function jsonOut_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  var p = e.parameter || {};
  var action = p.action;

  if (!action) {
    return jsonOut_({ success: true, message: 'Workshop Inventory API is alive.' });
  }

  try {
    var data;
    switch (action) {
      case 'warehouses':
        data = listWarehouses();
        break;
      case 'addWarehouse':
        data = addWarehouse(p.name, p.location, p.contact);
        break;
      case 'items':
        data = listItems();
        break;
      case 'addItem':
        data = addItem(p.name, p.unit, p.minStock, p.category);
        break;
      case 'stock':
        data = getStockForWarehouse(p.warehouse);
        break;
      case 'allStock':
        data = getAllStock();
        break;
      case 'search':
        data = searchItemAcrossWarehouses(p.q);
        break;
      case 'lowStock':
        data = getLowStock(p.warehouse);
        break;
      case 'stockIn':
        data = stockIn(p.warehouse, p.item, p.qty, p.note);
        break;
      case 'stockOut':
        data = stockOut(p.warehouse, p.item, p.qty, p.note);
        break;
      case 'transfer':
        data = transferStock(p.from, p.to, p.item, p.qty, p.note);
        break;
      case 'requestPurchase':
        data = requestPurchase(p.warehouse, p.item, p.qty, p.note, p.force === 'true');
        break;
      case 'requests':
        data = listPurchaseRequests(p.status);
        break;
      case 'updateRequestStatus':
        data = updatePurchaseRequestStatus(Number(p.row), p.status);
        break;
      default:
        return jsonOut_({ success: false, error: 'عملیات ناشناخته: ' + action });
    }
    return jsonOut_({ success: true, data: data });
  } catch (err) {
    return jsonOut_({ success: false, error: err.message });
  }
}

// ---------- Warehouses ----------

function listWarehouses() {
  return readRows_(getSheet_(SHEET_NAMES.WAREHOUSES)).map(function (r) {
    return { name: r.warehouse_name, location: r.location, contact: r.contact };
  });
}

function addWarehouse(name, location, contact) {
  name = (name || '').trim();
  if (!name) throw new Error('نام انبار الزامی است.');
  var sheet = getSheet_(SHEET_NAMES.WAREHOUSES);
  var existing = readRows_(sheet);
  if (existing.some(function (r) { return norm_(r.warehouse_name) === norm_(name); })) {
    throw new Error('انبار «' + name + '» از قبل ثبت شده است.');
  }
  sheet.appendRow([name, location || '', contact || '']);
  return { ok: true };
}

// ---------- Items ----------

function listItems() {
  return readRows_(getSheet_(SHEET_NAMES.ITEMS)).map(function (r) {
    return { name: r.item_name, unit: r.unit, minStock: r.min_stock, category: r.category };
  });
}

function addItem(name, unit, minStock, category) {
  name = (name || '').trim();
  if (!name) throw new Error('نام کالا الزامی است.');
  var sheet = getSheet_(SHEET_NAMES.ITEMS);
  var existing = readRows_(sheet);
  if (existing.some(function (r) { return norm_(r.item_name) === norm_(name); })) {
    throw new Error('کالای «' + name + '» از قبل در کاتالوگ ثبت شده است.');
  }
  sheet.appendRow([name, unit || '', Number(minStock) || 0, category || '']);
  return { ok: true };
}

// ---------- Stock ----------

function getStockQty_(row) {
  var q = Number(row.quantity);
  return isNaN(q) ? 0 : q;
}

function findStockRow_(rows, warehouse, item) {
  for (var i = 0; i < rows.length; i++) {
    if (norm_(rows[i].warehouse_name) === norm_(warehouse) && norm_(rows[i].item_name) === norm_(item)) {
      return rows[i];
    }
  }
  return null;
}

/** تغییر موجودی یک کالا در یک انبار به‌اندازه‌ی delta (مثبت یا منفی) */
function applyStockDelta_(sheet, warehouse, item, delta) {
  var rows = readRows_(sheet);
  var row = findStockRow_(rows, warehouse, item);

  if (!row) {
    if (delta < 0) {
      throw new Error('موجودی «' + item + '» در «' + warehouse + '» صفر است؛ نمی‌توان کاهش داد.');
    }
    sheet.appendRow([warehouse, item, delta, nowIso_()]);
    return delta;
  }

  var newQty = getStockQty_(row) + delta;
  if (newQty < 0) {
    throw new Error('موجودی ناکافی: «' + item + '» در «' + warehouse + '» فقط ' + getStockQty_(row) + ' عدد دارد.');
  }
  sheet.getRange(row._row, 3, 1, 2).setValues([[newQty, nowIso_()]]);
  return newQty;
}

function logTransaction_(type, warehouse, item, qty, refWarehouse, note) {
  getSheet_(SHEET_NAMES.TRANSACTIONS).appendRow([nowIso_(), type, warehouse, item, qty, refWarehouse || '', note || '']);
}

function getStockForWarehouse(warehouse) {
  var rows = readRows_(getSheet_(SHEET_NAMES.STOCK));
  return rows
    .filter(function (r) { return norm_(r.warehouse_name) === norm_(warehouse); })
    .map(function (r) { return { item: r.item_name, quantity: getStockQty_(r), updatedAt: r.last_updated }; });
}

function getAllStock() {
  var rows = readRows_(getSheet_(SHEET_NAMES.STOCK));
  return rows.map(function (r) {
    return { warehouse: r.warehouse_name, item: r.item_name, quantity: getStockQty_(r), updatedAt: r.last_updated };
  });
}

function searchItemAcrossWarehouses(query) {
  var q = norm_(query);
  var rows = readRows_(getSheet_(SHEET_NAMES.STOCK));
  return rows
    .filter(function (r) { return norm_(r.item_name).indexOf(q) !== -1; })
    .map(function (r) { return { warehouse: r.warehouse_name, item: r.item_name, quantity: getStockQty_(r) }; })
    .sort(function (a, b) { return b.quantity - a.quantity; });
}

function stockIn(warehouse, item, qty, note) {
  qty = Number(qty);
  if (!warehouse || !item || !qty || qty <= 0) throw new Error('انبار، کالا و تعداد (بزرگ‌تر از صفر) الزامی است.');
  var newQty = applyStockDelta_(getSheet_(SHEET_NAMES.STOCK), warehouse, item, qty);
  logTransaction_('IN', warehouse, item, qty, '', note);
  return { ok: true, newQty: newQty };
}

function stockOut(warehouse, item, qty, note) {
  qty = Number(qty);
  if (!warehouse || !item || !qty || qty <= 0) throw new Error('انبار، کالا و تعداد (بزرگ‌تر از صفر) الزامی است.');
  var newQty = applyStockDelta_(getSheet_(SHEET_NAMES.STOCK), warehouse, item, -qty);
  logTransaction_('OUT', warehouse, item, qty, '', note);
  return { ok: true, newQty: newQty };
}

function transferStock(fromWh, toWh, item, qty, note) {
  qty = Number(qty);
  if (!fromWh || !toWh || !item || !qty || qty <= 0) throw new Error('انبار مبدا، مقصد، کالا و تعداد الزامی است.');
  if (norm_(fromWh) === norm_(toWh)) throw new Error('انبار مبدا و مقصد نمی‌توانند یکسان باشند.');
  var sheet = getSheet_(SHEET_NAMES.STOCK);
  applyStockDelta_(sheet, fromWh, item, -qty);
  var newQtyDest = applyStockDelta_(sheet, toWh, item, qty);
  logTransaction_('TRANSFER', fromWh, item, qty, toWh, note);
  return { ok: true, newQtyDest: newQtyDest };
}

function getLowStock(warehouseFilter) {
  var stockRows = readRows_(getSheet_(SHEET_NAMES.STOCK));
  if (warehouseFilter) {
    stockRows = stockRows.filter(function (r) { return norm_(r.warehouse_name) === norm_(warehouseFilter); });
  }
  var itemRows = readRows_(getSheet_(SHEET_NAMES.ITEMS));
  var minByItem = {};
  itemRows.forEach(function (r) {
    minByItem[norm_(r.item_name)] = Number(r.min_stock) || 0;
  });

  var low = [];
  stockRows.forEach(function (r) {
    var threshold = minByItem[norm_(r.item_name)] || 0;
    var qty = getStockQty_(r);
    if (threshold > 0 && qty < threshold) {
      low.push({ warehouse: r.warehouse_name, item: r.item_name, quantity: qty, minStock: threshold });
    }
  });
  return low;
}

// ---------- Purchase Requests ----------

function requestPurchase(warehouse, item, qty, note, force) {
  qty = Number(qty);
  if (!warehouse || !item || !qty || qty <= 0) throw new Error('انبار، کالا و تعداد الزامی است.');

  var stockRows = readRows_(getSheet_(SHEET_NAMES.STOCK));
  var availableElsewhere = stockRows.filter(function (r) {
    return norm_(r.item_name) === norm_(item) && norm_(r.warehouse_name) !== norm_(warehouse) && getStockQty_(r) > 0;
  }).map(function (r) { return { warehouse: r.warehouse_name, quantity: getStockQty_(r) }; });

  if (availableElsewhere.length > 0 && !force) {
    return { ok: false, suggestion: availableElsewhere };
  }

  getSheet_(SHEET_NAMES.PURCHASE_REQUESTS).appendRow([nowIso_(), warehouse, item, qty, 'pending', note || '']);
  return { ok: true };
}

function listPurchaseRequests(statusFilter) {
  var rows = readRows_(getSheet_(SHEET_NAMES.PURCHASE_REQUESTS));
  if (statusFilter) {
    rows = rows.filter(function (r) { return norm_(r.status) === norm_(statusFilter); });
  }
  return rows.map(function (r) {
    return {
      row: r._row,
      timestamp: r.timestamp,
      warehouse: r.warehouse_name,
      item: r.item_name,
      quantity: r.quantity_requested,
      status: r.status,
      note: r.note
    };
  });
}

function updatePurchaseRequestStatus(rowNumber, newStatus) {
  var sheet = getSheet_(SHEET_NAMES.PURCHASE_REQUESTS);
  sheet.getRange(rowNumber, 5).setValue(newStatus);
  return { ok: true };
}
