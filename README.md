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

## Was der Bot kann

* **Doppelstunden zusammenfassen** — „1./2. Stunde" statt zweier wortgleicher
  Zeilen. Braucht das offizielle Stundenraster von WebUntis; ist es nicht
  abrufbar, steht überall die Uhrzeit und jede Stunde bleibt eine eigene Zeile.
* **Mehrere Änderungsarten je Stunde bündeln** — eine Vertretung mit
  Raumwechsel ist *ein* Eintrag, nicht zwei.
* **Mehrere Empfänger** — `TELEGRAM_CHAT_ID` nimmt kommagetrennte IDs. Hängt
  ein Chat, bekommen die anderen ihre Nachricht trotzdem.
* **Kurzfassung bei Massenänderungen** — ab 40 **Einträgen** wird gezählt statt
  aufgelistet. Fünfzig Zeilen liest niemand — gemessen werden deshalb Zeilen,
  nicht Änderungen: Eine Vertretung mit Raumwechsel ist *eine* Zeile.
* **Bremse gegen Fehlalarme** — liefert WebUntis wegen Wartung plötzlich viel
  weniger Stunden, meldet der Bot nicht „alles entfällt", sondern wartet auf
  Bestätigung.
* **Dauerbetrieb rund um die Uhr** — alle 5 Minuten in der Schulzeit, alle 30
  Minuten nachts und am Wochenende.

## Einrichten

Für alle, die den Bot im **eigenen** Repo betreiben wollen. Rechne mit einer
Viertelstunde.

