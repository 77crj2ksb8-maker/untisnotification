"""Tests fuer untisbot.

Schwerpunkt liegt bewusst auf den reinen Funktionen: Modell, Vergleich
und Nachrichten-Rendering. Die laufen ohne Netz, ohne Zugangsdaten und
ohne Wartezeit -- deshalb koennen es viele sein.

Die duenne I/O-Schicht wird mit Attrappen geprueft, nicht gegen echte
Server. Getestet wird dort nur, was schiefgehen KANN: Wiederholungen,
Rueckfallebenen, und vor allem die Zusicherungen, auf die man sich
verlassen koennen muss -- dass nie derselbe Stand zweimal gemeldet wird
etwa, oder dass ein git-Fehler keinen Lauf kippt, in dem schon gesendet
wurde.

Jeder Test, an dem eine solche Zusicherung haengt, traegt das Wort
SICHERHEITSNETZ im Docstring und dazu die Mutation, die ihn rot machen
muss: Guard-Klausel testweise entfernen, Test laufen lassen,
zurueckbauen. Welche das sind, sagt

    grep -n SICHERHEITSNETZ tests/test_bot.py

Hier stand frueher eine Aufzaehlung mit fester Anzahl. Die wurde zweimal
falsch, weil neue Netze dazukamen und niemand den Satz nachzog -- die
Liste steht jetzt nur noch in der README, und
test_readme_nennt_jedes_sicherheitsnetz haelt sie dort aktuell.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

import pytest

import bot
from bot import (
    CANCELLED,
    IRREGULAR,
    REGULAR,
    Change,
    Config,
    ConfigError,
    Implausible,
    Lesson,
    State,
    TelegramConfigError,
    TelegramError,
)

# ===========================================================================
#  Hilfsmittel
# ===========================================================================

MO = "2026-09-14"   # ein Montag
DI = "2026-09-15"
MI = "2026-09-16"

#: Ein realistisches Stundenraster fuer Montag/Dienstag: Die Pausen
#: zwischen den Stunden sind Absicht -- genau daran scheitert jede
#: Doppelstunden-Erkennung, die nur "Ende == Start" prueft.
RASTER = {
    0: [("07:40", "08:25", "1"), ("08:30", "09:15", "2"), ("09:35", "10:20", "3"),
        ("10:25", "11:10", "4"), ("11:30", "12:15", "5"), ("12:20", "13:05", "6")],
    1: [("07:40", "08:25", "1"), ("08:30", "09:15", "2"), ("09:35", "10:20", "3"),
        ("10:25", "11:10", "4")],
}


def lesson(date=MO, start="07:40", end="08:25", subjects=("M",), teachers=(),
           rooms=(), status=REGULAR, note="", group="", uid=1, lesson_no=None):
    return Lesson(uid=uid, date=date, start=start, end=end, subjects=tuple(subjects),
                  teachers=tuple(teachers), rooms=tuple(rooms), status=status,
                  note=note, group=group, lesson_no=lesson_no)


class FakePeriod:
    """Sieht von aussen aus wie ein webuntis-Period-Objekt."""

    def __init__(self, data, code=None, start=None, end=None):
        self._data = data
        self.code = code
        self.start = start or dt.datetime(2026, 9, 14, 7, 40)
        self.end = end or dt.datetime(2026, 9, 14, 8, 25)


def resolve_by_name(kind, entries):
    """Aufloeser wie ihn Untis._resolver() baut, nur ohne Netz."""
    return tuple(sorted(str(e.get("name")) for e in (entries or []) if e.get("name")))


@pytest.fixture
def cfg():
    return Config(
        telegram_token="123:ABC",
        telegram_chats=("42",),
        untis_server="server.webuntis.com",
        untis_school="ks-hausach",
        untis_user="schueler",
        untis_password="geheim",
    )


@pytest.fixture(autouse=True)
def _kein_schlaf(monkeypatch):
    """Kein Test darf echte Sekunden verbrauchen."""
    monkeypatch.setattr(bot.time, "sleep", lambda _s: None)


@pytest.fixture(autouse=True)
def _leerer_timegrid_cache():
    bot._TIMEGRID_CACHE.clear()
    yield
    bot._TIMEGRID_CACHE.clear()


# ===========================================================================
#  Workflows
# ===========================================================================

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent
                    / ".github" / "workflows").glob("*.yml"))


def run_bloecke():
    """Jeder run-Block aller Workflows, als (Datei, Schrittname, Text)."""
    import yaml

    for datei in WORKFLOWS:
        beschreibung = yaml.safe_load(datei.read_text(encoding="utf-8"))
        for job in beschreibung.get("jobs", {}).values():
            for schritt in job.get("steps", []):
                if "run" in schritt:
                    yield (datei.name,
                           schritt.get("name", "(ohne Namen)"),
                           schritt["run"])


def test_workflows_gefunden():
    """Wenn die Suche ins Leere greift, prueft der naechste Test nichts."""
    assert len(WORKFLOWS) >= 2


@pytest.mark.parametrize("datei,name,skript",
                         list(run_bloecke()),
                         ids=lambda w: str(w)[:40])
def test_workflow_shell_ist_syntaktisch_gueltig(datei, name, skript):
    """SICHERHEITSNETZ: Ein Syntaxfehler in einem run-Block faellt sonst
    erst im Betrieb auf -- und zwar doppelt, weil die Stoermeldung selbst
    ein run-Block ist und am selben Fehler stirbt. Dann bleibt gar keine
    Meldung mehr.

    Genau das ist in 2.3.0 passiert: Beim Einfuegen des Meldeschritts
    rutschte das schliessende "fi" des Ueberwachungsschritts in den neuen
    Schritt. Die damalige Abnahme hat nur geprueft, dass das YAML parst und
    der Schritt existiert -- nicht, dass das Skript darin laeuft.

    bash -n prueft nur die Syntax, nicht die Ausfuehrung; die
    ${{ ... }}-Ausdruecke von GitHub stoeren dabei nicht.
    """
    fertig = subprocess.run(["bash", "-n"], input=skript,
                            capture_output=True, text=True)
    assert fertig.returncode == 0, (
        f"{datei} / {name}:\n{fertig.stderr.strip()}\n\n{skript}")


# ===========================================================================
#  Doku
# ===========================================================================

def sicherheitsnetze() -> set[str]:
    """Die Tests, deren Docstring SICHERHEITSNETZ nennt.

    Bewusst textuell statt ueber Import und __doc__: So faellt auch ein
    Marker auf, der in einem uebersprungenen oder auskommentierten Test
    steckt.
    """
    quelle = Path(__file__).read_text(encoding="utf-8")
    treffer: set[str] = set()
    name: str | None = None
    for zeile in quelle.splitlines():
        passend = re.match(r"def (test_\w+)", zeile)
        if passend:
            name = passend.group(1)
        elif name and zeile.lstrip().startswith('"""') and "SICHERHEITSNETZ" in zeile:
            treffer.add(name)
    return treffer


def test_readme_nennt_jedes_sicherheitsnetz():
    """Die README fuehrt die Zusicherungen als Tabelle -- und behauptet, das
    seien alle. Zweimal stimmte das nicht: Erst blieb die Anzahl im Text
    stehen, waehrend die Tabelle wuchs, dann fehlten zwei Netze ganz.
    Beides faellt niemandem auf, denn eine Doku wird nicht ausgefuehrt.

    Also wird sie hier ausgefuehrt. Ein neues SICHERHEITSNETZ ohne Zeile in
    der Tabelle macht diesen Test rot, eine geloeschte oder umbenannte
    Zeile ebenso.
    """
    readme = (Path(__file__).resolve().parent.parent
              / "README.md").read_text(encoding="utf-8")
    # Nur die Tabelle, nicht der uebrige Fliesstext: Zeilen der Form
    # "| Zusicherung | `test_...` |".
    genannt = set(re.findall(r"^\|.*\|\s*`(test_\w+)`\s*\|$",
                             readme, re.MULTILINE))
    netze = sicherheitsnetze()
    assert netze, "kein einziger Marker gefunden -- die Suche ist kaputt"
    assert netze - genannt == set(), "in der README nicht aufgefuehrt"
    assert genannt - netze == set(), "in der README aufgefuehrt, aber kein Netz"


# ===========================================================================
#  Konfiguration
# ===========================================================================

BASIS_ENV = {
    "TELEGRAM_BOT_TOKEN": "123456:AAH-xxxx",
    "TELEGRAM_CHAT_ID": "42",
    "WEBUNTIS_SERVER": "server.webuntis.com",
    "WEBUNTIS_SCHOOL": "ks-hausach",
    "WEBUNTIS_USERNAME": "schueler",
    "WEBUNTIS_PASSWORD": "geheim",
}


@pytest.fixture
def env(monkeypatch):
    """Saubere Umgebung: alle bekannten Variablen erst weg, dann die Basis."""
    for name in [*BASIS_ENV, "WEBUNTIS_KLASSE", "LOOKAHEAD_DAYS", "TIMEZONE"]:
        monkeypatch.delenv(name, raising=False)
    for name, value in BASIS_ENV.items():
        monkeypatch.setenv(name, value)
    # .env im Projektverzeichnis darf Tests nicht beeinflussen
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    return monkeypatch


def test_config_aus_umgebung(env):
    cfg = Config.from_env()
    assert cfg.telegram_chats == ("42",)
    assert cfg.untis_school == "ks-hausach"
    assert cfg.lookahead_days == 7
    assert cfg.timezone == "Europe/Berlin"


def test_config_fehlendes_pflichtfeld(env):
    env.delenv("WEBUNTIS_PASSWORD")
    with pytest.raises(ConfigError, match="WEBUNTIS_PASSWORD"):
        Config.from_env()


def test_config_leeres_pflichtfeld_zaehlt_als_fehlend(env):
    env.setenv("WEBUNTIS_SCHOOL", "   ")
    with pytest.raises(ConfigError, match="WEBUNTIS_SCHOOL"):
        Config.from_env()


def test_config_token_ohne_doppelpunkt(env):
    env.setenv("TELEGRAM_BOT_TOKEN", "keintoken")
    with pytest.raises(ConfigError, match="Format"):
        Config.from_env()


def test_config_token_wird_in_fehlermeldung_maskiert(env):
    env.setenv("TELEGRAM_BOT_TOKEN", "abcdefghijklmnop")
    with pytest.raises(ConfigError) as fehler:
        Config.from_env()
    assert "abcdefghijklmnop" not in str(fehler.value)


def test_config_mehrere_chats(env):
    env.setenv("TELEGRAM_CHAT_ID", "42, 43 ,44")
    assert Config.from_env().telegram_chats == ("42", "43", "44")


def test_config_chat_liste_nur_kommas(env):
    env.setenv("TELEGRAM_CHAT_ID", " , , ")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_config_server_ohne_schema_und_schraegstrich(env):
    env.setenv("WEBUNTIS_SERVER", "https://server.webuntis.com/")
    assert Config.from_env().untis_server == "server.webuntis.com"


def test_config_lookahead_keine_zahl(env):
    env.setenv("LOOKAHEAD_DAYS", "viele")
    with pytest.raises(ConfigError, match="ganze Zahl"):
        Config.from_env()


@pytest.mark.parametrize("eingabe,erwartet", [("0", 1), ("1", 1), ("14", 14),
                                              ("30", 30), ("99", 30), ("-5", 1)])
def test_config_lookahead_wird_begrenzt(env, eingabe, erwartet):
    env.setenv("LOOKAHEAD_DAYS", eingabe)
    assert Config.from_env().lookahead_days == erwartet


def test_config_ist_unveraenderlich(cfg):
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.untis_school = "andere"


def test_dotenv_setzt_nur_fehlende_werte(tmp_path, monkeypatch):
    monkeypatch.delenv("FOO_A", raising=False)
    monkeypatch.setenv("FOO_B", "schon-da")
    datei = tmp_path / ".env"
    datei.write_text('FOO_A="aus-datei"\nFOO_B=aus-datei\n', encoding="utf-8")
    bot._load_dotenv(datei)
    assert bot.os.environ["FOO_A"] == "aus-datei"
    assert bot.os.environ["FOO_B"] == "schon-da"


def test_dotenv_ignoriert_kommentare_und_muell(tmp_path, monkeypatch):
    monkeypatch.delenv("FOO_C", raising=False)
    datei = tmp_path / ".env"
    datei.write_text("# Kommentar\n\nnur_text_ohne_gleich\nFOO_C='wert'\n",
                     encoding="utf-8")
    bot._load_dotenv(datei)
    assert bot.os.environ["FOO_C"] == "wert"


def test_dotenv_ignoriert_auskommentierte_zuweisung(tmp_path):
    """Genau die Form, die die .env-Vorlage im README liefert -- die
    optionalen Zeilen stehen dort auskommentiert, mitsamt ihrem Standardwert.
    Anders als "# Kommentar" enthaelt "#LOOKAHEAD_DAYS=7" ein "=", faellt
    also nicht in den Muell-Zweig: Nur die Kommentarpruefung haelt sie auf.
    Ohne sie legte jeder, der die Vorlage kopiert, Variablen wie
    "#LOOKAHEAD_DAYS" in seiner Umgebung an.

    Mutationstest: startswith("#") aus _load_dotenv entfernen -> dieser
    Test muss rot werden.
    """
    datei = tmp_path / ".env"
    datei.write_text("#LOOKAHEAD_DAYS=7\n# TIMEZONE=Europe/Berlin\n",
                     encoding="utf-8")
    vorher = set(bot.os.environ)
    bot._load_dotenv(datei)

    # Erst aufraeumen, dann pruefen: Sonst schleppte ein Fehlschlag seinen
    # Muell in jeden folgenden Test.
    dazu = sorted(set(bot.os.environ) - vorher)
    for name in dazu:
        del bot.os.environ[name]
    assert dazu == []


def test_dotenv_ohne_datei_ist_kein_fehler(tmp_path):
    bot._load_dotenv(tmp_path / "gibtsnicht.env")


@pytest.mark.parametrize("secret,erwartet", [
    ("", "<leer>"), (None, "<leer>"), ("kurz", "****"),
    ("123456789012", "1234...9012"),
])
def test_mask(secret, erwartet):
    assert bot.mask(secret) == erwartet


def test_enforce_network_timeout_setzt_grenze():
    """SICHERHEITSNETZ: Die webuntis-Bibliothek setzt selbst kein Zeitlimit.
    Ein Server, der annimmt und dann schweigt, wuerde den Lauf sonst bis
    zum Job-Limit blockieren -- 5,5 Stunden Blindflug ohne Fehlermeldung."""
    import socket
    vorher = socket.getdefaulttimeout()
    try:
        bot.enforce_network_timeout(17)
        assert socket.getdefaulttimeout() == 17
    finally:
        socket.setdefaulttimeout(vorher)


def test_enforce_network_timeout_standardwert():
    import socket
    vorher = socket.getdefaulttimeout()
    try:
        bot.enforce_network_timeout()
        assert socket.getdefaulttimeout() == bot.NETWORK_TIMEOUT
    finally:
        socket.setdefaulttimeout(vorher)


def test_now_local_faellt_bei_kaputter_zone_zurueck():
    assert isinstance(bot.now_local("Gibt/EsNicht"), dt.datetime)


def test_now_local_nutzt_zeitzone():
    assert bot.now_local("Europe/Berlin").tzinfo is not None


# ===========================================================================
#  Modell
# ===========================================================================

def test_lesson_sortiert_tupel_immer():
    """Die Invariante der Klasse -- ohne sie meldet jeder zweite Abruf
    Aenderungen, die keine sind."""
    stunde = Lesson(uid=1, date=MO, start="07:40", end="08:25",
                    subjects=("M", "D"), teachers=("Zeh", "Abel"),
                    rooms=("R2", "R1"))
    assert stunde.subjects == ("D", "M")
    assert stunde.teachers == ("Abel", "Zeh")
    assert stunde.rooms == ("R1", "R2")


def test_lesson_gleichheit_unabhaengig_von_reihenfolge():
    a = lesson(rooms=("R1", "R2"))
    b = lesson(rooms=("R2", "R1"))
    assert a == b


def test_lesson_aus_listen_wird_tupel():
    stunde = Lesson(uid=1, date=MO, start="07:40", end="08:25", rooms=["R2", "R1"])
    assert stunde.rooms == ("R1", "R2")


def test_lesson_ist_unveraenderlich():
    with pytest.raises(dataclasses.FrozenInstanceError):
        lesson().date = MI


def test_lesson_ist_hashbar():
    assert len({lesson(), lesson()}) == 1


def test_title_aus_faechern():
    assert lesson(subjects=("M",)).title == "M"


def test_title_mehrere_faecher_verbunden():
    assert lesson(subjects=("M", "D")).title == "D+M"


def test_title_faellt_auf_notiz_zurueck():
    assert lesson(subjects=(), note="D-KA").title == "D-KA"


def test_title_faellt_auf_gruppe_zurueck():
    assert lesson(subjects=(), note="", group="M-LK").title == "M-LK"


def test_title_ist_nie_leer():
    assert lesson(subjects=(), note="", group="").title == "Termin"


def test_key_enthaelt_datum_zeit_titel():
    assert lesson().key == f"{MO}|07:40|M"


def test_day_gibt_date():
    assert lesson(date=MO).day == dt.date(2026, 9, 14)


def test_json_hin_und_zurueck():
    original = lesson(teachers=("Abel",), rooms=("R1",), note="Info",
                      group="G", lesson_no=77, status=IRREGULAR)
    zurueck = Lesson.from_json(json.loads(json.dumps(original.to_json())))
    assert zurueck == original


def test_from_json_ignoriert_unbekannte_felder():
    roh = lesson().to_json()
    roh["voellig_neues_feld"] = "aus einer spaeteren Version"
    assert Lesson.from_json(roh) == lesson()


def test_from_json_ohne_listen():
    roh = {"uid": 1, "date": MO, "start": "07:40", "end": "08:25"}
    stunde = Lesson.from_json(roh)
    assert (stunde.subjects, stunde.teachers, stunde.rooms) == ((), (), ())


def test_from_json_mit_null_listen():
    roh = lesson().to_json()
    roh["teachers"] = None
    assert Lesson.from_json(roh).teachers == ()


@pytest.mark.parametrize("kaputtes_datum", [
    "14.09.2026",      # deutsches Format
    "",                # leer
    20260914,          # Zahl statt Zeichenkette
    "2026-13-45",      # gibt es nicht
])
def test_from_json_weist_kaputtes_datum_ab(kaputtes_datum):
    """SICHERHEITSNETZ: Ohne diese Pruefung winkt from_json den Eintrag
    durch, und er fliegt erst spaeter in within() oder period_index() um
    die Ohren -- dort faengt ihn niemand mehr ab, und jeder weitere Lauf
    scheitert identisch, weil state.json im Repo liegt."""
    roh = lesson().to_json()
    roh["date"] = kaputtes_datum
    with pytest.raises((ValueError, TypeError)):
        Lesson.from_json(roh)


def test_load_state_ueberspringt_kaputtes_datum(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson(uid=1), lesson(uid=2, start="08:30")], FENSTER, pfad)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten["lessons"][0]["date"] = "14.09.2026"
    pfad.write_text(json.dumps(daten), encoding="utf-8")

    zustand = bot.load_state(pfad)
    assert len(zustand.lessons) == 1


def test_within_ueberlebt_geladenen_zustand(tmp_path):
    """Der eigentliche Schaden: within() stuerzte am kaputten Datum ab."""
    pfad = tmp_path / "state.json"
    bot.save_state([lesson(uid=1), lesson(uid=2, start="08:30")], FENSTER, pfad)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten["lessons"][0]["date"] = ""
    pfad.write_text(json.dumps(daten), encoding="utf-8")

    zustand = bot.load_state(pfad)
    assert len(bot.within(zustand.lessons, FENSTER)) == 1


def test_from_json_sortiert_ebenfalls():
    """Auch der Weg ueber JSON muss die Invariante herstellen."""
    roh = lesson().to_json()
    roh["rooms"] = ["R9", "R1"]
    assert Lesson.from_json(roh).rooms == ("R1", "R9")


def test_change_sort_key_ordnet_nach_wichtigkeit():
    ausfall = Change("cancelled", lesson())
    raum = Change("room", lesson())
    assert ausfall.sort_key < raum.sort_key


def test_change_sort_key_ordnet_zuerst_nach_tag():
    heute = Change("room", lesson(date=MO))
    morgen = Change("cancelled", lesson(date=DI))
    assert heute.sort_key < morgen.sort_key


def test_change_sort_key_unbekannte_art_ganz_hinten():
    unbekannt = Change("voellig-neu", lesson())
    bekannt = Change("note", lesson())
    assert bekannt.sort_key < unbekannt.sort_key


def test_jede_art_hat_label_und_icon():
    for kind in bot.KINDS:
        assert kind in bot.LABELS
        assert kind in bot.ICONS


