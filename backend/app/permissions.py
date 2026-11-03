"""Ролевая модель: бизнес-роли ТПР (табл. 3, 4) + роли новой концепции, матрица «роль → действия»."""
from dataclasses import dataclass, field

ROLES: dict[str, dict] = {
    "BDTS.ORGWORK": {"label": "БДТС. Ответственный за организацию работ", "short": "Организация работ", "start": "/tasks"},
    "BDTS.SOGLZAD": {"label": "БДТС. Ответственный за согласование Задания на ДО", "short": "Согласование задания", "start": "/tasks"},
    "BDTS.POLEV": {"label": "БДТС. Исполнитель полевых работ", "short": "Полевые работы", "start": "/results"},
    "BDTS.KAMER": {"label": "БДТС. Исполнитель камеральных работ", "short": "Камеральные работы", "start": "/results"},
    "BDTS.SOGLTECH": {"label": "БДТС. Ответственный за согласование Технического отчета", "short": "Согласование ТО", "start": "/results"},
    "BDTS.OTVTECHOT": {"label": "БДТС. Ответственный за работу с Техническим отчетом", "short": "Работа с ТО (ДЭО)", "start": "/results"},
    "BDTS.OTVTS": {"label": "БДТС. Ответственный ДЭО за контроль технического состояния", "short": "Контроль ТС (ДЭО)", "start": "/hierarchy"},
    "BDTS.TO_UPLOAD": {"label": "Загрузка ТО XSD v3.8 (Роль 7.1, ГД)", "short": "Загрузка ТО", "start": "/reports", "delta": True},
    "BDTS.PLANNER": {"label": "Планирование ДО (Роли 1, 2)", "short": "Планирование", "start": "/cabinet", "delta": True},
    "BDTS.ADMIN": {"label": "Администратор модуля и НСИ", "short": "Администратор", "start": "/nsi/B306"},
    "BDTS.VIEWER": {"label": "Только просмотр", "short": "Просмотр", "start": "/hierarchy"},
}

ROLE_ACTIONS: dict[str, set[str]] = {
    "BDTS.ORGWORK": {"task.create", "task.edit", "task.delete", "task.send", "nsi.edit"},
    "BDTS.SOGLZAD": {"task.approve", "task.edit"},
    "BDTS.POLEV": {"result.pe", "result.pe_finish", "result.concl"},
    "BDTS.KAMER": {"result.kp", "result.form", "result.send", "result.vtd_upload", "result.export"},
    "BDTS.SOGLTECH": {"result.agree", "result.export"},
    "BDTS.OTVTECHOT": {"result.deo", "result.epb_need", "result.epb", "result.epb_export", "result.export", "to.decide", "to.hs"},
    "BDTS.OTVTS": {"ts.confirm", "ts.create", "ts.edit", "ts.import", "analytics", "int.load", "survey"},
    "BDTS.TO_UPLOAD": {"to.upload", "to.map", "to.send"},
    "BDTS.PLANNER": {"plan", "int.load", "survey", "analytics"},
    "BDTS.ADMIN": {"nsi.edit", "settings", "vtd.edit"},
    "BDTS.VIEWER": set(),
}

ALL_ACTIONS = sorted(set().union(*ROLE_ACTIONS.values()))

# Экраны, на которых роль изменяет данные (просмотр доступен всем ролям модуля)
ROLE_SCREENS: dict[str, list[str]] = {
    "BDTS.ORGWORK": ["W-1.1", "W-1.2", "W-5.1"],
    "BDTS.SOGLZAD": ["W-1.2"],
    "BDTS.POLEV": ["W-2.1", "W-2.2"],
    "BDTS.KAMER": ["W-2.1", "W-2.2", "W-2.5"],
    "BDTS.SOGLTECH": ["W-2.2"],
    "BDTS.OTVTECHOT": ["W-2.2", "W-2.4", "W-2.5"],
    "BDTS.OTVTS": ["W-3.1", "W-3.2", "W-3.3", "W-3.4", "W-3.5", "W-3.6", "W-4.1", "W-3.8", "W-8.1", "W-8.2", "W-8.3"],
    "BDTS.TO_UPLOAD": ["W-2.3", "W-2.4"],
    "BDTS.PLANNER": ["W-0.4", "W-3.7", "W-3.8", "W-4.1", "W-8.1", "W-8.2", "W-8.3"],
    "BDTS.ADMIN": ["W-5.1", "W-5.10", "W-6.1", "W-6.2", "W-7.1"],
    "BDTS.VIEWER": [],
}


@dataclass
class CurrentUser:
    username: str
    fio: str
    roles: list[str]
    deo: str = ""  # пусто — доступ ко всем ДЭО
    position: str = ""
    actions: set[str] = field(default_factory=set)

    @property
    def display(self) -> str:
        tech = ", ".join(r for r in self.roles if r in ROLES)
        return f"{self.fio} ({tech})" if tech else self.fio

    def can(self, action: str) -> bool:
        return action in self.actions

    def deo_allowed(self, deo: str | None) -> bool:
        return not self.deo or not deo or self.deo == deo

    @property
    def start_route(self) -> str:
        roles = [r for r in self.roles if r in ROLES]
        if len(roles) != 1:
            return "/cabinet"
        return ROLES[roles[0]]["start"]


def build_user(username: str, fio: str, roles: list[str], deo: str = "", position: str = "") -> CurrentUser:
    roles = [r for r in roles if r in ROLES]
    actions: set[str] = set()
    for r in roles:
        actions |= ROLE_ACTIONS.get(r, set())
    return CurrentUser(username=username, fio=fio or username, roles=roles, deo=deo or "", position=position, actions=actions)


# Демо-пользователи dev-режима; совпадают с infra/keycloak/realm-bdts.json
DEV_USERS: dict[str, dict] = {
    "demo": {"fio": "Демо Пользователь", "roles": list(ROLES.keys() - {"BDTS.VIEWER"}), "deo": ""},
    "gd.org": {"fio": "ФИО_1", "roles": ["BDTS.ORGWORK"], "deo": "", "position": "Начальник отдела организации работ"},
    "gd.sogl": {"fio": "ФИО_2", "roles": ["BDTS.SOGLZAD"], "deo": "ОРГ_9"},
    "gd.pole": {"fio": "ФИО_3", "roles": ["BDTS.POLEV"], "deo": "ОРГ_9"},
    "gd.kamer": {"fio": "ФИО_4", "roles": ["BDTS.KAMER"], "deo": "ОРГ_9"},
    "gd.soglto": {"fio": "ФИО_5", "roles": ["BDTS.SOGLTECH"], "deo": "ОРГ_9"},
    "deo.to": {"fio": "ФИО_6", "roles": ["BDTS.OTVTECHOT"], "deo": "ОРГ_9"},
    "deo.ts": {"fio": "ФИО_7", "roles": ["BDTS.OTVTS"], "deo": "ОРГ_9", "position": "Инженер по диагностике"},
    "gd.upload": {"fio": "ФИО_8", "roles": ["BDTS.TO_UPLOAD"], "deo": ""},
    "deo.plan": {"fio": "ФИО_9", "roles": ["BDTS.PLANNER"], "deo": ""},
    "admin": {"fio": "ФИО_10", "roles": ["BDTS.ADMIN"], "deo": ""},
    "viewer": {"fio": "ФИО_11", "roles": ["BDTS.VIEWER"], "deo": ""},
}
