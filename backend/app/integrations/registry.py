"""Выбор адаптеров по конфигурации. Реальный адаптер подключается регистрацией класса под именем ADAPTER_*."""
from functools import lru_cache

from app.config import get_settings
from app.integrations import mock

_ADAPTERS = {
    "plan": {"mock": mock.MockPlanSource},
    "bdo": {"mock": mock.MockBdoClient},
    "report_sink": {"mock": mock.MockReportSink},
    "diag_sink": {"mock": mock.MockDiagnosticsSink},
    "ps0": {"mock": mock.MockPs0Client},
    "notifier": {"mock": mock.MockNotifier},
}


def _make(port: str):
    mode = getattr(get_settings(), f"adapter_{port}")
    try:
        return _ADAPTERS[port][mode]()
    except KeyError as e:
        raise RuntimeError(f"Адаптер {port}={mode} не зарегистрирован") from e


@lru_cache
def plan_source():
    return _make("plan")


@lru_cache
def bdo_client():
    return _make("bdo")


@lru_cache
def report_sink():
    return _make("report_sink")


@lru_cache
def diag_sink():
    return _make("diag_sink")


@lru_cache
def ps0_client():
    return _make("ps0")


@lru_cache
def notifier():
    return _make("notifier")


def adapters_status() -> list[dict]:
    s = get_settings()
    rows = [
        ("Аутентификация и авторизация", "Keycloak OIDC (LDAP-федерация — по готовности каталога)", s.auth_mode, "in"),
        ("Пообъектный план", plan_source().name, s.adapter_plan, "in"),
        ("Атрибуты ТМ/ЕО из МП-3 «БДО»", bdo_client().name, s.adapter_bdo, "in"),
        ("Передача технических отчётов", report_sink().name, s.adapter_report_sink, "out"),
        ("Сведения по диагностическому обследованию", diag_sink().name, s.adapter_diag_sink, "out"),
        ("Задачи на добавление ЕО/ТМ в БДО", ps0_client().name, s.adapter_ps0, "out"),
        ("Оповещения e-mail", notifier().name, s.adapter_notifier, "out"),
    ]
    return [{"flow": f, "system": sysname, "mode": mode, "direction": d} for f, sysname, mode, d in rows]