> **Vorher:** Der Betrieb einer eigenen Instanz braucht die Erlaubnis des
> Rechteinhabers — siehe [Nutzungsrechte](#nutzungsrechte). Frag einmal kurz
> nach, das ist formlos möglich.

Zwei Dinge vorweg, die Zeit sparen:

* **Die Dateien sind für alle identisch.** Im Code steht nichts Persönliches,
  alles kommt aus Secrets. Du musst keine Datei anpassen.
* **Wenn du denselben Stundenplan hast wie jemand, der den Bot schon
  betreibt, brauchst du gar nichts** — siehe [Der kürzere
  Weg](#der-kürzere-weg).

Du brauchst einen GitHub-Account, einen Telegram-Account und deine
WebUntis-Zugangsdaten.

### 1. Telegram-Bot anlegen

1. In Telegram `@BotFather` anschreiben, `/newbot`, den Fragen folgen.
2. Der Token sieht aus wie `123456789:AAH-xxxxxxxxxxxxxxxxxxxxx`. Aufheben.
3. **Deinen neuen Bot anschreiben und `/start` senden.** Ohne das darf er dir
   nicht schreiben, und du bekommst später „chat not found".
4. Chat-ID holen — im Browser aufrufen, `<TOKEN>` ersetzen:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Die Zahl unter `"chat":{"id":...}` ist deine ID. Bei Gruppen ist sie negativ.

> Nimm einen **eigenen** Bot, nicht den von jemand anderem. Wer den Token hat,
> kann in fremdem Namen an jeden Chat schreiben, den er kennt.

### 2. WebUntis-Werte heraussuchen

Melde dich einmal im Browser bei WebUntis an und sieh dir die Adresszeile an:

```
https://ajax.webuntis.com/WebUntis/?school=ks-musterstadt#/basic/login
         └──── SERVER ────┘                 └─── SCHOOL ───┘
```

* `WEBUNTIS_SERVER` = `ajax.webuntis.com` (ohne `https://`, ohne Schrägstrich)
* `WEBUNTIS_SCHOOL` = `ks-musterstadt`
* Benutzername und Passwort sind dieselben wie beim Anmelden.

### 3. Repo anlegen

Am saubersten über **„Use this template"** (die Vorlage muss dafür unter
*Settings → General → Template repository* markiert sein). Ein Fork tut es
auch, schleppt aber die fremde Historie mit.

Danach, und das ist wichtig:

1. **`state.json` im neuen Repo löschen**, falls sie mitkopiert wurde. Sonst
   vergleicht dein erster Lauf deinen Plan gegen den einer fremden Person.
   Ohne die Datei ist der erste Lauf sauber ein „Erster Lauf: N Stunden
   gemerkt, nichts gesendet".
2. **Repo auf public lassen.** Public heißt unbegrenzte Actions-Minuten. Ein
   Lauf dauert 5,5 Stunden, und die Läufe lösen einander ab — im Dauerbetrieb
   sind das über 40.000 Minuten im Monat, während im Free-Tarif für private
   Repos 2.000 enthalten sind. Privat reicht nicht.
3. Unter *Actions* einmal bestätigen, dass Workflows laufen dürfen. **Bei
   Forks sind geplante Workflows standardmäßig aus** und müssen dort
   eingeschaltet werden.

> Bevor du auf public gehst: Der Bot legt deinen Stundenplan als `state.json`
> im Repo ab, für jeden lesbar. Fächer, Räume, Zeiten, Kursgruppen — siehe
> [unten](#achtung-statejson-ist-öffentlich-lesbar).

### 4. Secrets setzen

*Settings → Secrets and variables → Actions → New repository secret.*
Sechs Pflichtwerte:

| Name | Beispiel |
|---|---|
| `TELEGRAM_BOT_TOKEN` | `123456789:AAH-xxxxxxxxxxxxxxxxxxxxx` |
| `TELEGRAM_CHAT_ID` | `987654321` |
| `WEBUNTIS_SERVER` | `ajax.webuntis.com` |
| `WEBUNTIS_SCHOOL` | `ks-musterstadt` |
| `WEBUNTIS_USERNAME` | `max.mustermann` |
| `WEBUNTIS_PASSWORD` | dein Passwort |

Optional ist `WEBUNTIS_KLASSE` — siehe [Einstellungen](#einstellungen).

`LOOKAHEAD_DAYS` und `TIMEZONE` gehören **nicht** hierher. Der Workflow setzt
beide direkt als Umgebungsvariable, und die gewinnt immer gegen ein Secret
gleichen Namens — ein Secret dafür bliebe also wirkungslos. Wer die Werte
ändern will, ändert sie in `.github/workflows/check-timetable.yml`.

### 5. Ausprobieren

*Actions → „Stundenplan pruefen" → Run workflow*, bei **modus** `testmessage`
wählen, starten.

Nach ein bis zwei Minuten sollte eine Beispielnachricht in Telegram liegen.
Unter der Nachricht steht ein Befund, der dir die Frage beantwortet, die man
dem Bot im Betrieb sonst nicht ansieht:

```
— Befund —
Stundenraster: verfügbar (5 Tage, 11 Stunden) — echte Meldungen sehen aus wie oben.
```

Steht dort **NICHT verfügbar**, gibt deine Schule das Stundenraster nicht an
Schüler-Accounts heraus. Der Bot funktioniert trotzdem, zeigt aber Uhrzeiten
statt Stundennummern und fasst keine Doppelstunden zusammen.

> Zeigt der Dialog gar kein Feld **modus**, liest GitHub die Eingabefelder noch
> aus der Datei auf dem Standard-Branch. Dann startet der Lauf als normale
> Überwachung statt als Testnachricht — kein Schaden, nur nicht das, was du
> wolltest.

Kommt nichts an: *Run workflow* noch einmal, diesmal mit **modus** `selftest`.
Der prüft Token, jede Chat-ID und WebUntis **einzeln** und schreibt in die
Lauf-Ausgabe, welcher Zugang klemmt. Er ändert nichts — kein Zustand, kein
Commit, keine Nachricht.

Danach läuft der Bot von allein — rund um die Uhr. Der Zeitplaner stößt die
Kette an, jeder Lauf überwacht 5,5 Stunden und der nächste steht schon bereit.
Geprüft wird alle 5 Minuten während der Schulzeit, sonst alle 30 Minuten.

### Der kürzere Weg

Wenn jemand den Bot schon betreibt und ihr **denselben** Stundenplan habt,
braucht ihr weder Repo noch Secrets. Diese Person trägt eure Chat-IDs
kommagetrennt in ihr `TELEGRAM_CHAT_ID` ein:

```
987654321,555666777,111222333
```

Jeder muss vorher einmal `/start` an den Bot schicken. Hängt ein Chat, gehen
die Nachrichten an die anderen trotzdem raus.

**Der Haken:** Verschickt wird der *persönliche* Plan der einrichtenden
Person, inklusive ihrer Kurswahl. Wer andere Kurse belegt, bekommt Meldungen
zu Stunden, die er nicht hat — und verpasst seine eigenen. Für identische
Stundenpläne ist das der mit Abstand einfachste Weg, sonst richtet jeder
besser sein eigenes Repo ein.

## Befehle

| Befehl | Wirkung |
|---|---|
| `python bot.py check` | einmal prüfen, melden, Zustand sichern |
| `python bot.py check --dry-run` | prüfen und die Nachricht ausgeben, ohne zu senden oder zu speichern |
| `python bot.py watch --minutes 330` | 5,5 Stunden lang prüfen; `--interval` (Standard 300 s) gilt in der Schulzeit, `--night-interval` sonst |
| `python bot.py selftest` | jeden Zugang einzeln durchtesten und sagen, was klemmt |
| `python bot.py testmessage` | Beispielnachricht senden — ohne jede Wirkung auf den Betrieb |
| `python bot.py alert "..."` | Störmeldung senden (`--quelle` für den Link zum Lauf) |
| `python bot.py show --days 3` | Stundenplan im Klartext anzeigen |

`--log DEBUG` und `--version` gibt es zu jedem Befehl.

## Einstellungen

Alles kommt aus Umgebungsvariablen — im Code steht nichts Persönliches. Lokal
aus einer `.env`, auf GitHub aus den Actions-Secrets. Vorhandene
Umgebungsvariablen gewinnen, eine mitgelieferte `.env` überschreibt die
Secrets also nie.

| Variable | | Bedeutung |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Pflicht | vom `@BotFather`, enthält immer einen Doppelpunkt |
| `TELEGRAM_CHAT_ID` | Pflicht | eine ID oder mehrere, kommagetrennt; Gruppen-IDs sind negativ |
| `WEBUNTIS_SERVER` | Pflicht | z. B. `ajax.webuntis.com`, ohne `https://` und ohne Schrägstrich |
| `WEBUNTIS_SCHOOL` | Pflicht | Schulkürzel aus der WebUntis-URL |
| `WEBUNTIS_USERNAME` | Pflicht | |
| `WEBUNTIS_PASSWORD` | Pflicht | |
| `WEBUNTIS_KLASSE` | optional | **Rückfall**, kein Umschalter — siehe unten |
| `LOOKAHEAD_DAYS` | optional | Vorausschau in Tagen, Standard 7, begrenzt auf 1–30 |
| `TIMEZONE` | optional | Standard `Europe/Berlin` |
| `LOG_LEVEL` | optional | Standard `INFO`; `DEBUG` zeigt auch, was die `webuntis`-Bibliothek treibt. `--log` auf der Kommandozeile gewinnt |

`WEBUNTIS_KLASSE` greift **nur**, wenn der persönliche Stundenplan gar nicht
abrufbar ist. Liefert `my_timetable` Stunden, gewinnt der immer. Wer den
Klassenplan verschicken will statt des eigenen, braucht dafür eine
Code-Änderung.

## Lokal ausführen

Praktisch zum Prüfen, ohne auf einen Actions-Lauf zu warten:

```bash
git clone <dein-repo>
cd untisnotification
pip install -r requirements.txt
```

Dann eine Datei `.env` anlegen. Sie steht in `.gitignore` und landet nie im
Repo:

```dotenv
TELEGRAM_BOT_TOKEN=123456789:AAH-xxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=987654321
WEBUNTIS_SERVER=ajax.webuntis.com
WEBUNTIS_SCHOOL=ks-musterstadt
WEBUNTIS_USERNAME=max.mustermann
WEBUNTIS_PASSWORD=

# Optional, hier mit den Standardwerten:
#WEBUNTIS_KLASSE=
#LOOKAHEAD_DAYS=7
#TIMEZONE=Europe/Berlin
#LOG_LEVEL=INFO
```

```bash
python bot.py selftest          # jeden Zugang einzeln prüfen
python bot.py show              # Stundenplan im Klartext
python bot.py check --dry-run   # prüfen, ohne zu senden oder zu speichern
```

> Nimm lokal `check --dry-run`, nicht `check`. In einem geklonten Repo findet
> der Bot ein `.git`-Verzeichnis und sichert seinen Zustand wie in der Cloud —
> er würde also `state.json` committen und pushen. `selftest`, `show` und
> `--dry-run` fassen den Zustand nicht an.

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

## Wenn etwas schiefgeht

Der Bot meldet sich von selbst — zweistufig, weil ein Job, der nie startet,
sich auch nicht beschweren kann.

**Ein Lauf scheitert** → der Workflow schickt eine Telegram-Meldung mit Link
zum fehlgeschlagenen Lauf. Das greift bei abgelehnten Zugangsdaten, einem
anhaltenden Ausfall, einer übersehenen Ausnahme und beim Timeout.

Eine einzelne Störung beendet den Lauf **nicht**. Nach jedem Fehlschlag wird
der Takt verdoppelt (gedeckelt bei 15 Minuten); erst nach sechs Fehlschlägen in
Folge gibt der Lauf auf. Eine halbstündige WebUntis-Wartung kostet damit drei
Fehlversuche statt des ganzen 5,5-Stunden-Platzes.

**Es läuft gar nichts mehr** → der Wachhund (`watchdog.yml`) sieht alle vier
Stunden nach, wann der letzte **geplante** Überwachungslauf begonnen hat. Ist
das länger als 8 Stunden her, meldet er sich. Genau dieser Fall ist schon
eingetreten: Die Laufkette stand drei Tage still und fiel nur durch zufälliges
Nachsehen auf.

Anwerfen lässt sie sich von Hand: *Actions → „Stundenplan pruefen" → Run
workflow*, **modus** auf `watch` lassen und **minuten** nicht anfassen. Der Standard ist
der volle 5,5-Stunden-Lauf — genau deshalb, denn erst der hinterlässt wieder
einen wartenden Lauf. Ein kurzer Lauf endet, und danach steht die Kette wieder.

Zwei Grenzen, die kein Code beheben kann:

* **Ist Telegram selbst kaputt**, kann der Bot sich nicht über Telegram
  melden. Dann bleibt nur GitHubs eigene Fehlermail an den Repo-Besitzer.
* **Löst GitHub gar nichts mehr aus**, schweigt auch der Wachhund — er hängt
  an derselben Cron-Mechanik. Er fängt den häufigeren Fall ab: Die Kette
  reißt, während der Rest von GitHub weiterläuft.

Abgebrochene Läufe lösen **keine** Meldung aus. „Cancelled" ist kein
„failure", und die Laufkette bricht ständig wartende Läufe ab — jeder davon
würde sonst eine Meldung auslösen.

### Wenn etwas klemmt

| Meldung | Ursache |
|---|---|
| `TELEGRAM_BOT_TOKEN hat ein unerwartetes Format` | im Token fehlt der Doppelpunkt — vermutlich unvollständig kopiert |
| `chat not found` | `/start` an den Bot fehlt, oder die Chat-ID stimmt nicht |
| `Der Bot darf diesem Chat nicht schreiben` | blockiert oder aus der Gruppe entfernt |
| `Anmeldung abgelehnt` | Benutzername, Passwort oder Schulkürzel falsch |
| `Kein Schuljahr deckt … ab` | Ferien, oder das neue Schuljahr ist in WebUntis noch nicht angelegt. Kein Fehler, der Bot wartet es aus. |
| Es kommt gar nichts | Erst nach dem *ersten* Lauf kann verglichen werden — der merkt sich nur den Stand. Ansonsten: Gibt es gerade überhaupt Änderungen? |
| Läufe starten nicht | Actions im Repo aktiviert? Nach 60 Tagen ohne Commit schaltet GitHub geplante Workflows ab. |

## Achtung: `state.json` ist öffentlich lesbar

Das Repo muss public sein (siehe [Repo anlegen](#3-repo-anlegen)), und der Bot
legt seinen Zustand darin ab. Damit steht der Stundenplan im Netz — Fächer,
Räume, Zeiten, Kursgruppen, für jeden lesbar:

```json
{"uid": 842774, "date": "2026-09-15", "start": "07:40", "end": "08:25",
 "subjects": ["D(G2)"], "rooms": ["H1.04"], "group": "D(G2)_3WGI13_..."}
```

Zwei Dinge, die man dabei leicht übersieht:

* **Die Lehrerkürzel stehen trotzdem drin.** Das Feld `teachers` bleibt leer,
  weil die Schule Lehrerdaten nicht an Schülerkonten ausliefert — aber in
  `group` hängen sie hinten dran (`…_3WGI13_1_Ab`), zusammen mit der Klasse.
  Wer nur auf `teachers` schaut, hält den Plan für anonymer, als er ist.
* **Die Historie zählt mit.** Jeder Lauf committet die Datei neu. Sie später
  zu löschen entfernt sie aus dem aktuellen Stand, nicht aus den alten
  Commits — dafür bräuchte es einen Eingriff in die Historie und ein
  force-push.

Wer das nicht will, muss den Zustand woanders ablegen (Actions-Cache statt
Commit) — dann kann er verlorengehen, was ungefährlich ist: Ein Lauf ohne
gespeicherten Zustand meldet nichts, er merkt sich nur neu. Die Alternative
ohne diesen Nachteil wäre, `state.json` vor dem Commit zu verschlüsseln; ein
Secret dafür ist ohnehin schon da.

## Aufbau

Das Repo besteht aus 11 Dateien, und jede hat genau eine Aufgabe:

```
bot.py                                 der ganze Bot
tests/test_bot.py                      Tests, ohne Netz lauffähig
requirements.txt                       Abhängigkeiten
pyproject.toml                         Einstellungen für pytest und ruff
.gitignore                             hält .env und lokale Zustände draußen
state.json                             das Gedächtnis des Bots
README.md                              diese Datei
CHANGELOG.md                           was sich wann geändert hat
.github/workflows/check-timetable.yml  die Laufkette
.github/workflows/watchdog.yml         meldet, wenn gar nichts mehr läuft
.github/workflows/tests.yml            Linter und Tests bei jedem Push
```

Die drei Workflows sind bewusst drei Dateien. Sie sind keine Kapitel eines
Dokuments, sondern drei Systeme mit drei Auslösern, drei Rechten und drei
Bedeutungen von „rot":

* Der **Wachhund** fragt GitHub, wann der letzte geplante Lauf der Kette
  begann. Läge er in derselben Datei, zählte er seine eigenen Läufe als
  Lebenszeichen und meldete „alles in Ordnung", während die Kette längst tot
  ist. Er braucht außerdem `actions: read`, die Kette `contents: write`.
* Die **Tests** hingen in derselben Datei an der workflow-weiten
  `concurrency` der Kette. Schlimmer als die Wartezeit von bis zu 5,5
  Stunden: Ein Push-Lauf in dieser Gruppe ersetzte den wartenden Kettenlauf
  — jeder Push kostete dann ein ganzes Glied der Laufkette.

Der Bot selbst ist dagegen **eine** Datei. Auch das ist Absicht: Das Projekt
ist klein genug, und beim Einspielen über die GitHub-Weboberfläche ist eine
Datei ein Bruchteil der Arbeit von acht.

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

python -m pytest             # keine Netzverbindung nötig
ruff check .                 # Linter
```

Beides läuft bei jedem Push auch in GitHub Actions
(`.github/workflows/tests.yml`). Die Einstellungen stehen in
`pyproject.toml`; dort ist auch begründet, welche Linter-Regeln bewusst
abgewählt sind und warum.

Bei sicherheitskritischer Logik gilt zusätzlich ein Mutationstest:
Guard-Klausel testweise entfernen, prüfen dass ein Test rot wird,
zurücksetzen. Jeder Test, an dem so eine Zusicherung hängt, trägt im
Docstring das Wort `SICHERHEITSNETZ` und die Mutation, die ihn rot machen
muss. Diese Tabelle listet **alle** — ein Test wacht darüber, dass sie
vollständig bleibt:

| Zusicherung | Wächter |
|---|---|
| nie dieselbe Änderung zweimal melden | `test_check_meldet_dieselbe_aenderung_nie_zweimal` |
| der gemeldete Stand landet auch im Repo, nicht nur auf der Platte | `test_check_sichert_zustand_auch_nach_dem_melden` |
| eine Teilzustellung gilt als Erfolg — Wiederholen erzeugt Dopplungen | `test_send_teilzustellung_gilt_als_erfolg` |
| ein git-Fehler kippt nie einen Lauf, in dem schon gesendet wurde | `test_commit_state_wirft_nie` |
| keine Massenmeldung bei Datenproblemen | `test_unplausibel_wenn_grosser_teil_weg` |
| „findet doch statt“ nennt auch den neuen Raum und die Vertretung | `test_compare_ausfall_zurueckgenommen_nennt_raum_und_vertretung` |
| auch an einer abgesagten Stunde ändert sich noch etwas | `test_compare_bleibt_abgesagt_meldet_geaenderte_info` |
| unveränderter Zustand wird nicht neu geschrieben (Commit-Flut) | `test_save_state_schreibt_unveraenderten_zustand_nicht_neu` |
| eine Testnachricht ändert nichts am Zustand | `test_testmessage_ruehrt_den_zustand_nicht_an` |
| eine Störmeldung ändert nichts am Zustand | `test_alert_ruehrt_den_zustand_nicht_an` |
| der Telegram-Token steht in keiner Fehlermeldung | `test_telegram_call_leakt_den_token_nicht` |
| der WebUntis-Benutzername steht in keiner Diagnoseausgabe | `test_selftest_zeigt_den_benutzernamen_nicht_im_klartext` |
| ein kaputtes Datum tötet nicht jeden weiteren Lauf | `test_from_json_weist_kaputtes_datum_ab` |
| WebUntis-Aufrufe hängen nicht unbegrenzt | `test_enforce_network_timeout_setzt_grenze` |
| Parallelkurse verschmelzen nicht zu einer falschen Meldung | `test_entry_trennt_parallelkurse_desselben_fachs` |
| `split()` zerreißt die HTML-Auszeichnung nicht | `test_split_zerreisst_die_auszeichnung_nicht` |
| ein Dauerausfall endet mit Exit 1 (sonst käme keine Störmeldung) | `test_watch_bricht_nach_failure_limit_ab` |
| jeder `run`-Block der Workflows ist gültige Shell | `test_workflow_shell_ist_syntaktisch_gueltig` |

Der letzte ist aus Schaden entstanden: In 2.3.0 rutschte beim Einfügen des
Meldeschritts das schließende `fi` des Überwachungsschritts in den neuen
Schritt. Jeder Lauf wäre vor der ersten Zeile gescheitert — und die
Störmeldung am selben Fehler mit. Die damalige Abnahme prüfte nur, dass das
YAML parst und der Schritt existiert, nicht dass das Skript darin läuft.

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

Copyright © 2026 77crj2ksb8-maker. Alle Rechte vorbehalten.

> Trage hier deinen bürgerlichen Namen oder Firmennamen ein, wenn du dich
> rechtlich darauf berufen willst. Ein Pseudonym genügt für eine
> Urheberrechtsbehauptung meist, macht die Durchsetzung aber schwerer.

**Einsehbar, nicht frei.** Dieses Repository ist öffentlich lesbar. Das ist
eine technische Notwendigkeit, keine Freigabe: GitHub Actions ist nur für
öffentliche Repositories unbegrenzt kostenlos, und der Bot braucht diese
Laufzeit. Öffentlich sichtbar heißt **nicht** quelloffen.

Ohne ausdrückliche schriftliche Erlaubnis des Rechteinhabers ist nicht
gestattet:

* den Quelltext zu kopieren, zu verändern oder weiterzugeben
* ihn ganz oder in Teilen in eigene Projekte zu übernehmen
* eine eigene Instanz des Bots zu betreiben
* ihn kommerziell zu verwerten

Erlaubt ist das Lesen des Quelltextes. Wer den Bot nutzen möchte, fragt den
Rechteinhaber. Eine Erlaubnis kann formlos erteilt werden und gilt dann nur
für die Person, der sie erteilt wurde.

**Fremde Bestandteile.** Die verwendeten Bibliotheken stehen unter ihren
eigenen Lizenzen und sind von dieser Einschränkung nicht berührt: `requests`
(Apache 2.0), `webuntis` (BSD 3-Clause, inoffiziell, nicht von der Untis
GmbH), `pytest` (MIT), `ruff` (MIT), `PyYAML` (MIT).

„WebUntis" und „Untis" sind Marken der Untis GmbH. Dieses Projekt steht in
keiner Verbindung zu ihr und wird von ihr weder unterstützt noch geprüft.

**Keine Gewähr.** Die Software wird bereitgestellt „wie sie ist", ohne
Gewährleistung jeder Art. Der Rechteinhaber haftet nicht für Schäden, die aus
ihrer Nutzung entstehen — insbesondere nicht dafür, dass eine
Stundenplanänderung nicht, verspätet oder falsch gemeldet wird. Verbindlich
ist immer der Stundenplan in WebUntis selbst; der Bot ist eine Bequemlichkeit,
keine Garantie.
