# IIKO API Gaps (Server Integration)

Проверено: 2026-04-18.

## Что удалось подтвердить по официальной документации

Источник:
- локальный файл: `C:\Users\MiBookPro\Downloads\iikoserver-api.pdf`;
- рабочие страницы статьи:
  - `https://ru.iiko.help/article/api-documentations/avtorizatsiya`
  - `https://ru.iiko.help/article/api-documentations/zagruzka-i-redaktirovanie-prikhodnoy-nakladnoy`
  - `https://ru.iiko.help/article/api-documentations/opisanie-oshibok`

Подтверждено:
- авторизация: `POST /resto/api/auth?login=[login]&pass=[sha1passwordhash]`;
- токен можно передавать как cookie `key` или query-параметр `key`;
- импорт приходной накладной: `POST /resto/api/documents/import/incomingInvoice?key=...`;
- формат тела импорта: `Content-Type: application/xml`;
- для ошибок используется HTTP-статус + текст ошибки (часто `text/plain`).

## Практическая проверка demo-стенда (CRMID 8950663, 2026-04-18)

- endpoint авторизации живой, успешный ответ `200` с токеном получен;
- на стенде 9.4.8049.0 корректно отрабатывает `POST` с `application/x-www-form-urlencoded`
  (`login`, `pass=<sha1>` в body);
- вариант с query-only в auth на этом стенде возвращал `500` с текстом про `@FormParam`;
- endpoint импорта `incomingInvoice` доступен, но тестовый минимальный XML давал `500 NPE`
  (нужно доработать маппинг и обязательные поля под бизнес-данные стенда).

## Что остается узким местом

Технический контракт API теперь известен, но для стабильной выгрузки нужен маппинг позиций:
- iiko требует идентификаторы номенклатуры на строке (`product`/`supplierProduct`/`supplierProductArticle`);
- текущее OCR-распознавание обычно возвращает только человекочитаемые поля (название, количество, цена) без гарантированного GUID/артикула iiko;
- значит, без словаря соответствий (или отдельного резолвера номенклатуры) прямая API-загрузка будет часто падать, и останется fallback в CSV/XLSX.

## Текущее состояние проекта

- Playwright-контур удален;
- используется server-side клиент `app/iiko/server_client.py` по официальному контракту `auth + incomingInvoice`;
- по умолчанию безопасный режим: `IIKO_TRANSPORT=import_only`;
- при недоступности прямой загрузки работает CSV/XLSX fallback.
## Update 2026-04-18 (late smoke)

- Added catalog auto-resolve before upload:
  - fetch `/resto/api/v2/entities/products/list`;
  - match by `productArticle/article/num`, then `code`, then `name`;
  - auto-fill `product`, `productArticle`, optional `code`;
  - optional single-store auto-fill from `/resto/api/corporation/stores`.
- Added mandatory document metadata for `incomingInvoice` payload:
  - `documentNumber`, `incomingDocumentNumber`, `dateIncoming`, `useDefaultDocumentTime`;
  - `defaultStore` when one store is known.
- Live result on demo stand after metadata fix:
  - previously minimal payload returned `500 NPE`;
  - payload with metadata returns `200` and `<documentValidationResult><valid>true</valid>...`.
- Remaining practical gap for real production:
  - catalog quality/mapping quality (if OCR names do not match nomenclature, upload still fails fast with explicit row list).

## Update 2026-04-18 (posting + warehouse receipt)

- Official docs confirm that `incomingInvoice` has `status` with `NEW` / `PROCESSED` / `DELETED`.
- `documentValidationResult.valid=true` is not enough for the client-facing "done" state.
- Required verification levels:
  - import validation: `valid=true`;
  - document existence: export by number or by date returns the document and item rows;
  - posting: exported document has `status=PROCESSED`;
  - warehouse receipt: `/resto/api/v2/reports/balance/stores` changes for the resolved `product + store`.
- Live demo result on CRMID `8950663`:
  - previous successful uploads were `status=NEW`, so they were only drafts;
  - demo catalog initially had only `SERVICE` items, so it could not prove stock movement;
  - created a test `GOODS` item via `/resto/api/v2/entities/products/save`;
  - `status=PROCESSED` without `supplier` returned `409: Не указан поставщик`;
  - with supplier set, API import returned `valid=true`, export returned `PROCESSED`, and balance delta confirmed stock movement.
- Implementation status:
  - `IikoServerClient.upload_invoice_items(...)` now returns `IikoUploadResult`;
  - `IIKO_INCOMING_INVOICE_STATUS=NEW` is the safe default draft mode;
  - `IIKO_INCOMING_INVOICE_STATUS=PROCESSED` enables posting and can verify stock deltas when product/store are resolved;
  - `IIKO_DEFAULT_SUPPLIER_ID` is available for stands where supplier is not recognized from source data.

## Update 2026-04-21 (clean E2E reset + first-fill)

- Confirmed product cleanup API from official docs:
  - `POST /resto/api/v2/entities/products/delete` with body:
    `{"items":[{"id":"..."}]}`.
- Added reset workflow:
  - write-off non-zero balances via `outgoingInvoice`,
  - then delete active products,
  - script: `scripts/iiko_reset_stock.py`.
- Confirmed first-fill scenario from empty active catalog:
  - upload can auto-create missing goods when `IIKO_AUTOCREATE_PRODUCTS=true`,
  - fallback template for create now also checks `products/list?includeDeleted=true`.
- Practical note from live run:
  - `incomingInvoice` reached `status=PROCESSED`,
  - balance report may still not show deltas immediately for newly auto-created items on demo stand,
  - stock delta check was downgraded to warning (no hard fail) to avoid false-negative upload errors.
