# iikoRMS Demo Profile (2026-03-16)

## Environment snapshot
- License: `iikoRMS`
- Service contract: `yes`
- CrmID: `8950663`
- Domain: `https://840-786-070.iiko.it/resto/`
- Version: `9.4.8049.0`
- Type: `RMS without chain`
- Location: `RU, Moscow`
- Time zone: `Europe/Moscow`
- Language: `ru-RU`
- Tariff: `iikoCloud 2017`
- Open period: `60 days`

## Access (test credentials)
- iikoWeb: `https://840-786-070.iikoweb.ru/navigator/ru-RU/index.html#/main`
- Login: `user`
- Password: `user#test`
- PIN: `1111`

## Distributions
- Front: `https://downloads.iiko.online/9.4.8049.0/iiko/RMS/Front/Setup.Front.exe`
- BackOffice: `https://downloads.iiko.online/9.4.8049.0/iiko/RMS/BackOffice/Setup.RMS.BackOffice.exe`

## Official instructions
- Add cash register:
  - `https://ru.iiko.help/articles/#!iikooffice-7-9/topic-720/a/h2_541923364`
- Nomenclature directory:
  - `https://ru.iiko.help/articles/#!iikooffice-7-9/topic-201`
- Employees:
  - `https://ru.iiko.help/articles/iikooffice-7-9/topic-99`
- Menu export:
  - `https://ru.iiko.help/articles/iikooffice-7-9/topic-905`
- Demo stand installation:
  - `https://ru.iiko.help/articles/?readerUiPreview=1#!api-documentations/kak-ustanovit-demo-stend`

## Practical usage in this project
1. Manual smoke: sign in to `iikoWeb`, verify credentials and locale.
2. Integration prep: align endpoint behavior with `docs/exp/IIKO_SERVER_INCOMING_INVOICE_MAPPING.md`.
3. Development flow: use phone loop (`wplan` -> `wmailbox codexclip` -> `wmailbox watch`) for iterative checks while testing integration scripts.

## Security note
Credentials in this file are for demo/testing only. Before production usage, move secrets to secure storage and rotate test credentials.

