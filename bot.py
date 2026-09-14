#!/usr/bin/env python3
"""untisbot -- meldet WebUntis-Stundenplanaenderungen per Telegram.

Alles in einer Datei. Das ist Absicht: Das Projekt ist klein genug, und
beim Einspielen ueber die GitHub-Weboberflaeche ist eine Datei ein
Bruchteil der Arbeit von acht.

Aufbau, von innen nach aussen:

    Modell      Lesson, Change      -- unveraenderliche Datensaetze
    Rein        normalise, diff,    -- Funktionen ohne Seiteneffekte,
                render                 vollstaendig testbar ohne Netz
    Randschicht untis, telegram,    -- alles I/O, duenn gehalten
                store
    Ablauf      check, watch        -- setzt die Teile zusammen

Aufrufe:

    python bot.py check              einmal pruefen
    python bot.py watch --minutes 55 55 Minuten lang alle 5 Minuten pruefen
    python bot.py selftest           Zugangsdaten einzeln durchtesten
    python bot.py show               Stundenplan anzeigen (Diagnose)
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import html
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

import requests

log = logging.getLogger("untisbot")


# ===========================================================================
#  Konfiguration
# ===========================================================================

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"

#: Aussagekraeftiger User-Agent -- manche WebUntis-Instanzen verlangen einen.
USER_AGENT = "untisbot/2.0 (privates Stundenplan-Tool)"

#: Format-Version des gespeicherten Zustands. Passt sie nicht, wird der
#: alte Zustand verworfen statt falsch gedeutet.
SCHEMA = 2


class ConfigError(RuntimeError):
    """Eine noetige Einstellung fehlt oder ist unbrauchbar."""


@dataclass(frozen=True)
class Config:
    telegram_token: str
    telegram_chats: tuple[str, ...]
    untis_server: str
    untis_school: str
    untis_user: str
    untis_password: str
    untis_klasse: str = ""
    lookahead_days: int = 7
    timezone: str = "Europe/Berlin"

    @staticmethod
    def from_env() -> "Config":
        """Liest die Konfiguration aus Umgebungsvariablen.

        Die einzige Stelle im Programm, die os.environ anfasst.
        """
        _load_dotenv(BASE_DIR / ".env")

        def need(name: str) -> str:
            value = (os.environ.get(name) or "").strip()
            if not value:
                raise ConfigError(
                    f"{name} fehlt.\n"
                    "  Lokal: in die .env eintragen.\n"
                    "  Auf GitHub: Settings -> Secrets and variables -> Actions."
                )
            return value

        def maybe(name: str, default: str = "") -> str:
            return (os.environ.get(name) or default).strip()

        token = need("TELEGRAM_BOT_TOKEN")
        if ":" not in token:
            raise ConfigError(
                "TELEGRAM_BOT_TOKEN hat ein unerwartetes Format.\n"
                "  Erwartet: 123456789:AAH-xxxxxxxxxxxxxxxxxxxxxxxxx\n"
                f"  Bekommen: {mask(token)}"
            )

        chats = tuple(c.strip() for c in need("TELEGRAM_CHAT_ID").split(",") if c.strip())
        if not chats:
            raise ConfigError("TELEGRAM_CHAT_ID enthaelt keine gueltige ID.")

        try:
            days = int(maybe("LOOKAHEAD_DAYS", "7"))
        except ValueError:
            raise ConfigError("LOOKAHEAD_DAYS muss eine ganze Zahl sein.") from None

        return Config(
            telegram_token=token,
            telegram_chats=chats,
            untis_server=need("WEBUNTIS_SERVER").replace("https://", "").rstrip("/"),
            untis_school=need("WEBUNTIS_SCHOOL"),
            untis_user=need("WEBUNTIS_USERNAME"),
            untis_password=need("WEBUNTIS_PASSWORD"),
            untis_klasse=maybe("WEBUNTIS_KLASSE"),
            lookahead_days=max(1, min(days, 30)),
            timezone=maybe("TIMEZONE", "Europe/Berlin"),
        )


def _load_dotenv(path: Path) -> None:
    """Minimaler .env-Leser -- spart die Abhaengigkeit python-dotenv.

    Vorhandene Umgebungsvariablen gewinnen: Auf GitHub kommen die Werte aus
    den Secrets, eine mitgelieferte .env darf sie nicht ueberschreiben.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def mask(secret: str | None) -> str:
    """Kuerzt ein Geheimnis fuer die Log-Ausgabe."""
    if not secret:
        return "<leer>"
    return f"{secret[:4]}...{secret[-4:]}" if len(secret) > 10 else "*" * len(secret)


def now_local(tz_name: str) -> dt.datetime:
    """Aktuelle Zeit in der Schulzeitzone.

    Der GitHub-Runner laeuft in UTC. Ohne Umrechnung waere "heute"/"morgen"
    in den Nachrichten zeitweise um einen Tag daneben.
    """
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(ZoneInfo(tz_name))
    except Exception as exc:
        log.warning("Zeitzone %s nicht nutzbar (%s) -- nutze Systemzeit", tz_name, exc)
        return dt.datetime.now()


# ===========================================================================
#  Modell
# ===========================================================================

CANCELLED = "cancelled"
IRREGULAR = "irregular"
REGULAR = "regular"