# ===========================================================================
#  normalise
# ===========================================================================

def test_normalise_baut_lesson():
    period = FakePeriod({"id": 5, "su": [{"id": 1, "name": "M"}],
                         "te": [{"id": 2, "name": "Abel"}],
                         "ro": [{"id": 3, "name": "R1"}]})
    stunde = bot.normalise(period, resolve_by_name)
    assert (stunde.uid, stunde.date, stunde.start, stunde.end) == \
           (5, MO, "07:40", "08:25")
    assert (stunde.subjects, stunde.teachers, stunde.rooms) == \
           (("M",), ("Abel",), ("R1",))
    assert stunde.status == REGULAR


def test_normalise_uebernimmt_ausfall():
    period = FakePeriod({"id": 5}, code="cancelled")
    assert bot.normalise(period, resolve_by_name).status == CANCELLED


def test_normalise_uebernimmt_irregular():
    period = FakePeriod({"id": 5}, code="irregular")
    assert bot.normalise(period, resolve_by_name).status == IRREGULAR


def test_normalise_unbekannter_code_wird_regular():
    period = FakePeriod({"id": 5}, code="was-ganz-neues")
    assert bot.normalise(period, resolve_by_name).status == REGULAR


def test_normalise_substtext_hat_vorrang_vor_lstext():
    period = FakePeriod({"id": 5, "substText": "Vertretung", "lstext": "Kurs"})
    assert bot.normalise(period, resolve_by_name).note == "Vertretung"


def test_normalise_nutzt_lstext_wenn_substtext_leer():
    period = FakePeriod({"id": 5, "substText": "  ", "lstext": "Kurs"})
    assert bot.normalise(period, resolve_by_name).note == "Kurs"


def test_normalise_ohne_id():
    """Sonderfall, den WebUntis gelegentlich liefert -- darf nicht kippen."""
    assert bot.normalise(FakePeriod({}), resolve_by_name).uid is None


def test_normalise_leere_lehrerliste_ist_kein_fehler():
    """ks-hausach gibt Schuelern keine Lehrerdaten -- strukturell leer."""
    period = FakePeriod({"id": 5, "te": []})
    assert bot.normalise(period, resolve_by_name).teachers == ()


def test_normalise_nimmt_lsnumber_und_sg():
    period = FakePeriod({"id": 5, "lsnumber": 4242, "sg": "M-LK"})
    stunde = bot.normalise(period, resolve_by_name)
    assert (stunde.lesson_no, stunde.group) == (4242, "M-LK")


def test_resolver_ueberspringt_nicht_dicts():
    assert resolve_by_name("te", ["kaputt", {"name": "Abel"}][1:]) == ("Abel",)


def test_text_hilfsfunktion():
    assert bot._text(None) == ""
    assert bot._text("  x  ") == "x"
    assert bot._text(7) == "7"


def test_chronological_ordnet_gleichzeitige_stunden_eindeutig():
    """Zwei Parallelkurse zur selben Zeit muessen in BEIDER
    Eingabereihenfolge gleich herauskommen -- genau der in 2.1.0 behobene
    Fehler: "Bei zwei gleichzeitigen Stunden hing die Reihenfolge davon ab,
    wie WebUntis gerade auslieferte."

    Beide Reihenfolgen zu pruefen ist der Kern: Bei nur einer rettet
    Pythons stabile Sortierung jede kaputte Variante des Schluessels.

    Mutationstest: in chronological() lesson.key durch "" ersetzen ->
    dieser Test muss rot werden.
    """
    d = lesson(uid=1, subjects=("D",))
    m = lesson(uid=2, subjects=("M",))
    assert [s.title for s in sorted([d, m], key=bot.chronological)] == ["D", "M"]
    assert [s.title for s in sorted([m, d], key=bot.chronological)] == ["D", "M"]


# ===========================================================================
#  Fenster und Zuordnung
# ===========================================================================

def test_window_of():
    heute = dt.date(2026, 9, 14)
    assert bot.window_of(7, heute) == (heute, dt.date(2026, 9, 21))


def test_overlap_ohne_alten_stand():
    assert bot.overlap((dt.date(2026, 9, 14), dt.date(2026, 9, 21)), None) is None


def test_overlap_schnittmenge():
    neu = (dt.date(2026, 9, 15), dt.date(2026, 9, 22))
    alt = (dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert bot.overlap(neu, alt) == (dt.date(2026, 9, 15), dt.date(2026, 9, 21))


def test_overlap_ohne_schnittmenge():
    neu = (dt.date(2026, 10, 1), dt.date(2026, 10, 8))
    alt = (dt.date(2026, 9, 1), dt.date(2026, 9, 8))
    assert bot.overlap(neu, alt) is None


def test_overlap_beruehrung_an_einem_tag():
    neu = (dt.date(2026, 9, 21), dt.date(2026, 9, 28))
    alt = (dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert bot.overlap(neu, alt) == (dt.date(2026, 9, 21), dt.date(2026, 9, 21))


def test_within_ohne_fenster_gibt_alles():
    stunden = [lesson(date=MO), lesson(date=MI)]
    assert bot.within(stunden, None) == stunden


def test_within_beschneidet():
    stunden = [lesson(date=MO), lesson(date=DI), lesson(date=MI)]
    treffer = bot.within(stunden, (dt.date(2026, 9, 15), dt.date(2026, 9, 15)))
    assert [stunde.date for stunde in treffer] == [DI]


def test_within_raender_sind_eingeschlossen():
    stunden = [lesson(date=MO), lesson(date=MI)]
    treffer = bot.within(stunden, (dt.date(2026, 9, 14), dt.date(2026, 9, 16)))
    assert len(treffer) == 2


def test_pair_up_ueber_id():
    alt = [lesson(uid=1, rooms=("R1",))]
    neu = [lesson(uid=1, rooms=("R2",))]
    paare, nur_alt, nur_neu = bot.pair_up(alt, neu)
    assert len(paare) == 1 and not nur_alt and not nur_neu


def test_pair_up_ueber_schluessel_wenn_id_wechselt():
    """Neu angelegte Vertretungen bekommen eine neue id -- Stufe 2."""
    alt = [lesson(uid=1, rooms=("R1",), subjects=("M",))]
    neu = [lesson(uid=999, rooms=("R2",), subjects=("M",))]
    paare, nur_alt, nur_neu = bot.pair_up(alt, neu)
    assert len(paare) == 1 and not nur_alt and not nur_neu


def test_pair_up_ohne_entsprechung():
    alt = [lesson(uid=1, start="07:40")]
    neu = [lesson(uid=2, start="11:30", subjects=("D",))]
    paare, nur_alt, nur_neu = bot.pair_up(alt, neu)
    assert not paare and len(nur_alt) == 1 and len(nur_neu) == 1


def test_pair_up_leere_seiten():
    assert bot.pair_up([], []) == ([], [], [])


def test_pair_up_nur_neue():
    paare, nur_alt, nur_neu = bot.pair_up([], [lesson()])
    assert not paare and not nur_alt and len(nur_neu) == 1


def test_pair_up_nur_alte():
    paare, nur_alt, nur_neu = bot.pair_up([lesson()], [])
    assert not paare and len(nur_alt) == 1 and not nur_neu


def test_pair_up_doppelte_id_verliert_nichts():
    """Doppelte ids waeren ein WebUntis-Fehler -- trotzdem darf keine
    Stunde unter den Tisch fallen."""
    alt = [lesson(uid=1, subjects=("M",)),
           lesson(uid=1, subjects=("D",), start="08:30")]
    neu = [lesson(uid=1, subjects=("M",)),
           lesson(uid=1, subjects=("D",), start="08:30")]
    paare, nur_alt, nur_neu = bot.pair_up(alt, neu)
    assert len(paare) + len(nur_alt) == 2
    assert len(paare) + len(nur_neu) == 2


def test_pair_up_parallelkurse_werden_nicht_vertauscht():
    """Sport A und Sport B in derselben Stunde: ohne Bewertung wuerden vier
    Aenderungen gemeldet, wo keine ist."""
    alt = [lesson(uid=1, subjects=("SpA",), lesson_no=100, rooms=("Halle",)),
           lesson(uid=2, subjects=("SpB",), lesson_no=200, rooms=("Platz",))]
    neu = [lesson(uid=11, subjects=("SpB",), lesson_no=200, rooms=("Platz",)),
           lesson(uid=12, subjects=("SpA",), lesson_no=100, rooms=("Halle",))]
    paare, nur_alt, nur_neu = bot.pair_up(alt, neu)
    assert not nur_alt and not nur_neu
    for vorher, nachher in paare:
        assert vorher.subjects == nachher.subjects


def test_pair_up_beste_paarung_gewinnt_nicht_die_erste():
    """Konkurrieren zwei alte Stunden um denselben neuen Eintrag, darf nicht
    die zufaellig zuerst gelistete gewinnen.

    Der gemeinsame Raum ist der Grund, warum "schwach" ueberhaupt mitspielt:
    Er hebt den Score von 1 auf 2 und damit ueber die Schwelle in pair_up.
    Ohne ihn waere "stark" der einzige Bewerber -- und die Sortierung nach
    Guete haette gar nichts zu entscheiden.

    Mutationstest: candidates.sort() in pair_up entfernen -> dieser Test
    muss rot werden. Scores hier: schwach 2, stark 16.
    """
    schwach = lesson(uid=1, subjects=("D",), rooms=("R1",), lesson_no=None)
    stark = lesson(uid=2, subjects=("M",), rooms=("R1",), lesson_no=500)
    kandidat = lesson(uid=99, subjects=("M",), rooms=("R1",), lesson_no=500)
    assert bot._match_score(schwach, kandidat) == 2
    assert bot._match_score(stark, kandidat) == 16

    paare, _nur_alt, _nur_neu = bot.pair_up([schwach, stark], [kandidat])
    assert len(paare) == 1
    assert paare[0][0].subjects == ("M",)


def test_match_score_andere_zeit_null():
    assert bot._match_score(lesson(start="07:40"), lesson(start="08:30")) == 0


def test_match_score_anderer_tag_null():
    assert bot._match_score(lesson(date=MO), lesson(date=DI)) == 0


def test_match_score_nur_zeit_ist_eins():
    a = lesson(subjects=("M",), rooms=("R1",))
    b = lesson(subjects=("D",), rooms=("R9",))
    assert bot._match_score(a, b) == 1


def test_match_score_lsnumber_wiegt_am_schwersten():
    a = lesson(subjects=("M",), lesson_no=7)
    nur_lsnumber = lesson(subjects=("D",), lesson_no=7)
    nur_fach = lesson(subjects=("M",), lesson_no=None)
    assert bot._match_score(a, nur_lsnumber) > bot._match_score(a, nur_fach)


def test_match_score_identisch_ist_maximal():
    a = lesson(subjects=("M",), rooms=("R1",), lesson_no=7)
    assert bot._match_score(a, a) == 1 + 8 + 4 + 2 + 1


def test_match_score_paart_nicht_bei_score_eins():
    """Score 1 heisst 'nur die Uhrzeit stimmt' -- lieber entfallen + neu."""
    alt = [lesson(uid=1, subjects=("M",))]
    neu = [lesson(uid=2, subjects=("Sp",))]
    paare, nur_alt, nur_neu = bot.pair_up(alt, neu)
    assert not paare and len(nur_alt) == 1 and len(nur_neu) == 1


# ===========================================================================
#  compare / diff
# ===========================================================================

def test_compare_ohne_unterschied():
    assert bot.compare(lesson(), lesson()) == []


def test_compare_ausfall():
    aenderungen = bot.compare(lesson(), lesson(status=CANCELLED, note="krank"))
    assert [c.kind for c in aenderungen] == ["cancelled"]
    assert aenderungen[0].detail == "krank"


def test_compare_ausfall_hat_vorrang_vor_raumwechsel():
    """Wenn die Stunde entfaellt, interessiert der Raum niemanden mehr."""
    alt = lesson(rooms=("R1",))
    neu = lesson(rooms=("R2",), status=CANCELLED)
    assert [c.kind for c in bot.compare(alt, neu)] == ["cancelled"]


def test_compare_ausfall_zurueckgenommen():
    aenderungen = bot.compare(lesson(status=CANCELLED), lesson())
    assert [c.kind for c in aenderungen] == ["uncancelled"]


def test_compare_ausfall_zurueckgenommen_nennt_raum_und_vertretung():
    """SICHERHEITSNETZ: Die Stunde findet wieder statt -- dann ist wichtig,
    WO und mit WEM. Nur "findet doch statt" schickt den Leser in den alten
    Raum zur alten Lehrkraft."""
    alt = lesson(status=CANCELLED, rooms=("R1",), teachers=("Abel",))
    neu = lesson(rooms=("R9",), teachers=("Zeh",))
    aenderungen = bot.compare(alt, neu)
    assert [c.kind for c in aenderungen] == ["uncancelled", "teacher", "room"]
    assert aenderungen[2].detail == "R1 → R9"


def test_compare_ausfall_zurueckgenommen_bleibt_die_leitaenderung():
    """Das Symbol der Meldung darf nicht zum Raumwechsel kippen."""
    alt = lesson(status=CANCELLED, rooms=("R1",))
    eintrag = bot.build_entries(bot.compare(alt, lesson(rooms=("R2",))), RASTER)[0]
    assert eintrag.lead.kind == "uncancelled"
    assert eintrag.labels == "findet doch statt, Raumwechsel"


def test_compare_ausfall_zurueckgenommen_meldet_neuen_hinweis():
    alt = lesson(status=CANCELLED, note="Lehrkraft erkrankt")
    aenderungen = bot.compare(alt, lesson(note="findet in R2 statt"))
    assert aenderungen[0].detail.endswith("· findet in R2 statt")


def test_compare_ausfall_zurueckgenommen_verschweigt_weggefallenen_hinweis():
    """"Lehrkraft erkrankt" ist die Absagebegruendung -- dass sie hinfaellig
    ist, sagt schon "findet doch statt". "Hinweis entfernt" waere Laerm."""
    alt = lesson(status=CANCELLED, note="Lehrkraft erkrankt")
    aenderungen = bot.compare(alt, lesson(note=""))
    assert [c.kind for c in aenderungen] == ["uncancelled"]
    assert aenderungen[0].detail == "Der Ausfall wurde zurückgenommen"


def test_compare_bleibt_abgesagt_meldet_keine_felder():
    alt = lesson(status=CANCELLED, rooms=("R1",))
    neu = lesson(status=CANCELLED, rooms=("R2",))
    assert bot.compare(alt, neu) == []


def test_compare_bleibt_abgesagt_meldet_geaenderte_info():
    """SICHERHEITSNETZ: Ueber den Zusatztext teilt die Schule mit, was aus
    einer abgesagten Stunde stattdessen wird. Dieser Zweig gab frueher
    pauschal [] zurueck."""
    alt = lesson(status=CANCELLED, rooms=("R1",))
    neu = lesson(status=CANCELLED, rooms=("R2",), note="jetzt doch in R2")
    aenderungen = bot.compare(alt, neu)
    assert [c.kind for c in aenderungen] == ["note"]
    assert aenderungen[0].detail == "jetzt doch in R2"


def test_compare_bleibt_abgesagt_meldet_entfernte_info():
    alt = lesson(status=CANCELLED, note="Lehrkraft erkrankt")
    aenderungen = bot.compare(alt, lesson(status=CANCELLED))
    assert [c.kind for c in aenderungen] == ["note"]
    assert aenderungen[0].detail == "(entfernt)"


def test_compare_raumwechsel():
    aenderungen = bot.compare(lesson(rooms=("R1",)), lesson(rooms=("R2",)))
    assert [c.kind for c in aenderungen] == ["room"]
    assert aenderungen[0].detail == "R1 → R2"


def test_compare_vertretung():
    aenderungen = bot.compare(lesson(teachers=("Abel",)), lesson(teachers=("Zeh",)))
    assert [c.kind for c in aenderungen] == ["teacher"]


def test_compare_fachwechsel():
    aenderungen = bot.compare(lesson(subjects=("M",)), lesson(subjects=("D",)))
    assert [c.kind for c in aenderungen] == ["subject"]


def test_compare_leeres_feld_wird_als_gedankenstrich_gezeigt():
    aenderungen = bot.compare(lesson(rooms=()), lesson(rooms=("R2",)))
    assert aenderungen[0].detail == "— → R2"


def test_compare_mehrere_felder():
    alt = lesson(teachers=("Abel",), rooms=("R1",))
    neu = lesson(teachers=("Zeh",), rooms=("R2",))
    assert [c.kind for c in bot.compare(alt, neu)] == ["teacher", "room"]


def test_compare_zeitverschiebung_am_selben_tag():
    aenderungen = bot.compare(lesson(start="07:40", end="08:25"),
                              lesson(start="11:30", end="12:15"))
    assert [c.kind for c in aenderungen] == ["time"]
    assert aenderungen[0].detail == "07:40-08:25 → 11:30-12:15"


def test_compare_verlegung_auf_anderen_tag():
    aenderungen = bot.compare(lesson(date=MO), lesson(date=MI))
    assert [c.kind for c in aenderungen] == ["time"]
    assert "Montag" in aenderungen[0].detail and "Mittwoch" in aenderungen[0].detail


def test_compare_markierung_ohne_feldaenderung():
    """Bei Schulen ohne Lehrerdaten oft das EINZIGE Signal einer Vertretung."""
    aenderungen = bot.compare(lesson(), lesson(status=IRREGULAR))
    assert [c.kind for c in aenderungen] == ["marked"]


def test_compare_markierung_zurueckgenommen():
    aenderungen = bot.compare(lesson(status=IRREGULAR), lesson())
    assert [c.kind for c in aenderungen] == ["unmarked"]


def test_compare_markierung_nutzt_beschreibung_wenn_keine_notiz():
    neu = lesson(status=IRREGULAR, rooms=("R1",), teachers=("Abel",))
    assert "R1" in bot.compare(lesson(rooms=("R1",), teachers=("Abel",)), neu)[0].detail


def test_compare_nur_notiz():
    aenderungen = bot.compare(lesson(note=""), lesson(note="Bitte Buch mitbringen"))
    assert [c.kind for c in aenderungen] == ["note"]


def test_compare_notiz_entfernt():
    aenderungen = bot.compare(lesson(note="alt"), lesson(note=""))
    assert aenderungen[0].detail == "(entfernt)"


def test_compare_notiz_haengt_an_wichtigster_aenderung():
    alt = lesson(teachers=("Abel",), rooms=("R1",), note="")
    neu = lesson(teachers=("Zeh",), rooms=("R2",), note="Vertretung")
    aenderungen = bot.compare(alt, neu)
    assert "Vertretung" in aenderungen[0].detail
    assert aenderungen[0].kind == "teacher"
    assert "Vertretung" not in aenderungen[1].detail


def test_compare_notiz_geht_bei_nebenaenderung_nicht_verloren():
    alt = lesson(rooms=("R1",), note="")
    neu = lesson(rooms=("R2",), note="Raum getauscht")
    assert "Raum getauscht" in bot.compare(alt, neu)[0].detail


def test_compare_entfernte_notiz_neben_anderer_aenderung():
    alt = lesson(rooms=("R1",), note="alt")
    neu = lesson(rooms=("R2",), note="")
    assert "Hinweis entfernt" in bot.compare(alt, neu)[0].detail


def test_describe_setzt_teile_zusammen():
    text = bot.describe(lesson(rooms=("R1",), teachers=("Abel",), note="Info"))
    assert text == "Raum R1 · Abel · Info"


def test_describe_leer():
    assert bot.describe(lesson(rooms=(), teachers=(), note="")) == ""


def test_join():
    assert bot._join(("a", "b")) == "a, b"
    assert bot._join(()) == "—"


def test_diff_leer():
    assert bot.diff([], []) == []


def test_diff_neuer_termin():
    aenderungen = bot.diff([], [lesson()])
    assert [c.kind for c in aenderungen] == ["added"]


def test_diff_neuer_termin_der_schon_abgesagt_ist():
    aenderungen = bot.diff([], [lesson(status=CANCELLED)])
    assert [c.kind for c in aenderungen] == ["cancelled"]


def test_diff_aus_dem_plan_genommen():
    aenderungen = bot.diff([lesson()], [])
    assert [c.kind for c in aenderungen] == ["removed"]


def test_diff_bereits_abgesagte_stunde_verschwindet_lautlos():
    """Eine schon gemeldete Absage, die aus dem Plan faellt, ist keine
    Neuigkeit mehr."""
    assert bot.diff([lesson(status=CANCELLED)], []) == []


def test_diff_ist_sortiert():
    alt = [lesson(uid=1, date=MI, subjects=("M",)),
           lesson(uid=2, date=MO, subjects=("D",))]
    aenderungen = bot.diff(alt, [])
    assert [c.lesson.date for c in aenderungen] == [MO, MI]


def test_diff_beachtet_fenster():
    """Was ausserhalb des Vergleichsfensters liegt, wird gar nicht erst
    betrachtet -- sonst meldet der Bot jeden Tag einen kompletten Schultag
    als 'neuer Termin', nur weil das Fenster weitergerollt ist."""
    neu = [lesson(uid=1, date=MO), lesson(uid=2, date=MI, subjects=("D",))]
    fenster = (dt.date(2026, 9, 14), dt.date(2026, 9, 15))
    aenderungen = bot.diff([], neu, fenster)
    assert [c.lesson.date for c in aenderungen] == [MO]


def test_diff_ohne_ueberlappung_meldet_nichts():
    neu = [lesson(uid=1, date=MO), lesson(uid=2, date=MI, subjects=("D",))]
    fenster = (dt.date(2026, 10, 1), dt.date(2026, 10, 8))
    assert bot.diff([], neu, fenster) == []


def test_diff_kombiniert_paare_und_einzelne():
    alt = [lesson(uid=1, rooms=("R1",)), lesson(uid=2, date=MI, subjects=("D",))]
    neu = [lesson(uid=1, rooms=("R2",)), lesson(uid=3, date=DI, subjects=("Sp",))]
    arten = sorted(c.kind for c in bot.diff(alt, neu))
    assert arten == ["added", "removed", "room"]


# ===========================================================================
#  Plausibilitaet  -- SICHERHEITSNETZ gegen Massen-Fehlalarme
# ===========================================================================

def test_plausibel_bei_normalen_aenderungen():
    alt = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    neu = alt[:9]
    bot.check_plausible(alt, neu, None)


def test_unplausibel_wenn_alles_weg():
    """Das Muster ist absichtlich eng: "0 Stunden" allein steckt auch in der
    Meldung des ratio-Pfads -- "10 von 10 Stunden (100%)". Der Test wurde
    damit auch dann gruen, wenn der Guard ersatzlos verschwand, und prueft
    dann in Wahrheit einen ganz anderen Codepfad.

    Mutationstest: "if not new: raise" in check_plausible entfernen ->
    dieser Test muss rot werden.
    """
    alt = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    with pytest.raises(Implausible, match=r"lieferte 0 Stunden"):
        bot.check_plausible(alt, [], None)


def test_unplausibel_wenn_grosser_teil_weg():
    """SICHERHEITSNETZ: Der haeufigere Fall als die leere Antwort -- WebUntis
    liefert einen Teil. Ohne die Bremse meldete der Bot acht Ausfaelle auf
    einmal, und niemand koennte der Meldung noch trauen.

    Das Muster nennt die Zahlen, nicht nur das Prozentzeichen: Sonst genuegte
    irgendeine Implausible-Meldung, auch die aus dem Zweig daneben.

    Mutationstest: "if ratio > max_vanish: raise" in check_plausible
    entfernen -> dieser Test muss rot werden.
    """
    alt = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    with pytest.raises(Implausible, match=r"8 von 10 Stunden \(80%\)"):
        bot.check_plausible(alt, alt[:2], None)


def test_plausibel_wenn_alter_stand_leer():
    bot.check_plausible([], [], None)


def test_plausibel_wenn_alle_alten_schon_abgesagt():
    alt = [lesson(uid=i, status=CANCELLED, start=f"{7+i:02d}:40") for i in range(5)]
    bot.check_plausible(alt, [], None)


def test_plausibilitaet_beachtet_fenster():
    """Ohne Beschneidung zaehlen Stunden als verschwunden, die nur aus dem
    rollenden Fenster gerutscht sind."""
    alt = [lesson(uid=i, date=MO, start=f"{7+i:02d}:40") for i in range(10)]
    neu = [lesson(uid=99, date=MI, subjects=("D",))]
    fenster = (dt.date(2026, 9, 16), dt.date(2026, 9, 21))
    bot.check_plausible(alt, neu, fenster)


def test_plausibilitaet_schwelle_einstellbar():
    alt = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    bot.check_plausible(alt, alt[:2], None, max_vanish=0.95)


def test_plausibilitaet_genau_an_der_schwelle_ist_ok():
    alt = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    bot.check_plausible(alt, alt[:3], None, max_vanish=0.7)


# ===========================================================================
#  Nachrichten -- Grundlagen
# ===========================================================================

def test_esc_maskiert_spitze_klammern():
    assert bot.esc("<b>") == "&lt;b&gt;"


def test_esc_laesst_anfuehrungszeichen_stehen():
    assert bot.esc('Raum "A"') == 'Raum "A"'


def test_day_header():
    assert bot.day_header(MO) == "Montag, 14.09."


def test_day_header_bei_muell():
    assert bot.day_header("kein-datum") == "kein-datum"


@pytest.mark.parametrize("datum,erwartet", [
    (MO, "heute"), (DI, "morgen"), (MI, "übermorgen"),
    ("2026-09-17", ""), ("2026-09-13", ""),
])
def test_relative(datum, erwartet):
    assert bot.relative(datum, dt.date(2026, 9, 14)) == erwartet


def test_relative_bei_muell():
    assert bot.relative("kaputt", dt.date(2026, 9, 14)) == ""


# ===========================================================================
#  Doppelstunden
# ===========================================================================

def test_period_index_findet_stunde():
    assert bot.period_index(lesson(date=MO, start="08:30"), RASTER) == 1


def test_period_index_ohne_treffer():
    assert bot.period_index(lesson(date=MO, start="06:00"), RASTER) is None


def test_period_index_ohne_raster():
    assert bot.period_index(lesson(), {}) is None


def test_period_index_unbekannter_wochentag():
    """Samstag steht nicht im Raster -- darf nicht kippen."""
    assert bot.period_index(lesson(date="2026-09-19"), RASTER) is None


def test_period_name():
    assert bot.period_name(lesson(date=MO, start="09:35"), RASTER) == "3"


def test_period_name_ohne_treffer():
    assert bot.period_name(lesson(date=MO, start="06:00"), RASTER) is None


def test_consecutive_direkt_aufeinander():
    a = Change("room", lesson(start="07:40"))
    b = Change("room", lesson(start="08:30"))
    assert bot._consecutive(a, b, RASTER) is True


def test_consecutive_mit_freistunde_dazwischen():
    a = Change("room", lesson(start="07:40"))
    b = Change("room", lesson(start="09:35"))
    assert bot._consecutive(a, b, RASTER) is False


def test_consecutive_verkehrte_richtung():
    a = Change("room", lesson(start="08:30"))
    b = Change("room", lesson(start="07:40"))
    assert bot._consecutive(a, b, RASTER) is False


def test_consecutive_ohne_raster():
    a = Change("room", lesson(start="07:40"))
    b = Change("room", lesson(start="08:30"))
    assert bot._consecutive(a, b, {}) is False


def test_gruppierung_fasst_doppelstunde_zusammen():
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40", end="08:25")),
                   Change("cancelled", lesson(uid=2, start="08:30", end="09:15"))]
    gruppen = bot.group_doppelstunden(aenderungen, RASTER)
    assert len(gruppen) == 1 and len(gruppen[0]) == 2


def test_gruppierung_trennt_bei_freistunde():
    """Zwischen 2. und 4. Stunde liegt die 3. -- das ist eine echte Luecke."""
    aenderungen = [Change("cancelled", lesson(uid=1, start="08:30")),
                   Change("cancelled", lesson(uid=2, start="10:25"))]
    assert len(bot.group_doppelstunden(aenderungen, RASTER)) == 2


def test_gruppierung_trennt_verschiedene_arten():
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40")),
                   Change("room", lesson(uid=2, start="08:30"))]
    assert len(bot.group_doppelstunden(aenderungen, RASTER)) == 2


