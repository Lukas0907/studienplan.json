import enum
import json
import re
import subprocess
import sys

import dateutil.parser


class GermanParserInfo(dateutil.parser.parserinfo):
    MONTHS = [
        ("Jan", "Januar", "Jänner"),
        ("Feb", "Februar"),
        ("Mär", "Mrz", "März"),
        ("Apr", "April"),
        ("Mai",),
        ("Jun", "Juni"),
        ("Jul", "Juli"),
        ("Aug", "August"),
        ("Sep", "Sept", "September"),
        ("Okt", "Oktober"),
        ("Nov", "November"),
        ("Dez", "Dezember"),
    ]


class State(enum.Enum):
    PREAMBLE = 1
    STUDIUM_TYPE = 2
    STUDIUM_NAME = 3
    STUDIUM_KENNZAHL = 4
    BESCHLUSS_DATUM = 5
    GUELTIG_DATUM = 6
    INHALTSVERZEICHNIS = 7
    PRUEFUNGSFAECHER = 13
    PRUEFUNGSFACH_NAME = 14
    PRUEFUNGSFACH_MODUL = 15
    KURZBESCHREIBUNG_MODULE = 16
    MODULBESCHREIBUNGEN = 17
    MODUL_NAME = 18
    MODUL_REGELARBEITSAUFWAND = 19
    MODUL_LERNERGEBNISSE = 20
    MODUL_LVAS = 21
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