@dataclass(frozen=True)
class Lesson:
    """Eine Stunde, normalisiert und vergleichbar.

    Unveraenderlich und mit sortierten Listen -- damit zwei inhaltlich
    gleiche Stunden auch wirklich gleich sind. WebUntis liefert Raeume und
    Lehrer mal in dieser, mal in jener Reihenfolge; ohne Sortierung waere
    jede zweite Abfrage eine "Aenderung".
    """

    uid: int | None
    date: str                      # YYYY-MM-DD
    start: str                     # HH:MM
    end: str                       # HH:MM
    subjects: tuple[str, ...] = ()
    teachers: tuple[str, ...] = ()
    rooms: tuple[str, ...] = ()
    status: str = REGULAR
    note: str = ""                 # substText / lstext
    group: str = ""                # Kursgruppe (sg)
    lesson_no: int | None = None   # lsnumber -- stabil ueber Termine hinweg

    def __post_init__(self) -> None:
        """Erzwingt sortierte Tupel -- die Invariante dieser Klasse.

        Darauf beruht der gesamte Vergleich. Wuerde die Sortierung nur an
        der Stelle passieren, wo Lessons aus WebUntis gebaut werden, waere
        sie beim naechsten Konstruktionsweg (JSON laden, Test, Umbau)
        wieder weg -- und der Bot meldete Aenderungen, die keine sind.
        """
        for name in ("subjects", "teachers", "rooms"):
            value = getattr(self, name)
            object.__setattr__(self, name, tuple(sorted(value)))

    @property
    def title(self) -> str:
        """Anzeigename -- nie leer.

        Bei Sonderterminen (Klausuren, Exkursionen) liefert WebUntis kein
        Fach, aber einen Text wie "D-KA". Der ist aussagekraeftiger als
        ein Fragezeichen.
        """
        return "+".join(self.subjects) or self.note or self.group or "Termin"

    @property
    def key(self) -> str:
        """Fachlicher Schluessel, falls die WebUntis-id wechselt."""
        return f"{self.date}|{self.start}|{self.title}"

    @property
    def day(self) -> dt.date:
        return dt.date.fromisoformat(self.date)

    def to_json(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_json(raw: dict) -> "Lesson":
        fields = {f.name for f in dataclasses.fields(Lesson)}
        data = {k: v for k, v in raw.items() if k in fields}
        for name in ("subjects", "teachers", "rooms"):
            data[name] = tuple(data.get(name) or ())
        return Lesson(**data)


#: Aenderungsarten, nach Wichtigkeit sortiert -- bestimmt die Reihenfolge
#: in der Nachricht.
KINDS = (
    "cancelled",     # faellt aus
    "uncancelled",   # Ausfall zurueckgenommen
    "added",         # zusaetzlicher Termin
    "removed",       # aus dem Plan genommen
    "subject",       # anderes Fach
    "teacher",       # Vertretung
    "room",          # Raumwechsel
    "time",          # verschoben
    "marked",        # von WebUntis als Aenderung markiert, Felder gleich
    "unmarked",      # Markierung zurueckgenommen
    "note",          # nur Zusatztext
)

LABELS = {
    "cancelled": "entfällt",
    "uncancelled": "findet doch statt",
    "added": "neuer Termin",
    "removed": "nicht mehr im Plan",
    "subject": "Fachwechsel",
    "teacher": "Vertretung",
    "room": "Raumwechsel",
    "time": "verschoben",
    "marked": "als Änderung markiert",
    "unmarked": "wieder regulär",
    "note": "Info geändert",
}

ICONS = {
    "cancelled": "❌", "uncancelled": "✅", "added": "➕", "removed": "➖",
    "subject": "📚", "teacher": "👤", "room": "🚪", "time": "🕐",
    "marked": "⚠️", "unmarked": "✅", "note": "ℹ️",
}


@dataclass(frozen=True)
class Change:
    kind: str
    lesson: Lesson
    detail: str = ""

    @property
    def sort_key(self) -> tuple:
        rank = KINDS.index(self.kind) if self.kind in KINDS else len(KINDS)
        return (self.lesson.date, self.lesson.start, rank, self.lesson.title)


# ===========================================================================
#  WebUntis  (I/O)
# ===========================================================================

class UntisError(RuntimeError):
    """WebUntis ist nicht erreichbar oder antwortet nicht brauchbar."""


class AuthError(UntisError):
    """Zugangsdaten oder Schulkuerzel stimmen nicht. Wiederholen hilft nicht."""


class NothingToDo(UntisError):
    """Kein Fehler, sondern ein Zustand.

    Ferien, Wochenende, oder das Schuljahr ist noch nicht angelegt. Der Bot
    muss das ruhig aussitzen -- und auf keinen Fall "alles entfaellt" melden.
    """


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def normalise(period: Any, resolve: Callable[[str, Iterable], tuple[str, ...]]) -> Lesson:
    """Wandelt ein WebUntis-Objekt in eine Lesson.

    'resolve' loest Fach-/Raum-/Lehrer-IDs in Namen auf. Als Funktion
    hereingereicht, damit diese Funktion selbst ohne Netz testbar bleibt.
    """
    raw = getattr(period, "_data", {}) or {}
    code = getattr(period, "code", None)

    return Lesson(
        uid=raw.get("id"),
        date=f"{period.start:%Y-%m-%d}",
        start=f"{period.start:%H:%M}",
        end=f"{period.end:%H:%M}",
        subjects=resolve("subjects", raw.get("su")),
        teachers=resolve("teachers", raw.get("te")),
        rooms=resolve("rooms", raw.get("ro")),
        status=code if code in (CANCELLED, IRREGULAR) else REGULAR,
        note=_text(raw.get("substText")) or _text(raw.get("lstext")),
        group=_text(raw.get("sg")),
        lesson_no=raw.get("lsnumber"),
    )


class Untis:
    """Duenne Huelle um die webuntis-Bibliothek.

    Haelt saemtliches WebUntis-Wissen an einem Ort: Anmeldung, Aufloesung
    von IDs zu Namen, Schuljahresgrenzen, Abrufwege.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._session: Any = None
        self._lookup: dict[str, dict[int, str]] = {}

    # -- Lebenszyklus ------------------------------------------------------

    def __enter__(self) -> "Untis":
        import webuntis

        self._session = webuntis.Session(
            server=self.cfg.untis_server,
            school=self.cfg.untis_school,
            username=self.cfg.untis_user,
            password=self.cfg.untis_password,
            useragent=USER_AGENT,
        )
        try:
            self._session.login()
        except Exception as exc:
            name = type(exc).__name__
            if "Credential" in name or "Auth" in name:
                raise AuthError(
                    f"Anmeldung abgelehnt ({exc}).\n"
                    "  Pruefe WEBUNTIS_USERNAME, WEBUNTIS_PASSWORD und "
                    "WEBUNTIS_SCHOOL."
                ) from exc
            raise UntisError(
                f"Verbindung zu {self.cfg.untis_server} fehlgeschlagen: {exc}"
            ) from exc

        log.info("Bei WebUntis angemeldet (%s / %s)",
                 self.cfg.untis_server, self.cfg.untis_school)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._session is not None:
            try:
                self._session.logout(suppress_errors=True)
            except Exception:
                pass
            self._session = None

    # -- Namensaufloesung --------------------------------------------------

    def _table(self, kind: str) -> dict[int, str]:
        """ID -> Name fuer subjects/rooms/teachers, einmal pro Sitzung geholt.

        Schlaegt der Abruf fehl (viele Schueler-Accounts duerfen die
        Lehrerliste nicht lesen), bleibt die Tabelle leer -- dann greift der
        Rueckfall auf die Namen in den Rohdaten der Stunde.
        """
        if kind not in self._lookup:
            try:
                items = getattr(self._session, kind)()
                self._lookup[kind] = {
                    int(i.id): _text(i.name) for i in items if _text(i.name)
                }
                log.debug("%s: %d Eintraege aufgeloest", kind, len(self._lookup[kind]))
            except Exception as exc:
                log.debug("%s nicht abrufbar (%s) -- nutze Rohdaten", kind, exc)
                self._lookup[kind] = {}
        return self._lookup[kind]

    def _resolver(self) -> Callable[[str, Iterable], tuple[str, ...]]:
        def resolve(kind: str, entries: Iterable) -> tuple[str, ...]:
            table = self._table(kind)
            out = []
            for entry in entries or []:
                if not isinstance(entry, dict):
                    continue
                name = table.get(entry.get("id")) or _text(entry.get("name"))
                if name:
                    out.append(name)
            return tuple(sorted(out))
        return resolve

    # -- Schuljahre --------------------------------------------------------

    def schoolyears(self) -> list[Any]:
        try:
            return sorted(self._session.schoolyears(), key=lambda y: y.start)
        except Exception as exc:
            log.debug("Schuljahre nicht abrufbar: %s", exc)
            return []

    def clamp(self, start: dt.date, end: dt.date) -> tuple[dt.date, dt.date]:
        """Beschneidet das Fenster auf ein einzelnes Schuljahr.

        WebUntis lehnt Abfragen ab, die eine Schuljahresgrenze ueberschreiten
        oder ganz ausserhalb liegen.
        """
        years = self.schoolyears()
        if not years:
            return start, end

        covering = [y for y in years if y.start.date() <= start <= y.end.date()] or \
                   [y for y in years if y.start.date() <= end <= y.end.date()]

        if not covering:
            upcoming = [y for y in years if y.start.date() > end]
            hint = (
                f"Das naechste Schuljahr ({upcoming[0].name}) beginnt am "
                f"{upcoming[0].start:%d.%m.%Y}."
                if upcoming else
                f"Das letzte eingetragene Schuljahr ({years[-1].name}) endete am "
                f"{years[-1].end:%d.%m.%Y}; das neue ist noch nicht angelegt."
            )
            raise NothingToDo(
                f"Kein Schuljahr deckt {start:%d.%m.} bis {end:%d.%m.%Y} ab. {hint}"
            )

        year = covering[0]
        new = (max(start, year.start.date()), min(end, year.end.date()))
        if new != (start, end):
            log.info("Fenster auf Schuljahr %s beschnitten: %s bis %s",
                     year.name, *new)
        return new

    # -- Abruf -------------------------------------------------------------

    def timetable(self, start: dt.date, end: dt.date) -> list[Lesson]:
        """Holt den Stundenplan. Probiert persoenlichen Plan, dann Klassenplan."""
        start, end = self.clamp(start, end)
        resolve = self._resolver()
        problems: list[str] = []
        answered = False

        for label, getter in self._strategies(start, end):
            try:
                periods = list(getter())
            except Exception as exc:
                problems.append(f"{label}: {exc}")
                continue

            # Eine saubere Antwort beendet die Suche -- auch wenn sie leer
            # ist. Sonst liefert der Bot bei einem leeren persoenlichen Plan
            # stillschweigend den KLASSENPLAN: eine voellig andere
            # Datenmenge, die als Massen-Aenderung durchschlagen wuerde.
            answered = True
            if periods:
                lessons = self._convert(periods, resolve)
                if not lessons:
                    # WebUntis lieferte Stunden, aber KEINE liess sich lesen.
                    # Das ist ein Defekt (API-Aenderung?), kein leeres
                    # Fenster -- als "leer" durchgereicht wuerde daraus eine
                    # Massenmeldung "alles nicht mehr im Plan".
                    raise UntisError(
                        f"{len(periods)} Stunden empfangen, keine davon lesbar "
                        "-- vermutlich hat sich das WebUntis-Format geaendert."
                    )
                log.info("Abruf ueber %s: %d Stunden", label, len(lessons))
                return lessons

            problems.append(f"{label}: 0 Stunden")
            break

        if answered:
            # WebUntis hat sauber geantwortet, im Fenster steht nur nichts.
            raise NothingToDo(
                f"Keine Stunden zwischen {start:%d.%m.} und {end:%d.%m.%Y} "
                "(Wochenende, Ferien, oder der Plan ist noch nicht gefuellt)."
            )

        raise UntisError("Kein Stundenplan abrufbar:\n  - " + "\n  - ".join(problems))

    def _strategies(self, start: dt.date, end: dt.date) -> list[tuple[str, Callable]]:
        ways: list[tuple[str, Callable]] = [
            ("my_timetable", lambda: self._session.my_timetable(start=start, end=end)),
        ]
        if self.cfg.untis_klasse:
            ways.append((f"klasse:{self.cfg.untis_klasse}",
                         lambda: self._by_klasse(start, end)))
        return ways

    def _by_klasse(self, start: dt.date, end: dt.date) -> Iterable:
        wanted = self.cfg.untis_klasse.lower()
        klassen = list(self._session.klassen())
        match = next((k for k in klassen if _text(k.name).lower() == wanted), None)
        if match is None:
            available = ", ".join(sorted(_text(k.name) for k in klassen)[:30])
            raise UntisError(f"Klasse {self.cfg.untis_klasse!r} unbekannt. "
                             f"Verfuegbar: {available}")
        return self._session.timetable(klasse=match, start=start, end=end)

    @staticmethod
    def _convert(periods: Sequence, resolve: Callable) -> list[Lesson]:
        """Eine unlesbare Stunde darf nie den ganzen Lauf kippen."""
        lessons = []
        for period in periods:
            try:
                lessons.append(normalise(period, resolve))
            except Exception as exc:
                log.warning("Stunde uebersprungen (%s): %r",
                            exc, getattr(period, "_data", None))
        return sorted(lessons, key=lambda l: (l.date, l.start, l.key))


# ===========================================================================
#  Vergleich  (rein)
# ===========================================================================

def window_of(days: int, today: dt.date) -> tuple[dt.date, dt.date]:
    return today, today + dt.timedelta(days=days)


def overlap(
    new: tuple[dt.date, dt.date],
    old: tuple[dt.date, dt.date] | None,
) -> tuple[dt.date, dt.date] | None:
    """Der Zeitraum, in dem ein Vergleich ueberhaupt aussagekraeftig ist.

    Das Abruffenster rollt taeglich weiter. Was heute neu hineinrutscht, war
    gestern nicht im Blick -- diese Stunden sind also nicht "hinzugekommen",
    sie wurden nur noch nie betrachtet. Ohne diese Einschraenkung meldet der
    Bot jeden Tag einen kompletten Schultag als "neuer Termin".
    """
    if old is None:
        return None
    start, end = max(new[0], old[0]), min(new[1], old[1])
    return (start, end) if start <= end else None


def within(lessons: Iterable[Lesson], win: tuple[dt.date, dt.date] | None) -> list[Lesson]:
    if win is None:
        return list(lessons)
    start, end = win
    return [l for l in lessons if start <= l.day <= end]


def pair_up(
    old: Sequence[Lesson],
    new: Sequence[Lesson],
) -> tuple[list[tuple[Lesson, Lesson]], list[Lesson], list[Lesson]]:
    """Ordnet alte und neue Stunden einander zu.

    Zweistufig, weil keine Kennung allein genuegt:
      1. WebUntis-id   -- praezise, aber neu angelegte Vertretungen
                          bekommen eine neue id
      2. Datum|Zeit|Titel -- ueberlebt einen id-Wechsel

    Ohne Stufe 2 meldet der Bot "Stunde weg" plus "Stunde neu", wo in
    Wahrheit nur der Raum gewechselt hat.
    """
    pairs: list[tuple[Lesson, Lesson]] = []
    left, right = list(old), list(new)

    # Doppelte ids kaemen einem WebUntis-Fehler gleich, aber verlieren
    # duerfen wir dabei nichts: setdefault behaelt den ersten Treffer,
    # der Rest laeuft ueber die naechste Stufe.
    by_id: dict[int, Lesson] = {}
    for lesson in right:
        if lesson.uid is not None:
            by_id.setdefault(lesson.uid, lesson)

    matched_right: set[int] = set()
    rest_left: list[Lesson] = []

    for lesson in left:
        partner = by_id.get(lesson.uid) if lesson.uid is not None else None
        if partner is not None and id(partner) not in matched_right:
            pairs.append((lesson, partner))
            matched_right.add(id(partner))
        else:
            rest_left.append(lesson)

    # Stufe 2 vergibt NICHT der Reihe nach, sondern nach Guete: erst alle
    # denkbaren Paarungen bewerten, dann die besten zuerst festmachen.
    #
    # Der Unterschied ist nicht akademisch. Konkurrieren zwei alte Stunden
    # um denselben neuen Eintrag, gewaenne bei reihenfolge-basierter Vergabe
    # die zufaellig zuerst gelistete -- und der Bot meldete Aenderungen, die
    # es nicht gibt. Welche das ist, haengt allein daran, in welcher
    # Reihenfolge WebUntis den Zeitraum ausliefert.
    free = [l for l in right if id(l) not in matched_right]
    candidates: list[tuple[int, int, int, Lesson, Lesson]] = []
    for i, lesson in enumerate(rest_left):
        for j, other in enumerate(free):
            score = _match_score(lesson, other)
            if score > 1:
                candidates.append((-score, i, j, lesson, other))

    candidates.sort()  # bester Score zuerst, danach stabil nach Position
    taken_left: set[int] = set()
    taken_right: set[int] = set()

    for _score, i, j, lesson, other in candidates:
        if i in taken_left or j in taken_right:
            continue
        pairs.append((lesson, other))
        taken_left.add(i)
        taken_right.add(j)
        matched_right.add(id(other))

    still_left = [l for i, l in enumerate(rest_left) if i not in taken_left]
    only_new = [l for l in right if id(l) not in matched_right]
    return pairs, still_left, only_new


def _match_score(lesson: Lesson, other: Lesson) -> int:
    """Wie sehr gleichen sich zwei Stunden? 0 = gar nicht.

    Gebraucht, wenn die WebUntis-id gewechselt hat -- das passiert, sobald
    eine Vertretung neu angelegt wird. Ohne Bewertung wuerden parallele
    Kurse (Sport A und Sport B in derselben Stunde) vertauscht und vier
    Aenderungen gemeldet, wo keine ist.

    Unterrichtsnummer und Fach wiegen am schwersten: Sie ueberdauern
    Raum- und Lehrerwechsel.
    """
    if other.date != lesson.date or other.start != lesson.start:
        return 0  # andere Zeit: keine Entsprechung

    score = 1  # gleiche Zeit ist nur die Grundvoraussetzung
    if lesson.lesson_no is not None and other.lesson_no == lesson.lesson_no:
        score += 8
    if lesson.subjects and other.subjects == lesson.subjects:
        score += 4
    if lesson.title == other.title:
        score += 2
    if lesson.rooms and other.rooms == lesson.rooms:
        score += 1

    # Ein Wert von 1 heisst: nur die Uhrzeit stimmt, sonst nichts. Dann ist
    # es eher eine andere Stunde -- lieber "entfallen" + "neu" melden.
    return score


def _join(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "—"


def compare(old: Lesson, new: Lesson) -> list[Change]:
    """Vergleicht eine zugeordnete Stunde Feld fuer Feld."""
    # Ausfall hat Vorrang: Wenn die Stunde entfaellt, interessiert niemanden
    # mehr, dass sich nebenbei der Raum geaendert hat.
    if old.status != CANCELLED and new.status == CANCELLED:
        return [Change("cancelled", new, new.note)]
    if old.status == CANCELLED and new.status != CANCELLED:
        return [Change("uncancelled", new, "Der Ausfall wurde zurückgenommen")]
    if new.status == CANCELLED:
        return []  # war schon abgesagt, nichts Neues

    changes: list[Change] = []
    for kind, attr in (("subject", "subjects"),
                       ("teacher", "teachers"),
                       ("room", "rooms")):
        before, after = getattr(old, attr), getattr(new, attr)
        if before != after:
            changes.append(Change(kind, new, f"{_join(before)} → {_join(after)}"))

    if old.date != new.date:
        # Verlegung auf einen anderen Tag. Wurde frueher nie gemeldet:
        # bleibt die WebUntis-id gleich, greift die Zuordnung ueber sie --
        # und verglichen wurden nur die Uhrzeiten.
        changes.append(Change("time", new,
                              f"{day_header(old.date)} → {day_header(new.date)}"))
    elif (old.start, old.end) != (new.start, new.end):
        changes.append(Change("time", new,
                              f"{old.start}-{old.end} → {new.start}-{new.end}"))

    if changes:
        # Der Vertretungstext gehoert an die wichtigste Aenderung, nicht in
        # eine eigene Zeile -- und er darf nicht verlorengehen, nur weil
        # sich nebenbei der Raum geaendert hat.
        if new.note != old.note:
            first = changes[0]
            zusatz = new.note or "Hinweis entfernt"
            detail = f"{first.detail} · {zusatz}" if first.detail else zusatz
            changes[0] = dataclasses.replace(first, detail=detail)
        return changes

    # Kein Feld hat sich geaendert. Trotzdem kann WebUntis die Stunde als
    # Aenderung markiert haben (code "irregular") -- bei Schulen, die keine
    # Lehrerdaten herausgeben, ist das oft das EINZIGE sichtbare Signal
    # einer Vertretung. Ohne diese Pruefung bliebe sie unbemerkt.
    if old.status != new.status:
        kind = "marked" if new.status == IRREGULAR else "unmarked"
        return [Change(kind, new, new.note or describe(new))]

    if old.note != new.note:
        return [Change("note", new, new.note or "(entfernt)")]

    return []


def describe(lesson: Lesson) -> str:
    parts = []
    if lesson.rooms:
        parts.append(f"Raum {_join(lesson.rooms)}")
    if lesson.teachers:
        parts.append(_join(lesson.teachers))
    if lesson.note:
        parts.append(lesson.note)
    return " · ".join(parts)


def diff(
    old: Sequence[Lesson],
    new: Sequence[Lesson],
    win: tuple[dt.date, dt.date] | None = None,
) -> list[Change]:
    """Alle Unterschiede zwischen zwei Stundenplaenen."""
    old, new = within(old, win), within(new, win)
    pairs, only_old, only_new = pair_up(old, new)

    changes: list[Change] = []
    for before, after in pairs:
        changes.extend(compare(before, after))

    for lesson in only_new:
        kind = "cancelled" if lesson.status == CANCELLED else "added"
        changes.append(Change(kind, lesson, describe(lesson)))

    for lesson in only_old:
        # Eine bereits gemeldete Absage, die aus dem Plan faellt, ist keine
        # Neuigkeit mehr.
        if lesson.status != CANCELLED:
            changes.append(Change("removed", lesson))

    changes.sort(key=lambda c: c.sort_key)
    return changes


class Implausible(RuntimeError):
    """Die neuen Daten sehen nach einer Stoerung aus, nicht nach Aenderungen."""


def check_plausible(
    old: Sequence[Lesson],
    new: Sequence[Lesson],
    win: tuple[dt.date, dt.date] | None,
    max_vanish: float = 0.7,
) -> None:
    """Bremse gegen Massen-Fehlalarme.

    Liefert WebUntis wegen Wartung oder eines Session-Problems eine leere
    oder stark reduzierte Antwort, wuerde ein naiver Vergleich "alles
    entfaellt" melden. Genau das macht solche Bots unbrauchbar.

    Das Fenster ist Pflicht: Ohne Beschneidung zaehlen Stunden als
    verschwunden, die nur aus dem rollenden Fenster gerutscht sind.
    """
    old, new = within(old, win), within(new, win)
    alive = [l for l in old if l.status != CANCELLED]
    if not alive:
        return

    if not new:
        raise Implausible(
            f"WebUntis lieferte 0 Stunden, gespeichert waren {len(alive)}."
        )

    _pairs, only_old, _only_new = pair_up(old, new)
    new_keys = {l.key for l in new}
    vanished = [l for l in only_old
                if l.status != CANCELLED and l.key not in new_keys]

    ratio = len(vanished) / len(alive)
    if ratio > max_vanish:
        raise Implausible(
            f"{len(vanished)} von {len(alive)} Stunden ({ratio:.0%}) auf einmal "
            "verschwunden -- sieht nach einem Datenproblem aus."
        )


# ===========================================================================
#  Nachrichten  (rein)
# ===========================================================================

WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
            "Freitag", "Samstag", "Sonntag")


def esc(text: Any) -> str:
    return html.escape(str(text), quote=False)


def day_header(date: str) -> str:
    try:
        day = dt.date.fromisoformat(date)
    except ValueError:
        return date
    return f"{WEEKDAYS[day.weekday()]}, {day:%d.%m.}"


def relative(date: str, today: dt.date) -> str:
    try:
        delta = (dt.date.fromisoformat(date) - today).days
    except ValueError:
        return ""
    return {0: "heute", 1: "morgen", 2: "übermorgen"}.get(delta, "")


#: Ab so vielen Aenderungen wird zusammengefasst statt aufgelistet.
#: Eine Nachricht mit 50 Zeilen liest niemand -- die Information "der ganze
#: Plan ist neu" steckt ohnehin in der Zahl.
BULK_THRESHOLD = 40


def render(changes: Sequence[Change], today: dt.date,
           header: str = "Stundenplan-Änderungen", bulk_note: str = "") -> str:
    """Baut die Telegram-Nachricht, nach Tagen gruppiert."""
    if not changes:
        return ""

    if len(changes) >= BULK_THRESHOLD:
        return render_summary(changes, today, bulk_note)

    lines = [f"<b>{esc(header)}</b>"]
    if bulk_note:
        lines.append(f"<i>{esc(bulk_note)}</i>")
    current: str | None = None

    for change in changes:
        lesson = change.lesson
        if lesson.date != current:
            current = lesson.date
            rel = relative(current, today)
            suffix = f" <i>({rel})</i>" if rel else ""
            lines.append("")
            lines.append(f"<b>{esc(day_header(current))}</b>{suffix}")

        icon = ICONS.get(change.kind, "•")
        label = LABELS.get(change.kind, change.kind)
        lines.append(f"{icon} <b>{esc(lesson.start)}</b> "
                     f"{esc(lesson.title)} — {esc(label)}")
        if change.detail:
            lines.append(f"    <i>{esc(change.detail)}</i>")

    return "\n".join(lines)


def render_summary(changes: Sequence[Change], today: dt.date,
                   bulk_note: str = "") -> str:
    """Kurzfassung bei sehr vielen Aenderungen.

    Zaehlt nach Art und nennt die betroffenen Tage, statt fuenfzig Zeilen
    aufzulisten. Wer es genau wissen will, schaut in WebUntis.
    """
    counts: dict[str, int] = {}
    for change in changes:
        counts[change.kind] = counts.get(change.kind, 0) + 1

    days = sorted({c.lesson.date for c in changes})
    lines = ["<b>Stundenplan-Änderungen</b>"]
    if bulk_note:
        lines.append(f"<i>{esc(bulk_note)}</i>")
    lines.append("")
    lines.append(f"<b>{len(changes)} Änderungen</b> an "
                 f"{len(days)} Tag{'en' if len(days) != 1 else ''}:")

    for kind in KINDS:
        if kind in counts:
            lines.append(f"{ICONS.get(kind, '•')} {counts[kind]}× "
                         f"{esc(LABELS.get(kind, kind))}")

    lines.append("")
    spanne = (f"{day_header(days[0])} bis {day_header(days[-1])}"
              if len(days) > 1 else day_header(days[0]))
    lines.append(f"<i>Betroffen: {esc(spanne)}</i>")
    lines.append("<i>Einzelheiten stehen in WebUntis.</i>")
    return "\n".join(lines)


def render_plan(lessons: Sequence[Lesson], today: dt.date) -> str:
    """Kompletter Plan -- fuer Diagnose und den spaeteren /heute-Befehl."""
    if not lessons:
        return "<b>Keine Stunden im Plan.</b>"

    lines: list[str] = []
    current: str | None = None
    for lesson in sorted(lessons, key=lambda l: (l.date, l.start)):
        if lesson.date != current:
            current = lesson.date
            rel = relative(current, today)
            suffix = f" <i>({rel})</i>" if rel else ""
            lines.append("")
            lines.append(f"<b>{esc(day_header(current))}</b>{suffix}")

        room = f" · {esc(_join(lesson.rooms))}" if lesson.rooms else ""
        if lesson.status == CANCELLED:
            lines.append(f"❌ <b>{esc(lesson.start)}</b> <s>{esc(lesson.title)}</s>")
        else:
            lines.append(f"<b>{esc(lesson.start)}</b> {esc(lesson.title)}{room}")

    return "\n".join(lines).strip()


MAX_LEN = 4096
SPLIT_AT = 3500


def split(text: str, limit: int = SPLIT_AT) -> list[str]:
    """Teilt lange Nachrichten an Zeilengrenzen.

    Telegram bricht ueber 4096 Zeichen ab. An Zeilengrenzen zu teilen haelt
    ausserdem die HTML-Auszeichnung heil -- alle Tags stehen zeilenintern.
    """
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    buffer: list[str] = []
    size = 0

    for line in text.split("\n"):
        while len(line) > limit:
            if buffer:
                parts.append("\n".join(buffer))
                buffer, size = [], 0
            parts.append(line[:limit])
            line = line[limit:]
        if size + len(line) + 1 > limit and buffer:
            parts.append("\n".join(buffer))
            buffer, size = [], 0
        buffer.append(line)
        size += len(line) + 1

    if buffer:
        parts.append("\n".join(buffer))
    return [p for p in parts if p.strip()]


def strip_html(text: str) -> str:
    """Macht aus der HTML-Nachricht lesbaren Klartext.

    Rueckfallebene: Sollte Telegram die Auszeichnung einmal nicht annehmen,
    geht die Meldung trotzdem raus -- lieber ohne Fettschrift als gar nicht.
    """
    import re

    plain = re.sub(r"<[^>]+>", "", text)
    return html.unescape(plain)


# ===========================================================================
#  Telegram  (I/O)
# ===========================================================================

API = "https://api.telegram.org"
TIMEOUT = 20
ATTEMPTS = 3

#: Bei diesen Antworten lohnt ein erneuter Versuch.
RETRY_CODES = {429, 500, 502, 503, 504}


class TelegramError(RuntimeError):
    """Telegram hat die Anfrage nicht angenommen."""


class TelegramConfigError(TelegramError):
    """Dauerhaft falsch -- Token, Chat-ID oder Berechtigung.

    Getrennt von den voruebergehenden Fehlern, weil hier Wiederholen
    sinnlos ist und ein Mensch eingreifen muss.
    """


HINTS = {
    401: "Der Token wird abgelehnt. Pruefe TELEGRAM_BOT_TOKEN -- auf GitHub "
         "unter Settings -> Secrets and variables -> Actions.",
    403: "Der Bot darf diesem Chat nicht schreiben. Blockiert oder aus der "
         "Gruppe entfernt?",
    400: "Meist eine falsche TELEGRAM_CHAT_ID ('chat not found') -- der Chat "
         "muss vom Menschen mit /start eroeffnet worden sein.",
    404: "Der Token existiert nicht (mehr).",
}


def telegram_call(token: str, method: str, payload: dict) -> dict:
    """Ruft die Telegram-API auf, mit Wiederholung bei Stoerungen."""
    url = f"{API}/bot{token}/{method}"
    last: Exception | None = None

    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = requests.post(url, json=payload, timeout=TIMEOUT)
            data = response.json()
        except requests.RequestException as exc:
            last = TelegramError(f"Netzwerkfehler bei {method}: {exc}")
        except ValueError:
            last = TelegramError(f"Unlesbare Antwort bei {method} "
                                 f"(HTTP {response.status_code})")
        else:
            if data.get("ok"):
                return data.get("result", {})

            code = data.get("error_code")
            desc = data.get("description", "")
            message = f"{method} -> {code}: {desc}"
            hint = HINTS.get(code)
            if hint:
                message += f"\n  {hint}"

            if code not in RETRY_CODES:
                raise TelegramConfigError(message)

            last = TelegramError(message)
            wait = (data.get("parameters") or {}).get("retry_after")
            _backoff(attempt, method, message, wait)
            continue

        _backoff(attempt, method, str(last))

    raise last or TelegramError(f"{method} nach {ATTEMPTS} Versuchen gescheitert")


def _backoff(attempt: int, method: str, why: str, override: float | None = None) -> None:
    if attempt >= ATTEMPTS:
        return
    # Telegram nennt bei Flood-Control durchaus dreistellige Sekundenwerte.
    # Ungebremst blockierte das den 5-Minuten-Takt und liefe gegen das
    # Job-Zeitlimit -- deshalb gedeckelt.
    try:
        wait = max(0.0, min(float(override), 30.0)) if override is not None else 2 ** (attempt - 1)
    except (TypeError, ValueError):
        wait = 2 ** (attempt - 1)
    log.warning("%s Versuch %d/%d fehlgeschlagen (%s) -- erneut in %.0fs",
                method, attempt, ATTEMPTS, why[:120], wait)
    time.sleep(wait)


def send(cfg: Config, text: str, silent: bool = False) -> int:
    """Schickt eine Nachricht an alle konfigurierten Chats.

    Nimmt Telegram die HTML-Auszeichnung nicht an, geht dieselbe Nachricht
    als Klartext raus. Eine Meldung darf nie an der Formatierung scheitern.
    """
    chunks = split(text)
    complete = 0
    partial: list[str] = []
    problems: list[TelegramError] = []

    for chat in cfg.telegram_chats:
        done = 0
        try:
            for index, chunk in enumerate(chunks):
                _send_chunk(cfg, chat, chunk, silent)
                done += 1
                if index:
                    time.sleep(0.4)  # Telegrams Drosselung nicht reizen
            complete += 1
        except TelegramError as exc:
            # Pro Empfaenger abfangen: Haengt ein Chat, sollen die anderen
            # ihre Nachricht trotzdem bekommen -- sonst kaeme dieselbe
            # Meldung beim naechsten Durchlauf bei allen anderen erneut an.
            log.warning("Versand an %s fehlgeschlagen (%d/%d Teile): %s",
                        chat, done, len(chunks), exc)
            if done:
                partial.append(chat)
            problems.append(exc)

    if partial:
        # Ein halb zugestellter Empfaenger ist der unangenehmste Fall:
        # Wiederholen erzeugt Dopplungen, Schweigen verliert den Rest.
        # Sichtbar machen ist das Mindeste.
        log.error("Nur teilweise zugestellt an: %s", ", ".join(partial))

    if complete or partial:
        return complete + len(partial)

    # Kein einziger Empfaenger erreicht -- ein echter Fehlschlag.
    if not problems:
        raise TelegramError("Kein Empfaenger konfiguriert")

    # "Dauerhaft kaputt" nur melden, wenn ALLE Fehler dauerhaft sind.
    # Sonst haenge der Job an der zufaelligen Reihenfolge der Chats: ein
    # voruebergehender 503 daneben wuerde als Konfigurationsfehler gelten
    # und den ganzen Lauf beenden.
    if all(isinstance(p, TelegramConfigError) for p in problems):
        raise problems[0]
    raise next(p for p in problems if not isinstance(p, TelegramConfigError))


def _send_chunk(cfg: Config, chat: str, chunk: str, silent: bool) -> None:
    payload = {
        "chat_id": chat,
        "text": chunk,
        "parse_mode": "HTML",
        "disable_notification": silent,
        "link_preview_options": {"is_disabled": True},
    }
    try:
        telegram_call(cfg.telegram_token, "sendMessage", payload)
    except TelegramConfigError as exc:
        text = str(exc).lower()
        if "parse" not in text and "entit" not in text:
            raise
        log.warning("HTML abgelehnt (%s) -- sende als Klartext", exc)
        payload.pop("parse_mode")
        payload["text"] = strip_html(chunk)
        telegram_call(cfg.telegram_token, "sendMessage", payload)


# ===========================================================================
#  Zustand  (I/O)
# ===========================================================================

@dataclass(frozen=True)
class State:
    exists: bool
    lessons: tuple[Lesson, ...] = ()
    window: tuple[dt.date, dt.date] | None = None
    saved_at: str = ""
    #: Fingerabdruck einer Datenlage, die beim letzten Lauf als unplausibel
    #: abgewiesen wurde. Kommt dieselbe Lage noch einmal, ist sie echt --
    #: siehe confirm_or_hold().
    pending: str = ""


#: Nach so vielen ungewoehnlichen Durchlaeufen in Folge wird die Lage auch
#: dann akzeptiert, wenn die Daten dabei schwanken. Bei 5-Minuten-Takt
#: entspricht das einer knappen halben Stunde.
PENDING_LIMIT = 6


def parse_pending(raw: str) -> tuple[str, int]:
    """Zerlegt das gespeicherte 'fingerabdruck:zaehler'."""
    mark, _, count = (raw or "").partition(":")
    try:
        return mark, int(count)
    except ValueError:
        return mark, 1 if mark else 0


def fingerprint(lessons: Sequence[Lesson]) -> str:
    """Kurzer, stabiler Fingerabdruck einer Stundenliste."""
    import hashlib

    material = "|".join(sorted(f"{l.key}#{l.status}#{l.rooms}" for l in lessons))
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def load_state(path: Path = STATE_FILE) -> State:
    if not path.exists():
        log.info("Kein gespeicherter Zustand -- das ist der erste Lauf")
        return State(exists=False)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # Kaputte Datei beiseitelegen statt loeschen: sie ist die einzige
        # Spur, falls spaeter etwas nachvollzogen werden muss.
        log.warning("Zustandsdatei unlesbar (%s) -- wird ersetzt", exc)
        try:
            path.replace(path.with_suffix(".broken"))
        except OSError:
            pass
        return State(exists=False)

    # Die Huelle pruefen, nicht nur die Eintraege: Eine Datei mit einer
    # Liste statt eines Objekts wuerde sonst bis in check_once durchschlagen
    # -- und weil sie im Repo liegt, JEDEN weiteren Lauf toeten.
    if not isinstance(raw, dict) or not isinstance(raw.get("lessons", []), list):
        log.warning("Zustandsdatei hat ein unerwartetes Format -- wird ersetzt")
        try:
            path.replace(path.with_suffix(".broken"))
        except OSError:
            pass
        return State(exists=False)

    if raw.get("schema") != SCHEMA:
        log.warning("Zustand hat Schema %s, erwartet %s -- wird verworfen",
                    raw.get("schema"), SCHEMA)
        return State(exists=False)

    # Ohne lesbares Fenster liesse sich der Vergleichszeitraum nicht
    # bestimmen -- das saehe aus wie "Fenster komplett verschoben" und
    # wuerde anstehende Aenderungen stillschweigend verwerfen. Lieber
    # sauber als Erstlauf behandeln.
    try:
        win = raw.get("window") or {}
        window = (dt.date.fromisoformat(win["from"]), dt.date.fromisoformat(win["to"]))
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Gespeichertes Zeitfenster unlesbar (%s) -- wie Erstlauf", exc)
        return State(exists=False)

    # Einzelne kaputte Eintraege ueberspringen statt den Lauf zu kippen.
    # state.json liegt im Repo -- ein ungefangener Fehler hier wuerde JEDEN
    # weiteren Lauf toeten, bis ein Mensch eingreift.
    lessons: list[Lesson] = []
    for item in raw.get("lessons", []):
        try:
            lessons.append(Lesson.from_json(item))
        except (TypeError, AttributeError, ValueError) as exc:
            log.warning("Gespeicherte Stunde unlesbar, uebersprungen (%s): %r",
                        exc, item)

    if raw.get("lessons") and not lessons:
        log.warning("Keine einzige gespeicherte Stunde lesbar -- wie Erstlauf")
        return State(exists=False)

    log.info("Zustand geladen: %d Stunden (%s)", len(lessons), raw.get("saved_at", "?"))
    return State(True, tuple(lessons), window, raw.get("saved_at", ""),
                 str(raw.get("pending") or ""))


def save_state(lessons: Sequence[Lesson], win: tuple[dt.date, dt.date],
               path: Path = STATE_FILE, pending: str = "") -> bool:
    """Speichert den Zustand atomar. Gibt True zurueck, wenn geschrieben wurde.

    Unveraenderte Zustaende werden NICHT neu geschrieben. Das ist im
    Dauerbetrieb entscheidend: Der Bot prueft alle fuenf Minuten, und jeder
    Schreibvorgang wird auf GitHub zu einem Commit. Ohne diese Sparsamkeit
    waeren das hunderte Commits pro Tag, nur um festzuhalten, dass sich
    nichts geaendert hat.
    """
    window = {"from": f"{win[0]:%Y-%m-%d}", "to": f"{win[1]:%Y-%m-%d}"}

    # Ueber JSON normalisieren, bevor verglichen wird: asdict() liefert
    # Tupel, aus der Datei kommen Listen zurueck. Ohne diesen Schritt gaelte
    # jeder Zustand als veraendert -- und im 5-Minuten-Takt entstuende genau
    # die Commit-Flut, die dieser Vergleich verhindern soll.
    payload_lessons = json.loads(json.dumps([l.to_json() for l in lessons]))

    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if (old.get("schema") == SCHEMA
                    and old.get("window") == window
                    and old.get("lessons") == payload_lessons
                    and str(old.get("pending") or "") == pending):
                log.debug("Zustand unveraendert -- nicht neu geschrieben")
                return False
        except (json.JSONDecodeError, OSError):
            pass

    payload = {
        "schema": SCHEMA,
        "saved_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "window": window,
        "pending": pending,
        "lessons": payload_lessons,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent,
        prefix=path.name + ".", suffix=".tmp", delete=False,
    )
    try:
        with tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=1)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp.name, path)
    except BaseException:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise

    log.info("Zustand gespeichert: %d Stunden (%s bis %s)",
             len(lessons), *win)
    return True


# ===========================================================================
#  Zustand sichern (git)  -- nur auf GitHub relevant
# ===========================================================================

def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=BASE_DIR,
                          capture_output=True, text=True, timeout=60)


def commit_state(path: Path = STATE_FILE) -> bool:
    """Sichert state.json ins Repo -- die einzige Erinnerung des Bots.

    Wird nach JEDEM Durchlauf aufgerufen, auch wenn nichts zu speichern
    war: Ein frueher gescheiterter Push muss nachgeholt werden koennen.
    Sonst kaeme eine bereits gesendete Meldung beim naechsten Job ein
    zweites Mal.

    Wirft nie. Ein Problem mit git darf niemals einen Lauf beenden, in dem
    die Nachricht bereits raus ist.
    """
    try:
        return _commit_state(path)
    except Exception as exc:
        log.warning("Zustand konnte nicht gesichert werden (%s) -- "
                    "naechster Durchlauf versucht es erneut", exc)
        return False


def _commit_state(path: Path) -> bool:
    if not (BASE_DIR / ".git").exists():
        return False

    # -f, weil state.json bewusst in .gitignore steht: lokal soll sie nicht
    # versehentlich mitcommittet werden, in der Cloud ist genau das der Sinn.
    if path.exists():
        git("add", "-f", str(path.name))

    if git("diff", "--staged", "--quiet").returncode != 0:
        if git("commit", "-q", "-m", "state: Stundenplan-Zustand [skip ci]").returncode != 0:
            log.warning("git commit fehlgeschlagen")
            return False

    # Getrennt pruefen, ob ueberhaupt etwas ungepusht ist. So wird auch ein
    # frueher gescheiterter Push nachgeholt, nicht nur der von eben.
    if not git("log", "@{u}..HEAD", "--oneline").stdout.strip():
        return False

    if git("push", "-q").returncode == 0:
        log.info("Zustand ins Repo gesichert")
        return True

    # Ein fremder Commit dazwischen? Einmal nachziehen und erneut versuchen.
    if git("pull", "--rebase", "--autostash", "-q").returncode != 0:
        # Rebase steckengeblieben -- das Repo darf nicht in diesem Zustand
        # zurueckbleiben, sonst schlaegt jeder weitere Lauf fehl und
        # state.json enthaelt Konfliktmarker.
        log.warning("Rebase fehlgeschlagen -- wird zurueckgenommen")
        git("rebase", "--abort")
        git("merge", "--abort")
        return False

    if git("push", "-q").returncode == 0:
        log.info("Zustand ins Repo gesichert (nach Rebase)")
        return True

    log.warning("Push fehlgeschlagen -- naechster Durchlauf holt es nach")
    return False


# ===========================================================================
#  Ablauf
# ===========================================================================

OK, FAILED, IDLE = "ok", "failed", "idle"


@dataclass
class Result:
    status: str
    changes: int = 0
    message: str = ""
    fatal: bool = False   # menschliches Eingreifen noetig -> Schleife beenden


def check_once(cfg: Config, dry_run: bool = False,
               state_path: Path = STATE_FILE) -> Result:
    """Ein vollstaendiger Durchlauf: abrufen, vergleichen, melden, sichern."""
    now = now_local(cfg.timezone)
    today = now.date()
    win = window_of(cfg.lookahead_days, today)

    # -- abrufen
    try:
        with Untis(cfg) as untis:
            lessons = untis.timetable(*win)
    except NothingToDo as exc:
        return Result(IDLE, message=str(exc))
    except AuthError as exc:
        return Result(FAILED, message=str(exc), fatal=True)
    except UntisError as exc:
        return Result(FAILED, message=str(exc))

    previous = load_state(state_path)
    compare_win = overlap(win, previous.window)

    # -- Sonderfall: keine Ueberlappung (sehr lange Pause)
    # Muss VOR der Plausibilitaetspruefung kommen, sonst zaehlt die alle
    # gespeicherten Stunden als verschwunden.
    if previous.exists and compare_win is None:
        if not dry_run:
            save_state(lessons, win, state_path)
            commit_state(state_path)
        return Result(OK, message="Fenster komplett verschoben -- neu grundiert")

    # -- Plausibilitaet
    bulk_note = ""
    try:
        check_plausible(previous.lessons, lessons, compare_win)
    except Implausible as exc:
        mark, seen = parse_pending(previous.pending)
        now_mark = fingerprint(lessons)

        # Der Zaehler laeuft ueber JEDE ungewoehnliche Lage weiter, auch
        # wenn sich die Daten dabei aendern. Wuerde er bei jedem Wechsel
        # zurueckgesetzt, koennte der Bot bei schwankenden Teilantworten
        # unbegrenzt still bleiben -- ohne dass es jemand bemerkt.
        seen += 1

        # Zwei Wege zur Bestaetigung:
        #   * zweimal exakt dieselbe Lage  -> eindeutig kein Aussetzer
        #   * oder anhaltend ungewoehnlich -> nach einer knappen halben
        #     Stunde ist auch schwankender Unsinn kein Schluckauf mehr
        bestaetigt = (mark == now_mark and seen >= 2) or seen >= PENDING_LIMIT

        if not bestaetigt:
            if not dry_run:
                save_state(previous.lessons, previous.window or win,
                           state_path, pending=f"{now_mark}:{seen}")
                commit_state(state_path)
            return Result(IDLE, message=f"Ungewoehnliche Lage gemerkt "
                                        f"({seen}), warte auf Bestaetigung: {exc}")

        # Die neue Wahrheit (Halbjahreswechsel, Projektwoche, neuer
        # Kursplan). Ohne diesen Ausweg bliebe der Bot fuer immer stehen
        # und die wichtigste Planaenderung des Jahres kaeme nie an.
        log.warning("Grossflaechige Aenderung bestaetigt (%d. Sichtung): %s",
                    seen, exc)
        bulk_note = "Der Stundenplan hat sich großflächig geändert."

    # -- Erstlauf: nur merken, nicht fluten
    if not previous.exists:
        if not dry_run:
            save_state(lessons, win, state_path)
            commit_state(state_path)
        return Result(OK, message=f"Erster Lauf: {len(lessons)} Stunden gemerkt, "
                                  "nichts gesendet")

    # -- vergleichen
    changes = diff(previous.lessons, lessons, compare_win)
    if not changes:
        if not dry_run:
            save_state(lessons, win, state_path)
            commit_state(state_path)
        return Result(OK, message=f"Keine Aenderungen ({len(lessons)} Stunden)")

    text = render(changes, today, bulk_note=bulk_note)
    if dry_run:
        return Result(OK, changes=len(changes), message=text)

    # -- melden. Erst danach speichern: Geht der Versand schief, wird die
    #    Aenderung beim naechsten Durchlauf erneut versucht statt verloren.
    try:
        send(cfg, text)
    except TelegramConfigError as exc:
        return Result(FAILED, message=f"Telegram lehnt dauerhaft ab:\n{exc}",
                      fatal=True)
    except TelegramError as exc:
        return Result(FAILED, message=f"Versand fehlgeschlagen: {exc}")

    save_state(lessons, win, state_path)
    commit_state(state_path)
    return Result(OK, changes=len(changes),
                  message=f"{len(changes)} Aenderung(en) gemeldet")


def watch(cfg: Config, minutes: int, interval: int,
          sleeper: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.monotonic) -> int:
    """Prueft ueber einen laengeren Zeitraum in festem Takt.

    Der Grund fuer diese Schleife: GitHubs Zeitplaner haelt kurze
    Intervalle nicht ein -- ein "alle 5 Minuten" wird verzoegert, gebuendelt
    oder ganz verworfen. Statt auf 288 puenktliche Starts pro Tag zu hoffen,
    braucht es nur noch einen Start pro Stunde; den Takt macht diese
    Schleife selbst.

    Rueckgabewert ist der Exit-Code: 0 = in Ordnung, 1 = Eingriff noetig.
    """
    deadline = clock() + minutes * 60
    run = 0
    consecutive_failures = 0

    while True:
        run += 1
        started = clock()

        try:
            result = check_once(cfg)
        except Exception as exc:
            # Ein unerwarteter Fehler darf nicht den Rest der Stunde kosten.
            # Ohne dieses Netz beendete jede uebersehene Ausnahme den Job --
            # und bis zum naechsten Start vergingen bis zu 30 Minuten ohne
            # jede Pruefung.
            log.exception("Unerwarteter Fehler im Durchlauf %d", run)
            result = Result(FAILED, message=f"Unerwarteter Fehler: {exc}")

        marker = {OK: "ok  ", IDLE: "idle", FAILED: "FEHL"}[result.status]
        first_line = result.message.splitlines()[0] if result.message else ""
        print(f"[{run:02d}] {marker} {first_line}", flush=True)

        if result.status == FAILED:
            consecutive_failures += 1
            log.warning("Durchlauf %d fehlgeschlagen (%d in Folge): %s",
                        run, consecutive_failures, result.message)
        else:
            consecutive_failures = 0

        if result.fatal:
            print(f"\nAbbruch -- das muss ein Mensch beheben:\n{result.message}",
                  file=sys.stderr)
            return 1

        # Drei Fehlschlaege hintereinander sind kein Schluckauf mehr.
        if consecutive_failures >= 3:
            print(f"\nDrei Durchlaeufe in Folge fehlgeschlagen:\n{result.message}",
                  file=sys.stderr)
            return 1

        remaining = deadline - clock()
        if remaining < interval:
            break
        # Die eigene Laufzeit abziehen, damit der Takt nicht wegdriftet.
        sleeper(max(0.0, interval - (clock() - started)))

    print(f"Fertig: {run} Durchlaeufe.")
    return 0


# ===========================================================================
#  Diagnose
# ===========================================================================

def selftest(cfg: Config) -> int:
    """Prueft jeden Zugang einzeln und sagt genau, was klemmt."""
    ok = True
    print("=" * 58)

    print(f"Telegram-Token   {mask(cfg.telegram_token)}")
    try:
        me = telegram_call(cfg.telegram_token, "getMe", {})
        print(f"  [ja  ] Bot erkannt: @{me.get('username')}")
    except Exception as exc:
        print(f"  [NEIN] {exc}")
        ok = False

    for chat in cfg.telegram_chats:
        print(f"Chat {chat}")
        try:
            info = telegram_call(cfg.telegram_token, "getChat", {"chat_id": chat})
            name = info.get("title") or info.get("first_name") or "?"
            print(f"  [ja  ] erreichbar: {name}")
        except Exception as exc:
            print(f"  [NEIN] {str(exc).splitlines()[0]}")
            ok = False

    print(f"WebUntis         {cfg.untis_server} / {cfg.untis_school} "
          f"/ {cfg.untis_user}")
    try:
        with Untis(cfg) as untis:
            print("  [ja  ] Anmeldung erfolgreich")
            years = untis.schoolyears()
            if years:
                today = dt.date.today()
                current = next((y for y in years
                                if y.start.date() <= today <= y.end.date()), None)
                print(f"  [info] Schuljahr heute: "
                      f"{current.name if current else 'keines (Ferien)'}")
            start, end = window_of(cfg.lookahead_days, dt.date.today())
            try:
                lessons = untis.timetable(start, end)
                print(f"  [ja  ] {len(lessons)} Stunden im Fenster")
            except NothingToDo as exc:
                print(f"  [info] {exc}")
    except Exception as exc:
        print(f"  [NEIN] {str(exc).splitlines()[0]}")
        ok = False

    print("=" * 58)
    print("Alles in Ordnung." if ok else "Mindestens ein Zugang ist kaputt.")
    return 0 if ok else 1


def show(cfg: Config, days: int | None) -> int:
    """Zeigt den Stundenplan im Klartext."""
    today = now_local(cfg.timezone).date()
    win = window_of(days or cfg.lookahead_days, today)
    try:
        with Untis(cfg) as untis:
            lessons = untis.timetable(*win)
    except NothingToDo as exc:
        print(f"Nichts abrufbar: {exc}")
        return 0
    except UntisError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

    current = None
    for lesson in lessons:
        if lesson.date != current:
            current = lesson.date
            print(f"\n{day_header(current)}")
            print("  " + "-" * 52)
        mark = {CANCELLED: "<< ENTFAELLT", IRREGULAR: "<< AENDERUNG"}.get(lesson.status, "")
        print(f"  {lesson.start}-{lesson.end}  {lesson.title[:14]:14} "
              f"{_join(lesson.rooms)[:12]:12} {mark}")
        if lesson.note:
            print(f"       Info: {lesson.note}")

    changed = sum(1 for l in lessons if l.status != REGULAR)
    print(f"\n{len(lessons)} Stunden, davon {changed} mit Aenderungsmarkierung.")
    return 0


# ===========================================================================
#  Einstieg
# ===========================================================================

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    # Die webuntis-Bibliothek loggt jede API-Fehlerantwort selbst als ERROR --
    # auch die, die wir bewusst abfangen. Das Rauschen unterdruecken.
    if level.upper() != "DEBUG":
        logging.getLogger("webuntis").setLevel(logging.CRITICAL)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bot.py",
        description="Meldet WebUntis-Stundenplanaenderungen per Telegram.",
    )
    parser.add_argument("--log", default=None,
                        help="DEBUG, INFO, WARNING, ERROR")
    parser.set_defaults(dry_run=False)   # gilt auch ohne Unterbefehl
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check", help="einmal pruefen")
    p_check.add_argument("--dry-run", action="store_true",
                         help="nichts senden, nichts speichern")

    p_watch = sub.add_parser("watch", help="laenger pruefen, in festem Takt")
    p_watch.add_argument("--minutes", type=int, default=55)
    p_watch.add_argument("--interval", type=int, default=300,
                         help="Sekunden zwischen zwei Pruefungen")

    sub.add_parser("selftest", help="Zugangsdaten einzeln pruefen")

    p_show = sub.add_parser("show", help="Stundenplan anzeigen")
    p_show.add_argument("--days", type=int, default=None)

    args = parser.parse_args(argv)

    # Erst die .env einlesen, dann das Log-Niveau bestimmen -- sonst wirkt
    # ein LOG_LEVEL-Eintrag aus der Datei nicht.
    _load_dotenv(BASE_DIR / ".env")
    setup_logging(args.log or os.environ.get("LOG_LEVEL", "INFO"))

    try:
        cfg = Config.from_env()
    except ConfigError as exc:
        print(f"KONFIGURATIONSFEHLER: {exc}", file=sys.stderr)
        return 1

    command = args.command or "check"

    if command == "selftest":
        return selftest(cfg)
    if command == "show":
        return show(cfg, args.days)
    if command == "watch":
        return watch(cfg, args.minutes, args.interval)

    result = check_once(cfg, dry_run=args.dry_run)
    print(result.message or result.status)
    if result.status == FAILED:
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
