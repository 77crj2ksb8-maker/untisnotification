# Änderungen

Kurzfassung, ein Absatz je Version. **Die ausführliche Fassung steht in
`git log`** — dort auch die Mutationsproben, die Messreihen und die
Begründungen, warum etwas *nicht* gemacht wurde.

## 2.8.0 — 2026-09-22

Verdichtungsrunde. Kein Verhalten geändert, keine Datei entfernt — die
Redundanz saß nicht in der Dateiliste, sondern im Fließtext: 29 % des Repos
waren Prosa, vieles davon in zweiter und dritter Fassung.

* **Dieser CHANGELOG ist auf ein Drittel eingedampft** (17 → 6,6 kB). Die
  sieben Versions-Commits tragen zusammen mehr Text als die Langfassung hier;
  gestrichen wurde nur, was dort vollständiger steht. Nicht gelöscht wurde die
  Datei: Wer dem README folgt und über „Use this template" einrichtet, bekommt
  laut GitHub-Doku ein Repo, das „starts with a single commit" — die
  `git log`-Historie erreicht das ausgelieferte Produkt also gar nicht.
* **Der Architektur-Essay lebt nur noch im README.** Die Workflow-Köpfe
  wiederholten ihn in zweiter Fassung und verweisen jetzt darauf. Alle
  betriebsnahen Kommentare bleiben wortgleich an ihrer Zeile — die haben in
  diesem Projekt schon zwei Ausfälle verhindert, die Essays keinen.
* **Neuer Wächter `test_readme_listet_genau_die_versionierten_dateien`.** Die
  Dateiliste im README war reine Behauptung: Wer eine Datei anlegt oder
  löscht, merkte nichts. Geprüft wird in beide Richtungen, samt der Zahl im
  Einleitungssatz.
* Das handgepflegte Inhaltsverzeichnis ist weg; GitHub rendert für jede
  Markdown-Datei ein Gliederungsmenü.

**Geprüft und verworfen:** `state.json` kompakter zu serialisieren hätte die
Datei um 45 % verkleinert, die gepackte Historie aber nur um **0,11 %** (300
Commits simuliert, `.git` nach `git gc`: 285.832 → 285.513 Bytes) — Git
delta-komprimiert wiederholte Default-Felder praktisch gratis. Dafür wird das
einzige Gedächtnis eines 24/7-Systems nicht angefasst. Ebenso verworfen:
`requirements.txt` in `pyproject.toml` auflösen (ein vergessener
`cache-dependency-path` risse Laufkette und Wachhund gleichzeitig ab) und die
`.gitignore`-Kommentare kürzen (sie erklären die einzige kontraintuitive Regel
des Repos, und kein Test bewacht diese Datei).

## 2.7.0 — 2026-09-21

Vierzehn Dateien wurden elf: `SETUP.md`, `COPYRIGHT` und `.env.example` gingen
im README auf. Die drei Workflows blieben getrennt — ein einverleibter
Wachhund- oder Test-Lauf käme in die `concurrency`-Gruppe der Laufkette und
verdrängte dort den wartenden Nachfolger.

* **Ein gescheitertes `git fetch` blieb folgenlos.** Ohne `set -e` liefe der Job
  bei Netzausfall stumm auf dem veralteten Checkout weiter — und meldete genau
  die Dopplungen, gegen die der Schritt eingebaut wurde.
* **Der Wachhund zählte eine Testnachricht als Lebenszeichen.** Ein
  `testmessage`-Lauf dauert eine Minute und hält die Kette nicht am Leben; die
  Abfrage filtert jetzt auf `event=schedule`.
* **`split()` zerriss im Notfallzweig doch ein Tag**, wenn zwischen
  Schnittpunkt und Limit ein Tag zuging. Bei `SPLIT_AT = 3500` trat der Fall
  **0 von 40.000 Mal** auf (Grenzen 500–4000), bei kleineren zuverlässig.
* Der Klassenplan-Rückfall hat jetzt Tests — er greift nur, wenn der
  persönliche Plan schon klemmt.

## 2.6.0 — 2026-09-21

Ergebnis einer Prüfrunde aus zwei Auditoren und zwei Developern. Kein neues
Verhalten, sondern geschlossene Lücken in Tests, Bedienung und Doku.

* **Mehrere Tests waren grün, ohne zu prüfen** — darunter eine Fixture, die die
  Uhr festhielt und damit jede teilweise Fensterüberlappung ungeprüft ließ.
  Jeder Fall ist per Mutationsprobe belegt.
* **Vier Zusicherungen hatten keinen Wächter**, darunter: Der Zustand wird auch
  nach dem Melden committet — sonst holt der nächste Job einen Checkout mit der
  alten `state.json` und meldet dieselbe Änderung erneut.
* **Der Handstart-Standard von 10 Minuten riss die Kette ab**, die man von Hand
  anwirft: Ein kurzer Lauf hinterlässt keinen wartenden Nachfolger. Jetzt 330.
* `selftest` steht jetzt als dritter `modus` in der Eingabemaske.

## 2.5.0 — 2026-09-21

Die Runde, in der ein selbst eingebauter Fehler auffiel, der durch zwei eigene
Abnahmen gerutscht war.

* **Der Workflow war seit 2.3.0 kaputte Shell.** Ein verrutschtes `fi` hätte
  jeden Lauf vor der ersten Zeile abbrechen lassen — und die Störmeldung am
  selben Fehler mit, weil sie ebenfalls ein `run`-Block ist. Ausgeführt wurde
  der Stand nie, reines Glück. Seitdem schickt ein Test jeden `run`-Block durch
  `bash -n`.
