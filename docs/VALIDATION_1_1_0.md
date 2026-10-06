# Проверка Network Tools 1.1.0

Дата: 06.10.2026. Статус: исходники проверены; native candidate CI выполняется перед выпуском.

Локально пройдены 222 pytest tests, включая 36 GUI checks в Tk display;
186 tests проверяют расчёты, MAC CLI, тему и release gating без GUI. Ruff проходит.
Это подтверждение исходного GUI, не Windows EXE. Числа будут обновлены после
окончания release-gating tests и actual native Windows smoke.

Native report, source commit, environment и hash готового EXE фиксируются
после CI в этом документе и RELEASE_VERIFICATION.json. Клиентские Windows
10/11, разные DPI, Defender и SmartScreen пока не проверены отдельно.

Историческая проверка 1.0.0 сохранена в VALIDATION_2026-10-05.md.
