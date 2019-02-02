import enum
import re
import subprocess


class State(enum.Enum):
    PREAMBLE = 1
    STUDIUM_TYPE = 2
    STUDIUM_NAME = 3
    STUDIUM_KENNZAHL = 4
    BESCHLUSS_DATUM = 5
    GUELTIG_DATUM = 6
    INHALTSVERZEICHNIS = 7
    GRUNDLAGE = 8
    QUALIFIKATIONSPROFIL = 9
    DAUER_UMFANG = 10
    ZULASSUNG = 11
    AUFBAU_DES_STUDIUMS = 12
    PRUEFUNGSFAECHER = 13
    PRUEFUNGSFACH_TITLE = 14
    PRUEFUNGSFACH_MODUL = 15
    KURZBESCHREIBUNG_MODULE = 16
    MODULBESCHREIBUNGEN = 17
    MODUL_TITLE = 18
    MODUL_REGELARBEITSAUFWAND = 19
    MODUL_LERNERGEBNISSE = 20
    MODUL_LVAS = 21
    MODUL_LVA_DESC = 22
    LEHRVERANSTALTUNGSTYPEN = 23
    SEMESTEREINTEILUNG = 24
    SEMESTEREINTEILUNG_SEMESTER = 25
    SEMESTEREINTEILUNG_LVA = 26
    SEMESTEREMPFEHLUNG_SCHIEFEINSTEIGEND = 27

    END = 99


def next_line(lines, skip_empty=True, strip=True):
    """Returns the next not empty line."""
    while True:
        line = next(lines)
        if strip:
            line = line.strip()
        if line or not skip_empty:
            return line


