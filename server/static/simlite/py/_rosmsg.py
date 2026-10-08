"""Builds ROS message classes from .msg text (the same definitions the robot uses)."""
import copy
import importlib
import re

_PRIM = {"bool": False, "byte": 0, "char": 0, "int8": 0, "uint8": 0, "int16": 0, "uint16": 0, "int32": 0,
         "uint32": 0, "int64": 0, "uint64": 0, "float32": 0.0, "float64": 0.0, "string": "", "wstring": ""}
_LINE = re.compile(r"^\s*([A-Za-z0-9_/]+(?:<=\d+)?)(\[(?:<=)?(\d*)\])?\s+([A-Za-z0-9_]+)\s*(?:(=)\s*(.+?)|\s+(\S.*?))?\s*$")


def _const(typ, text):
    text = text.strip()
    if typ == "bool":
        return text.lower() in ("true", "1")
    if typ in ("string", "wstring"):
        return text.strip("'\"")
    return float(text) if typ.startswith("float") else int(text, 0)


def _resolve(pkg, typ):
    if typ == "Header":
        typ = "std_msgs/Header"
    p, _, n = typ.rpartition("/")
    mod = importlib.import_module(f"{p or pkg}.msg")
    return getattr(mod, n)


def define(pkg, name, text):
    fields, consts = [], {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        m = _LINE.match(line)
        if not m:
            continue
        typ, arr, size, fname, eq, cval, dval = m.groups()
        typ = typ.split("<=")[0]
        if eq:                                        # NAME=VALUE: a constant
            consts[fname] = _const(typ, cval)
            continue
        dflt = _const(typ, dval) if (dval is not None and typ in _PRIM and not arr) else None
        fields.append((fname, typ, arr is not None, int(size) if size else None, dflt))

    def default(f):
        fname, base, is_arr, size, dflt = f
        if dflt is not None:
            return dflt
        if is_arr:
            if size:
                return [(_PRIM[base] if base in _PRIM else _resolve(pkg, base)()) for _ in range(size)]
            return []
        if base in _PRIM:
            return _PRIM[base]
        return _resolve(pkg, base)()

    def __init__(self, **kw):
        for f in fields:
            setattr(self, f[0], kw[f[0]] if f[0] in kw else default(f))
        bad = set(kw) - {f[0] for f in fields}
        if bad:
            raise TypeError(f"{name}: unknown field(s) {sorted(bad)}")

    def __eq__(self, other):
        return type(self) is type(other) and all(getattr(self, f[0]) == getattr(other, f[0]) for f in fields)

    def __repr__(self):
        return f"{pkg}.msg.{name}(" + ", ".join(f"{f[0]}={getattr(self, f[0])!r}" for f in fields) + ")"

    def get_fields_and_field_types(cls):
        return {f[0]: f[1] for f in fields}

    ns = {"__init__": __init__, "__eq__": __eq__, "__repr__": __repr__, "__slots__": (),
          "__copy__": lambda self: copy.deepcopy(self), "__hash__": None,
          "get_fields_and_field_types": classmethod(get_fields_and_field_types),
          "_fields": tuple(f[0] for f in fields)}
    ns.pop("__slots__")
    ns.update(consts)
    return type(name, (object,), ns)