def parse_studienplan(text):
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
                studienplan["studienkennzahl"] = line
                state = State.BESCHLUSS_DATUM
                line = next_line(lines)
            elif state == State.BESCHLUSS_DATUM:
                if line.startswith("mit Wirksamkeit"):
                    studienplan["beschluss_datum"] = line.replace(
                        "mit Wirksamkeit ", ""
                    )
                    state = State.GUELTIG_DATUM
                line = next_line(lines)
            elif state == State.GUELTIG_DATUM:
                assert line.startswith("Gültig ab")
                studienplan["gueltig_datum"] = line.replace("Gültig ab ", "")
                state = State.INHALTSVERZEICHNIS
                line = next_line(lines)
            elif state == State.INHALTSVERZEICHNIS:
                # A lot of text inbetween is skipped.
                if line.startswith("Prüfungsfächer und zugehörige Module"):
                    state = State.PRUEFUNGSFAECHER
                line = next_line(lines)
            elif state == State.PRUEFUNGSFAECHER:
                if line.endswith("mindestens 180 ECTS ergibt."):
                    studienplan["pruefungsfaecher"] = []
                    pruefungsfaecher = studienplan["pruefungsfaecher"]
                    state = State.PRUEFUNGSFACH_NAME
                line = next_line(lines)
            elif state == State.PRUEFUNGSFACH_NAME:
                if line == "Kurzbeschreibung der Module":
                    state = State.KURZBESCHREIBUNG_MODULE
                else:
                    pruefungsfach = {"name": line, "module": []}
                    pruefungsfaecher.append(pruefungsfach)
                    state = State.PRUEFUNGSFACH_MODUL
                line = next_line(lines)
            elif state == State.PRUEFUNGSFACH_MODUL:
                if line.endswith("ECTS)"):
                    pruefungsfach["module"].append(line)
                    line = next_line(lines)
                elif line in [
                    "*Vertiefung Bakkalaureat Technische Informatik",
                    "*Verbreiterung Bakkalaureat Technische Informatik",
                ]:
                    # These two modules do not have fixed ECTS.
                    pruefungsfach["module"].append(line)
                    line = next_line(lines)
                elif line in ["Vertiefung:", "Verbreiterung:"]:
                    # Skip Vertiefung/Verbreiterung in Bachelor Technische Informatik.
                    line = next_line(lines)
                else:
                    state = State.PRUEFUNGSFACH_NAME
            elif state == State.KURZBESCHREIBUNG_MODULE:
                if line.startswith("A. Modulbeschreibungen"):
                    state = State.MODULBESCHREIBUNGEN
                line = next_line(lines)
            elif state == State.MODULBESCHREIBUNGEN:
                if line.endswith("ist in Anhang B im Detail erläutert."):
                    studienplan["modulbeschreibungen"] = []
                    modulbeschreibungen = studienplan["modulbeschreibungen"]
                    state = State.MODUL_NAME
                line = next_line(lines)
            elif state == State.MODUL_NAME:
                if line.startswith("B. Lehrveranstaltungstypen"):
                    state = State.LEHRVERANSTALTUNGSTYPEN
                else:
                    modul = {
                        "name": line,
                        "lvas": [],
                        "regelarbeitsaufwand": None,
                        "lernergebnisse": [],
                    }
                    modulbeschreibungen.append(modul)
                    state = State.MODUL_REGELARBEITSAUFWAND
                line = next_line(lines)
            elif state == State.MODUL_REGELARBEITSAUFWAND:
                if line.startswith("Regelarbeitsaufwand:"):
                    modul["regelarbeitsaufwand"] = line.replace(
                        "Regelarbeitsaufwand: ", ""
                    )
                    line = next_line(lines)
                state = State.MODUL_LERNERGEBNISSE
            elif state == State.MODUL_LERNERGEBNISSE:
                if line.startswith("Lehrveranstaltungen des Moduls:"):
                    state = State.MODUL_LVAS
                    line = next_line(lines, strip=False)
                elif line.endswith("Individuell nach gewählten Modulen/LVAs."):
                    # Bachelor Technische Informatik has two Module that do not have a
                    # list of LVAs.
                    state = State.MODUL_NAME
                    line = next_line(lines)
                else:
                    modul["lernergebnisse"].append(line)
                    line = next_line(lines)
            elif state == State.MODUL_LVAS:
                if re.match(r"^((?:\*| )\d|\d\d),\d", line):
                    # Line is not stripped so we can distinguish between continuing
                    # LVA name, new LVA name as well as new modules.
                    modul["lvas"].append(line.strip())
                    line = next_line(lines, strip=False)
                elif line.startswith("            ") and line.strip():
                    # LVA name goes over two lines.
                    modul["lvas"][-1] += " " + line.strip()
                    line = next_line(lines, strip=False)
                elif "zentralen Wahlfachkatalog der TU Wien" in line:
                    # The Modul "Freie Wahlfächer und Transferable Skills" doesn't have
                    # a list of LVAs. Just skip the description.
                    line = next_line(lines)
                    state = State.MODUL_NAME
                elif len(modul["lvas"]) == 0 or line in ["Verpflichtend:", "Wahl:"]:
                    # There might be some text before/in the list of LVAs that we just
                    # skip.
                    line = next_line(lines, strip=False)
                else:
                    state = State.MODUL_NAME
            elif state == State.LEHRVERANSTALTUNGSTYPEN:
                # A lot of text inbetween is skipped.
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

    return studienplan


def read_pdf(filename):
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
            filename,
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
    text = text.replace("“", '"')
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


def remove_footnotes(text):
    fixed_text = []
    in_footnote = False

    for line in text.splitlines():
        if re.match(r"^ \d$", line):
            in_footnote = True
            continue

        if in_footnote and line.startswith("   "):
            continue

        in_footnote = False
        fixed_text.append(line)

    return "\n".join(fixed_text)


def cleanup_text(text):
    text = fix_quotes(text)
    text = dehyphenate(text)
    text = remove_footnotes(text)
    return text