def test_gruppierung_trennt_verschiedene_faecher():
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40", subjects=("M",))),
                   Change("cancelled", lesson(uid=2, start="08:30", subjects=("D",)))]
    assert len(bot.group_doppelstunden(aenderungen, RASTER)) == 2


def test_gruppierung_trennt_verschiedene_details():
    aenderungen = [Change("room", lesson(uid=1, start="07:40"), "R1 → R2"),
                   Change("room", lesson(uid=2, start="08:30"), "R1 → R9")]
    assert len(bot.group_doppelstunden(aenderungen, RASTER)) == 2


def test_gruppierung_trennt_verschiedene_tage():
    aenderungen = [Change("cancelled", lesson(uid=1, date=MO, start="10:25")),
                   Change("cancelled", lesson(uid=2, date=DI, start="07:40"))]
    assert len(bot.group_doppelstunden(aenderungen, RASTER)) == 2


def test_gruppierung_ohne_raster_fasst_nie_zusammen():
    """Kein Raster -> Verhalten exakt wie vor der Doppelstunden-Funktion."""
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40")),
                   Change("cancelled", lesson(uid=2, start="08:30"))]
    assert len(bot.group_doppelstunden(aenderungen, {})) == 2


def test_gruppierung_dreierblock():
    aenderungen = [Change("cancelled", lesson(uid=i, start=s))
                   for i, s in enumerate(("07:40", "08:30", "09:35"))]
    gruppen = bot.group_doppelstunden(aenderungen, RASTER)
    assert len(gruppen) == 1 and len(gruppen[0]) == 3


def test_gruppierung_vertretung_mit_raumwechsel():
    """Der Fall, an dem reine Listen-Nachbarschaft scheitern wuerde:
    compare() liefert je Stunde ZWEI Changes, die zusammengehoerenden
    liegen darum nie nebeneinander."""
    aenderungen = [
        Change("teacher", lesson(uid=1, start="07:40"), "Abel → Zeh"),
        Change("room", lesson(uid=1, start="07:40"), "R1 → R2"),
        Change("teacher", lesson(uid=2, start="08:30"), "Abel → Zeh"),
        Change("room", lesson(uid=2, start="08:30"), "R1 → R2"),
    ]
    gruppen = bot.group_doppelstunden(aenderungen, RASTER)
    assert len(gruppen) == 2
    assert all(len(g) == 2 for g in gruppen)


def test_gruppierung_behaelt_chronologische_reihenfolge():
    """Das Bucketing zerstoert die Reihenfolge -- danach wird neu sortiert."""
    aenderungen = [
        Change("room", lesson(uid=1, start="10:25"), "R1 → R2"),
        Change("cancelled", lesson(uid=2, start="07:40")),
        Change("cancelled", lesson(uid=3, start="08:30")),
    ]
    gruppen = bot.group_doppelstunden(aenderungen, RASTER)
    assert [g[0].lesson.start for g in gruppen] == ["07:40", "10:25"]


def test_gruppierung_verliert_keine_aenderung():
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40")),
                   Change("cancelled", lesson(uid=2, start="08:30")),
                   Change("room", lesson(uid=3, start="09:35"), "R1 → R2"),
                   Change("added", lesson(uid=4, date=DI, start="07:40"))]
    gruppen = bot.group_doppelstunden(aenderungen, RASTER)
    assert sum(len(g) for g in gruppen) == len(aenderungen)


def test_gruppierung_leere_liste():
    assert bot.group_doppelstunden([], RASTER) == []


def test_gruppierung_liefert_gruppen_in_sortierter_reihenfolge():
    """Invariante, auf die build_entries() baut: Die Gruppen kommen nach
    sort_key geordnet -- also je Block die wichtigste Aenderung zuerst.
    Faellt die Sortierung am Ende von group_doppelstunden() weg, traegt
    ein gebuendelter Eintrag das falsche Symbol."""
    aenderungen = [Change("room", lesson(uid=1, start="10:25"), "R1 → R2"),
                   Change("cancelled", lesson(uid=2, start="07:40")),
                   Change("teacher", lesson(uid=3, start="10:25"), "Abel → Zeh")]
    gruppen = bot.group_doppelstunden(aenderungen, RASTER)
    schluessel = [g[0].sort_key for g in gruppen]
    assert schluessel == sorted(schluessel)


def test_block_label_einzelstunde_zeigt_stundennummer():
    gruppe = [Change("cancelled", lesson(start="07:40"))]
    assert bot.block_label(gruppe, RASTER) == "1. Stunde"


def test_block_label_einzelstunde_spaeter_am_tag():
    gruppe = [Change("cancelled", lesson(start="12:20"))]
    assert bot.block_label(gruppe, RASTER) == "6. Stunde"


def test_block_label_einzelstunde_quer_zum_raster_zeigt_uhrzeit():
    """Sondertermine (Klausuren, Exkursionen) liegen oft nicht auf einem
    Rasterbeginn -- dann ist die Uhrzeit die einzige ehrliche Angabe."""
    gruppe = [Change("added", lesson(start="13:30"))]
    assert bot.block_label(gruppe, RASTER) == "13:30"


def test_block_label_einzelstunde_an_tag_ohne_raster():
    gruppe = [Change("cancelled", lesson(date="2026-09-19", start="07:40"))]
    assert bot.block_label(gruppe, RASTER) == "07:40"


def test_block_label_doppelstunde():
    gruppe = [Change("cancelled", lesson(uid=1, start="07:40")),
              Change("cancelled", lesson(uid=2, start="08:30"))]
    assert bot.block_label(gruppe, RASTER) == "1./2. Stunde"


def test_block_label_dreierblock():
    gruppe = [Change("cancelled", lesson(uid=i, start=s))
              for i, s in enumerate(("07:40", "08:30", "09:35"))]
    assert bot.block_label(gruppe, RASTER) == "1.–3. Stunde"


def test_block_label_einzelstunde_ohne_raster():
    assert bot.block_label([Change("cancelled", lesson(start="11:30"))], {}) == "11:30"


# ===========================================================================
#  render
# ===========================================================================

HEUTE = dt.date(2026, 9, 14)


# ===========================================================================
#  Eintraege -- Buendelung mehrerer Aenderungsarten derselben Stunde
# ===========================================================================

def test_entry_einzelne_aenderung():
    eintraege = bot.build_entries([Change("cancelled", lesson())], RASTER)
    assert len(eintraege) == 1
    assert eintraege[0].label == "1. Stunde"
    assert eintraege[0].title == "M"


def test_entry_leere_liste():
    assert bot.build_entries([], RASTER) == []


def test_entry_buendelt_vertretung_und_raumwechsel():
    """Der haeufigste echte Fall: compare() liefert zwei Change-Objekte
    fuer dieselbe Stunde -- die gehoeren in EINEN Eintrag."""
    aenderungen = [Change("teacher", lesson(uid=1), "Abel → Zeh"),
                   Change("room", lesson(uid=1), "R1 → R2")]
    eintraege = bot.build_entries(aenderungen, RASTER)
    assert len(eintraege) == 1
    assert eintraege[0].labels == "Vertretung, Raumwechsel"


def test_entry_buendelt_auch_ueber_eine_doppelstunde():
    aenderungen = [
        Change("teacher", lesson(uid=1, start="07:40"), "Abel → Zeh"),
        Change("room", lesson(uid=1, start="07:40"), "R1 → R2"),
        Change("teacher", lesson(uid=2, start="08:30"), "Abel → Zeh"),
        Change("room", lesson(uid=2, start="08:30"), "R1 → R2"),
    ]
    eintraege = bot.build_entries(aenderungen, RASTER)
    assert len(eintraege) == 1
    assert eintraege[0].label == "1./2. Stunde"
    assert eintraege[0].labels == "Vertretung, Raumwechsel"


def test_entry_arten_nach_wichtigkeit_sortiert():
    """KINDS ist nach Wichtigkeit sortiert -- die Eingabereihenfolge darf
    keine Rolle spielen."""
    aenderungen = [Change("room", lesson(uid=1), "R1 → R2"),
                   Change("subject", lesson(uid=1), "M → D"),
                   Change("teacher", lesson(uid=1), "Abel → Zeh")]
    eintrag = bot.build_entries(aenderungen, RASTER)[0]
    assert eintrag.labels == "Fachwechsel, Vertretung, Raumwechsel"


def test_entry_lead_bestimmt_das_symbol():
    """Bei 'Vertretung + Raumwechsel' soll 👤 stehen, nicht 🚪."""
    aenderungen = [Change("room", lesson(uid=1), "R1 → R2"),
                   Change("teacher", lesson(uid=1), "Abel → Zeh")]
    assert bot.build_entries(aenderungen, RASTER)[0].lead.kind == "teacher"


def test_entry_details_in_derselben_reihenfolge():
    aenderungen = [Change("room", lesson(uid=1), "R1 → R2"),
                   Change("teacher", lesson(uid=1), "Abel → Zeh")]
    assert bot.build_entries(aenderungen, RASTER)[0].details == \
           ["Abel → Zeh", "R1 → R2"]


def test_entry_details_ueberspringt_leere():
    aenderungen = [Change("teacher", lesson(uid=1), ""),
                   Change("room", lesson(uid=1), "R1 → R2")]
    assert bot.build_entries(aenderungen, RASTER)[0].details == ["R1 → R2"]


def test_entry_details_entfernt_dopplungen():
    """Zweimal dieselbe Zeile untereinander sieht nach einem Fehler aus."""
    aenderungen = [Change("teacher", lesson(uid=1), "A → B"),
                   Change("room", lesson(uid=1), "A → B")]
    assert bot.build_entries(aenderungen, RASTER)[0].details == ["A → B"]


def test_entry_trennt_aenderungen_mit_unterschiedlicher_reichweite():
    """Vertretung ueber beide Stunden, Raumwechsel nur in der ersten: Ein
    gemeinsamer Eintrag wuerde behaupten, der Raum habe sich in beiden
    Stunden geaendert."""
    aenderungen = [
        Change("teacher", lesson(uid=1, start="07:40"), "Abel → Zeh"),
        Change("teacher", lesson(uid=2, start="08:30"), "Abel → Zeh"),
        Change("room", lesson(uid=1, start="07:40"), "R1 → R2"),
    ]
    eintraege = bot.build_entries(aenderungen, RASTER)
    assert [(e.label, e.labels) for e in eintraege] == \
           [("1./2. Stunde", "Vertretung"), ("1. Stunde", "Raumwechsel")]


def test_entry_trennt_verschiedene_faecher_zur_selben_zeit():
    """Parallelkurse -- gleiche Stunde, aber nichts miteinander zu tun."""
    aenderungen = [Change("room", lesson(uid=1, subjects=("SpA",)), "Halle → Platz"),
                   Change("room", lesson(uid=2, subjects=("SpB",)), "Platz → Halle")]
    assert len(bot.build_entries(aenderungen, RASTER)) == 2


def test_entry_trennt_parallelkurse_desselben_fachs():
    """SICHERHEITSNETZ: Zwei Sportgruppen zur selben Stunde, dasselbe
    Fachkuerzel. Gruppe A entfaellt, Gruppe B wechselt nur den Raum.

    Ohne die Kursgruppe im Schluessel wird daraus EIN Eintrag
    "Sp — entfaellt, Raumwechsel". Wer in Gruppe B ist, liest "entfaellt"
    und bleibt zu Hause, obwohl sein Kurs stattfindet."""
    aenderungen = [
        Change("cancelled", lesson(uid=1, subjects=("Sp",), group="SpA"),
               "Lehrkraft erkrankt"),
        Change("room", lesson(uid=2, subjects=("Sp",), group="SpB"),
               "Halle → Platz"),
    ]
    eintraege = bot.build_entries(aenderungen, RASTER)
    assert [e.labels for e in eintraege] == ["entfällt", "Raumwechsel"]


def test_entry_parallelkurse_bilden_keinen_gemischten_block():
    """Beide Gruppen entfallen ueber dieselbe Doppelstunde. Ohne die
    Kursgruppe im Bucket-Schluessel verkettet die Sortierung nach Startzeit
    Stunde 2 der einen Gruppe an Stunde 1 der anderen -- Bloecke, die es
    nie gab."""
    aenderungen = [
        Change("cancelled", lesson(uid=1, start="07:40", subjects=("Sp",),
                                   group="SpA"), "krank"),
        Change("cancelled", lesson(uid=2, start="07:40", subjects=("Sp",),
                                   group="SpB"), "krank"),
        Change("cancelled", lesson(uid=3, start="08:30", end="09:15",
                                   subjects=("Sp",), group="SpA"), "krank"),
        Change("cancelled", lesson(uid=4, start="08:30", end="09:15",
                                   subjects=("Sp",), group="SpB"), "krank"),
    ]
    eintraege = bot.build_entries(aenderungen, RASTER)
    assert [e.label for e in eintraege] == ["1./2. Stunde", "1./2. Stunde"]


def test_entry_ohne_kursgruppe_unveraendert():
    """Die meisten Schulen liefern kein sg-Feld. Dann darf sich nichts
    aendern -- sonst haette der Schluessel den haeufigen Fall verschlechtert,
    um den seltenen zu retten."""
    aenderungen = [Change("teacher", lesson(uid=1), "Abel → Zeh"),
                   Change("room", lesson(uid=1), "R1 → R2")]
    eintraege = bot.build_entries(aenderungen, RASTER)
    assert len(eintraege) == 1
    assert eintraege[0].labels == "Vertretung, Raumwechsel"


