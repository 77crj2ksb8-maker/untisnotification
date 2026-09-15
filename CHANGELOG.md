# Änderungen

Das Format folgt lose [Keep a Changelog](https://keepachangelog.com/de/).

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