def parse(text):
    state = State.PREAMBLE
    lines = iter(text.splitlines())
    studienplan = {}

    try:
        line = next_line(lines)
        while True:
            if state == State.PREAMBLE:
                if line.startswith("Bachelorstudium") or line.startswith(
                    "Masterstudium"
                ):
                    state = State.STUDIUM_TYPE
                else:
                    line = next_line(lines)
            elif state == State.STUDIUM_TYPE:
                studienplan["studium_type"] = line
                state = State.STUDIUM_NAME
                line = next_line(lines)
            elif state == State.STUDIUM_NAME:
                studienplan["studium_name"] = line
                state = State.STUDIUM_KENNZAHL
                line = next_line(lines)
            elif state == State.STUDIUM_KENNZAHL:
                studienplan["studium_kennzahl"] = line
                state = State.BESCHLUSS_DATUM
                line = next_line(lines)
            elif state == State.BESCHLUSS_DATUM:
                if line.startswith("mit Wirksamkeit"):
                    studienplan["beschluss_datum"] = line.replace("mit Wirksamkeit ", "")
                    state = State.GUELTIG_DATUM
                line = next_line(lines)
            elif state == State.GUELTIG_DATUM:
                assert line.startswith("Gültig ab")
                studienplan["gueltig_datum"] = line.replace("Gültig ab ", "")
                state = State.INHALTSVERZEICHNIS
                line = next_line(lines)
            elif state == State.INHALTSVERZEICHNIS:
                if line.startswith("1. Grundlage und Geltungsbereich"):
                    state = State.GRUNDLAGE
                line = next_line(lines)
            elif state == State.GRUNDLAGE:
                if line.startswith("2. Qualifikationsprofil"):
                    state = State.QUALIFIKATIONSPROFIL
                line = next_line(lines)
            elif state == State.QUALIFIKATIONSPROFIL:
                if line.startswith("3. Dauer und Umfang"):
                    state = State.DAUER_UMFANG
                line = next_line(lines)
            elif state == State.DAUER_UMFANG:
                if line.startswith("4. Zulassung zum"):
                    state = State.ZULASSUNG
                line = next_line(lines)
            elif state == State.ZULASSUNG:
                if line.startswith("5. Aufbau des Studiums"):
                    state = State.AUFBAU_DES_STUDIUMS
                line = next_line(lines)
            elif state == State.AUFBAU_DES_STUDIUMS:
                if line.startswith("Prüfungsfächer und zugehörige Module"):
                    state = State.PRUEFUNGSFAECHER
                line = next_line(lines)
            elif state == State.PRUEFUNGSFAECHER:
                if line.endswith("mindestens 180 ECTS ergibt."):
                    studienplan["pruefungsfaecher"] = []
                    pruefungsfaecher = studienplan["pruefungsfaecher"]
                    state = State.PRUEFUNGSFACH_TITLE
                line = next_line(lines)
            elif state == State.PRUEFUNGSFACH_TITLE:
                if line == "Kurzbeschreibung der Module":
                    state = State.KURZBESCHREIBUNG_MODULE
                else:
                    pruefungsfach = {"title": line, "module": []}
                    pruefungsfaecher.append(pruefungsfach)
                    state = State.PRUEFUNGSFACH_MODUL
                line = next_line(lines)
            elif state == State.PRUEFUNGSFACH_MODUL:
                if line.endswith("ECTS)"):
                    pruefungsfach["module"].append(line)
                    line = next_line(lines)
                else:
                    state = State.PRUEFUNGSFACH_TITLE
            elif state == State.KURZBESCHREIBUNG_MODULE:
                if line.startswith("A. Modulbeschreibungen"):
                    state = State.MODULBESCHREIBUNGEN
                line = next_line(lines)
            elif state == State.MODULBESCHREIBUNGEN:
                if line.endswith("ist in Anhang B im Detail erläutert."):
                    studienplan["modulbeschreibungen"] = []
                    modulbeschreibungen = studienplan["modulbeschreibungen"]
                    state = State.MODUL_TITLE
                line = next_line(lines)
            elif state == State.MODUL_TITLE:
                if line.startswith("B. Lehrveranstaltungstypen"):
                    state = State.LEHRVERANSTALTUNGSTYPEN
                else:
                    modul = {
                        "title": line, "lvas": [], "regelarbeitsaufwand": None,
                        "lernergebnisse": []
                    }
                    modulbeschreibungen.append(modul)
                    state = State.MODUL_REGELARBEITSAUFWAND
                line = next_line(lines)
            elif state == State.MODUL_REGELARBEITSAUFWAND:
                modul["regelarbeitsaufwand"] = line.replace("Regelarbeitsaufwand: ", "")
                state = State.MODUL_LERNERGEBNISSE
                line = next_line(lines)
            elif state == State.MODUL_LERNERGEBNISSE:
                if line == "Lehrveranstaltungen des Moduls:":
                    state = State.MODUL_LVAS
                    line = next_line(lines, strip=False)
                elif line.startswith("Lehrveranstaltungen des Moduls:"):
                    # In case the Modul doesn't have a list but a textual description.
                    state = State.MODUL_LVA_DESC
                    line = next_line(lines)
                else:
                    modul["lernergebnisse"].append(line)
                    line = next_line(lines)
            elif state == State.MODUL_LVAS:
                if re.match(r"^( \d|\d\d),\d", line):
                    # Line is not stripped so we can distinguish between continuing
                    # LVA titles,  new LVA titles as well as new modules.
                    modul["lvas"].append(line.strip())
                    line = next_line(lines, strip=False)
                elif line.startswith("            "):
                    # LVA title goes over two lines.
                    modul["lvas"][-1] += " " + line.strip()
                    line = next_line(lines, strip=False)
                else:
                    state = State.MODUL_TITLE
            elif state == State.MODUL_LVA_DESC:
                # The Modul "Freie Wahlfächer und Transferable Skills" doesn't have a
                # list of LVAs. Just skip the description.
                if "zentralen Wahlfachkatalog der TU Wien" in line:
                    state = State.MODUL_TITLE
                line = next_line(lines)
            elif state == State.LEHRVERANSTALTUNGSTYPEN:
                if line.startswith("D. Semestereinteilung der Lehrveranstaltungen"):
                    state = State.SEMESTEREINTEILUNG
                    studienplan["semestereinteilung"] = {}
                    semestereinteilung = studienplan["semestereinteilung"]
                line = next_line(lines)
            elif state == State.SEMESTEREINTEILUNG:
                if line.endswith("Semester (WS)") or line.endswith("Semester (SS)"):
                    state = State.SEMESTEREINTEILUNG_SEMESTER
                else:
                    line = next_line(lines)
            elif state == State.SEMESTEREINTEILUNG_SEMESTER:
                semestereinteilung[line] = []
                semester = semestereinteilung[line]
                state = State.SEMESTEREINTEILUNG_LVA
                line = next_line(lines)
            elif state == State.SEMESTEREINTEILUNG_LVA:
                if line.endswith("Semester (WS)") or line.endswith("Semester (SS)"):
                    state = State.SEMESTEREINTEILUNG_SEMESTER
                elif line.startswith("E. Semesterempfehlung"):
                    state = State.SEMESTEREMPFEHLUNG_SCHIEFEINSTEIGEND
                else:
                    semester.append(line)
                    line = next_line(lines)
            elif state == State.SEMESTEREMPFEHLUNG_SCHIEFEINSTEIGEND:
                state = state.END
            elif state == State.END:
                break
    except StopIteration:
        pass

    import pdb
    pdb.set_trace()
    return studienplan


def read_from_pdf():
    result = subprocess.run(
        [
            "pdftotext",
            "-nopgbrk",
            "-layout",
            "-x",
            "72",
            "-y",
            "72",
            "-W",
            "460",
            "-H",
            "650",
            "BachelorSoftwareandInformationEngineering.pdf",
            "-",
        ],
        encoding="utf8",
        capture_output=True,
    )
    return result.stdout


def dehyphenate(text):
    while "-\n" in text:
        text = re.sub("-\n\\s*", "", text)
    return text


def fix_quotes(text):
    text = text.replace("“", "\"")
    fixed_text = []
    prev_line = None

    for line in text.splitlines():
        while "”" in line:
            i_quote = line.index("”")
            line = line.replace("”", " ", 1)
            assert prev_line is not None
            if prev_line[i_quote] == " ":
                i_word = i_quote + 1
            else:
                i_word = prev_line.rindex(" ", 0, i_quote) + 1
            # XXX what if quote is at the beginning of the line
            prev_line = prev_line[:i_word] + '"' + prev_line[i_word:]
        fixed_text.append(prev_line)
        prev_line = line

    return "\n".join(fixed_text[1:])


def cleanup(text):
    text = fix_quotes(text)
    text = dehyphenate(text)
    return text


def main():
    text = cleanup(read_from_pdf())
    import pdb

    pdb.set_trace()
    parse(text)


main()