def test_entry_trennt_verschiedene_tage():
    aenderungen = [Change("room", lesson(uid=1, date=MO), "R1 → R2"),
                   Change("teacher", lesson(uid=2, date=DI), "Abel → Zeh")]
    assert len(bot.build_entries(aenderungen, RASTER)) == 2


def test_entry_chronologisch_sortiert():
    aenderungen = [Change("room", lesson(uid=1, date=DI, start="07:40"), "a → b"),
                   Change("cancelled", lesson(uid=2, date=MO, start="10:25")),
                   Change("cancelled", lesson(uid=3, date=MO, start="07:40"))]
    eintraege = bot.build_entries(aenderungen, RASTER)
    assert [(e.date, e.label) for e in eintraege] == \
           [(MO, "1. Stunde"), (MO, "4. Stunde"), (DI, "1. Stunde")]


def test_entry_verliert_keine_art():
    aenderungen = [Change("subject", lesson(uid=1), "M → D"),
                   Change("teacher", lesson(uid=1), "Abel → Zeh"),
                   Change("room", lesson(uid=1), "R1 → R2"),
                   Change("added", lesson(uid=2, start="08:30", subjects=("Sp",)))]
    arten = {c.kind for e in bot.build_entries(aenderungen, RASTER) for c in e.changes}
    assert arten == {"subject", "teacher", "room", "added"}


def test_entry_buendelt_auch_ohne_raster():
    """Ohne Raster dient die Uhrzeit als Blockkennung -- die Buendelung
    funktioniert trotzdem, nur eben je Einzelstunde."""
    aenderungen = [Change("teacher", lesson(uid=1), "Abel → Zeh"),
                   Change("room", lesson(uid=1), "R1 → R2")]
    eintraege = bot.build_entries(aenderungen, {})
    assert len(eintraege) == 1 and eintraege[0].label == "07:40"


def test_entry_ist_unveraenderlich():
    eintrag = bot.build_entries([Change("cancelled", lesson())], RASTER)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        eintrag.label = "anders"


def test_entry_sort_key_nimmt_den_blockbeginn():
    aenderungen = [Change("teacher", lesson(uid=1, start="07:40"), "Abel → Zeh"),
                   Change("teacher", lesson(uid=2, start="08:30"), "Abel → Zeh")]
    assert bot.build_entries(aenderungen, RASTER)[0].sort_key[1] == "07:40"


def test_render_zeigt_gebuendelte_arten_in_einer_zeile():
    aenderungen = [Change("teacher", lesson(uid=1), "Abel → Zeh"),
                   Change("room", lesson(uid=1), "R1 → R2")]
    text = bot.render(aenderungen, HEUTE, periods=RASTER)
    assert "Vertretung, Raumwechsel" in text
    assert text.count("1. Stunde") == 1


def test_render_zeigt_alle_details_des_eintrags():
    aenderungen = [Change("teacher", lesson(uid=1), "Abel → Zeh"),
                   Change("room", lesson(uid=1), "R1 → R2")]
    text = bot.render(aenderungen, HEUTE, periods=RASTER)
    assert "<i>Abel → Zeh</i>" in text and "<i>R1 → R2</i>" in text


def test_render_nutzt_symbol_der_wichtigsten_art():
    aenderungen = [Change("room", lesson(uid=1), "R1 → R2"),
                   Change("cancelled", lesson(uid=1), "krank")]
    text = bot.render(aenderungen, HEUTE, periods=RASTER)
    assert "❌" in text and "🚪" not in text


def test_render_zeigt_stundennummer_bei_einzelaenderung():
    text = bot.render([Change("room", lesson(start="12:20"), "R1 → R2")],
                      HEUTE, periods=RASTER)
    assert "6. Stunde" in text and "12:20" not in text


def test_render_bleibt_bei_uhrzeit_ohne_raster():
    text = bot.render([Change("room", lesson(start="12:20"), "R1 → R2")], HEUTE)
    assert "<b>12:20</b>" in text
    # Nicht auf "Stunde" pruefen -- das steckt schon in der Ueberschrift.
    assert ". Stunde" not in text


def test_render_vollstaendiges_szenario_wird_kuerzer():
    """Der Praxisnutzen in einer Zahl."""
    aenderungen = [
        Change("cancelled", lesson(uid=1, start="07:40"), "krank"),
        Change("cancelled", lesson(uid=2, start="08:30"), "krank"),
        Change("teacher", lesson(uid=3, start="09:35", subjects=("D",)), "Abel → Zeh"),
        Change("room", lesson(uid=3, start="09:35", subjects=("D",)), "R1 → R2"),
        Change("teacher", lesson(uid=4, start="10:25", subjects=("D",)), "Abel → Zeh"),
        Change("room", lesson(uid=4, start="10:25", subjects=("D",)), "R1 → R2"),
    ]
    assert len(bot.build_entries(aenderungen, RASTER)) == 2
    assert len(bot.build_entries(aenderungen, {})) == 4


def test_render_ohne_aenderungen_ist_leer():
    assert bot.render([], HEUTE) == ""


def test_render_enthaelt_ueberschrift():
    text = bot.render([Change("cancelled", lesson())], HEUTE)
    assert text.startswith("<b>Stundenplan-Änderungen</b>")


def test_render_eigene_ueberschrift():
    text = bot.render([Change("cancelled", lesson())], HEUTE, header="Test")
    assert "<b>Test</b>" in text


def test_render_zeigt_tag_und_relativen_bezug():
    text = bot.render([Change("cancelled", lesson(date=MO))], HEUTE)
    assert "Montag, 14.09." in text and "(heute)" in text


def test_render_ohne_relativen_bezug_bei_fernem_tag():
    text = bot.render([Change("cancelled", lesson(date="2026-09-21"))], HEUTE)
    assert "(heute)" not in text and "(morgen)" not in text


def test_render_zeigt_icon_und_label():
    text = bot.render([Change("cancelled", lesson())], HEUTE)
    assert "❌" in text and "entfällt" in text


def test_render_zeigt_detail_kursiv():
    text = bot.render([Change("room", lesson(), "R1 → R2")], HEUTE)
    assert "<i>R1 → R2</i>" in text


def test_render_ohne_detail_keine_leerzeile():
    text = bot.render([Change("cancelled", lesson(), "")], HEUTE)
    assert "<i></i>" not in text


def test_render_gruppiert_nach_tagen():
    aenderungen = [Change("cancelled", lesson(uid=1, date=MO)),
                   Change("cancelled", lesson(uid=2, date=MI, subjects=("D",)))]
    text = bot.render(aenderungen, HEUTE)
    assert text.count("Montag") == 1 and text.count("Mittwoch") == 1


def test_render_maskiert_html_in_daten():
    """Ein Raum namens '<b>' darf die Nachricht nicht zerlegen."""
    text = bot.render([Change("room", lesson(subjects=("<b>",)), "a < b")], HEUTE)
    assert "&lt;b&gt;" in text and "a &lt; b" in text


def test_render_bulk_note():
    text = bot.render([Change("cancelled", lesson())], HEUTE,
                      bulk_note="Großflächig geändert.")
    assert "<i>Großflächig geändert.</i>" in text


def test_render_nutzt_doppelstunden_mit_raster():
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40")),
                   Change("cancelled", lesson(uid=2, start="08:30"))]
    text = bot.render(aenderungen, HEUTE, periods=RASTER)
    assert "1./2. Stunde" in text
    assert text.count("entfällt") == 1


def test_render_ohne_raster_zwei_zeilen():
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40")),
                   Change("cancelled", lesson(uid=2, start="08:30"))]
    text = bot.render(aenderungen, HEUTE)
    assert text.count("entfällt") == 2
    assert "07:40" in text and "08:30" in text


def test_render_periods_none_wie_ohne_raster():
    aenderungen = [Change("cancelled", lesson(uid=1, start="07:40")),
                   Change("cancelled", lesson(uid=2, start="08:30"))]
    assert bot.render(aenderungen, HEUTE, periods=None) == \
           bot.render(aenderungen, HEUTE)


def test_render_wechselt_ab_schwelle_zur_kurzfassung():
    viele = [Change("cancelled", lesson(uid=i, start=f"{i:02d}:00"))
             for i in range(bot.BULK_THRESHOLD)]
    text = bot.render(viele, HEUTE)
    assert "Einzelheiten stehen in WebUntis" in text


def test_render_knapp_unter_der_schwelle_listet_auf():
    viele = [Change("cancelled", lesson(uid=i, start=f"{i:02d}:00"))
             for i in range(bot.BULK_THRESHOLD - 1)]
    assert "Einzelheiten stehen in WebUntis" not in bot.render(viele, HEUTE)


def test_render_schwelle_zaehlt_zeilen_nicht_aenderungen():
    """Der haeufigste echte Fall -- Vertretung MIT Raumwechsel -- liefert
    zwei Changes pro Stunde, die zu EINER Zeile werden. An Changes gemessen
    loeste schon die halbe Stundenzahl die Kurzfassung aus."""
    viele = [c for i in range(bot.BULK_THRESHOLD - 1)
             for c in (Change("teacher", lesson(uid=i, start=f"{i:02d}:00"),
                              "Abel → Zeh"),
                       Change("room", lesson(uid=i, start=f"{i:02d}:00"),
                              "R1 → R2"))]
    assert len(viele) > bot.BULK_THRESHOLD
    text = bot.render(viele, HEUTE)
    assert "Einzelheiten stehen in WebUntis" not in text
    assert text.count("Vertretung, Raumwechsel") == bot.BULK_THRESHOLD - 1


def test_render_summary_zaehlt_nach_art():
    aenderungen = [*[Change("cancelled", lesson(uid=i, start=f"{i:02d}:00"))
                     for i in range(3)],
                   Change("room", lesson(uid=9, start="23:00"), "a → b")]
    text = bot.render_summary(aenderungen)
    assert "3× entfällt" in text and "1× Raumwechsel" in text


def test_render_summary_nennt_gesamtzahl():
    aenderungen = [Change("cancelled", lesson(uid=i, start=f"{i:02d}:00"))
                   for i in range(5)]
    assert "<b>5 Änderungen</b>" in bot.render_summary(aenderungen)


def test_render_summary_einzahl_bei_einem_tag():
    aenderungen = [Change("cancelled", lesson(uid=i, start=f"{i:02d}:00"))
                   for i in range(3)]
    assert "1 Tag:" in bot.render_summary(aenderungen)


def test_render_summary_mehrzahl_bei_mehreren_tagen():
    aenderungen = [Change("cancelled", lesson(uid=1, date=MO)),
                   Change("cancelled", lesson(uid=2, date=MI))]
    assert "2 Tagen:" in bot.render_summary(aenderungen)


def test_render_summary_nennt_spanne():
    aenderungen = [Change("cancelled", lesson(uid=1, date=MO)),
                   Change("cancelled", lesson(uid=2, date=MI))]
    text = bot.render_summary(aenderungen)
    assert "Montag, 14.09. bis Mittwoch, 16.09." in text


def test_render_summary_haelt_reihenfolge_der_arten_ein():
    aenderungen = [Change("room", lesson(uid=1, start="09:00"), "a → b"),
                   Change("cancelled", lesson(uid=2, start="10:00"))]
    text = bot.render_summary(aenderungen)
    assert text.index("entfällt") < text.index("Raumwechsel")


def test_render_summary_ohne_notiz_keine_fremdzeile():
    """Waechter gegen ein stilles Abrutschen von Argumenten: Ohne
    bulk_note darf zwischen Ueberschrift und Zaehlung nichts stehen."""
    aenderungen = [Change("cancelled", lesson(uid=1))]
    zeilen = bot.strip_html(bot.render_summary(aenderungen)).splitlines()
    assert zeilen[0] == "Stundenplan-Änderungen"
    assert zeilen[1] == ""


def test_render_summary_mit_notiz():
    aenderungen = [Change("cancelled", lesson(uid=1))]
    text = bot.render_summary(aenderungen, "Großflächig geändert.")
    assert "<i>Großflächig geändert.</i>" in text


# ===========================================================================
#  split / strip_html
# ===========================================================================

def test_split_kurzer_text_bleibt_ganz():
    assert bot.split("kurz") == ["kurz"]


def test_split_teilt_an_zeilengrenzen():
    text = "\n".join(f"Zeile {i}" for i in range(500))
    teile = bot.split(text, limit=200)
    assert len(teile) > 1
    assert all(len(t) <= 200 for t in teile)


def test_split_zerschneidet_keine_zeile_unnoetig():
    text = "\n".join(["a" * 50] * 10)
    for teil in bot.split(text, limit=120):
        for zeile in teil.split("\n"):
            assert zeile == "a" * 50


def test_split_bricht_ueberlange_einzelzeile_um():
    teile = bot.split("x" * 500, limit=100)
    assert len(teile) == 5


def ist_ausgeglichen(teil):
    """Prueft die Auszeichnung ohne bot-Hilfsmittel -- sonst pruefte der
    Test die Funktion mit sich selbst."""
    for tag in ("b", "i", "s"):
        auf, zu = teil.count(f"<{tag}>"), teil.count(f"</{tag}>")
        if auf != zu:
            return False
        if auf and teil.index(f"<{tag}>") > teil.index(f"</{tag}>"):
            return False
    return True


def test_split_zerreisst_die_auszeichnung_nicht():
    """SICHERHEITSNETZ: Ein sehr langer substText erzeugt eine Zeile
    jenseits des Limits. Hart geschnitten beginnt der Folgeteil mit
    "<i>xxx..." und endet ohne "</i>" -- Telegram lehnt ihn ab und
    _send_chunk schickt ausgerechnet DIESEN Teil als Klartext nach."""
    text = "<b>Kopf</b>\n    <i>" + "x" * 4000 + "</i>"
    teile = bot.split(text, limit=1000)
    assert len(teile) > 2
    assert all(ist_ausgeglichen(t) for t in teile)


def test_split_notfallschnitt_zerreisst_trotzdem_kein_tag():
    """Der Notfallzweig von _split_long_line greift, wenn die
    schliessenden Tags nicht mehr ins Limit passen -- konkret dann, wenn
    zwischen Schnittpunkt und Limit ein Tag zugeht: Die Ruecklage wird aus
    line[:limit] berechnet, der Stapel aber am Schnittpunkt, und der ist
    dann tiefer als die Ruecklage annimmt.

    Frueher schnitt dieser Zweig hart auf line[:limit] und zerriss dabei
    genau das, wogegen die Funktion antritt:

        ['<b>x<i>y</i', '>z</b>ww']

    Das zweite Stueck beginnt mit einem nackten ">", das Telegram als Text
    zeigt. Heute wird auch im Notfall nur an unverfaenglicher Stelle
    geschnitten. Dass das erste Stueck unausgeglichen bleibt, ist der
    Preis: Telegram lehnt es ab, _send_chunk schickt es als Klartext --
    sichtbar, aber heil. Ein zerrissenes Tag verdirbt zwei Stuecke.

    Mutationstest: in _split_long_line "hart = _cut_point(line, limit) or
    limit" durch "hart = limit" ersetzen -> dieser Test muss rot werden.
    """
    teile = bot.split("<b>x<i>y</i>z</b>ww", limit=11)
    assert teile == ["<b>x<i>y", "</i>z</b>ww"]
    for teil in teile:
        assert teil.count("<") == teil.count(">"), f"Tag zerrissen: {teil!r}"


def test_split_haelt_das_limit_auch_beim_harten_schnitt():
    text = "    <i>" + "x" * 4000 + "</i>"
    assert all(len(t) <= 500 for t in bot.split(text, limit=500))


def test_split_schneidet_nie_mitten_in_ein_tag():
    # Viele kurze Tags: Ein Schnitt auf gut Glueck landet fast sicher in
    # einem davon.
    text = "<i>x</i>" * 500
    for teil in bot.split(text, limit=101):
        assert "<" not in teil.replace("<i>", "").replace("</i>", "")
        assert ">" not in teil.replace("<i>", "").replace("</i>", "")


def test_split_schneidet_nie_mitten_in_eine_entitaet():
    """Eine halbierte Entitaet ("&am") ist genauso ungueltig wie ein
    halbiertes Tag. Das Limit ist so gewaehlt, dass der Schnitt ohne
    Absicherung MITTEN in einer Entitaet laege -- bei anderen Limits trifft
    er zufaellig eine Grenze und der Test bewiese nichts."""
    text = "<i>" + "&amp;" * 400 + "</i>"
    for teil in bot.split(text, limit=100):
        rest = teil.replace("&amp;", "").replace("<i>", "").replace("</i>", "")
        assert "&" not in rest and ";" not in rest


def test_split_behaelt_den_text_beim_harten_schnitt():
    """Nur Auszeichnung darf hinzukommen, kein Zeichen verlorengehen."""
    text = "    <i>" + "x" * 4000 + "</i>"
    zusammen = "".join(bot.split(text, limit=600))
    assert zusammen.count("x") == 4000


def test_split_ohne_auszeichnung_unveraendert():
    """Ohne Tags darf der harte Schnitt genau so arbeiten wie frueher."""
    assert bot.split("x" * 500, limit=100) == ["x" * 100] * 5


def test_split_verliert_nichts():
    text = "\n".join(f"Zeile {i}" for i in range(200))
    assert "".join(bot.split(text, limit=180)).replace("\n", "") == \
           text.replace("\n", "")


def test_split_wirft_leere_teile_weg():
    assert bot.split("\n\n\n\n", limit=2) == []


def test_split_standardgrenze_unter_telegram_limit():
    assert bot.SPLIT_AT < bot.MAX_LEN


def test_strip_html_entfernt_tags():
    assert bot.strip_html("<b>fett</b> normal") == "fett normal"


def test_strip_html_stellt_entities_her():
    assert bot.strip_html("a &lt; b") == "a < b"


def test_strip_html_behaelt_zeilenumbrueche():
    assert bot.strip_html("<b>a</b>\n<i>b</i>") == "a\nb"


# ===========================================================================
#  Telegram  (mit Attrappen, nie gegen den echten Dienst)
# ===========================================================================

class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        if self._payload is _UNLESBAR:
            raise ValueError("keine JSON-Antwort")
        return self._payload


_UNLESBAR = object()


def antworten(monkeypatch, *payloads):
    """Legt eine Folge von Antworten bereit und merkt sich die Aufrufe."""
    aufrufe = []
    folge = list(payloads)

    def fake_post(url, json=None, timeout=None):
        aufrufe.append({"url": url, "payload": json})
        return FakeResponse(folge.pop(0) if folge else {"ok": True, "result": {}})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    return aufrufe


def test_scrub_entfernt_den_token():
    text = "Max retries exceeded with url: /bot123:AAH-geheim/sendMessage"
    assert "AAH-geheim" not in bot.scrub(text, "123:AAH-geheim")


def test_scrub_setzt_platzhalter():
    assert bot.scrub("a 123:AAH b", "123:AAH") == "a <TOKEN> b"


def test_scrub_ohne_token_unveraendert():
    assert bot.scrub("nichts zu holen", "") == "nichts zu holen"


def test_scrub_laesst_uebrigen_text_stehen():
    text = "Netzwerkfehler bei sendMessage: Verbindung abgelehnt"
    assert bot.scrub(text, "123:AAH") == text


def test_telegram_call_leakt_den_token_nicht(monkeypatch):
    """SICHERHEITSNETZ: requests nennt in Netzwerkfehlern die volle URL --
    samt Token. Die Fehlermeldung wandert bis in die Job-Ausgabe.
    Mutationstest: das scrub() in telegram_call entfernen -> dieser Test
    muss rot werden."""
    geheim = "123456789:AAH-streng-geheim-xyz"

    def fake_post(url, json=None, timeout=None):
        raise bot.requests.exceptions.ConnectionError(
            f"HTTPSConnectionPool(host='api.telegram.org', port=443): "
            f"Max retries exceeded with url: /bot{geheim}/sendMessage")

    monkeypatch.setattr(bot.requests, "post", fake_post)
    with pytest.raises(TelegramError) as fehler:
        bot.telegram_call(geheim, "sendMessage", {})
    assert geheim not in str(fehler.value)
    assert "<TOKEN>" in str(fehler.value)


def test_send_leakt_den_token_nicht(monkeypatch, cfg):
    """Derselbe Schutz auf dem Weg, den eine echte Meldung nimmt."""
    geheim = cfg.telegram_token

    def fake_post(url, json=None, timeout=None):
        raise bot.requests.exceptions.ConnectionError(
            f"Max retries exceeded with url: /bot{geheim}/sendMessage")

    monkeypatch.setattr(bot.requests, "post", fake_post)
    with pytest.raises(TelegramError) as fehler:
        bot.send(cfg, "Hallo")
    assert geheim not in str(fehler.value)


