"""The client's organisation and its classes.

Roles: admin (the client's manager: organisation, logo, teachers, the Jetson) → teacher (their own
classes) → student (their own work). state/org.json holds the organisation, state/classes.json the
classes. A student belongs to one class (users.json "class"); a teacher owns classes ("teacher").
"""
import datetime
import io
import json
import os
import re
import secrets
import threading
import time
import zipfile
from xml.sax.saxutils import escape

import config

ORG = os.path.join(config.STATE, "org.json")
CLASSES = os.path.join(config.STATE, "classes.json")
LOGO = os.path.join(config.STATE, "org_logo.png")
SETUP_CODE = os.path.join(config.STATE, "setup_code.txt")
_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"        # no 0/O, 1/I
_lock = threading.RLock()


def _read(p, default):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(p, d):
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, p)


def _code(prefix="", n=7):
    r = "".join(secrets.choice(_ALPHABET) for _ in range(n))
    return f"{prefix}{r[:3]}-{r[3:]}"


# ---------------------------------------------------------------- organisation
def org():
    return _read(ORG, {})


def configured():
    return bool(org().get("name"))


def save_org(**fields):
    with _lock:
        o = org()
        o.update({k: v for k, v in fields.items() if v is not None})
        o.setdefault("teacher_code", _code("T-"))
        o.setdefault("created", time.strftime("%Y-%m-%d %H:%M"))
        _write(ORG, o)
        return o


def new_teacher_code():
    return save_org(teacher_code=_code("T-"))["teacher_code"]


def setup_code():
    """One-time code for the first-start page (printed on the sticker): only whoever holds the Jetson
    can create its first administrator."""
    if not os.path.exists(SETUP_CODE):
        fd = os.open(SETUP_CODE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(_code("S-") + "\n")
    with open(SETUP_CODE) as f:
        return f.read().strip()


def save_logo(data):
    """PNG or JPEG only, re-drawn as a clean PNG (never stored as sent: an SVG could carry a script)."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    if im.format not in ("PNG", "JPEG"):
        raise ValueError("the logo must be a PNG or JPEG picture")
    im = im.convert("RGBA")
    im.thumbnail((800, 400))
    im.save(LOGO, "PNG")
    save_org(logo=True, logo_v=int(time.time()))


# ---------------------------------------------------------------- classes
def classes():
    return _read(CLASSES, {})


def get(cid):
    return classes().get(cid)


def by_code(code):
    code = re.sub(r"[^A-Z0-9]", "", (code or "").upper())
    return next((c for c in classes().values() if re.sub(r"[^A-Z0-9]", "", c["code"]) == code), None) if code else None


def owned_by(teacher):
    return [c for c in classes().values() if c["teacher"] == teacher]


def create(teacher, name, starts=None, ends=None, seats=30):
    with _lock:
        d = classes()
        cid = "c" + secrets.token_hex(4)
        codes = {c["code"] for c in d.values()}
        code = _code()
        while code in codes:
            code = _code()
        d[cid] = {"id": cid, "name": name, "teacher": teacher, "code": code, "starts": starts or "", "ends": ends or "",
                  "seats": int(seats or 30), "join": True, "ranking": False, "cert_class": True,
                  "legs": {}, "created": time.strftime("%Y-%m-%d %H:%M")}
        _write(CLASSES, d)
        return d[cid]


def update(cid, **f):
    with _lock:
        d = classes()
        if cid not in d:
            return None
        c = d[cid]
        for k in ("name", "starts", "ends", "seats", "join", "ranking", "cert_class", "legs", "teacher"):
            if k in f and f[k] is not None:
                c[k] = f[k]
        if f.get("new_code"):
            codes = {x["code"] for x in d.values()}
            code = _code()
            while code in codes:
                code = _code()
            c["code"] = code
        _write(CLASSES, d)
        return c


def delete(cid):
    with _lock:
        d = classes()
        d.pop(cid, None)
        _write(CLASSES, d)


def today():
    return datetime.date.today().isoformat()


def leg_open_from(c, leg_index):
    """'' if the leg is open now, else the date it opens ('YYYY-MM-DD'); legs = {"0": "2026-11-03", …}."""
    if not c:
        return ""
    d = (c.get("legs") or {}).get(str(leg_index), "")
    return d if d and d > today() else ""


def join_problem(c, students_in_class):
    """Why a student cannot join this class now (None if they can)."""
    if not c:
        return "This class code does not exist — check it with your teacher."
    if not c.get("join", True):
        return "This class is closed to new students — ask your teacher."
    if c.get("ends") and c["ends"] < today():
        return "This class has ended."
    if students_in_class >= int(c.get("seats") or 0):
        return "This class is full — ask your teacher for a seat."
    return None


# ---------------------------------------------------------------- Excel export (a minimal .xlsx, no extra library)
def xlsx(rows, sheet="Students"):
    """rows: list of lists (first row = header). Numbers stay numbers; everything else is text."""
    def cell(v, r, c):
        ref = f"{_col(c)}{r}"
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return f'<c r="{ref}"><v>{v}</v></c>'
        bold = ' s="1"' if r == 1 else ""
        text = escape(str(v if v is not None else ""))
        return f'<c r="{ref}" t="inlineStr"{bold}><is><t xml:space="preserve">{text}</t></is></c>'
    body = "".join(f'<row r="{i + 1}">' + "".join(cell(v, i + 1, j) for j, v in enumerate(row)) + "</row>"
                   for i, row in enumerate(rows))
    widths = "".join(f'<col min="{j + 1}" max="{j + 1}" width="{min(45, max(10, max(len(str(r[j])) for r in rows if j < len(r)) + 2))}" customWidth="1"/>'
                     for j in range(max(len(r) for r in rows)))
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{escape(sheet[:31])}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf/><xf fontId="1" applyFont="1"/></cellXfs></styleSheet>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{widths}</cols><sheetData>{body}</sheetData></worksheet>',
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, t in files.items():
            z.writestr(n, t)
    return buf.getvalue()


def _col(j):
    s = ""
    j += 1
    while j:
        j, r = divmod(j - 1, 26)
        s = chr(65 + r) + s
    return s
