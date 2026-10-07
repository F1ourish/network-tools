# Changelog

## 1.2.0 — 2026-10-07

- Генератор паролей: secrets/CSPRNG, длина 8–128 (default 20), обязательные выбранные
  группы, ручной набор спецсимволов, исключение похожих символов и точная энтропия.
- Скрытие/показ, Copy/Очистить, очистка устаревшего результата при изменении политики;
  условная очистка собственного clipboard через 30 с и при закрытии.
- Контекстная offline справка всех шести вкладок (F1): назначение, шаги, примеры,
  ограничения, включая LPM и отличия wildcard от netmask и permit/deny.
- Ctrl+6 выбирает генератор; Ctrl+Shift+C копирует пароль. Темы и прежние инструменты сохранены.
- Publisher выбирает release notes по текущей версии вместо фиксированного 1.1.0.


## 1.1.0 — 2026-10-06

- Added IPv4 subnet calculator with default 192.168.1.0/24, CIDR paste,
  netmask validation, network-only validation and separate subnet/host/broadcast outputs.
- Added full/binary masks, wildcard, /31 and /32 handling, and explicit /0 conventions.
- Added bounded host-list pagination and page copy without enumerating large networks.
- Added offline MTU/MSS calculator for IPv4/IPv6 with manual encapsulation overhead.
- Added route longest-prefix matching, equal candidates and address wildcard matching for ACLs.
- Replaced the original interface with five tabs and saved day/night themes.
- Added tab navigation, current-tool copy and theme keyboard shortcuts.
- Preserved the four MAC formats, case controls, source CLI and portable EXE filename.
- Added pinned UI dependencies, bundled third-party notices, expanded EXE verification,
  portable ZIP, SHA-256 checksums and a gated GitHub Release workflow.

## 1.0.0 — verified candidate, not separately released

- MAC-48 conversion: Cisco, Colon, Hyphen, Plain; case selection.
- Live Tkinter GUI, readonly result, Copy and keyboard shortcuts.
- Shared parsing API and optional source CLI.
- Native Windows build verified on 2026-10-05: 81 tests and 19 EXE checks.
- Historical evidence: docs/VALIDATION_2026-10-05.md.