def test_version_ist_gesetzt():
    assert bot.VERSION in bot.USER_AGENT


def test_telegram_call_erfolg(monkeypatch):
    antworten(monkeypatch, {"ok": True, "result": {"username": "untisbot"}})
    assert bot.telegram_call("t", "getMe", {}) == {"username": "untisbot"}


def test_telegram_call_baut_url(monkeypatch):
    aufrufe = antworten(monkeypatch, {"ok": True, "result": {}})
    bot.telegram_call("123:ABC", "sendMessage", {"a": 1})
    assert aufrufe[0]["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"


def test_telegram_call_dauerhafter_fehler_wird_nicht_wiederholt(monkeypatch):
    aufrufe = antworten(monkeypatch, {"ok": False, "error_code": 401,
                                      "description": "Unauthorized"})
    with pytest.raises(TelegramConfigError):
        bot.telegram_call("t", "getMe", {})
    assert len(aufrufe) == 1


def test_telegram_call_haengt_hinweis_an(monkeypatch):
    antworten(monkeypatch, {"ok": False, "error_code": 403, "description": "Forbidden"})
    with pytest.raises(TelegramConfigError, match="Gruppe entfernt"):
        bot.telegram_call("t", "sendMessage", {})


def test_telegram_call_wiederholt_bei_stoerung(monkeypatch):
    aufrufe = antworten(monkeypatch,
                        {"ok": False, "error_code": 503, "description": "busy"},
                        {"ok": True, "result": {"x": 1}})
    assert bot.telegram_call("t", "getMe", {}) == {"x": 1}
    assert len(aufrufe) == 2


def test_telegram_call_gibt_nach_allen_versuchen_auf(monkeypatch):
    aufrufe = antworten(monkeypatch, *([{"ok": False, "error_code": 500,
                                         "description": "boom"}] * 5))
    with pytest.raises(TelegramError):
        bot.telegram_call("t", "getMe", {})
    assert len(aufrufe) == bot.ATTEMPTS


def test_telegram_call_netzfehler_wird_wiederholt(monkeypatch):
    aufrufe = []

    def fake_post(url, json=None, timeout=None):
        aufrufe.append(url)
        if len(aufrufe) < 2:
            raise bot.requests.RequestException("Netz weg")
        return FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    bot.telegram_call("t", "getMe", {})
    assert len(aufrufe) == 2


def test_telegram_call_unlesbare_antwort(monkeypatch):
    antworten(monkeypatch, *([_UNLESBAR] * 5))
    with pytest.raises(TelegramError, match="Unlesbar"):
        bot.telegram_call("t", "getMe", {})


def test_backoff_deckelt_retry_after(monkeypatch):
    """Telegram nennt bei Flood-Control dreistellige Sekundenwerte -- die
    wuerden den 5-Minuten-Takt sprengen."""
    gewartet = []
    monkeypatch.setattr(bot.time, "sleep", lambda s: gewartet.append(s))
    bot._backoff(1, "sendMessage", "flood", override=900)
    assert gewartet == [30.0]


def test_backoff_nimmt_retry_after_wenn_klein(monkeypatch):
    gewartet = []
    monkeypatch.setattr(bot.time, "sleep", lambda s: gewartet.append(s))
    bot._backoff(1, "sendMessage", "flood", override=5)
    assert gewartet == [5.0]


def test_backoff_bei_muellwert(monkeypatch):
    gewartet = []
    monkeypatch.setattr(bot.time, "sleep", lambda s: gewartet.append(s))
    bot._backoff(2, "sendMessage", "flood", override="viel")
    assert gewartet == [2]


def test_backoff_wartet_nach_letztem_versuch_nicht(monkeypatch):
    gewartet = []
    monkeypatch.setattr(bot.time, "sleep", lambda s: gewartet.append(s))
    bot._backoff(bot.ATTEMPTS, "sendMessage", "egal")
    assert gewartet == []


def test_send_an_einen_chat(cfg, monkeypatch):
    aufrufe = antworten(monkeypatch, {"ok": True, "result": {}})
    assert bot.send(cfg, "Hallo") == 1
    assert aufrufe[0]["payload"]["chat_id"] == "42"
    assert aufrufe[0]["payload"]["parse_mode"] == "HTML"


def test_send_an_mehrere_chats(cfg, monkeypatch):
    cfg = dataclasses.replace(cfg, telegram_chats=("42", "43"))
    aufrufe = antworten(monkeypatch)
    assert bot.send(cfg, "Hallo") == 2
    assert [a["payload"]["chat_id"] for a in aufrufe] == ["42", "43"]


def test_send_teilt_lange_nachricht(cfg, monkeypatch):
    aufrufe = antworten(monkeypatch)
    bot.send(cfg, "\n".join(["x" * 100] * 100))
    assert len(aufrufe) > 1


def test_send_stiller_versand(cfg, monkeypatch):
    aufrufe = antworten(monkeypatch)
    bot.send(cfg, "Hallo", silent=True)
    assert aufrufe[0]["payload"]["disable_notification"] is True


def test_send_ein_kaputter_chat_stoppt_die_anderen_nicht(cfg, monkeypatch):
    """Sonst kaeme dieselbe Meldung beim naechsten Durchlauf bei allen
    anderen erneut an."""
    cfg = dataclasses.replace(cfg, telegram_chats=("kaputt", "43"))
    aufrufe = []

    def fake_post(url, json=None, timeout=None):
        aufrufe.append(json)
        if json["chat_id"] == "kaputt":
            return FakeResponse({"ok": False, "error_code": 400,
                                 "description": "chat not found"})
        return FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    assert bot.send(cfg, "Hallo") == 1
    assert "43" in [a["chat_id"] for a in aufrufe]


def test_send_teilzustellung_gilt_als_erfolg(cfg, monkeypatch):
    """SICHERHEITSNETZ: Bricht der Versand zwischen zwei Teilen ab, ist der
    Empfaenger halb bedient. Als Fehlschlag gewertet, versuchte der naechste
    Durchlauf dieselbe Meldung erneut -- und der erste Teil kaeme ein zweites
    Mal an. Hier erreicht KEIN Chat alle Teile; send() darf trotzdem nicht
    werfen.

    Mutationstest: in send() "if complete or partial" zu "if complete"
    aendern -> dieser Test muss rot werden.
    """
    aufrufe = []

    def fake_post(url, json=None, timeout=None):
        aufrufe.append(json)
        if len(aufrufe) == 1:
            return FakeResponse({"ok": True, "result": {}})
        return FakeResponse({"ok": False, "error_code": 400,
                             "description": "chat not found"})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    text = "\n".join(["x" * 100] * 100)
    assert len(bot.split(text)) > 1, "sonst prueft der Test die Teilung nicht"

    assert bot.send(cfg, text) == 1
    assert len(aufrufe) == 2   # nach dem Fehlschlag wird nicht weitergesendet


def test_send_ohne_empfaenger(cfg):
    cfg = dataclasses.replace(cfg, telegram_chats=())
    with pytest.raises(TelegramError, match="Kein Empfaenger"):
        bot.send(cfg, "Hallo")


def test_send_alle_dauerhaft_kaputt_meldet_konfigurationsfehler(cfg, monkeypatch):
    antworten(monkeypatch, *([{"ok": False, "error_code": 401,
                               "description": "Unauthorized"}] * 5))
    with pytest.raises(TelegramConfigError):
        bot.send(cfg, "Hallo")


def test_send_gemischte_fehler_melden_den_voruebergehenden(cfg, monkeypatch):
    """Ein zufaelliger 503 daneben darf nicht als Konfigurationsfehler
    gelten und den ganzen Lauf beenden."""
    cfg = dataclasses.replace(cfg, telegram_chats=("a", "b"))

    def fake_post(url, json=None, timeout=None):
        if json["chat_id"] == "a":
            return FakeResponse({"ok": False, "error_code": 401, "description": "no"})
        return FakeResponse({"ok": False, "error_code": 503, "description": "busy"})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    with pytest.raises(TelegramError) as fehler:
        bot.send(cfg, "Hallo")
    assert not isinstance(fehler.value, TelegramConfigError)


def test_send_faellt_bei_parse_fehler_auf_klartext_zurueck(cfg, monkeypatch):
    """Eine Meldung darf nie an der Formatierung scheitern."""
    aufrufe = []

    def fake_post(url, json=None, timeout=None):
        aufrufe.append(json)
        if "parse_mode" in json:
            return FakeResponse({"ok": False, "error_code": 400,
                                 "description": "can't parse entities"})
        return FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr(bot.requests, "post", fake_post)
    assert bot.send(cfg, "<b>fett</b>") == 1
    assert aufrufe[-1]["text"] == "fett"
    assert "parse_mode" not in aufrufe[-1]


def test_send_faellt_bei_anderem_fehler_nicht_auf_klartext_zurueck(cfg, monkeypatch):
    aufrufe = antworten(monkeypatch, *([{"ok": False, "error_code": 403,
                                         "description": "Forbidden"}] * 5))
    with pytest.raises(TelegramConfigError):
        bot.send(cfg, "<b>fett</b>")
    assert len(aufrufe) == 1


# ===========================================================================
#  Zustand
# ===========================================================================

FENSTER = (dt.date(2026, 9, 14), dt.date(2026, 9, 21))


def test_parse_pending_leer():
    assert bot.parse_pending("") == ("", 0)


def test_parse_pending_normal():
    assert bot.parse_pending("abc123:3") == ("abc123", 3)


def test_parse_pending_ohne_zaehler():
    assert bot.parse_pending("abc123") == ("abc123", 1)


def test_parse_pending_kaputter_zaehler():
    assert bot.parse_pending("abc:viele") == ("abc", 1)


def test_parse_pending_none():
    assert bot.parse_pending(None) == ("", 0)


def test_confirm_or_hold_erste_sichtung_wartet():
    """Eine einzelne ungewoehnliche Lage ist noch kein Beweis."""
    bestaetigt, pending, sichtung = bot.confirm_or_hold("", "abc")
    assert bestaetigt is False
    assert pending == "abc:1"
    assert sichtung == 1


def test_confirm_or_hold_zweimal_dieselbe_lage_bestaetigt():
    bestaetigt, pending, sichtung = bot.confirm_or_hold("abc:1", "abc")
    assert bestaetigt is True
    assert pending == "abc:2" and sichtung == 2


def test_confirm_or_hold_andere_lage_wartet_weiter():
    """Schwankende Daten bestaetigen sich nicht gegenseitig ..."""
    bestaetigt, pending, _ = bot.confirm_or_hold("abc:1", "xyz")
    assert bestaetigt is False
    assert pending == "xyz:2"


def test_confirm_or_hold_zaehler_laeuft_trotz_wechsel_weiter():
    """... aber der Zaehler laeuft weiter, sonst bliebe der Bot bei
    schwankenden Teilantworten unbegrenzt still."""
    _b, pending, sichtung = bot.confirm_or_hold("abc:4", "xyz")
    assert sichtung == 5 and pending == "xyz:5"


def test_confirm_or_hold_gibt_nach_pending_limit_auf():
    bestaetigt, _p, sichtung = bot.confirm_or_hold(f"abc:{bot.PENDING_LIMIT - 1}",
                                                   "voellig-andere-lage")
    assert bestaetigt is True and sichtung == bot.PENDING_LIMIT


def test_confirm_or_hold_kaputter_eintrag_kippt_nicht():
    bestaetigt, pending, _s = bot.confirm_or_hold("voellig:kaputt", "abc")
    assert bestaetigt is False and pending.startswith("abc:")


def test_fingerprint_ist_stabil():
    stunden = [lesson(uid=1), lesson(uid=2, start="08:30")]
    assert bot.fingerprint(stunden) == bot.fingerprint(list(reversed(stunden)))


def test_fingerprint_aendert_sich_bei_ausfall():
    assert bot.fingerprint([lesson()]) != bot.fingerprint([lesson(status=CANCELLED)])


def test_fingerprint_aendert_sich_bei_raumwechsel():
    assert bot.fingerprint([lesson(rooms=("R1",))]) != \
           bot.fingerprint([lesson(rooms=("R2",))])


def test_fingerprint_leer_ist_definiert():
    assert isinstance(bot.fingerprint([]), str)


def test_load_state_ohne_datei(tmp_path):
    zustand = bot.load_state(tmp_path / "gibtsnicht.json")
    assert zustand.exists is False and zustand.lessons == ()


def test_speichern_und_laden(tmp_path):
    pfad = tmp_path / "state.json"
    stunden = [lesson(uid=1, rooms=("R1",)), lesson(uid=2, start="08:30")]
    assert bot.save_state(stunden, FENSTER, pfad) is True
    zustand = bot.load_state(pfad)
    assert zustand.exists is True
    assert list(zustand.lessons) == stunden
    assert zustand.window == FENSTER


def test_save_state_schreibt_unveraenderten_zustand_nicht_neu(tmp_path):
    """SICHERHEITSNETZ: Jeder Schreibvorgang wird auf GitHub zu einem
    Commit. Im 5-Minuten-Takt waeren das hunderte pro Tag."""
    pfad = tmp_path / "state.json"
    stunden = [lesson()]
    assert bot.save_state(stunden, FENSTER, pfad) is True
    assert bot.save_state(stunden, FENSTER, pfad) is False


def test_save_state_schreibt_bei_geaendertem_fenster(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson()], FENSTER, pfad)
    anderes = (dt.date(2026, 9, 15), dt.date(2026, 9, 22))
    assert bot.save_state([lesson()], anderes, pfad) is True


def test_save_state_schreibt_bei_geaendertem_pending(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson()], FENSTER, pfad)
    assert bot.save_state([lesson()], FENSTER, pfad, pending="abc:1") is True


def test_save_state_erkennt_gleichheit_trotz_tupel_vs_liste(tmp_path):
    """asdict() liefert Tupel, aus der Datei kommen Listen -- ohne
    Normalisierung gaelte jeder Zustand als veraendert."""
    pfad = tmp_path / "state.json"
    bot.save_state([lesson(rooms=("R1", "R2"))], FENSTER, pfad)
    assert bot.save_state([lesson(rooms=("R2", "R1"))], FENSTER, pfad) is False


def test_save_state_ist_gueltiges_json(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson()], FENSTER, pfad)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    assert daten["schema"] == bot.SCHEMA
    assert daten["window"] == {"from": "2026-09-14", "to": "2026-09-21"}


def test_save_state_laesst_keine_temporaeren_dateien_zurueck(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson()], FENSTER, pfad)
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_load_state_verwirft_altes_schema(tmp_path):
    """Das gueltige Fenster gehoert ins Fixture: Ohne es greift der
    Fenster-Guard, und der Test wuerde auch ohne jede Schema-Pruefung gruen.

    Mutationstest: "if raw.get("schema") != SCHEMA" zu "if False" machen ->
    dieser Test muss rot werden.
    """
    pfad = tmp_path / "state.json"
    pfad.write_text(json.dumps({"schema": 1, "lessons": [],
                                "window": {"from": "2026-09-14",
                                           "to": "2026-09-21"}}),
                    encoding="utf-8")
    assert bot.load_state(pfad).exists is False


def test_load_state_kaputte_datei_wird_beiseitegelegt(tmp_path):
    """state.json liegt im Repo -- ein ungefangener Fehler wuerde JEDEN
    weiteren Lauf toeten."""
    pfad = tmp_path / "state.json"
    pfad.write_text("{kein json", encoding="utf-8")
    assert bot.load_state(pfad).exists is False
    assert (tmp_path / "state.broken").exists()


def test_load_state_falsche_huelle_wird_beiseitegelegt(tmp_path):
    pfad = tmp_path / "state.json"
    pfad.write_text(json.dumps(["eine", "liste"]), encoding="utf-8")
    assert bot.load_state(pfad).exists is False
    assert (tmp_path / "state.broken").exists()


def test_load_state_lessons_kein_array(tmp_path):
    pfad = tmp_path / "state.json"
    pfad.write_text(json.dumps({"schema": bot.SCHEMA, "lessons": "kaputt"}),
                    encoding="utf-8")
    assert bot.load_state(pfad).exists is False


def test_load_state_ohne_fenster_wie_erstlauf(tmp_path):
    """Ohne lesbares Fenster saehe es aus wie 'Fenster komplett verschoben'
    und wuerde anstehende Aenderungen stillschweigend verwerfen."""
    pfad = tmp_path / "state.json"
    pfad.write_text(json.dumps({"schema": bot.SCHEMA, "lessons": []}), encoding="utf-8")
    assert bot.load_state(pfad).exists is False


def test_load_state_kaputtes_fenster_wie_erstlauf(tmp_path):
    pfad = tmp_path / "state.json"
    pfad.write_text(json.dumps({"schema": bot.SCHEMA, "lessons": [],
                                "window": {"from": "gestern", "to": "morgen"}}),
                    encoding="utf-8")
    assert bot.load_state(pfad).exists is False


def test_load_state_ueberspringt_einzelne_kaputte_stunden(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson(uid=1), lesson(uid=2, start="08:30")], FENSTER, pfad)
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten["lessons"].append({"kein": "gueltiger eintrag"})
    pfad.write_text(json.dumps(daten), encoding="utf-8")
    assert len(bot.load_state(pfad).lessons) == 2


def test_load_state_keine_einzige_stunde_lesbar_wie_erstlauf(tmp_path):
    pfad = tmp_path / "state.json"
    pfad.write_text(json.dumps({"schema": bot.SCHEMA,
                                "window": {"from": "2026-09-14", "to": "2026-09-21"},
                                "lessons": [{"muell": 1}, {"muell": 2}]}),
                    encoding="utf-8")
    assert bot.load_state(pfad).exists is False


def test_load_state_leerer_plan_bleibt_gueltig(tmp_path):
    """Leer ist nicht kaputt -- ein leerer Ferienplan ist ein echter Stand."""
    pfad = tmp_path / "state.json"
    bot.save_state([], FENSTER, pfad)
    assert bot.load_state(pfad).exists is True


def test_load_state_liest_pending(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson()], FENSTER, pfad, pending="abc:2")
    assert bot.load_state(pfad).pending == "abc:2"


def test_state_ist_unveraenderlich():
    with pytest.raises(dataclasses.FrozenInstanceError):
        State(exists=True).exists = False


# ===========================================================================
#  Ablauf: check_once
# ===========================================================================

class FakeUntis:
    """Ersetzt die ganze WebUntis-Randschicht."""

    def __init__(self, lessons=(), periods=None, fehler=None, timegrid_fehler=False):
        self.lessons = list(lessons)
        self.periods = periods or {}
        self.fehler = fehler
        self.timegrid_fehler = timegrid_fehler

    def __call__(self, _cfg):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def timetable(self, _start, _end):
        if self.fehler:
            raise self.fehler
        return self.lessons

    def timegrid(self):
        # Wie das Original: faengt eigene Fehler ab und liefert {}.
        return {} if self.timegrid_fehler else self.periods


@pytest.fixture
def ablauf(monkeypatch, tmp_path):
    """Verkabelt check_once mit Attrappen und protokolliert, was passiert."""
    protokoll = {"gesendet": [], "committed": 0}

    monkeypatch.setattr(bot, "send",
                        lambda _cfg, text, **_k: protokoll["gesendet"].append(text))
    def fake_commit(*_a, **_k):
        protokoll["committed"] += 1
        return True

    monkeypatch.setattr(bot, "commit_state", fake_commit)
    # Die Uhr liegt im Protokoll statt in der Lambda, damit ein Test sie
    # weiterstellen kann. Erst dann rollt das Abruffenster wie im Betrieb --
    # ohne das gilt in jedem Test overlap(win, previous.window) == win, und
    # die ganze Fensterverdrahtung bleibt ungeprueft.
    protokoll["jetzt"] = dt.datetime(2026, 9, 14, 8, 0)
    monkeypatch.setattr(bot, "now_local", lambda _tz: protokoll["jetzt"])
    protokoll["pfad"] = tmp_path / "state.json"
    protokoll["monkeypatch"] = monkeypatch
    return protokoll


def untis_liefert(ablauf, lessons=(), periods=None, fehler=None):
    ablauf["monkeypatch"].setattr(bot, "Untis", FakeUntis(lessons, periods, fehler))


def am_tag(ablauf, jahr, monat, tag):
    """Stellt die Uhr des Ablaufs auf 8 Uhr des genannten Tages."""
    ablauf["jetzt"] = dt.datetime(jahr, monat, tag, 8, 0)


def test_check_erstlauf_sendet_nichts(cfg, ablauf):
    untis_liefert(ablauf, [lesson(uid=1)])
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.status == bot.OK
    assert ablauf["gesendet"] == []
    assert "Erster Lauf" in ergebnis.message


