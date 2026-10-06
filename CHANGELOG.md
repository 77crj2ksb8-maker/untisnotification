# Änderungen

Kurzfassung, ein Absatz je Version. **Die ausführliche Fassung steht in den
Commit-Nachrichten des Original-Repos**
(<https://github.com/77crj2ksb8-maker/untisnotification/commits/main/CHANGELOG.md>,
nur die Versions-Commits, ohne die täglichen Zustands-Commits des Bots) — dort
auch die Mutationsproben, die Messreihen und die Begründungen, warum etwas
*nicht* gemacht wurde. Bewusst die URL und nicht `git log`: Ein Repo, das
über „Use this template" entsteht, beginnt mit einem einzigen Commit und hat
diese Historie nicht.

## 2.12.0 — 2026-10-06

**`/tomorrow` schickt den Plan für morgen.** Gleiche Darstellung wie `/today`,
auch als `/morgen`, und im Befehlsmenü. Steht morgen nichts im Plan, kommt der
nächste Schultag der folgenden sieben Tage mit dem Hinweis „Morgen stehen keine
Stunden im Plan" — Freitagabend also gleich der Montag. Ein Tag, an dem alles
ausfällt, zählt als Schultag: Genau dieser Ausfall ist dann die Antwort. In
den Ferien bleibt es bei „Keine Stunden im Plan" statt eines Plans in zwei
Wochen. Ein einziger WebUntis-Abruf für die ganze Woche. Ein neuer Test hält
Menü, Hilfe und Kurzformen deckungsgleich. Dazu die Actions auf
`checkout@v7` und `setup-python@v7` (Dependabot).

## 2.11.0 — 2026-10-06

**`/today` schickt die Tagesübersicht.** Bis hierher sprach der Bot nur, jetzt
hört er auch zu: In den Pausen zwischen zwei Prüfungen hält er eine
Long-Polling-Anfrage an Telegram offen (`watch --befehle`) und beantwortet
`/today` (oder `/heute`) nach Sekunden — mit dem heutigen Plan frisch aus
WebUntis, Doppelstunden zusammengefasst, Ausfälle und Änderungen markiert.
Jeder andere Befehl bekommt eine kurze Hilfe, und `/today` steht im
Befehlsmenü.

Geantwortet wird nur in den Chats aus `TELEGRAM_CHAT_ID`. Befehle älter als
15 Minuten verfallen, damit nach einem Kettenabriss nicht die Antwort auf eine
Frage vom Vorabend kommt. Den Prüftakt verschiebt das Postfach nicht. Klemmt es
(Webhook gesetzt, zweiter Abholer, Netz weg), wird geschlafen wie bisher; nach
fünf Fehlschlägen in Folge fragt es bis zum Ende des Laufs nicht mehr. Jede
dieser Zusicherungen hat ihre Mutationsprobe. Ende-zu-Ende geprüft gegen einen
lokalen Telegram-Nachbau: Antwort nur an den eingetragenen Chat, sofort
quittiert, Wartezeit auf die Hundertstelsekunde gehalten.


**Die Kette übersteht auch einen Lauf, der nie bis zum Ende kommt.**

* **Der Nachfolger wird nach 20 Minuten angemeldet statt am Ende.** Bis 2.9
  war die Anmeldung der letzte Schritt eines Laufs und fiel genau dann aus,
  wenn ein Lauf nie dort ankam: Runner verloren, Zeitlimit, Abbruch. Jetzt
  wartet der Nachfolger, egal wie der laufende endet. Scheitert die
  Anmeldung, versucht es jeder weitere Durchlauf erneut, statt nur einmal.
  Sturmschutz wie bisher (erst nach 20 Minuten), dazu: nie direkt nach
  einem gescheiterten Durchlauf. Der eigene Workflow-Schritt, der Befehl
  `nachfolger` und die Startzeit-Variable entfallen; `watch --kette`
  übernimmt.
* **Lebenszeichen für einen Aufpasser außerhalb von GitHub** (freiwillig,
  Secret `UNTISBOT_PING_URL`, etwa healthchecks.io). Nach jedem gelungenen
  Durchlauf geht ein Signal raus; bleibt es aus, alarmiert der Dienst. Das
  schließt die beiden Lücken, die Wachhund und Störmeldung nicht abdecken:
  GitHub löst gar nichts mehr aus, oder Telegram selbst ist weg. `selftest`
  prüft es mit. Die Adresse steht in keinem Log, ein Fehler beim Senden
  stört die Überwachung nie.
* Dependabot meldet monatlich neue Versionen der Actions als einen Pull
  Request — bewusst nicht für `requirements.txt`, ein Test hält das fest.
