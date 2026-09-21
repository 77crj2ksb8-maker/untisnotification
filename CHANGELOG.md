# Änderungen

Das Format folgt lose [Keep a Changelog](https://keepachangelog.com/de/).

## 2.5.0 — 2026-09-21

### Behoben

* **Der Workflow war seit 2.3.0 kaputte Shell.** Beim Einfügen des
  Meldeschritts rutschte das schließende `fi` des Überwachungsschritts in
  den neuen Schritt. `bash` wäre vor der ersten Zeile abgebrochen — und die
  Störmeldung am selben Fehler gestorben, weil sie ebenfalls ein `run`-Block
  ist. Übrig geblieben wäre nur GitHubs Fehlermail; der Wachhund hätte
  geschwiegen, weil Läufe ja *starten*.

  Nie ausgeführt worden: Der Stand ging um 12:44 live, und GitHubs
  Zeitplaner hat seitdem keinen Lauf ausgelöst. Reines Glück.

  Neuer Wächter: `test_workflow_shell_ist_syntaktisch_gueltig` schickt jeden
  `run`-Block aller Workflows durch `bash -n`. Die damalige Abnahme hatte
  nur geprüft, dass das YAML parst und der Schritt existiert.

* **Parallelkurse desselben Fachs verschmolzen zu einer falschen Meldung.**
  Entfällt Sportgruppe A und wechselt Gruppe B nur den Raum, stand dort
  „❌ 3. Stunde · Sp — entfällt, Raumwechsel". Wer in B ist, wäre zu Hause
  geblieben. `lesson.group` geht jetzt in den Schlüssel von `build_entries`
  **und** in den Bucket-Schlüssel von `group_doppelstunden` — sonst hätte
  die Verkettung Stunde 2 der einen Gruppe an Stunde 1 der anderen gehängt.

* **`split()` zerschnitt überlange Zeilen mitten im HTML-Tag.** Telegram
  lehnte den Teil ab, der Rückfall schickte ihn als Klartext. Jetzt wird nur
  an Stellen geschnitten, die weder in einem Tag noch in einer Entität
  liegen; offene Tags werden geschlossen und im nächsten Teil wieder
  geöffnet.

* **„Findet doch statt" verschluckte gleichzeitige Änderungen.** Wurde eine
  Absage zurückgenommen und dabei Raum oder Lehrkraft getauscht, stand nur
  „findet doch statt". Eine weiterhin abgesagte Stunde mit geänderter
  Zusatzinfo meldete gar nichts.

* **`_commit_state` committete immer `BASE_DIR/state.json`**, egal welchen
  Pfad es bekam. Latent, im Produktivpfad identisch.

### Geändert

* **Eine kurze Störung beendet den Lauf nicht mehr.** Statt nach drei
  Fehlschlägen abzubrechen, verdoppelt sich der Takt je Fehlschlag (gedeckelt
  bei 15 Minuten), und erst nach sechs Fehlschlägen gibt der Lauf auf. Eine
  halbstündige WebUntis-Wartung kostet damit drei Fehlversuche statt des
  ganzen 5,5-Stunden-Platzes. Der Exit-Code 1 bei Dauerausfall bleibt
  ausdrücklich erhalten — daran hängt die Störmeldung.
* **`BULK_THRESHOLD` misst jetzt Einträge statt Änderungen.** Die Begründung
  „Fünfzig Zeilen liest niemand" trifft erst damit zu: Eine Vertretung mit
  Raumwechsel sind zwei Änderungen, aber eine Zeile.
* **`bot.py testmessage` nennt jetzt Stundenzahl und Alter des Zustands.**
  Damit lässt sich „Ferien" von „die Schule hat den Plan abgedreht"
  unterscheiden — bisher sahen beide von außen gleich aus, und der Bot wäre
  unbegrenzt grün und still geblieben.
* `selftest` maskiert den WebUntis-Benutzernamen.

### Sonstiges

* `pyyaml` als Test-Abhängigkeit, damit die Tests die Workflows lesen können.
* Testsuite: 411 → 460 Tests.

## 2.4.0 — 2026-09-21

Aus einem Audit-Durchgang. Der erste Punkt behebt einen Fehler, den erst
der Dauerbetrieb aus 2.2.0 gefährlich gemacht hat.

### Behoben

* **Die Laufkette meldete Änderungen doppelt.** `actions/checkout` holt
  nicht den aktuellen Branch-Kopf, sondern den SHA vom Moment der
  *Auslösung*. Ein wartender Lauf übernimmt aber bis zu 5,5 Stunden
  später — und bekam damit eine veraltete `state.json`, meldete die
  Änderungen des gerade beendeten Laufs erneut und konnte seinen eigenen
  Stand nie pushen (der Rebase kollidiert zwangsläufig, weil beide Seiten
  dieselbe `saved_at`-Zeile neu schreiben). Der Lauf gleicht sich jetzt vor
  dem Start auf den echten Branch-Kopf ab.

  Belegt an der Historie: Lauf 19 lief auf `fec69f6` und erzeugte
  `4636fc2`; Lauf 20 zwei Minuten später bekam `4636fc2`. Der SHA ist je
  Lauf eingefroren.

* **WebUntis-Aufrufe hatten kein Zeitlimit.** Die `webuntis`-Bibliothek
  setzt keines. Ein Server, der die Verbindung annimmt und dann schweigt,
  blockierte den Lauf bis zum Job-Limit — seit 2.2.0 also 5,5 Stunden
  Blindflug, ohne Fehlschlag, ohne Meldung. Jetzt gedeckelt auf 30
  Sekunden (`NETWORK_TIMEOUT`).

* **`Lesson.from_json` winkte kaputte Datumswerte durch.** Ein deutsches
  Datum, eine Zahl oder ein leerer String kamen durch und stürzten erst
  später in `within()` ab — außerhalb jeder Absicherung, und bei jedem
  weiteren Lauf identisch, weil `state.json` im Repo liegt. Das Datum wird
  jetzt beim Laden probeweise geparst, damit `load_state` den Eintrag
  überspringen kann, wie sein Kommentar es verspricht.

  Ausdrücklich ohne `str()`: Die Zahl `20260914` wäre als Zeichenkette ein
  gültiges ISO-Datum, bliebe im Feld aber eine Zahl — und `Lesson.day`
  stürzte doch ab. Das ist beim Testen des eigenen Fixes aufgefallen.

### Sonstiges

* Testsuite: 403 → 411 Tests.

## 2.3.0 — 2026-09-21

### Neu

* **Störmeldungen.** Der Bot meldet sich von selbst, wenn etwas nicht
  funktioniert, statt darauf zu hoffen, dass jemand in den Actions-Tab
  schaut. Zwei Stufen:
  * Ein fehlgeschlagener Lauf löst über `if: failure()` eine Telegram-Meldung
    mit Link zum Lauf aus — bei abgelehnten Zugangsdaten, drei Fehlschlägen in
    Folge, einer übersehenen Ausnahme oder einem Timeout. Abgebrochene Läufe
    lösen bewusst nichts aus, sonst meldete sich jeder von der Laufkette
    ersetzte wartende Lauf.
  * Der neue Workflow `watchdog.yml` sieht alle vier Stunden von außen nach,
    wann zuletzt ein Überwachungslauf begonnen hat, und meldet einen
    Stillstand von mehr als 8 Stunden. Das deckt den Fall ab, den sonst
    niemand melden kann: Es läuft überhaupt nichts mehr.
* **`bot.py alert "<text>" [--quelle ...]`** als neuer Unterbefehl. Fasst
  weder Zustand noch Stundenplan an.
* `Config.from_env(telegram_only=True)` verlangt keine WebUntis-Werte. Sonst
  könnte der Wachhund nicht melden, dass nichts mehr läuft — ausgerechnet
  dann, wenn die Meldung am nötigsten ist.

### Sonstiges

* Testsuite: 391 → 403 Tests.

## 2.2.0 — 2026-09-21

### Neu

* **Dauerbetrieb rund um die Uhr.** Der Cron läuft jetzt an jedem Tag zu jeder
  Stunde und dient nur noch als Anlasser; jeder Lauf überwacht 5,5 Stunden
  statt 55 Minuten. Die `concurrency`-Gruppe hält immer einen Lauf bereit, der
  nahtlos übernimmt — so entsteht eine lückenlose Kette, obwohl ein einzelner
  Actions-Job nur 6 Stunden laufen darf.
* **Takt nach Tageszeit** (`interval_for`): alle 5 Minuten werktags zwischen 6
  und 19 Uhr, sonst alle 30 Minuten. Neuer Schalter `--night-interval`; ohne
  ihn bleibt der Takt konstant wie bisher. Spart im Dauerbetrieb rund zwei
  Drittel der WebUntis-Anmeldungen.

### Behoben

* `render_summary` nahm ein Argument `today` entgegen und benutzte es nie. Die
  Tests reichten dort ein Datum hinein, das stillschweigend als Zusatznotiz in
  der Nachricht landete — sichtbar als Datumszeile unter der Überschrift. Das
  Argument ist weg, ein Wächtertest hält die Stelle offen.
* „1 Änderungen an 1 Tag" → „1 Änderung". In der Praxis unerreichbar, weil die
  Kurzfassung erst ab 40 Änderungen greift.

### Sonstiges

* `confirm_or_hold()` aus `check_once` herausgelöst. Der Docstring von `State`
  verwies schon auf diese Funktion — es gab sie nur nicht, die Logik stand
  eingebettet in der mit Abstand längsten Funktion des Programms.
* `bot.py` ist jetzt ausführbar; der Shebang war vorhanden, die Rechte fehlten.
* `subprocess.run` mit ausdrücklichem `check=False`.
* Testsuite: 366 → 391 Tests.

## 2.1.0 — 2026-09-15

### Neu

* **Doppelstunden werden zusammengefasst.** Aufeinanderfolgende gleichartige
  Änderungen erscheinen als ein Eintrag: „1./2. Stunde" statt zweier
  wortgleicher Zeilen. Braucht das Stundenraster von WebUntis.
* **Mehrere Änderungsarten je Stunde werden gebündelt.** Eine Vertretung mit
  Raumwechsel ist ein Eintrag („Vertretung, Raumwechsel"), nicht zwei. Reichen
  die Änderungen unterschiedlich weit — Vertretung über beide Stunden, Raum nur
  über die erste — bleiben es getrennte Einträge.
* **Stundennummern statt Uhrzeiten**, auch bei Einzelstunden. Die Uhrzeit bleibt
  der Rückfall, wenn kein Raster vorliegt oder die Stunde nicht darin steht.
* **`bot.py testmessage`** schickt eine Beispielnachricht, ohne Zustand oder
  Kalender anzufassen. Darunter ein Befund, ob das Stundenraster abrufbar ist.
* **`bot.py --version`.**
* **Testsuite:** 366 Tests, ohne Netz und ohne Zugangsdaten lauffähig.
* **CI:** Linter und Tests laufen bei jedem Push.
* **README.md, SETUP.md, .env.example, COPYRIGHT.**

### Behoben

* **Der Telegram-Token konnte in Fehlermeldungen landen.** `requests` nennt bei
  Netzwerkfehlern die vollständige URL, und die enthält den Token. Die Meldung
  wurde bis in die Job-Ausgabe durchgereicht. Token werden jetzt herausgefiltert.
* `render_plan` sortierte nur nach Tag und Uhrzeit. Bei zwei gleichzeitigen
  Stunden hing die Reihenfolge davon ab, wie WebUntis gerade auslieferte.

### Sonstiges

* Linter (ruff) eingeführt, Konfiguration in `pyproject.toml`.
* Tote Kopie von `check-timetable.yml` in der Wurzel entfernt.
* 33 Variablen namens `l` umbenannt — im Editor kaum von einer Eins zu
  unterscheiden.

## 2.0

Ausgangsstand: Abruf, Vergleich, Telegram-Versand, Selbsttaktung über
`watch`, Plausibilitätsbremse, Zustandssicherung per git.
