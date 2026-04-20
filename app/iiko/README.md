# `app/iiko/`

Server-side iiko integration without browser automation.

Contents:
- `server_client.py` - API client for auth and incoming invoice import.
- `import_export.py` - CSV/XLSX export for manual import fallback.

Notes:
- transport mode is controlled by `IIKO_TRANSPORT` (`api` or `import_only`);
- default safe mode is `import_only`;
- API mode can auto-resolve product mapping by catalog lookup
  (`IIKO_AUTORESOLVE_PRODUCTS=true`);
- optional first-fill mode can auto-create missing products in iiko and continue upload
  (`IIKO_AUTOCREATE_PRODUCTS=true`).
- explicit mapping in `InvoiceItem.extras` has priority
  (`product` / `productArticle` / `supplierProduct` / `supplierProductArticle`).
- `IIKO_INCOMING_INVOICE_STATUS=NEW` creates a draft incoming invoice.
- `IIKO_INCOMING_INVOICE_STATUS=PROCESSED` attempts real posting; this requires supplier mapping
  (`supplier` in extras or `IIKO_DEFAULT_SUPPLIER_ID`) and can verify stock balance deltas
  when `IIKO_VERIFY_STOCK_BALANCE=true`.
- A successful upload result should be interpreted by exported document status:
  `NEW` means created but not posted, `PROCESSED` means posted; stock verification is a
  stronger proof for goods receipts.