def test_check_erstlauf_merkt_sich_den_stand(cfg, ablauf):
    untis_liefert(ablauf, [lesson(uid=1)])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    assert bot.load_state(ablauf["pfad"]).exists is True


def test_check_ohne_aenderungen_sendet_nichts(cfg, ablauf):
    untis_liefert(ablauf, [lesson(uid=1)])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ablauf["gesendet"] == []
    assert "Keine Aenderungen" in ergebnis.message


def test_check_meldet_aenderung(cfg, ablauf):
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R1",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R2",))])
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.changes == 1
    assert len(ablauf["gesendet"]) == 1
    assert "Raumwechsel" in ablauf["gesendet"][0]


def test_check_meldet_dieselbe_aenderung_nie_zweimal(cfg, ablauf):
    """SICHERHEITSNETZ: Nach dem Versand wird der neue Stand gespeichert.
    Mutationstest: das save_state() nach send() in check_once entfernen ->
    dieser Test muss rot werden."""
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R1",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R2",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    assert len(ablauf["gesendet"]) == 1


def test_check_speichert_erst_nach_erfolgreichem_versand(cfg, ablauf):
    """Geht der Versand schief, muss die Aenderung beim naechsten Durchlauf
    erneut versucht werden statt verloren zu sein."""
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R1",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])

    def versand_faellt_aus(*_a, **_k):
        raise TelegramError("Netz weg")

    ablauf["monkeypatch"].setattr(bot, "send", versand_faellt_aus)
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R2",))])
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.status == bot.FAILED

    # Zweiter Anlauf, diesmal klappt es -- die Meldung ist nicht verloren.
    ablauf["monkeypatch"].setattr(
        bot, "send", lambda _cfg, text, **_k: ablauf["gesendet"].append(text))
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.changes == 1


def test_check_dauerhafter_telegram_fehler_ist_fatal(cfg, ablauf):
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R1",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])

    def abgelehnt(*_a, **_k):
        raise TelegramConfigError("Token falsch")

    ablauf["monkeypatch"].setattr(bot, "send", abgelehnt)
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R2",))])
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.status == bot.FAILED and ergebnis.fatal is True


def test_check_nutzt_das_stundenraster_fuer_doppelstunden(cfg, ablauf):
    alt = [lesson(uid=1, start="07:40", end="08:25", rooms=("R1",)),
           lesson(uid=2, start="08:30", end="09:15", rooms=("R1",))]
    neu = [dataclasses.replace(stunde, rooms=("R2",)) for stunde in alt]
    untis_liefert(ablauf, alt, periods=RASTER)
    bot.check_once(cfg, state_path=ablauf["pfad"])
    untis_liefert(ablauf, neu, periods=RASTER)
    bot.check_once(cfg, state_path=ablauf["pfad"])
    assert "1./2. Stunde" in ablauf["gesendet"][0]


def test_check_ohne_raster_zwei_zeilen(cfg, ablauf):
    alt = [lesson(uid=1, start="07:40", rooms=("R1",)),
           lesson(uid=2, start="08:30", rooms=("R1",))]
    neu = [dataclasses.replace(stunde, rooms=("R2",)) for stunde in alt]
    untis_liefert(ablauf, alt)
    bot.check_once(cfg, state_path=ablauf["pfad"])
    untis_liefert(ablauf, neu)
    bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ablauf["gesendet"][0].count("Raumwechsel") == 2


def test_check_dry_run_sendet_und_speichert_nichts(cfg, ablauf):
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R1",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R2",))])
    ergebnis = bot.check_once(cfg, dry_run=True, state_path=ablauf["pfad"])
    assert ablauf["gesendet"] == []
    assert "Raumwechsel" in ergebnis.message
    # Der gespeicherte Stand ist unveraendert -- der naechste echte Lauf
    # meldet die Aenderung noch.
    assert bot.load_state(ablauf["pfad"]).lessons[0].rooms == ("R1",)


def test_check_ferien_ist_kein_fehler(cfg, ablauf):
    untis_liefert(ablauf, fehler=bot.NothingToDo("Ferien"))
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.status == bot.IDLE and ablauf["gesendet"] == []


def test_check_authfehler_ist_fatal(cfg, ablauf):
    untis_liefert(ablauf, fehler=bot.AuthError("Passwort falsch"))
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.status == bot.FAILED and ergebnis.fatal is True


def test_check_untisfehler_ist_nicht_fatal(cfg, ablauf):
    untis_liefert(ablauf, fehler=bot.UntisError("Server weg"))
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.status == bot.FAILED and ergebnis.fatal is False


def test_check_unplausible_lage_wird_erst_gemerkt(cfg, ablauf):
    viele = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    untis_liefert(ablauf, viele)
    bot.check_once(cfg, state_path=ablauf["pfad"])

    untis_liefert(ablauf, viele[:1])
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ergebnis.status == bot.IDLE
    assert ablauf["gesendet"] == []
    assert bot.load_state(ablauf["pfad"]).pending != ""


def test_check_unplausible_lage_wird_beim_zweiten_mal_bestaetigt(cfg, ablauf):
    viele = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    untis_liefert(ablauf, viele)
    bot.check_once(cfg, state_path=ablauf["pfad"])

    untis_liefert(ablauf, viele[:1])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    assert len(ablauf["gesendet"]) == 1
    assert "großflächig" in ablauf["gesendet"][0]


def test_check_schwankende_lage_wird_nach_pending_limit_akzeptiert(cfg, ablauf):
    """Sonst koennte der Bot bei schwankenden Teilantworten unbegrenzt
    still bleiben, ohne dass es jemand bemerkt."""
    viele = [lesson(uid=i, start=f"{7+i:02d}:40") for i in range(10)]
    untis_liefert(ablauf, viele)
    bot.check_once(cfg, state_path=ablauf["pfad"])

    for runde in range(bot.PENDING_LIMIT):
        # Jedes Mal eine andere Teilmenge -- der Fingerabdruck wechselt.
        untis_liefert(ablauf, [*viele[:1], lesson(uid=90 + runde, start="20:00")])
        bot.check_once(cfg, state_path=ablauf["pfad"])

    assert len(ablauf["gesendet"]) == 1


def test_check_fenster_komplett_verschoben(cfg, ablauf):
    """Muss VOR der Plausibilitaetspruefung greifen, sonst zaehlt die alle
    gespeicherten Stunden als verschwunden."""
    pfad = ablauf["pfad"]
    bot.save_state([lesson(uid=1, date="2025-01-10")],
                   (dt.date(2025, 1, 6), dt.date(2025, 1, 13)), pfad)
    untis_liefert(ablauf, [lesson(uid=2, date=MO)])
    ergebnis = bot.check_once(cfg, state_path=pfad)
    assert ergebnis.status == bot.OK
    assert "neu grundiert" in ergebnis.message
    assert ablauf["gesendet"] == []


def test_check_meldet_neu_ins_fenster_gerollte_stunden_nicht(cfg, ablauf):
    """Das Abruffenster rollt taeglich weiter. Was heute neu hineinrutscht,
    war gestern nicht im Blick -- diese Stunden sind nicht "hinzugekommen",
    sie wurden nur noch nie betrachtet. Bricht die Verdrahtung, meldet der
    Bot jeden Morgen einen kompletten Schultag als "➕ neuer Termin".

    Gespeichertes Fenster 07.-14.09., heute der 14.09., neues Fenster
    14.-21.09. -- die Ueberlappung ist genau ein Tag.

    Mutationstest: in check_once diff(..., compare_win) zu diff(..., win)
    -> dieser Test muss rot werden.
    """
    am_tag(ablauf, 2026, 9, 7)
    untis_liefert(ablauf, [lesson(uid=1, date="2026-09-07"),
                           lesson(uid=2, date="2026-09-14")])
    bot.check_once(cfg, state_path=ablauf["pfad"])

    am_tag(ablauf, 2026, 9, 14)
    untis_liefert(ablauf, [lesson(uid=2, date="2026-09-14"),
                           lesson(uid=3, date="2026-09-21")])
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])

    assert ablauf["gesendet"] == []
    assert "Keine Aenderungen" in ergebnis.message


def test_check_plausibilitaet_misst_nur_die_ueberlappung(cfg, ablauf):
    """Der zweite Fehlermodus derselben Verdrahtung: Zaehlt die Bremse auch
    die aus dem Fenster gerollten Stunden als verschwunden, schlaegt sie
    jeden Tag an -- und der Bot meldet dauerhaft nichts mehr.

    Mutationstest: in check_once check_plausible(..., compare_win) zu
    check_plausible(..., None) -> dieser Test muss rot werden.
    """
    alte_woche = [lesson(uid=i + 1, date=f"2026-09-{i + 7:02d}") for i in range(8)]
    am_tag(ablauf, 2026, 9, 7)
    untis_liefert(ablauf, alte_woche)
    bot.check_once(cfg, state_path=ablauf["pfad"])

    # Der 14.09. ist der einzige Tag, den beide Fenster abdecken -- und er
    # steht unveraendert in beiden Abrufen.
    neue_woche = [alte_woche[-1],
                  *[lesson(uid=20 + i, date=f"2026-09-{i + 15:02d}")
                    for i in range(7)]]
    am_tag(ablauf, 2026, 9, 14)
    untis_liefert(ablauf, neue_woche)
    ergebnis = bot.check_once(cfg, state_path=ablauf["pfad"])

    assert ergebnis.status == bot.OK
    assert "Keine Aenderungen" in ergebnis.message


def test_check_sichert_zustand_nach_jedem_lauf(cfg, ablauf):
    untis_liefert(ablauf, [lesson(uid=1)])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    assert ablauf["committed"] == 2