* **Parallelkurse desselben Fachs verschmolzen zu einer falschen Meldung.**
  Entfällt Sportgruppe A und wechselt B nur den Raum, stand dort „entfällt,
  Raumwechsel" — wer in B ist, wäre zu Hause geblieben.
* **`split()` zerschnitt überlange Zeilen mitten im HTML-Tag**, Telegram lehnte
  den Teil ab. **„Findet doch statt" verschluckte gleichzeitige Änderungen** —
  eine zurückgenommene Absage mit getauschtem Raum meldete nur „findet doch
  statt".
* **Eine kurze Störung beendet den Lauf nicht mehr.** Der Takt verdoppelt sich
  je Fehlschlag (gedeckelt bei 15 Minuten), Abbruch erst nach sechs
  (`FAILURE_LIMIT`) — eine halbstündige Wartung kostet damit drei Fehlversuche
  statt des ganzen 5,5-Stunden-Platzes. Exit-Code 1 bei Dauerausfall bleibt,
  daran hängt die Störmeldung.
* **`BULK_THRESHOLD` misst Einträge statt Änderungen**, Schwelle 40: Eine
  Vertretung mit Raumwechsel sind zwei Änderungen, aber eine Zeile.
* **`testmessage` nennt Stundenzahl und Alter des Zustands.** Damit lässt sich
  „Ferien" von „die Schule hat den Plan abgedreht" unterscheiden — sonst wäre
  der Bot unbegrenzt grün und still geblieben.

## 2.4.0 — 2026-09-21

Aus einem Audit. Der erste Punkt behebt einen Fehler, den erst der Dauerbetrieb
aus 2.2.0 gefährlich gemacht hat.

* **Die Laufkette meldete Änderungen doppelt.** `actions/checkout` holt den SHA
  vom Moment der *Auslösung*. Ein wartender Lauf übernimmt bis zu 5,5 Stunden
  später, bekam also eine veraltete `state.json` und konnte nie pushen. Der Lauf
  gleicht sich jetzt vor dem Start auf den Branch-Kopf ab.
* **WebUntis-Aufrufe hatten kein Zeitlimit.** Ein Server, der annimmt und dann
  schweigt, blockierte den Lauf bis zum Job-Limit — seit 2.2.0 also 5,5 Stunden
  Blindflug ohne Fehlschlag und ohne Meldung. Jetzt 30 s (`NETWORK_TIMEOUT`).
* **`Lesson.from_json` winkte kaputte Datumswerte durch** und stürzte erst
  später außerhalb jeder Absicherung ab — und das bei jedem weiteren Lauf
  erneut, weil `state.json` im Repo liegt.

## 2.3.0 — 2026-09-21

**Störmeldungen**, zweistufig — weil ein Job, der nie startet, sich auch nicht
beschweren kann. Ein fehlgeschlagener Lauf löst über `if: failure()` eine
Telegram-Meldung mit Link aus; abgebrochene bewusst nicht, sonst meldete sich
jeder von der Kette ersetzte wartende Lauf. Der neue Workflow `watchdog.yml`
sieht alle vier Stunden von außen nach und meldet Stillstand über 8 Stunden.
Neuer Unterbefehl `bot.py alert`, der weder Zustand noch Stundenplan anfasst.

## 2.2.0 — 2026-09-21

**Dauerbetrieb rund um die Uhr.** Der Cron ist nur noch Anlasser; jeder Lauf
überwacht 5,5 Stunden statt 55 Minuten, und die `concurrency`-Gruppe hält immer
einen Nachfolger bereit. So entsteht eine lückenlose Kette, obwohl ein Job nur
6 Stunden laufen darf — nötig, weil GitHubs Zeitplaner gemessen nur **rund 10
von 48** Auslösungen ausführt. Dazu ein Takt nach Tageszeit: 5 Minuten werktags
6–19 Uhr, sonst 30, was zwei Drittel der WebUntis-Anmeldungen spart. Behoben:
`render_summary` benutzte ein Argument nicht, das die Tests hineinreichten — es
landete als Datumszeile in der Nachricht.

## 2.1.0 — 2026-09-15

Die Version, die das Nachrichtenformat lesbar machte: **Doppelstunden
zusammengefasst** („1./2. Stunde" statt zweier gleicher Zeilen), **mehrere
Änderungsarten je Stunde gebündelt** (Vertretung mit Raumwechsel = ein
Eintrag), **Stundennummern statt Uhrzeiten**, wo das Raster vorliegt. Neu
außerdem `bot.py testmessage` und `--version`, eine Testsuite ohne Netz und
Zugangsdaten, Linter und Tests bei jedem Push.

* **Der Telegram-Token konnte in Fehlermeldungen landen.** `requests` nennt bei
  Netzwerkfehlern die vollständige URL, und die enthält den Token; die Meldung
  wurde bis in die Job-Ausgabe durchgereicht. Token werden jetzt herausgefiltert.
* Bei zwei gleichzeitigen Stunden hing die Reihenfolge davon ab, wie WebUntis
  gerade auslieferte.

## 2.0

Ausgangsstand: Abruf, Vergleich, Telegram-Versand, Selbsttaktung über `watch`,
Plausibilitätsbremse, Zustandssicherung per git.
