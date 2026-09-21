# untisbot

[![Tests](https://github.com/77crj2ksb8-maker/untisnotification/actions/workflows/tests.yml/badge.svg)](https://github.com/77crj2ksb8-maker/untisnotification/actions/workflows/tests.yml)

Meldet Änderungen am WebUntis-Stundenplan per Telegram — Ausfall, Vertretung,
Raumwechsel, verschobene Stunden. Läuft kostenlos auf GitHub Actions, braucht
keinen eigenen Server.

```
Stundenplan-Änderungen

Montag, 14.09. (heute)
❌ 1./2. Stunde · M — entfällt
    Lehrkraft erkrankt
👤 3./4. Stunde · D — Vertretung, Raumwechsel
    Abel → Zeh
    R201 → R105
🚪 6. Stunde · Ph — Raumwechsel
    R301 → Labor
```

Einrichtung im eigenen Repo: **[SETUP.md](SETUP.md)**.

## Was der Bot kann

* **Doppelstunden zusammenfassen** — „1./2. Stunde" statt zweier wortgleicher
  Zeilen. Braucht das offizielle Stundenraster von WebUntis; ist es nicht
  abrufbar, steht überall die Uhrzeit und jede Stunde bleibt eine eigene Zeile.
* **Mehrere Änderungsarten je Stunde bündeln** — eine Vertretung mit
  Raumwechsel ist *ein* Eintrag, nicht zwei.
* **Mehrere Empfänger** — `TELEGRAM_CHAT_ID` nimmt kommagetrennte IDs. Hängt
  ein Chat, bekommen die anderen ihre Nachricht trotzdem.
* **Kurzfassung bei Massenänderungen** — ab 40 Änderungen wird gezählt statt
  aufgelistet. Fünfzig Zeilen liest niemand.
* **Bremse gegen Fehlalarme** — liefert WebUntis wegen Wartung plötzlich viel
  weniger Stunden, meldet der Bot nicht „alles entfällt", sondern wartet auf
  Bestätigung.
* **Dauerbetrieb rund um die Uhr** — alle 5 Minuten in der Schulzeit, alle 30
  Minuten nachts und am Wochenende.

## Befehle

| Befehl | Wirkung |
|---|---|
| `python bot.py check` | einmal prüfen, melden, Zustand sichern |
| `python bot.py check --dry-run` | prüfen und die Nachricht ausgeben, ohne zu senden oder zu speichern |
| `python bot.py watch --minutes 330` | 5,5 Stunden lang prüfen; `--interval` (Standard 300 s) gilt in der Schulzeit, `--night-interval` sonst |
| `python bot.py selftest` | jeden Zugang einzeln durchtesten und sagen, was klemmt |
| `python bot.py testmessage` | Beispielnachricht senden — ohne jede Wirkung auf den Betrieb |
| `python bot.py show --days 3` | Stundenplan im Klartext anzeigen |

`--log DEBUG` und `--version` gibt es zu jedem Befehl.

## Einstellungen

Alles kommt aus Umgebungsvariablen — im Code steht nichts Persönliches. Lokal
aus einer `.env`, auf GitHub aus den Actions-Secrets. Vorhandene
Umgebungsvariablen gewinnen, eine mitgelieferte `.env` überschreibt die
Secrets also nie.

| Variable | | Bedeutung |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Pflicht | vom `@BotFather` |
| `TELEGRAM_CHAT_ID` | Pflicht | eine ID oder mehrere, kommagetrennt |
| `WEBUNTIS_SERVER` | Pflicht | z. B. `ajax.webuntis.com` |
| `WEBUNTIS_SCHOOL` | Pflicht | Schulkürzel aus der WebUntis-URL |
| `WEBUNTIS_USERNAME` | Pflicht | |
| `WEBUNTIS_PASSWORD` | Pflicht | |
| `WEBUNTIS_KLASSE` | optional | **Rückfall**, kein Umschalter — siehe unten |
| `LOOKAHEAD_DAYS` | optional | Vorausschau in Tagen, Standard 7, begrenzt auf 1–30 |
| `TIMEZONE` | optional | Standard `Europe/Berlin` |

`WEBUNTIS_KLASSE` greift **nur**, wenn der persönliche Stundenplan gar nicht
abrufbar ist. Liefert `my_timetable` Stunden, gewinnt der immer. Wer den
Klassenplan verschicken will statt des eigenen, braucht dafür eine
Code-Änderung.

## Wie es läuft

Zwei Dinge stehen dem Dauerbetrieb im Weg:

1. **GitHubs Zeitplaner hält seinen eigenen Plan nicht ein.** Gemessen kamen an
   einem Werktag rund **10 von 48** geplanten Auslösungen tatsächlich zustande.
2. **Ein Actions-Job darf höchstens 6 Stunden laufen.** Ein echter
   Dauerprozess ist also gar nicht möglich.

Die Lösung ist eine Kette statt eines Dauerlaufs. Sie beruht auf einer
Eigenschaft der `concurrency`-Gruppe: Trifft ein Lauf ein, während einer läuft,
wird er nicht verworfen, sondern **wartet**. Ein bereits wartender Lauf wird
dabei vom neueren ersetzt — es steht also immer genau einer bereit. Endet der
laufende, übernimmt der wartende im selben Moment.

```
Lauf A  ├────────── 5,5 h ──────────┤
Cron         ↓ B wartet  ↓ C ersetzt B  ↓ D ersetzt C
Lauf D                               ├────────── 5,5 h ──────────┤
```

Solange der Zeitplaner innerhalb von 5,5 Stunden **auch nur ein einziges Mal**
auslöst, reißt die Kette nicht ab. Bei rund 10 Auslösungen pro Tag ist das
reichlich Sicherheitsabstand.

Den Takt innerhalb eines Laufs macht der Bot selbst — und zwar nach Tageszeit:
alle 5 Minuten werktags zwischen 6 und 19 Uhr, sonst alle 30 Minuten. Nachts im
Fünfminutentakt zu fragen wäre sinnlose Last: Jede Abfrage ist eine
vollständige WebUntis-Anmeldung. Verpasst wird dabei nichts — was um 2 Uhr
nachts eingetragen wird, steht spätestens eine halbe Stunde später im Chat.

In der Lauf-Liste tauchen regelmäßig **abgebrochene** Einträge auf. Das ist kein
Fehler, sondern genau der Mechanismus: wartende Läufe, die von einem neueren
wartenden ersetzt wurden.

Sein Gedächtnis ist `state.json` im Repo — der Bot committet sie nach jedem
Durchlauf selbst. Unveränderte Zustände werden nicht neu geschrieben, sonst
entstünden hunderte Commits pro Tag.

## Achtung: `state.json` ist öffentlich lesbar

Das Repo muss public sein (siehe SETUP.md), und der Bot legt seinen Zustand
darin ab. Damit steht der Stundenplan im Netz — Fächer, Räume, Zeiten,
Kursgruppen, für jeden lesbar:

```json
{"uid": 842774, "date": "2026-09-15", "start": "07:40", "end": "08:25",
 "subjects": ["D(G2)"], "rooms": ["H1.04"], "group": "D(G2)_3WGI13_..."}
```

Wer das nicht will, muss den Zustand woanders ablegen (Actions-Cache statt
Commit) — dann kann er verlorengehen, was ungefährlich ist: Ein Lauf ohne
gespeicherten Zustand meldet nichts, er merkt sich nur neu.

## Was wo liegt

```
bot.py                              der ganze Bot
tests/test_bot.py                   391 Tests, ohne Netz lauffähig
pyproject.toml                      Einstellungen für pytest und ruff
requirements.txt                    Abhängigkeiten
.env.example                        Vorlage für die lokale Entwicklung
.github/workflows/check-timetable.yml   der Bot-Lauf
.github/workflows/tests.yml         Linter und Tests bei jedem Push
SETUP.md                            Einrichtung im eigenen Repo
CHANGELOG.md                        was sich wann geändert hat
COPYRIGHT                           Nutzungsrechte
state.json                          das Gedächtnis des Bots
```

## Aufbau

Alles in einer Datei. Das ist Absicht: Das Projekt ist klein genug, und beim
Einspielen über die GitHub-Weboberfläche ist eine Datei ein Bruchteil der
Arbeit von acht.

```
Modell       Lesson, Change          unveränderliche Datensätze
Rein         normalise, diff,        Funktionen ohne Seiteneffekte,
             compare, Entry, render  vollständig testbar ohne Netz
Randschicht  Untis, telegram,        alles I/O, dünn gehalten
             state, git
Ablauf       check_once, watch       setzt die Teile zusammen
```

Die Trennung ist der Grund, warum die Testsuite ohne Netz und ohne
Zugangsdaten auskommt. Fehler in Nebenfunktionen dürfen den Hauptpfad — den
Telegram-Versand — nie zum Absturz bringen; deshalb überall `try/except` mit
Logging statt Weiterreichen.

## Entwicklung

```bash
pip install -r requirements.txt

python -m pytest             # 391 Tests, keine Netzverbindung nötig
ruff check .                 # Linter
```

Beides läuft bei jedem Push auch in GitHub Actions
(`.github/workflows/tests.yml`). Die Einstellungen stehen in
`pyproject.toml` — dort ist auch begründet, welche Linter-Regeln bewusst
abgewählt sind und warum.

Für einen lokalen Lauf gegen echte Daten `.env.example` nach `.env`
kopieren und ausfüllen. Dann:

```bash
python bot.py selftest        # prüft jeden Zugang einzeln
python bot.py check --dry-run # prüft, ohne zu senden oder zu speichern
```

Bei sicherheitskritischer Logik gilt zusätzlich ein Mutationstest:
Guard-Klausel testweise entfernen, prüfen dass ein Test rot wird,
zurücksetzen. Vier Zusicherungen sind im Testcode als `SICHERHEITSNETZ`
markiert:

| Zusicherung | Wächter |
|---|---|
| nie dieselbe Änderung zweimal melden | `test_check_meldet_dieselbe_aenderung_nie_zweimal` |
| ein git-Fehler kippt nie einen Lauf, in dem schon gesendet wurde | `test_commit_state_wirft_nie` |
| keine Massenmeldung bei Datenproblemen | `test_unplausibel_wenn_grosser_teil_weg` |
| unveränderter Zustand wird nicht neu geschrieben (Commit-Flut) | `test_save_state_schreibt_unveraenderten_zustand_nicht_neu` |
| eine Testnachricht ändert nichts am Zustand | `test_testmessage_ruehrt_den_zustand_nicht_an` |

Kommentare erklären das **Warum**, nicht das Was. Eine Zeile, die nur
wiederholt was ohnehin dasteht, kann weg.

## Bekannte Eigenheiten

* Manche Felder bleiben strukturell leer. Viele Schulen geben
  Schüler-Accounts keine Lehrerdaten heraus — dann ist eine Vertretung oft nur
  als „als Änderung markiert" sichtbar. Das ist kein Fehler.
* GitHub schaltet geplante Workflows ab, wenn 60 Tage lang kein Commit im Repo
  passiert. Da der Bot selbst committet, erledigt sich das im Schuljahr von
  allein — nach langen Ferien einmal „Enable workflow" klicken.

## Nutzungsrechte

Einsehbar, aber nicht frei. Das Repository ist öffentlich, weil GitHub Actions
nur für öffentliche Repositories unbegrenzt kostenlos ist — das ist eine
technische Notwendigkeit, keine Freigabe. Kopieren, Verändern, Weitergeben und
der Betrieb einer eigenen Instanz brauchen die Erlaubnis des Rechteinhabers.
Einzelheiten in [COPYRIGHT](COPYRIGHT).

„WebUntis" und „Untis" sind Marken der Untis GmbH. Dieses Projekt steht in
keiner Verbindung zu ihr. Die verwendete `webuntis`-Bibliothek ist inoffiziell.

Verbindlich ist immer der Stundenplan in WebUntis selbst — der Bot ist eine
Bequemlichkeit, keine Garantie.