def test_check_sichert_zustand_auch_nach_dem_melden(cfg, ablauf):
    """SICHERHEITSNETZ: Der Melde-Pfad ist der, an dem die Zusicherung "nie
    dieselbe Aenderung zweimal melden" haengt -- und der einzige, in dem
    Speichern allein nicht genuegt. Ohne Push holt der naechste
    Actions-Job einen Checkout mit der ALTEN state.json und meldet dieselbe
    Aenderung erneut. Der Test daneben deckt nur Erstlauf und "keine
    Aenderungen" ab.

    Mutationstest: das commit_state() NACH send() in check_once entfernen
    -> dieser Test muss rot werden.
    """
    untis_liefert(ablauf, [lesson(uid=1, rooms=("R1",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])
    vorher = ablauf["committed"]

    untis_liefert(ablauf, [lesson(uid=1, rooms=("R2",))])
    bot.check_once(cfg, state_path=ablauf["pfad"])

    assert len(ablauf["gesendet"]) == 1
    assert ablauf["committed"] == vorher + 1


# ===========================================================================
#  Zustand sichern (git)
# ===========================================================================

def test_commit_state_wirft_nie(monkeypatch, tmp_path):
    """SICHERHEITSNETZ: Ein git-Problem darf niemals einen Lauf beenden, in
    dem die Nachricht bereits raus ist. Mutationstest: das try/except in
    commit_state entfernen -> dieser Test muss rot werden."""
    def explodiert(_path):
        raise RuntimeError("git ist kaputt")

    monkeypatch.setattr(bot, "_commit_state", explodiert)
    assert bot.commit_state(tmp_path / "state.json") is False


def test_commit_state_ohne_git_verzeichnis(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
    assert bot.commit_state(tmp_path / "state.json") is False


def test_commit_state_reicht_erfolg_durch(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "_commit_state", lambda _p: True)
    assert bot.commit_state(tmp_path / "state.json") is True


class FakeGit:
    """Protokolliert git-Aufrufe und antwortet nach Drehbuch."""

    def __init__(self, drehbuch=None):
        self.aufrufe = []
        self.drehbuch = drehbuch or {}

    def __call__(self, *args):
        self.aufrufe.append(args)
        rc, out = self.drehbuch.get(args[0], (0, ""))
        if callable(out):
            out = out(self.aufrufe)
        return bot.subprocess.CompletedProcess(args, rc, stdout=out, stderr="")

    def hat(self, befehl):
        return [a for a in self.aufrufe if a[0] == befehl]


@pytest.fixture
def git_repo(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(bot, "BASE_DIR", tmp_path)
    pfad = tmp_path / "state.json"
    pfad.write_text("{}", encoding="utf-8")
    return pfad


def test_commit_state_committet_und_pusht(monkeypatch, git_repo):
    fake = FakeGit({"diff": (1, ""), "log": (0, "abc Aenderung")})
    monkeypatch.setattr(bot, "git", fake)
    assert bot._commit_state(git_repo) is True
    assert fake.hat("commit") and fake.hat("push")


def test_commit_state_nutzt_add_f(monkeypatch, git_repo):
    """state.json steht bewusst nicht unter normaler Versionierung --
    in der Cloud ist das Mitcommitten aber genau der Sinn."""
    fake = FakeGit({"diff": (1, ""), "log": (0, "abc")})
    monkeypatch.setattr(bot, "git", fake)
    bot._commit_state(git_repo)
    assert fake.hat("add")[0] == ("add", "-f", str(git_repo))


def test_commit_state_committet_den_uebergebenen_pfad(monkeypatch, git_repo):
    """git laeuft mit cwd=BASE_DIR. Ein blosser Dateiname bezoege sich
    deshalb immer auf BASE_DIR/state.json -- auch wenn geprueft wurde, ob
    eine ganz andere Datei existiert."""
    anderer = git_repo.parent / "anderswo.json"
    anderer.write_text("{}", encoding="utf-8")
    fake = FakeGit({"diff": (1, ""), "log": (0, "abc")})
    monkeypatch.setattr(bot, "git", fake)
    bot._commit_state(anderer)
    assert fake.hat("add")[0] == ("add", "-f", str(anderer))


def test_commit_state_ohne_aenderung_kein_commit(monkeypatch, git_repo):
    fake = FakeGit({"diff": (0, ""), "log": (0, "")})
    monkeypatch.setattr(bot, "git", fake)
    assert bot._commit_state(git_repo) is False
    assert not fake.hat("commit")


def test_commit_state_holt_frueher_gescheiterten_push_nach(monkeypatch, git_repo):
    """Sonst kaeme eine bereits gesendete Meldung beim naechsten Job ein
    zweites Mal."""
    fake = FakeGit({"diff": (0, ""), "log": (0, "abc alter Commit")})
    monkeypatch.setattr(bot, "git", fake)
    assert bot._commit_state(git_repo) is True
    assert not fake.hat("commit") and fake.hat("push")


def test_commit_state_zieht_bei_push_fehler_nach(monkeypatch, git_repo):
    versuche = []

    def fake(*args):
        if args[0] == "push":
            versuche.append(1)
            rc = 1 if len(versuche) == 1 else 0
            return bot.subprocess.CompletedProcess(args, rc, stdout="", stderr="")
        if args[0] == "diff":
            return bot.subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        if args[0] == "log":
            return bot.subprocess.CompletedProcess(args, 0, stdout="abc", stderr="")
        return bot.subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(bot, "git", fake)
    assert bot._commit_state(git_repo) is True
    assert len(versuche) == 2


def test_commit_state_bricht_steckengebliebenen_rebase_ab(monkeypatch, git_repo):
    """Sonst schlaegt jeder weitere Lauf fehl und state.json enthaelt
    Konfliktmarker."""
    fake = FakeGit({"diff": (1, ""), "log": (0, "abc"), "push": (1, ""),
                    "pull": (1, "")})
    monkeypatch.setattr(bot, "git", fake)
    assert bot._commit_state(git_repo) is False
    assert fake.hat("rebase") and fake.hat("merge")


# ===========================================================================
#  Ablauf: watch
# ===========================================================================

class Uhr:
    """Stellbare Uhr -- die Tests duerfen keine echte Zeit verbrauchen."""

    def __init__(self):
        self.jetzt = 0.0

    def __call__(self):
        return self.jetzt

    def schlafe(self, sekunden):
        self.jetzt += sekunden


def watch_mit(monkeypatch, cfg, ergebnisse, minutes=55, interval=300):
    uhr = Uhr()
    folge = list(ergebnisse)
    laeufe = []

    def fake_check(_cfg):
        laeufe.append(1)
        ergebnis = folge.pop(0) if folge else bot.Result(bot.OK)
        uhr.jetzt += 3   # ein Durchlauf dauert rund drei Sekunden
        return ergebnis

    monkeypatch.setattr(bot, "check_once", fake_check)
    code = bot.watch(cfg, minutes, interval, sleeper=uhr.schlafe, clock=uhr)
    return code, len(laeufe)


@pytest.mark.parametrize("wochentag,stunde,schulzeit", [
    (0, 6, True), (0, 12, True), (0, 18, True),      # Montag, Schulzeit
    (0, 5, False), (0, 19, False), (0, 23, False),   # Montag, Randzeiten
    (4, 8, True),                                     # Freitag
    (5, 8, False), (6, 8, False),                     # Samstag, Sonntag
])
def test_is_school_time(wochentag, stunde, schulzeit):
    # 2026-09-14 ist ein Montag, also Wochentag 0.
    tag = dt.date(2026, 9, 14) + dt.timedelta(days=wochentag)
    jetzt = dt.datetime.combine(tag, dt.time(stunde, 0))
    assert bot.is_school_time(jetzt) is schulzeit


def test_interval_for_in_der_schulzeit():
    montag_mittag = dt.datetime(2026, 9, 14, 12, 0)
    assert bot.interval_for(montag_mittag, busy=300, idle=1800) == 300


def test_interval_for_nachts():
    montag_nachts = dt.datetime(2026, 9, 15, 3, 0)
    assert bot.interval_for(montag_nachts, busy=300, idle=1800) == 1800


def test_interval_for_am_wochenende():
    samstag_mittag = dt.datetime(2026, 9, 19, 12, 0)
    assert bot.interval_for(samstag_mittag, busy=300, idle=1800) == 1800


def test_watch_ohne_night_interval_taktet_konstant(cfg, monkeypatch):
    """Rueckwaertskompatibel: ohne den Wert aendert sich nichts."""
    uhr = Uhr()
    gewartet = []
    monkeypatch.setattr(bot, "check_once", lambda _c: bot.Result(bot.OK))

    def schlafe(s):
        gewartet.append(s)
        uhr.jetzt += s

    bot.watch(cfg, 30, 300, sleeper=schlafe, clock=uhr)
    assert gewartet and all(w == 300 for w in gewartet)


def test_watch_nutzt_kurzen_takt_in_der_schulzeit(cfg, monkeypatch):
    uhr = Uhr()
    gewartet = []
    monkeypatch.setattr(bot, "check_once", lambda _c: bot.Result(bot.OK))
    monkeypatch.setattr(bot, "now_local",
                        lambda _tz: dt.datetime(2026, 9, 14, 10, 0))

    def schlafe(s):
        gewartet.append(s)
        uhr.jetzt += s

    bot.watch(cfg, 30, 300, 1800, sleeper=schlafe, clock=uhr)
    assert gewartet and all(w == 300 for w in gewartet)


def test_watch_nutzt_langen_takt_nachts(cfg, monkeypatch):
    """Nachts jede Stunde zwoelfmal anzumelden waere sinnlose Last."""
    uhr = Uhr()
    gewartet = []
    monkeypatch.setattr(bot, "check_once", lambda _c: bot.Result(bot.OK))
    monkeypatch.setattr(bot, "now_local",
                        lambda _tz: dt.datetime(2026, 9, 15, 3, 0))

    def schlafe(s):
        gewartet.append(s)
        uhr.jetzt += s

    bot.watch(cfg, 120, 300, 1800, sleeper=schlafe, clock=uhr)
    assert gewartet and all(w == 1800 for w in gewartet)


def test_watch_zaehlt_im_nachttakt_weniger_durchlaeufe(cfg, monkeypatch):
    """Derselbe Zeitraum, ein Sechstel der Anmeldungen."""
    def laeufe(jetzt):
        uhr = Uhr()
        zaehler = []
        monkeypatch.setattr(bot, "check_once",
                            lambda _c: zaehler.append(1) or bot.Result(bot.OK))
        monkeypatch.setattr(bot, "now_local", lambda _tz: jetzt)
        bot.watch(cfg, 180, 300, 1800, sleeper=uhr.schlafe, clock=uhr)
        return len(zaehler)

    # 180 Minuten = 10800 s. Geprueft wird vor dem ersten Warten, deshalb
    # jeweils ein Durchlauf mehr als 10800/Takt.
    schulzeit = laeufe(dt.datetime(2026, 9, 14, 10, 0))
    nachts = laeufe(dt.datetime(2026, 9, 15, 3, 0))
    assert (schulzeit, nachts) == (37, 7)


def test_watch_wechselt_den_takt_mitten_im_lauf(cfg, monkeypatch):
    """Ein Lauf dauert 5,5 Stunden und ueberspannt damit die Grenze
    zwischen Schul- und Nachtzeit. Der Takt muss mitwandern, nicht beim
    Wert vom Start kleben bleiben."""
    uhr = Uhr()
    gewartet = []
    # Wanduhr laeuft mit der Testuhr mit, Start 18:30 Uhr an einem Montag.
    start = dt.datetime(2026, 9, 14, 18, 30)
    monkeypatch.setattr(bot, "check_once", lambda _c: bot.Result(bot.OK))
    monkeypatch.setattr(bot, "now_local",
                        lambda _tz: start + dt.timedelta(seconds=uhr.jetzt))

    def schlafe(s):
        gewartet.append(s)
        uhr.jetzt += s

    bot.watch(cfg, 120, 300, 1800, sleeper=schlafe, clock=uhr)

    # Bis 19:00 Uhr der kurze Takt, danach der lange.
    assert gewartet[0] == 300
    assert gewartet[-1] == 1800
    assert set(gewartet) == {300, 1800}


def test_watch_taktet_selbst(cfg, monkeypatch):
    """Der Grund fuer die Schleife: GitHubs Zeitplaner haelt 5 Minuten nicht
    ein. 55 Minuten / 5 Minuten ergeben elf Durchlaeufe."""
    code, laeufe = watch_mit(monkeypatch, cfg, [])
    assert code == 0 and laeufe == 11


def test_watch_kurzer_lauf(cfg, monkeypatch):
    code, laeufe = watch_mit(monkeypatch, cfg, [], minutes=10)
    assert code == 0 and laeufe == 2


def test_watch_mindestens_ein_durchlauf(cfg, monkeypatch):
    code, laeufe = watch_mit(monkeypatch, cfg, [], minutes=0)
    assert code == 0 and laeufe == 1


def test_watch_bricht_bei_fatalem_fehler_ab(cfg, monkeypatch):
    code, laeufe = watch_mit(monkeypatch, cfg,
                             [bot.Result(bot.FAILED, message="Token weg", fatal=True)])
    assert code == 1 and laeufe == 1


def test_failure_interval_ohne_fehler_unveraendert():
    assert bot.failure_interval(300, 0) == 300


def test_failure_interval_verdoppelt_je_fehlschlag():
    assert [bot.failure_interval(300, f) for f in (1, 2)] == [600, 900]


def test_failure_interval_ist_gedeckelt():
    assert bot.failure_interval(300, 20) == bot.FAILURE_INTERVAL_MAX


def test_failure_interval_wird_nie_kuerzer_als_der_takt():
    """Sonst beschleunigte ein von Hand gesetztes langes --interval
    ausgerechnet dann, wenn es klemmt."""
    assert bot.failure_interval(1800, 3) == 1800


def test_watch_haelt_drei_fehlschlaege_aus(cfg, monkeypatch):
    """Frueher war hier Schluss. Drei Stoerungen kosteten den ganzen Platz
    in der Laufkette -- und den holt erst die naechste tatsaechliche
    Cron-Ausloesung zurueck."""
    folge = [bot.Result(bot.FAILED, message="weg")] * 3 + [bot.Result(bot.OK)]
    code, laeufe = watch_mit(monkeypatch, cfg, folge, minutes=120)
    assert code == 0 and laeufe > 3


def test_watch_bricht_nach_failure_limit_ab(cfg, monkeypatch):
    """SICHERHEITSNETZ: Bei einem Dauerausfall muss watch mit Exit 1 enden
    -- daran haengt der Schritt "Stoerung melden" (if: failure()) im
    Workflow. Ohne ihn bliebe ein kaputter Bot voellig stumm."""
    fehler = [bot.Result(bot.FAILED, message="weg")] * bot.FAILURE_LIMIT
    code, laeufe = watch_mit(monkeypatch, cfg, fehler, minutes=120)
    assert code == 1 and laeufe == bot.FAILURE_LIMIT


def test_watch_streckt_den_takt_nach_fehlschlaegen(cfg, monkeypatch):
    uhr = Uhr()
    gewartet = []

    def fake_check(_cfg):
        uhr.jetzt += 3
        return bot.Result(bot.FAILED, message="weg")

    def schlafe(sekunden):
        gewartet.append(sekunden)
        uhr.jetzt += sekunden

    monkeypatch.setattr(bot, "check_once", fake_check)
    bot.watch(cfg, 120, 300, sleeper=schlafe, clock=uhr)
    assert [round(s) for s in gewartet[:2]] == [597, 897]


def test_watch_einzelne_fehler_sind_kein_abbruch(cfg, monkeypatch):
    folge = [bot.Result(bot.FAILED, message="weg"), bot.Result(bot.OK),
             bot.Result(bot.FAILED, message="weg"), bot.Result(bot.OK)]
    code, laeufe = watch_mit(monkeypatch, cfg, folge)
    # Weniger als die elf eines stoerungsfreien Laufs: Die beiden
    # Fehlschlaege strecken den Takt jeweils einmal.
    assert code == 0 and laeufe == 9


def test_watch_zaehler_wird_bei_erfolg_zurueckgesetzt(cfg, monkeypatch):
    folge = [bot.Result(bot.FAILED, message="weg")] * 2 + [bot.Result(bot.OK)] \
            + [bot.Result(bot.FAILED, message="weg")] * 2
    code, _laeufe = watch_mit(monkeypatch, cfg, folge)
    assert code == 0


def test_watch_idle_gilt_nicht_als_fehler(cfg, monkeypatch):
    code, laeufe = watch_mit(monkeypatch, cfg, [bot.Result(bot.IDLE)] * 11)
    assert code == 0 and laeufe == 11


def test_watch_faengt_unerwartete_ausnahme(cfg, monkeypatch):
    """Ohne dieses Netz beendete jede uebersehene Ausnahme den Job -- und
    bis zum naechsten Start vergingen bis zu 30 Minuten ohne Pruefung."""
    uhr = Uhr()
    laeufe = []

    def fake_check(_cfg):
        laeufe.append(1)
        uhr.jetzt += 3
        if len(laeufe) == 1:
            raise ZeroDivisionError("uebersehen")
        return bot.Result(bot.OK)

    monkeypatch.setattr(bot, "check_once", fake_check)
    code = bot.watch(cfg, 55, 300, sleeper=uhr.schlafe, clock=uhr)
    # Zehn statt elf Durchlaeufe: Der eine Fehlschlag streckt den Takt einmal.
    assert code == 0 and len(laeufe) == 10


def test_watch_zieht_eigene_laufzeit_vom_takt_ab(cfg, monkeypatch):
    """Sonst driftet der Takt weg."""
    uhr = Uhr()
    gewartet = []

    def fake_check(_cfg):
        uhr.jetzt += 20   # ein besonders zaeher Durchlauf
        return bot.Result(bot.OK)

    def schlafe(sekunden):
        gewartet.append(sekunden)
        uhr.jetzt += sekunden

    monkeypatch.setattr(bot, "check_once", fake_check)
    bot.watch(cfg, 10, 300, sleeper=schlafe, clock=uhr)
    assert gewartet and all(w == 280 for w in gewartet)


def test_watch_wartet_nie_negativ(cfg, monkeypatch):
    uhr = Uhr()
    gewartet = []

    def fake_check(_cfg):
        uhr.jetzt += 600   # laenger als der Takt
        return bot.Result(bot.OK)

    def schlafe(sekunden):
        gewartet.append(sekunden)
        uhr.jetzt += sekunden

    monkeypatch.setattr(bot, "check_once", fake_check)
    bot.watch(cfg, 60, 300, sleeper=schlafe, clock=uhr)
    assert all(w >= 0 for w in gewartet)


# ===========================================================================
#  WebUntis-Randschicht  (mit Attrappen)
# ===========================================================================

class FakeYear:
    def __init__(self, name, start, end):
        self.name = name
        self.start = dt.datetime.combine(start, dt.time())
        self.end = dt.datetime.combine(end, dt.time())


class FakeTimeUnit:
    def __init__(self, name, start, end):
        self.name = name
        self.start = dt.time.fromisoformat(start)
        self.end = dt.time.fromisoformat(end)


class FakeGridDay:
    def __init__(self, day, units):
        self.day = day
        self.time_units = units


class FakeSession:
    def __init__(self, years=(), grid=None, grid_fehler=False):
        self._years = list(years)
        self._grid = grid
        self._grid_fehler = grid_fehler

    def schoolyears(self):
        return self._years

    def timegrid_units(self):
        if self._grid_fehler:
            raise RuntimeError("keine Berechtigung")
        return self._grid or []


def untis_mit(cfg, session):
    u = bot.Untis(cfg)
    u._session = session
    return u


def test_schoolyears_sortiert(cfg):
    a = FakeYear("2025/26", dt.date(2025, 9, 1), dt.date(2026, 7, 31))
    b = FakeYear("2026/27", dt.date(2026, 9, 1), dt.date(2027, 7, 31))
    u = untis_mit(cfg, FakeSession(years=[b, a]))
    assert [y.name for y in u.schoolyears()] == ["2025/26", "2026/27"]


def test_schoolyears_fehler_gibt_leere_liste(cfg):
    class Bockig(FakeSession):
        def schoolyears(self):
            raise RuntimeError("nein")

    assert untis_mit(cfg, Bockig()).schoolyears() == []


class FakeKlasse:
    def __init__(self, name):
        self.name = name


def klassen_session(namen, geholt):
    """FakeSession, die Klassen kennt und den Abruf protokolliert."""

    class Sitzung(FakeSession):
        def klassen(self):
            return [FakeKlasse(n) for n in namen]

        def timetable(self, klasse, start, end):
            geholt.append((klasse.name, start, end))
            return ["stunde"]

        def my_timetable(self, start, end):
            raise RuntimeError("persoenlicher Plan gesperrt")

    return Sitzung()


def test_by_klasse_findet_die_klasse():
    """Der Rueckfall auf den Klassenplan greift nur, wenn der persoenliche
    Plan gar nicht abrufbar ist -- also genau dann, wenn ohnehin schon
    etwas klemmt. Ungeprueft faellt ein Fehler darin erst in dem Moment
    auf, in dem man ihn am wenigsten gebrauchen kann.
    """
    geholt = []
    cfg = Config(telegram_token="123:ABC", telegram_chats=("42",),
                 untis_server="s", untis_school="k", untis_user="u",
                 untis_password="p", untis_klasse="3WGI13")
    u = untis_mit(cfg, klassen_session(["1A", "3WGI13", "2B"], geholt))
    spanne = (dt.date(2026, 9, 14), dt.date(2026, 9, 21))

    assert list(u._by_klasse(*spanne)) == ["stunde"]
    assert geholt == [("3WGI13", *spanne)]


def test_by_klasse_ignoriert_gross_und_kleinschreibung():
    """WEBUNTIS_KLASSE tippt ein Mensch in ein Secret-Feld ab. "3wgi13"
    darf nicht an der Schreibweise scheitern."""
    geholt = []
    cfg = Config(telegram_token="123:ABC", telegram_chats=("42",),
                 untis_server="s", untis_school="k", untis_user="u",
                 untis_password="p", untis_klasse="3wgi13")
    u = untis_mit(cfg, klassen_session(["3WGI13"], geholt))
    u._by_klasse(dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert [n for n, _s, _e in geholt] == ["3WGI13"]


def test_by_klasse_nennt_die_vorhandenen_klassen():
    """Ein Tippfehler im Secret ist der wahrscheinlichste Fehler hier.
    "Klasse unbekannt" allein zwingt zum Raten -- die Liste beantwortet
    die Frage sofort."""
    cfg = Config(telegram_token="123:ABC", telegram_chats=("42",),
                 untis_server="s", untis_school="k", untis_user="u",
                 untis_password="p", untis_klasse="3WGI31")
    u = untis_mit(cfg, klassen_session(["1A", "3WGI13"], []))
    with pytest.raises(bot.UntisError, match="3WGI13"):
        u._by_klasse(dt.date(2026, 9, 14), dt.date(2026, 9, 21))


def test_timetable_faellt_auf_den_klassenplan_zurueck():
    """Die Verdrahtung, nicht nur der Baustein: Erst wenn my_timetable
    WIRFT, wird der Klassenplan geholt. Ein LEERER persoenlicher Plan darf
    ihn nicht ausloesen -- sonst verschickte der Bot bei einem stillen
    Ausfall den Plan der ganzen Klasse als Massen-Aenderung."""
    geholt = []
    cfg = Config(telegram_token="123:ABC", telegram_chats=("42",),
                 untis_server="s", untis_school="k", untis_user="u",
                 untis_password="p", untis_klasse="3WGI13")

    u = untis_mit(cfg, klassen_session(["3WGI13"], geholt))
    u._convert = lambda periods, _resolve: [lesson(uid=1)]
    u._resolver = lambda: (lambda _art, _ids: ())
    assert len(u.timetable(dt.date(2026, 9, 14), dt.date(2026, 9, 21))) == 1
    assert [n for n, _s, _e in geholt] == ["3WGI13"]


def test_timetable_leerer_persoenlicher_plan_holt_nicht_die_klasse():
    geholt = []
    cfg = Config(telegram_token="123:ABC", telegram_chats=("42",),
                 untis_server="s", untis_school="k", untis_user="u",
                 untis_password="p", untis_klasse="3WGI13")

    sitzung = klassen_session(["3WGI13"], geholt)
    sitzung.my_timetable = lambda start, end: []
    u = untis_mit(cfg, sitzung)
    u._resolver = lambda: (lambda _art, _ids: ())
    with pytest.raises(bot.NothingToDo):
        u.timetable(dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert geholt == [], "der Klassenplan darf hier nicht geholt werden"


def test_clamp_ohne_schuljahre_unveraendert(cfg):
    u = untis_mit(cfg, FakeSession())
    fenster = (dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert u.clamp(*fenster) == fenster


def test_clamp_beschneidet_auf_schuljahresende(cfg):
    jahr = FakeYear("2025/26", dt.date(2025, 9, 1), dt.date(2026, 9, 16))
    u = untis_mit(cfg, FakeSession(years=[jahr]))
    assert u.clamp(dt.date(2026, 9, 14), dt.date(2026, 9, 21)) == \
           (dt.date(2026, 9, 14), dt.date(2026, 9, 16))


def test_clamp_innerhalb_bleibt_unveraendert(cfg):
    jahr = FakeYear("2026/27", dt.date(2026, 9, 1), dt.date(2027, 7, 31))
    u = untis_mit(cfg, FakeSession(years=[jahr]))
    fenster = (dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert u.clamp(*fenster) == fenster


def test_clamp_ausserhalb_meldet_nothingtodo(cfg):
    jahr = FakeYear("2024/25", dt.date(2024, 9, 1), dt.date(2025, 7, 31))
    u = untis_mit(cfg, FakeSession(years=[jahr]))
    with pytest.raises(bot.NothingToDo, match="noch nicht angelegt"):
        u.clamp(dt.date(2026, 9, 14), dt.date(2026, 9, 21))


def test_clamp_nennt_kommendes_schuljahr(cfg):
    jahr = FakeYear("2027/28", dt.date(2027, 9, 1), dt.date(2028, 7, 31))
    u = untis_mit(cfg, FakeSession(years=[jahr]))
    with pytest.raises(bot.NothingToDo, match="2027/28"):
        u.clamp(dt.date(2026, 9, 14), dt.date(2026, 9, 21))


def test_timegrid_uebersetzt_wochentage(cfg):
    """WebUntis zaehlt 1=Sonntag..7=Samstag, Python 0=Montag."""
    grid = [FakeGridDay(2, [FakeTimeUnit("1", "07:40", "08:25")]),   # Montag
            FakeGridDay(6, [FakeTimeUnit("1", "07:40", "08:25")]),   # Freitag
            FakeGridDay(1, [FakeTimeUnit("1", "09:00", "09:45")])]   # Sonntag
    raster = untis_mit(cfg, FakeSession(grid=grid)).timegrid()
    assert set(raster) == {0, 4, 6}


def test_timegrid_sortiert_nach_startzeit(cfg):
    grid = [FakeGridDay(2, [FakeTimeUnit("2", "08:30", "09:15"),
                            FakeTimeUnit("1", "07:40", "08:25")])]
    raster = untis_mit(cfg, FakeSession(grid=grid)).timegrid()
    assert [u[0] for u in raster[0]] == ["07:40", "08:30"]


def test_timegrid_formatiert_zeiten(cfg):
    grid = [FakeGridDay(2, [FakeTimeUnit("1", "07:40", "08:25")])]
    raster = untis_mit(cfg, FakeSession(grid=grid)).timegrid()
    assert raster[0] == [("07:40", "08:25", "1")]


def test_timegrid_fehler_gibt_leeres_raster(cfg):
    """Der Aufrufer faellt dann auf Einzelzeilen zurueck, statt den ganzen
    Lauf zu gefaehrden."""
    assert untis_mit(cfg, FakeSession(grid_fehler=True)).timegrid() == {}


def test_timegrid_kaputte_zeile_gibt_leeres_raster(cfg):
    class KaputteEinheit:
        name = "1"
        start = "keine Zeit"
        end = "auch nicht"

    grid = [FakeGridDay(2, [KaputteEinheit()])]
    assert untis_mit(cfg, FakeSession(grid=grid)).timegrid() == {}


def test_timegrid_wird_zwischengespeichert(cfg):
    """watch() ruft check_once() rund zwoelfmal pro Stunde auf -- ohne
    Cache waeren elf von zwoelf Abrufen reine Verschwendung."""
    abrufe = []

    class ZaehlendeSession(FakeSession):
        def timegrid_units(self):
            abrufe.append(1)
            return [FakeGridDay(2, [FakeTimeUnit("1", "07:40", "08:25")])]

    u = untis_mit(cfg, ZaehlendeSession())
    u.timegrid()
    u.timegrid()
    untis_mit(cfg, ZaehlendeSession()).timegrid()
    assert len(abrufe) == 1


def test_timegrid_fehler_wird_nicht_zwischengespeichert(cfg):
    """Der naechste Poll darf es erneut versuchen."""
    abrufe = []

    class ZaehlendeSession(FakeSession):
        def timegrid_units(self):
            abrufe.append(1)
            raise RuntimeError("nein")

    u = untis_mit(cfg, ZaehlendeSession())
    u.timegrid()
    u.timegrid()
    assert len(abrufe) == 2


def test_timegrid_cache_trennt_schulen(cfg):
    grid = [FakeGridDay(2, [FakeTimeUnit("1", "07:40", "08:25")])]
    untis_mit(cfg, FakeSession(grid=grid)).timegrid()
    andere = dataclasses.replace(cfg, untis_school="andere-schule")
    abrufe = []

    class ZaehlendeSession(FakeSession):
        def timegrid_units(self):
            abrufe.append(1)
            return grid

    untis_mit(andere, ZaehlendeSession()).timegrid()
    assert len(abrufe) == 1


def test_convert_ueberspringt_unlesbare_stunde(cfg):
    """Eine unlesbare Stunde darf nie den ganzen Lauf kippen."""
    class KaputtesPeriod:
        _data = {"id": 1}
        code = None

        @property
        def start(self):
            raise ValueError("kaputt")

    stunden = bot.Untis._convert([KaputtesPeriod(), FakePeriod({"id": 2})],
                                 resolve_by_name)
    assert len(stunden) == 1


def test_convert_sortiert(cfg):
    spaet = FakePeriod({"id": 1}, start=dt.datetime(2026, 9, 14, 11, 30),
                       end=dt.datetime(2026, 9, 14, 12, 15))
    frueh = FakePeriod({"id": 2}, start=dt.datetime(2026, 9, 14, 7, 40),
                       end=dt.datetime(2026, 9, 14, 8, 25))
    stunden = bot.Untis._convert([spaet, frueh], resolve_by_name)
    assert [stunde.start for stunde in stunden] == ["07:40", "11:30"]


def test_strategies_ohne_klasse(cfg):
    wege = bot.Untis(cfg)._strategies(dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert [name for name, _ in wege] == ["my_timetable"]


def test_strategies_mit_klasse(cfg):
    cfg = dataclasses.replace(cfg, untis_klasse="K1")
    wege = bot.Untis(cfg)._strategies(dt.date(2026, 9, 14), dt.date(2026, 9, 21))
    assert [name for name, _ in wege] == ["my_timetable", "klasse:K1"]


def test_timetable_leere_saubere_antwort_ist_nothingtodo(cfg, monkeypatch):
    """Eine saubere leere Antwort beendet die Suche -- sonst liefert der Bot
    stillschweigend den KLASSENPLAN, eine voellig andere Datenmenge."""
    u = untis_mit(dataclasses.replace(cfg, untis_klasse="K1"), FakeSession())
    monkeypatch.setattr(u, "_strategies",
                        lambda s, e: [("my_timetable", lambda: []),
                                      ("klasse:K1", lambda: [FakePeriod({"id": 1})])])
    with pytest.raises(bot.NothingToDo):
        u.timetable(dt.date(2026, 9, 14), dt.date(2026, 9, 21))


def test_timetable_faellt_bei_fehler_auf_klassenplan_zurueck(cfg, monkeypatch):
    u = untis_mit(dataclasses.replace(cfg, untis_klasse="K1"), FakeSession())

    def erster():
        raise RuntimeError("keine Berechtigung")

    monkeypatch.setattr(u, "_strategies",
                        lambda s, e: [("my_timetable", erster),
                                      ("klasse:K1", lambda: [FakePeriod({"id": 1})])])
    assert len(u.timetable(dt.date(2026, 9, 14), dt.date(2026, 9, 21))) == 1


def test_timetable_unlesbare_antwort_ist_ein_defekt(cfg, monkeypatch):
    """Als 'leer' durchgereicht wuerde daraus eine Massenmeldung
    'alles nicht mehr im Plan'."""
    class VoelligKaputt:
        _data = {"id": 1}
        code = None

        @property
        def start(self):
            raise ValueError("Format geaendert")

    u = untis_mit(cfg, FakeSession())
    monkeypatch.setattr(u, "_strategies",
                        lambda s, e: [("my_timetable", lambda: [VoelligKaputt()])])
    with pytest.raises(bot.UntisError, match="keine davon lesbar"):
        u.timetable(dt.date(2026, 9, 14), dt.date(2026, 9, 21))


def test_timetable_alle_wege_kaputt(cfg, monkeypatch):
    u = untis_mit(cfg, FakeSession())

    def kaputt():
        raise RuntimeError("Server weg")

    monkeypatch.setattr(u, "_strategies", lambda s, e: [("my_timetable", kaputt)])
    with pytest.raises(bot.UntisError, match="Kein Stundenplan abrufbar"):
        u.timetable(dt.date(2026, 9, 14), dt.date(2026, 9, 21))


# ===========================================================================
#  Einstieg (CLI)
# ===========================================================================

def test_main_konfigurationsfehler_gibt_1(monkeypatch, capsys):
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    def kaputt(**_k):
        raise ConfigError("fehlt")

    monkeypatch.setattr(Config, "from_env", staticmethod(kaputt))
    assert bot.main(["check"]) == 1
    assert "KONFIGURATIONSFEHLER" in capsys.readouterr().err


def test_main_ohne_unterbefehl_ist_check(cfg, monkeypatch, capsys):
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "check_once",
                        lambda c, dry_run=False: bot.Result(bot.OK, message="fertig"))
    assert bot.main([]) == 0
    assert "fertig" in capsys.readouterr().out


def test_main_check_dry_run(cfg, monkeypatch):
    gesehen = {}
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))


    def fake_check(_cfg, dry_run=False):
        gesehen["dry"] = dry_run
        return bot.Result(bot.OK)

    monkeypatch.setattr(bot, "check_once", fake_check)
    bot.main(["check", "--dry-run"])
    assert gesehen["dry"] is True


def test_main_check_ohne_dry_run(cfg, monkeypatch):
    gesehen = {}
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))

    def fake_check(_cfg, dry_run=False):
        gesehen["dry"] = dry_run
        return bot.Result(bot.OK)

    monkeypatch.setattr(bot, "check_once", fake_check)
    bot.main(["check"])
    assert gesehen["dry"] is False


def test_main_fehlgeschlagener_check_gibt_1(cfg, monkeypatch):
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "check_once",
                        lambda c, dry_run=False: bot.Result(bot.FAILED, message="weg"))
    assert bot.main(["check"]) == 1


def test_main_watch_reicht_parameter_durch(cfg, monkeypatch):
    gesehen = {}
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "watch",
                        lambda c, m, i, n: gesehen.update(minutes=m, interval=i,
                                                          night=n) or 0)
    bot.main(["watch", "--minutes", "12", "--interval", "60",
              "--night-interval", "900"])
    assert gesehen == {"minutes": 12, "interval": 60, "night": 900}


def test_main_watch_standardwerte(cfg, monkeypatch):
    gesehen = {}
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "watch",
                        lambda c, m, i, n: gesehen.update(minutes=m, interval=i,
                                                          night=n) or 0)
    bot.main(["watch"])
    # 330 = 5,5 Stunden, dieselbe Laufzeit wie im Workflow. Ein kuerzerer
    # Standard hinterliesse nach einem Handstart keinen wartenden Lauf.
    assert gesehen == {"minutes": 330, "interval": 300, "night": None}


def test_main_selftest(cfg, monkeypatch):
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "selftest", lambda c: 0)
    assert bot.main(["selftest"]) == 0