def normalize_studienplan(studienplan):
    studienplan["beschluss_datum"] = dateutil.parser.parse(
        studienplan["beschluss_datum"], GermanParserInfo()
    ).date()
    studienplan["gueltig_datum"] = dateutil.parser.parse(
        studienplan["gueltig_datum"], GermanParserInfo()
    ).date()
    studienplan["studienkennzahl"] = studienplan["studienkennzahl"].replace(" ", "")

    for pruefungsfach in studienplan["pruefungsfaecher"]:
        for i, modul in enumerate(pruefungsfach["module"]):
            modul = re.match(
                r"(?P<wahl>\*)?"
                + r"(?:(?P<name>.*)\s+\((?P<ects>.*) ECTS\)|(?P<name_no_ects>.*))",
                modul,
            ).groupdict()
            name_no_ects = modul.pop("name_no_ects")
            if name_no_ects:
                modul["name"] = name_no_ects
            modul["wahl"] = modul["wahl"] == "*"
            pruefungsfach["module"][i] = modul

    for semester, lvas in studienplan["semestereinteilung"].items():
        for i, lva in enumerate(lvas):
            lva = re.match(
                r"(?P<not_steop_constrained>\*)?\s*(?P<ects>\d{1,2},\d)\s*"
                + r"(?P<lva_typ>[A-Z]+)\s+(?P<name>.*)",
                lva,
            ).groupdict()
            lva["not_steop_constrained"] = lva["not_steop_constrained"] != "*"
            lvas[i] = lva

    for modul in studienplan["modulbeschreibungen"]:
        if modul["regelarbeitsaufwand"]:
            modul["regelarbeitsaufwand"] = {
                "ects": modul["regelarbeitsaufwand"].replace(" ECTS", "")
            }
        else:
            modul["regelarbeitsaufwand"] = {"ects": None}
        modul["lernergebnisse"] = (
            "\n".join(modul["lernergebnisse"]).replace("Lernergebnisse:", "").strip()
        )
        for i, lva in enumerate(modul["lvas"]):
            # The Modul "Software Engineering und Projektmanagement" in Medizinische
            # Informatik has a special rule.
            lva = re.match(
                r"(?:\*)?(?P<ects>\d{1,2},\d)/(?P<sst>\d{1,2},\d)\s*"
                + r"(?P<lva_typ>[A-Z]+)\s+(?P<name>.*)",
                lva,
            ).groupdict()
            # Normalize spaces in name.
            lva["name"] = re.sub("\s+", " ", lva["name"])
            modul["lvas"][i] = lva


def condense_studienplan(studienplan):
    def _get_modulbeschreibung(modul_name):
        for i, modulbeschreibung in enumerate(studienplan["modulbeschreibungen"]):
            if modulbeschreibung["name"] == modul_name:
                del studienplan["modulbeschreibungen"][i]
                return modulbeschreibung

    def _get_semester_steop(lva):
        for semester, lvas in studienplan["semestereinteilung"].items():
            for i, l in enumerate(lvas):
                if (
                    lva["name"] == l["name"]
                    and lva["lva_typ"] == l["lva_typ"]
                    and lva["ects"] == l["ects"]
                ):
                    del lvas[i]
                    return semester, l["not_steop_constrained"]
        return None, False

    for pruefungsfach in studienplan["pruefungsfaecher"]:
        for modul in pruefungsfach["module"]:
            modulbeschreibung = _get_modulbeschreibung(modul["name"])
            assert modulbeschreibung["regelarbeitsaufwand"]["ects"] == modul["ects"]
            # modul["lernergebnisse"] = modulbeschreibung["lernergebnisse"]
            modul["lvas"] = modulbeschreibung["lvas"]
            for lva in modul["lvas"]:
                lva["semester"], lva["not_steop_constrained"] = _get_semester_steop(lva)

    # Delete redundant information and make sure that it has been used.

    assert studienplan["modulbeschreibungen"] == []
    del studienplan["modulbeschreibungen"]

    for semestereinteilung in studienplan["semestereinteilung"].values():
        assert semestereinteilung == []
    del studienplan["semestereinteilung"]


def main():
    text = cleanup_text(read_pdf(sys.argv[1]))
    studienplan = parse_studienplan(text)
    normalize_studienplan(studienplan)
    condense_studienplan(studienplan)
    with open(sys.argv[1].replace("pdf", "json"), "w") as f:
        json.dump(studienplan["pruefungsfaecher"], f, indent=4, sort_keys=True)


if __name__ == "__main__":
    main()
