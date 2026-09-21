# Änderungen

Das Format folgt lose [Keep a Changelog](https://keepachangelog.com/de/).

## 2.7.0 — 2026-09-21

Aufräumen: vierzehn Dateien auf elf, dazu zwei Fehler in den Workflows und
einer in `split()`, gefunden bei der Durchsicht danach.

### Behoben

* **Ein gescheitertes `git fetch` blieb folgenlos.** Der Schritt „Auf den
  aktuellen Stand bringen" lief ohne `set -e`; der Rückgabewert war also der
  des abschließenden `echo`. Fällt das Netz während des Fetch aus, liefe der
  Job stillschweigend auf dem veralteten Checkout weiter — und meldete genau
  die Dopplungen, gegen die dieser Schritt überhaupt eingebaut wurde. Jetzt
  scheitert er laut, und die Störmeldung greift.

* **Der Wachhund zählte eine Testnachricht als Lebenszeichen.** Er fragte den
  *neuesten* Lauf des Bot-Workflows ab, unabhängig vom Auslöser. Ein von Hand
  gestarteter `testmessage`- oder `selftest`-Lauf dauert eine Minute und hält
  die Kette gerade **nicht** am Leben — ausgerechnet am Tag, an dem jemand
  nach einem Aussetzer eine Testnachricht schickt, hätte der Wachhund
  geschwiegen. Die Abfrage filtert jetzt auf `event=schedule`.

* **`split()` zerriss im Notfallzweig doch ein Tag.** Passen die
  schließenden Tags nicht mehr ins Limit, schnitt die Funktion hart auf
  `line[:limit]` — ohne Rücksicht auf Tags und Entitäten:

  ```
  vorher:  ['<b>x<i>y</i', '>z</b>ww']
  nachher: ['<b>x<i>y',    '</i>z</b>ww']
  ```

  Das zweite Stück begann mit einem nackten `>`, das Telegram als Text
  anzeigt. Der Zweig greift, wenn zwischen Schnittpunkt und Limit ein Tag
  zugeht: Die Rücklage wird aus `line[:limit]` berechnet, der Stapel aber am
  Schnittpunkt — und der ist dann tiefer.

  Gefunden mit einer Eigenschaftssuche über 100.000 zufällige Nachrichten.
  **Bei `SPLIT_AT = 3500` trat der Fall nie ein** (0 von 40.000 bei Grenzen
  von 500 bis 4000), der alte Kommentar hatte insofern recht. Bei kleineren
  Grenzen schlug er zuverlässig zu — eine Mine für den Tag, an dem jemand
  das Limit senkt. Mutationsgeprüft.

### Geändert

* **Vierzehn Dateien auf elf.** `SETUP.md`, `COPYRIGHT` und `.env.example`
  sind im README aufgegangen: Sie sprachen denselben Leser zur selben Zeit an,
  und die `.env`-Vorlage wiederholte nur die Einstellungstabelle. Die
  Nutzungsrechte stehen jetzt als Abschnitt dort, wo sie auch gelesen werden.

  Nicht zusammengelegt wurden die drei Workflows, und zwar aus Gründen, nicht
  aus Bequemlichkeit: Der **Wachhund** fragt, wann der letzte geplante Lauf
  des Bot-Workflows begann — in derselben Datei zählte er seine eigenen Läufe
  als Lebenszeichen. Die **Tests** hingen dort an der workflow-weiten
  `concurrency` der Laufkette; ein Push müsste bis zu 5,5 Stunden auf seine
  Prüfung warten. `.gitignore` kann ebenfalls nicht weg: Eine ignorierte
  `.gitignore` ignoriert nichts, und sie ist der einzige Schutz davor, dass
  eine `.env` im öffentlichen Repo landet.

* **Der Klassenplan-Rückfall hat jetzt Tests.** `_by_klasse` war die einzige
  Funktion ohne jede Abdeckung — und sie greift ausschließlich dann, wenn der
  persönliche Stundenplan schon klemmt. Ein Fehler darin wäre genau in dem
  Moment aufgefallen, in dem man ihn am wenigsten gebrauchen kann. Fünf neue
  Tests, darunter zwei für die Verdrahtung: Ein **leerer** persönlicher Plan
  darf den Klassenplan nicht auslösen, sonst verschickte der Bot bei einem
  stillen Ausfall den Plan der ganzen Klasse als Massen-Änderung.

* 463 → 469 Tests.

## 2.6.0 — 2026-09-21

Ergebnis der zweiten Prüfrunde: zwei Auditoren, zwei Developer. Kein neues
Verhalten im Bot — diese Version schließt Lücken in den Tests, in der
Bedienung von Hand und in der Doku.

### Behoben

* **Tests, die grün waren, ohne zu prüfen.** Für jeden Punkt hier ist per
  Mutationstest belegt, dass die genannte Änderung am Code ihn jetzt rot
  macht — vorher überlebte sie die komplette Suite:

  | Test | war blind gegen |
  |---|---|
  | `test_pair_up_beste_paarung_gewinnt_nicht_die_erste` | entferntes `candidates.sort()` — der schwache Bewerber kam mangels gemeinsamem Raum gar nicht erst über die Schwelle |
  | `test_unplausibel_wenn_alles_weg` | entfernten `if not new`-Guard — `match="0 Stunden"` passte auch auf „1**0 Stunden**" aus dem Prozent-Zweig |
  | `test_load_state_verwirft_altes_schema` | ausgeschaltete Schema-Prüfung — es griff in Wahrheit der Fenster-Guard |
  | die `ablauf`-Fixture | jede teilweise Fensterüberlappung: die Uhr stand fest, also galt in jedem Test `overlap(win, previous.window) == win`. Geprüft war nur der Sonderfall gar keiner Überlappung |

  Die Fixture hält die Uhr jetzt im Protokoll, und zwei neue Tests rollen
  das Fenster wie im Betrieb weiter: einmal, dass neu hineingerutschte
  Stunden nicht als „➕ neuer Termin" gemeldet werden (sonst käme jeden
  Morgen ein kompletter Schultag), und einmal, dass die Plausibilitätsbremse
  nur die Überlappung misst (sonst schlüge sie täglich an und der Bot
  meldete dauerhaft nichts mehr).

  Im selben Zug enger gefasst, ohne dass eine Mutation sie überlebt hätte:
  `test_unplausibel_wenn_grosser_teil_weg` prüfte auf `match="%"` und hätte
  damit jede beliebige `Implausible`-Meldung durchgewinkt, auch die aus dem
  Zweig daneben. Jetzt nennt das Muster die Zahlen.

  Dazu vier Zusicherungen, die überhaupt keinen Wächter hatten: der
  Zustand wird **auch nach dem Melden** committet (sonst holt der nächste
  Actions-Job einen Checkout mit der alten `state.json` und meldet
  dieselbe Änderung erneut), eine Teilzustellung gilt als Erfolg,
  `chronological()` ordnet gleichzeitige Stunden eindeutig, und
  `_load_dotenv` ignoriert `#KEY=value` — genau die Form, die
  `.env.example` liefert.