def test_main_show(cfg, monkeypatch):
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "show", lambda c, d: 0 if d == 3 else 1)
    assert bot.main(["show", "--days", "3"]) == 0


def test_selftest_meldet_kaputten_token(cfg, monkeypatch, capsys):
    monkeypatch.setattr(bot, "telegram_call",
                        lambda *a, **k: (_ for _ in ()).throw(TelegramError("nein")))
    monkeypatch.setattr(bot, "Untis", FakeUntis([lesson()]))
    assert bot.selftest(cfg) == 1
    assert "[NEIN]" in capsys.readouterr().out


def test_selftest_zeigt_den_benutzernamen_nicht_im_klartext(cfg, monkeypatch,
                                                           capsys):
    """SICHERHEITSNETZ: In Actions maskiert GitHub registrierte Secrets,
    lokal maskiert niemand -- und das README schickt Leute bei Problemen
    genau dorthin, um eine Diagnoseausgabe zu erzeugen, die man dann
    weiterreicht."""
    geheim = dataclasses.replace(cfg, untis_user="max.mustermann.2026")
    monkeypatch.setattr(bot, "telegram_call", lambda *a, **k: {"username": "bot"})
    monkeypatch.setattr(bot, "Untis", FakeUntis([lesson()]))
    bot.selftest(geheim)
    ausgabe = capsys.readouterr().out
    assert "max.mustermann.2026" not in ausgabe
    # Diagnostisch weiterhin brauchbar: das richtige Konto bleibt erkennbar.
    assert bot.mask("max.mustermann.2026") in ausgabe


def test_show_gibt_plan_aus(cfg, monkeypatch, capsys):
    monkeypatch.setattr(bot, "Untis", FakeUntis([lesson(rooms=("R1",), note="Info")]))
    assert bot.show(cfg, 3) == 0
    ausgabe = capsys.readouterr().out
    assert "Montag" in ausgabe and "R1" in ausgabe and "Info" in ausgabe


def test_show_markiert_ausfall(cfg, monkeypatch, capsys):
    monkeypatch.setattr(bot, "Untis", FakeUntis([lesson(status=CANCELLED)]))
    bot.show(cfg, 3)
    assert "ENTFAELLT" in capsys.readouterr().out


def test_show_bei_ferien(cfg, monkeypatch, capsys):
    monkeypatch.setattr(bot, "Untis", FakeUntis(fehler=bot.NothingToDo("Ferien")))
    assert bot.show(cfg, 3) == 0
    assert "Ferien" in capsys.readouterr().out


def test_show_bei_fehler_gibt_1(cfg, monkeypatch, capsys):
    monkeypatch.setattr(bot, "Untis", FakeUntis(fehler=bot.UntisError("Server weg")))
    assert bot.show(cfg, 3) == 1


def test_setup_logging_daempft_webuntis():
    bot.setup_logging("INFO")
    assert bot.logging.getLogger("webuntis").level == bot.logging.CRITICAL


def test_setup_logging_debug_laesst_webuntis_reden():
    bot.logging.getLogger("webuntis").setLevel(bot.logging.NOTSET)
    bot.setup_logging("DEBUG")
    assert bot.logging.getLogger("webuntis").level != bot.logging.CRITICAL
    bot.setup_logging("INFO")   # aufraeumen


def test_setup_logging_unbekannte_stufe_kippt_nicht():
    """LOG_LEVEL kommt aus der Umgebung -- ein Tippfehler darf den Start
    nicht verhindern."""
    bot.setup_logging("gibtsnicht")
    bot.setup_logging("INFO")   # aufraeumen


# ===========================================================================
#  Testnachricht
# ===========================================================================

def test_demo_changes_trifft_viele_arten():
    arten = {c.kind for c in bot.demo_changes(HEUTE)}
    assert {"cancelled", "teacher", "room", "marked"} <= arten


def test_demo_changes_liegt_im_demo_raster():
    """Sonst stuenden in der Testnachricht Uhrzeiten statt Stundennummern
    und sie zeigte nicht das, was sie zeigen soll."""
    for change in bot.demo_changes(HEUTE):
        assert bot.period_name(change.lesson, bot.DEMO_RASTER) is not None


def test_demo_raster_deckt_jeden_wochentag():
    """Die Testnachricht muss an jedem Tag funktionieren, an dem sie
    ausgeloest wird -- auch sonntags."""
    assert set(bot.DEMO_RASTER) == set(range(7))


def test_demo_changes_zeigt_buendelung_und_doppelstunde():
    eintraege = bot.build_entries(bot.demo_changes(HEUTE), bot.DEMO_RASTER)
    labels = [(e.label, e.labels) for e in eintraege]
    assert ("1./2. Stunde", "entfällt") in labels
    assert ("3./4. Stunde", "Vertretung, Raumwechsel") in labels
    assert ("6. Stunde", "Raumwechsel") in labels


def test_testmessage_sendet_genau_einmal(cfg, monkeypatch):
    gesendet = []
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis(periods=RASTER))
    assert bot.testmessage(cfg) == 0
    assert len(gesendet) == 1


def test_testmessage_ist_als_test_erkennbar(cfg, monkeypatch):
    gesendet = []
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis(periods=RASTER))
    bot.testmessage(cfg)
    assert "TESTNACHRICHT" in gesendet[0]


def test_testmessage_ruehrt_den_zustand_nicht_an(cfg, monkeypatch):
    """SICHERHEITSNETZ: Eine Testnachricht darf den Betrieb nicht
    veraendern -- sonst faelscht sie den Vergleich des naechsten Laufs."""
    def verboten(*_a, **_k):
        raise AssertionError("testmessage darf das nicht anfassen")

    monkeypatch.setattr(bot, "save_state", verboten)
    monkeypatch.setattr(bot, "load_state", verboten)
    monkeypatch.setattr(bot, "commit_state", verboten)
    monkeypatch.setattr(bot, "send", lambda *_a, **_k: 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis(periods=RASTER))
    assert bot.testmessage(cfg) == 0


def test_testmessage_meldet_verfuegbares_raster(cfg, monkeypatch):
    gesendet = []
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis(periods=RASTER))
    bot.testmessage(cfg)
    assert "Stundenraster: verfügbar" in gesendet[0]


def test_testmessage_meldet_fehlendes_raster(cfg, monkeypatch):
    """Die Frage, die man dem Bot im Betrieb sonst nicht ansieht."""
    gesendet = []
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis(timegrid_fehler=True))
    bot.testmessage(cfg)
    assert "NICHT verfügbar" in gesendet[0]


def test_read_saved_at_liest_den_zeitstempel(tmp_path):
    pfad = tmp_path / "state.json"
    bot.save_state([lesson()], (dt.date(2026, 9, 14), dt.date(2026, 9, 21)), pfad)
    assert bot.read_saved_at(pfad) != ""


def test_read_saved_at_ohne_datei(tmp_path):
    assert bot.read_saved_at(tmp_path / "gibtsnicht.json") == ""


def test_read_saved_at_kaputte_datei_legt_nichts_beiseite(tmp_path):
    """Anders als load_state: Eine Diagnose darf den Zustand nicht anfassen,
    auch nicht im Fehlerfall."""
    pfad = tmp_path / "state.json"
    pfad.write_text("{kein json", encoding="utf-8")
    assert bot.read_saved_at(pfad) == ""
    assert pfad.exists() and not (tmp_path / "state.broken").exists()


def test_read_saved_at_falsche_huelle(tmp_path):
    pfad = tmp_path / "state.json"
    pfad.write_text("[1, 2, 3]", encoding="utf-8")
    assert bot.read_saved_at(pfad) == ""


JETZT = dt.datetime(2026, 9, 21, 12, 0)


@pytest.mark.parametrize("gesichert,erwartet", [
    ("2026-09-21T11:45:00", "vor 15 Minuten gesichert"),
    ("2026-09-21T09:00:00", "vor 3 Stunden gesichert"),
    ("2026-09-18T12:00:00", "vor 3 Tagen gesichert"),
])
def test_describe_age(gesichert, erwartet):
    assert bot.describe_age(gesichert, JETZT) == erwartet


def test_describe_age_ohne_zustand():
    assert bot.describe_age("", JETZT) == "keiner vorhanden"


def test_describe_age_kaputter_zeitstempel():
    assert bot.describe_age("neulich", JETZT) == "Zeitstempel unlesbar"


def test_describe_age_mit_zeitzone_kippt_nicht():
    """Der Bot schreibt mit Zone, JETZT kommt ohne -- der Vergleich darf
    daran nicht scheitern."""
    assert "gesichert" in bot.describe_age("2026-09-21T09:00:00+02:00", JETZT)


def test_describe_age_zukunft():
    assert bot.describe_age("2026-09-22T12:00:00", JETZT) == "in der Zukunft datiert"


def test_testmessage_nennt_die_abrufbare_stundenzahl(cfg, monkeypatch, tmp_path):
    gesendet = []
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis([lesson(), lesson(uid=2)],
                                                periods=RASTER))
    bot.testmessage(cfg, tmp_path / "state.json")
    assert "Abrufbare Stunden: 2" in gesendet[0]


def test_testmessage_macht_den_stillen_ausfall_sichtbar(cfg, monkeypatch, tmp_path):
    """Antwortet WebUntis sauber mit 0 Stunden, bleibt der Lauf gruen und
    der Bot schweigt unbegrenzt -- von aussen wie Ferien. Der Befund ist
    die einzige Stelle, an der das ueberhaupt sichtbar wird."""
    gesendet = []
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis([], periods=RASTER))
    bot.testmessage(cfg, tmp_path / "state.json")
    assert "Abrufbare Stunden: 0" in gesendet[0]
    assert "Gespeicherter Zustand: keiner vorhanden" in gesendet[0]


def test_testmessage_nennt_das_alter_des_zustands(cfg, monkeypatch, tmp_path):
    gesendet = []
    pfad = tmp_path / "state.json"
    bot.save_state([lesson()], (dt.date(2026, 9, 14), dt.date(2026, 9, 21)), pfad)
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", FakeUntis([lesson()], periods=RASTER))
    bot.testmessage(cfg, pfad)
    assert "Gespeicherter Zustand: vor 0 Minuten gesichert" in gesendet[0]


def test_testmessage_ueberlebt_kaputten_stundenabruf(cfg, monkeypatch, tmp_path):
    """Ein Fehler im Befund darf die Testnachricht nie verhindern."""
    gesendet = []

    class OhneStunden(FakeUntis):
        def timetable(self, _start, _end):
            raise bot.UntisError("Abruf kaputt")

    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", OhneStunden(periods=RASTER))
    assert bot.testmessage(cfg, tmp_path / "state.json") == 0
    assert "Abrufbare Stunden: Abruf fehlgeschlagen" in gesendet[0]
    # Das Raster kam vorher an und darf nicht mit verlorengehen.
    assert "Stundenraster: verfügbar" in gesendet[0]


def test_testmessage_ueberlebt_kaputtes_webuntis(cfg, monkeypatch):
    """Das Format soll auch dann vorfuehrbar sein, wenn WebUntis klemmt."""
    gesendet = []

    class KaputtesUntis(FakeUntis):
        def __enter__(self):
            raise bot.UntisError("Server weg")

    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    monkeypatch.setattr(bot, "Untis", KaputtesUntis())
    assert bot.testmessage(cfg) == 0
    assert "TESTNACHRICHT" in gesendet[0] and "NICHT verfügbar" in gesendet[0]


def test_testmessage_gibt_1_bei_versandfehler(cfg, monkeypatch, capsys):
    def abgelehnt(*_a, **_k):
        raise TelegramConfigError("Token falsch")

    monkeypatch.setattr(bot, "send", abgelehnt)
    monkeypatch.setattr(bot, "Untis", FakeUntis(periods=RASTER))
    assert bot.testmessage(cfg) == 1
    assert "nicht zugestellt" in capsys.readouterr().err


def test_render_alert_ist_als_stoerung_erkennbar():
    text = bot.render_alert("WebUntis antwortet nicht")
    assert "Störung" in text
    assert "WebUntis antwortet nicht" in text


def test_render_alert_mit_quelle():
    text = bot.render_alert("kaputt", "Lauf 42 · https://example.invalid/x")
    assert "<i>Lauf 42 · https://example.invalid/x</i>" in text


def test_render_alert_ohne_quelle_keine_leere_zeile():
    assert "<i></i>" not in bot.render_alert("kaputt")


def test_render_alert_maskiert_html():
    """Fehlertexte kommen aus Ausnahmen und koennen alles enthalten."""
    assert "&lt;b&gt;" in bot.render_alert("kaputt: <b>")


def test_alert_sendet(cfg, monkeypatch):
    gesendet = []
    monkeypatch.setattr(bot, "send", lambda _c, text, **_k: gesendet.append(text) or 1)
    assert bot.alert(cfg, "WebUntis antwortet nicht") == 0
    assert len(gesendet) == 1 and "Störung" in gesendet[0]


def test_alert_ruehrt_den_zustand_nicht_an(cfg, monkeypatch):
    """SICHERHEITSNETZ: Eine Stoermeldung darf den Vergleich des naechsten
    Laufs nicht verfaelschen."""
    def verboten(*_a, **_k):
        raise AssertionError("alert darf das nicht anfassen")

    monkeypatch.setattr(bot, "save_state", verboten)
    monkeypatch.setattr(bot, "load_state", verboten)
    monkeypatch.setattr(bot, "commit_state", verboten)
    monkeypatch.setattr(bot, "send", lambda *_a, **_k: 1)
    assert bot.alert(cfg, "kaputt") == 0


def test_alert_gibt_1_wenn_telegram_nicht_erreichbar(cfg, monkeypatch, capsys):
    def abgelehnt(*_a, **_k):
        raise TelegramConfigError("Token falsch")

    monkeypatch.setattr(bot, "send", abgelehnt)
    assert bot.alert(cfg, "kaputt") == 1
    assert "nicht zustellbar" in capsys.readouterr().err


def test_config_alert_braucht_kein_webuntis(env):
    """Der Wachhund meldet, dass nichts mehr laeuft -- er darf nicht selbst
    an fehlenden WebUntis-Werten scheitern."""
    for name in ("WEBUNTIS_SERVER", "WEBUNTIS_SCHOOL",
                 "WEBUNTIS_USERNAME", "WEBUNTIS_PASSWORD"):
        env.delenv(name)
    cfg = Config.from_env(telegram_only=True)
    assert cfg.telegram_chats == ("42",)
    assert cfg.untis_server == ""


def test_config_verlangt_webuntis_sonst_weiterhin(env):
    env.delenv("WEBUNTIS_PASSWORD")
    with pytest.raises(ConfigError, match="WEBUNTIS_PASSWORD"):
        Config.from_env()


def test_main_alert(cfg, monkeypatch):
    gesehen = {}
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "alert",
                        lambda c, text, quelle: gesehen.update(text=text,
                                                               quelle=quelle) or 0)
    assert bot.main(["alert", "Lauf fehlgeschlagen", "--quelle", "Lauf 7"]) == 0
    assert gesehen == {"text": "Lauf fehlgeschlagen", "quelle": "Lauf 7"}


def test_main_alert_fordert_nur_telegram_an(cfg, monkeypatch):
    """Der Unterbefehl muss VOR dem Lesen der Konfiguration feststehen."""
    gesehen = {}
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env",
                        staticmethod(lambda telegram_only=False:
                                     gesehen.setdefault("nur_telegram",
                                                        telegram_only) or cfg))
    monkeypatch.setattr(bot, "alert", lambda *_a, **_k: 0)
    bot.main(["alert", "kaputt"])
    assert gesehen["nur_telegram"] is True


def test_main_check_fordert_alles_an(cfg, monkeypatch):
    gesehen = {}
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env",
                        staticmethod(lambda telegram_only=False:
                                     gesehen.setdefault("nur_telegram",
                                                        telegram_only) or cfg))
    monkeypatch.setattr(bot, "check_once",
                        lambda _c, dry_run=False: bot.Result(bot.OK))
    bot.main(["check"])
    assert gesehen["nur_telegram"] is False


def test_main_testmessage(cfg, monkeypatch):
    monkeypatch.setattr(bot, "_load_dotenv", lambda _p: None)
    monkeypatch.setattr(Config, "from_env", staticmethod(lambda **_k: cfg))
    monkeypatch.setattr(bot, "testmessage", lambda c: 0)
    assert bot.main(["testmessage"]) == 0
