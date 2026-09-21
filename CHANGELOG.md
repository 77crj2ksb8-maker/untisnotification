# Änderungen

Das Format folgt lose [Keep a Changelog](https://keepachangelog.com/de/).

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