* **Der Standard für einen Handstart war 10 Minuten und riss damit genau
  die Kette ab, die man von Hand anwirft.** Ein kurzer Lauf endet, ohne
  einen wartenden Lauf zu hinterlassen; danach steht alles wieder still,
  bis der Zeitplaner sich erbarmt. Der Standard ist jetzt der volle Lauf
  (330 Minuten), in der Eingabemaske wie in `bot.py watch`. Wer schnell
  ein Ergebnis will, nimmt `selftest` oder `testmessage` — beide antworten
  in Sekunden und haben eine eigene `concurrency`-Gruppe.

* **`selftest` ließ sich nur lokal starten**, obwohl SETUP ihn als
  Notnagel nennt, wenn nichts ankommt. Er steht jetzt als dritter `modus`
  in der Eingabemaske.

* **SETUP verlangte `LOOKAHEAD_DAYS` und `TIMEZONE` als Secrets.** Der
  Workflow setzt beide als Umgebungsvariable, und die gewinnt immer — ein
  Secret dafür bliebe wirkungslos.

### Geändert

* Die Störmeldung des Wachhunds sagt jetzt **wie** man die Kette wieder
  anwirft. Wer sie abends auf dem Handy liest, hat kein README zur Hand.
* `render_plan()` entfernt. Nicht angeschlossen, und `bot.py show` gibt auf
  dem Terminal ohnehin mehr her.
* Die Liste der `SICHERHEITSNETZ`-Zusicherungen im README ist vollständig —
  zwei fehlten, und die Anzahl im Text stimmte seit zwei Versionen nicht.
  `test_readme_nennt_jedes_sicherheitsnetz` hält sie ab jetzt aktuell:
  ein neues Netz ohne Zeile in der Tabelle macht die Suite rot, eine
  verwaiste Zeile ebenso.
* SETUP nennt den Verbrauch an Actions-Minuten realistisch: im
  Dauerbetrieb über 40.000 im Monat, nicht „ein paar tausend".
* `LOG_LEVEL` steht jetzt in der Einstellungstabelle des README.
* Toter `per-file-ignores`-Block aus `pyproject.toml` entfernt.

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
