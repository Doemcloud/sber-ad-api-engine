Сюда положите сертификат «Russian Trusted Root CA» (Минцифры) — он нужен для HTTPS к GigaChat:
https://www.gosuslugi.ru/crt → файл `russian_trusted_root_ca.crt`.
Затем в `.env`: `GIGACHAT_CA_BUNDLE=/certs/russian_trusted_root_ca.crt` и уберите `GIGACHAT_VERIFY_SSL=0`.
Сами сертификаты в git не коммитятся.