* `repr()` der Konfiguration zeigt weder Token noch Passwort, Benutzername
  oder Lebenszeichen-Adresse. Der Tests-Workflow darf nur noch lesen.
* Neue Tests, unter anderem für den Wachhund-Neustart bei unklarem
  Workflow-Zustand. Jede neue Zusicherung hat ihre Mutationsprobe.


**Nur die Workflows, kein Verhalten.** Alle drei laufen fest auf
`ubuntu-24.04` statt `ubuntu-latest`: Das Label wandert ab 19.10. auf Ubuntu
26.04, und bei einem Bot, der rund um die Uhr läuft, soll ein Wechsel des
Betriebssystems eine bewusste Änderung sein. Ein Test hält Image und
Python-Version in allen Workflows gleich, damit CI prüft, was im Betrieb
läuft. `actions/checkout@v5` und `actions/setup-python@v6` laufen nativ auf
Node 24 — die Deprecation-Warnung in jedem Lauf ist weg. Die Tests laufen nur
noch für `main` und Pull Requests: Der Arbeitsbranch zeigt immer auf
denselben Commit, und sein identischer Zwilling-Lauf scheiterte am 05.10. an
einem Runner-Engpass („not acquired by Runner") — samt Fehler-Mail, obwohl der
Code auf `main` grün war.

## 2.9.1 — 2026-10-05

**Aufgeräumt, ohne den Hauptpfad zu ändern.** `webuntis` ist auf `<0.2`
begrenzt, weil jeder Kettenlauf frisch installiert und eine neue
Schnittstelle sonst ungeprüft in den Betrieb käme; `ruff` ist auf 0.16
festgelegt, damit CI nicht ohne Codeänderung rot wird. CI prüft die
Workflow-Dateien jetzt zusätzlich mit actionlint, samt shellcheck für jeden
`run`-Block — die Fehlerklasse aus 2.3.0 fängt damit ein eigenes Werkzeug,
nicht nur `bash -n`. Die Wachhund-Meldungen setzen den Gedankenstrich wie alle
anderen Telegram-Texte. Im Code: Importe oben statt verstreut, `main()` lädt
die Konfiguration an einer Stelle; in den Tests ersetzen eine `cli`-Fixture,
ein Workflow-Lader und die `cfg`-Fixture kopierte Stubs und Configs. Ein
neuer Test hält `VERSION` und den obersten CHANGELOG-Eintrag gleich.

## 2.9.0 — 2026-10-05

**Die Laufkette trägt sich selbst.** Am 05.10. löste GitHubs Zeitplaner während
der gesamten Laufzeit von Lauf 96 kein einziges Mal aus — der Lauf endete um
15:38 UTC, kein Nachfolger wartete, die Kette stand, bis der Wachhund sich
meldete und von Hand neu gestartet wurde. Bis 2.8 war genau das die
Voraussetzung der Kette.

* **Jeder erfolgreiche Lauf meldet am Ende seinen Nachfolger an**
  (`workflow_dispatch` über die API). Der Zeitplaner ist nur noch
  Rückfallebene. Angemeldet wird nur nach Erfolg und nach mindestens
  20 Minuten Laufzeit, sonst könnte ein Fehler, der jeden Lauf sofort beendet,
  eine Schleife im Minutentakt auslösen.
* **Der Wachhund wirft die Kette selbst wieder an.** Er fragt jetzt, ob gerade
  ein Lauf läuft oder wartet, statt wann der letzte geplante begann. Die alte
  Frage hätte mit der Selbst-Anmeldung bei jeder Zeitplaner-Dürre Fehlalarm
  gegeben, und sie maß ab dem Auslösen statt ab dem Ende („482 Minuten" ohne
  Lauf, als die Kette seit gut anderthalb Stunden stand). Nach einem
  gescheiterten Lauf wartet er zwei Stunden, damit ein Dauerfehler keine
  Meldungsflut auslöst.
* **Der Wachhund sieht zweimal pro Stunde nach** statt alle vier. Gemessen vom
  24.09. bis 05.10. kam er im Median nur alle 6,4 Stunden dran, im schlimmsten
  Fall nach 11,2.
* Seine Entscheidung steht jetzt als reine Funktion in `bot.py` statt als
  ungetestetes Bash im Workflow; nachgestellt am echten Vorfall entscheidet
  sie auf Neustart mit „stand seit 17:37 Uhr still — 104 Minuten". Läufe
  tragen den Modus im Titel (`run-name`), damit eine eben beendete
  Testnachricht nicht als Lebenszeichen gilt. Ältere Läufe ohne Modus im
  Titel erkennt er an der Dauer, damit er schon beim ersten Abriss nach dem
  Umstieg die richtige Uhrzeit nennt.
* Ist der Kettenworkflow deaktiviert, wirft der Wachhund nichts an und
  schweigt — so hält man den Bot an. Hat GitHub selbst ihn abgeschaltet, sagt
  er, wie man ihn wieder einschaltet.

Was bleibt: Fällt GitHub Actions, Telegram oder WebUntis selbst aus, kann der
Bot das nicht ausgleichen — siehe README, „Wenn etwas schiefgeht".

## 2.8.2 — 2026-09-24

Nachbesserung nach einem zweiten Review, diesmal von 2.8.1.

* **2.8.1 versprach mehr, als es hielt:** Pfade mit Leerzeichen kamen zwar
  von git heil an, das README wurde aber weiter am ersten Leerzeichen
  zerlegt — eine solche Datei konnte den Test nie bestehen. Getrennt wird jetzt
  an zwei Leerzeichen, wie der spaltenbündige Block es vorgibt.
* **Ein übersprungener Test in CI ist jetzt ein Fehler.** Sonst stünde da
  „469 passed, 1 skipped" — grün, und der Wächter stillschweigend aus. Lokal
  wird weiter übersprungen, auch wenn git zwar einen Arbeitsbaum findet, aber
  keine einzige Datei darin verfolgt.
* git-Ausgabe ausdrücklich als UTF-8 gelesen statt in der Locale; eine
  doppelte Zeile im Block wird mit Namen gemeldet.
* Doku: Zahlen im 2.8.0-Eintrag nochmals berichtigt (Datei und Einträge
  getrennt), der Link im Kopf zeigt auf die Versions-Commits statt auf eine
  Liste voller Zustands-Commits, und der 2.7.0-Eintrag sagt richtig, dass die
  Concurrency-Verdrängung auch den Wachhund träfe.

## 2.8.1 — 2026-09-24

Korrekturen aus einem Code-Review von 2.8.0.

* **Der neue Dateilisten-Test brach die eigene Einrichtungsanleitung.** Wer
  `state.json` löschte — wie das README es für neue Repos verlangt —, bekam
  einen dauerhaft roten Test, denn das README nennt die Datei weiter. Dateien,
  die der Bot zur Laufzeit selbst anlegt, dürfen jetzt fehlen. Außerdem fällt
  eine doppelte Zeile im Block auf, die Zahl im Einleitungssatz ist eine
  Ziffer und wird gegen die Zeilen des Blocks geprüft, git liefert Dateinamen
  mit Leerzeichen oder Umlauten unverstümmelt, und ohne git-Arbeitsbaum
  (etwa nach einem ZIP-Download) wird der Test übersprungen statt rot.
* **Die Größenangabe im 2.8.0-Eintrag war falsch** — „auf ein Drittel" stimmte
  weder für die Datei noch für die alten Einträge. Korrigiert auf gemessene
  Werte.
* Zwei Verweise auf einen Kopfkommentar, den 2.8.0 durch einen README-Zeiger
  ersetzt hatte, zeigen jetzt direkt aufs README. Der CHANGELOG-Kopf verweist
  auf die Commit-Historie des Original-Repos statt auf `git log`, die ein über
  „Use this template" angelegtes Repo nicht hat. Der 2.7.0-Eintrag nennt
  wieder beide Gründe für die getrennten Workflows.

## 2.8.0 — 2026-09-22

Verdichtungsrunde. Kein Verhalten geändert, keine Datei entfernt — die
Redundanz saß nicht in der Dateiliste, sondern im Fließtext: 29 % des Repos
waren Prosa, vieles davon in zweiter und dritter Fassung.

* **Dieser CHANGELOG ist eingedampft:** Die Datei schrumpfte von 16.969 auf
  8.649 Bytes (51 %), die Einträge 2.0 bis 2.7.0 allein von 16.879 auf 6.432
  (38 %). Die
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
im README auf. Die drei Workflows blieben getrennt, aus zwei Gründen: Der
Wachhund fragt ab, wann der letzte Lauf *dieses* Workflows begann — in
derselben Datei zählte er seine eigenen Läufe als Lebenszeichen und meldete
„alles in Ordnung", während die Kette tot ist. Und jeder einverleibte Lauf, ob
Wachhund oder Test, käme in die `concurrency`-Gruppe der Laufkette und
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
* `render_plan` sortierte nur nach Tag und Uhrzeit — bei zwei gleichzeitigen
  Stunden hing die Reihenfolge davon ab, wie WebUntis gerade auslieferte.

## 2.0

Ausgangsstand: Abruf, Vergleich, Telegram-Versand, Selbsttaktung über `watch`,
Plausibilitätsbremse, Zustandssicherung per git.
