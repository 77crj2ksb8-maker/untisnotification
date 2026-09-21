# Einrichtung

Für alle, die den Bot im **eigenen** Repo betreiben wollen. Rechne mit einer
Viertelstunde.

> **Vorher:** Der Betrieb einer eigenen Instanz braucht die Erlaubnis des
> Rechteinhabers — siehe [COPYRIGHT](COPYRIGHT). Frag einmal kurz nach, das
> ist formlos möglich.

Vorweg zwei Dinge, die Zeit sparen:

* **Die Dateien sind für alle identisch.** Im Code steht nichts Persönliches,
  alles kommt aus Secrets. Du musst keine Datei anpassen.
* **Wenn du denselben Stundenplan hast wie jemand, der den Bot schon
  betreibt, brauchst du gar nichts** — siehe [Der kürzere Weg](#der-kürzere-weg).

## Was du brauchst

* einen GitHub-Account
* einen Telegram-Account
* deine WebUntis-Zugangsdaten

## 1. Telegram-Bot anlegen

1. In Telegram `@BotFather` anschreiben, `/newbot`, den Fragen folgen.
2. Der Token sieht aus wie `123456789:AAH-xxxxxxxxxxxxxxxxxxxxx`. Aufheben.
3. **Deinen neuen Bot anschreiben und `/start` senden.** Ohne das darf er dir
   nicht schreiben, und du bekommst später „chat not found".
4. Chat-ID holen — im Browser aufrufen, `<TOKEN>` ersetzen:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Die Zahl unter `"chat":{"id":...}` ist deine ID. Bei Gruppen ist sie negativ.

> Nimm einen **eigenen** Bot, nicht den von jemand anderem. Wer den Token hat,
> kann in fremdem Namen an jeden Chat schreiben, den er kennt.

## 2. WebUntis-Werte heraussuchen

Melde dich einmal im Browser bei WebUntis an und sieh dir die Adresszeile an:

```
https://ajax.webuntis.com/WebUntis/?school=ks-musterstadt#/basic/login
         └──── SERVER ────┘                 └─── SCHOOL ───┘
```

* `WEBUNTIS_SERVER` = `ajax.webuntis.com` (ohne `https://`, ohne Schrägstrich)
* `WEBUNTIS_SCHOOL` = `ks-musterstadt`
* Benutzername und Passwort sind dieselben wie beim Anmelden.

## 3. Repo anlegen

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
> im Repo ab, für jeden lesbar. Fächer, Räume, Zeiten, Kursgruppen. Siehe
> [README](README.md#achtung-statejson-ist-öffentlich-lesbar).

## 4. Secrets setzen

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

Optional ist `WEBUNTIS_KLASSE` — siehe [README](README.md#einstellungen).

`LOOKAHEAD_DAYS` und `TIMEZONE` gehören **nicht** hierher. Der Workflow setzt
beide direkt als Umgebungsvariable, und die gewinnt immer gegen ein Secret
gleichen Namens — ein Secret dafür bliebe also wirkungslos. Wer die Werte
ändern will, ändert sie in `.github/workflows/check-timetable.yml`.

## 5. Ausprobieren

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
Commit, keine Nachricht. Wer den Bot ohnehin lokal ausgecheckt hat, bekommt
mit `python bot.py selftest` dieselbe Ausgabe (siehe unten).

Danach läuft der Bot von allein — rund um die Uhr. Der Zeitplaner stößt die
Kette an, jeder Lauf überwacht 5,5 Stunden und der nächste steht schon bereit.
Geprüft wird alle 5 Minuten während der Schulzeit, sonst alle 30 Minuten.

## Lokal ausführen

Praktisch zum Prüfen, ohne auf einen Actions-Lauf zu warten:

```bash
git clone <dein-repo>
cd untisnotification
pip install -r requirements.txt

cp .env.example .env            # und ausfüllen

python bot.py selftest          # jeden Zugang einzeln prüfen
python bot.py show              # Stundenplan im Klartext
python bot.py check --dry-run   # prüfen, ohne zu senden oder zu speichern
```

Die `.env` steht in `.gitignore` und landet nicht im Repo.

> Nimm lokal `check --dry-run`, nicht `check`. In einem geklonten Repo findet
> der Bot ein `.git`-Verzeichnis und sichert seinen Zustand wie in der Cloud —
> er würde also `state.json` committen und pushen. `selftest`, `show` und
> `--dry-run` fassen den Zustand nicht an.

## Der kürzere Weg

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

## Du wirst benachrichtigt, wenn etwas schiefgeht

Sobald die Secrets gesetzt sind, meldet sich der Bot von selbst per Telegram —
wenn ein Lauf scheitert, und wenn die Laufkette länger als 8 Stunden
stillsteht. Du musst dafür nichts einrichten. Einzelheiten im
[README](README.md#wenn-etwas-schiefgeht).

## Wenn etwas klemmt

| Meldung | Ursache |
|---|---|
| `TELEGRAM_BOT_TOKEN hat ein unerwartetes Format` | im Token fehlt der Doppelpunkt — vermutlich unvollständig kopiert |
| `chat not found` | `/start` an den Bot fehlt, oder die Chat-ID stimmt nicht |
| `Der Bot darf diesem Chat nicht schreiben` | blockiert oder aus der Gruppe entfernt |
| `Anmeldung abgelehnt` | Benutzername, Passwort oder Schulkürzel falsch |
| `Kein Schuljahr deckt … ab` | Ferien, oder das neue Schuljahr ist in WebUntis noch nicht angelegt. Kein Fehler, der Bot wartet es aus. |
| Es kommt gar nichts | Erst nach dem *ersten* Lauf kann verglichen werden — der merkt sich nur den Stand. Ansonsten: Gibt es gerade überhaupt Änderungen? |
| Läufe starten nicht | Actions im Repo aktiviert? Nach 60 Tagen ohne Commit schaltet GitHub geplante Workflows ab. |
