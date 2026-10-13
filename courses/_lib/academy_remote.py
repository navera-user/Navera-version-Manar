"""Student code during a sealed check runs in its own process (the "host"), never in the checker's.

Why: check.py holds the expected values (and hidden test data, in memory). If the student's module
were imported in the checker's process (as load_student did before 2026-10-13), the student's code
could read them (module globals, code constants) or forge the result. So, in a sealed check
(academy_sealed.py), load_student() and any import of a module that lives in a writable folder
(~/lessons/…, ~/navera/…) are done by a separate Python process started from this file, and the
checker gets PROXIES:

    m = load_student("navera_lite/geo.py")     # a proxy of the module in the host
    m.distance(1, 2, 3, 4)                     # call → pipe → host runs it → the result comes back

Plain data comes back as real values (numbers, str, bytes, list/tuple/dict/set, namedtuple, NumPy
arrays and scalars, pandas objects, datetime, ROS messages of installed packages). Anything else (an
instance of a student class, a generator, a function…) stays in the host and comes back as a proxy
that forwards attribute access, calls, operators, len/iter/[]/==/float()… Arguments go the other way:
data by value, and functions/objects of check.py as call-only proxies (the student's code may call them
and read their public attributes, nothing else). A list/dict/set/bytearray/ndarray argument the
student's function changes in place is copied back after the call.

Exceptions keep their built-in class (ValueError stays ValueError; a student class derived from
ValueError becomes a ValueError subclass with the same name); e.academy_where says where in the
student's file it happened. inspect.getsource()/signature()/isfunction()… work on proxies (patched).
The time limit of academy_check.run() (SIGALRM) interrupts the student's code in the host (SIGUSR1);
if it does not stop within 2 s the host is killed and restarted, and the proxies of modules,
functions and classes reconnect by themselves (other objects are lost).

The wire format is pickle restricted to plain data (no class or function can be named), plus NumPy /
pandas / datetime blobs checked against an explicit allow-list: nothing the host sends can run code
in the checker.
"""
import copy
import io
import math
import operator
import os
import pickle
import select
import signal
import struct
import sys
import types

# ---------------------------------------------------------------- what may be rebuilt from a blob
ALLOW = {
    ("array", "_array_reconstructor"), ("array", "array"), ("builtins", "slice"), ("builtins", "complex"),
    ("builtins", "set"), ("builtins", "frozenset"), ("builtins", "bytearray"), ("builtins", "range"),
    ("datetime", "date"), ("datetime", "datetime"), ("datetime", "time"), ("datetime", "timedelta"),
    ("datetime", "timezone"), ("decimal", "Decimal"), ("fractions", "Fraction"), ("functools", "partial"),
    ("numpy", "dtype"), ("numpy", "ndarray"),
    ("numpy.core.multiarray", "_reconstruct"), ("numpy.core.multiarray", "scalar"),
    ("numpy.core.numeric", "_frombuffer"),
    ("numpy._core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "scalar"),
    ("numpy._core.numeric", "_frombuffer"),
    ("pandas._libs.arrays", "__pyx_unpickle_NDArrayBacked"), ("pandas._libs.interval", "Interval"),
    ("pandas._libs.missing", "NA"), ("pandas._libs.tslibs.nattype", "__nat_unpickle"),
    ("pandas._libs.tslibs.offsets", "Day"), ("pandas._libs.tslibs.offsets", "Hour"),
    ("pandas._libs.tslibs.offsets", "Micro"), ("pandas._libs.tslibs.offsets", "Milli"),
    ("pandas._libs.tslibs.offsets", "Minute"), ("pandas._libs.tslibs.offsets", "MonthEnd"),
    ("pandas._libs.tslibs.offsets", "Second"), ("pandas._libs.tslibs.offsets", "Nano"),
    ("pandas._libs.tslibs.period", "Period"), ("pandas._libs.tslibs.timedeltas", "Timedelta"),
    ("pandas._libs.tslibs.timestamps", "_unpickle_timestamp"),
    ("pandas.core.arrays.boolean", "BooleanArray"), ("pandas.core.arrays.boolean", "BooleanDtype"),
    ("pandas.core.arrays.categorical", "Categorical"), ("pandas.core.arrays.datetimes", "DatetimeArray"),
    ("pandas.core.arrays.floating", "Float64Dtype"), ("pandas.core.arrays.floating", "Float32Dtype"),
    ("pandas.core.arrays.floating", "FloatingArray"), ("pandas.core.arrays.integer", "Int64Dtype"),
    ("pandas.core.arrays.integer", "Int32Dtype"), ("pandas.core.arrays.integer", "IntegerArray"),
    ("pandas.core.arrays.string_", "StringArray"), ("pandas.core.arrays.string_", "StringDtype"),
    ("pandas.core.arrays.timedeltas", "TimedeltaArray"), ("pandas.core.dtypes.dtypes", "CategoricalDtype"),
    ("pandas.core.dtypes.dtypes", "DatetimeTZDtype"), ("pandas.core.frame", "DataFrame"),
    ("pandas.core.indexes.base", "Index"), ("pandas.core.indexes.base", "_new_Index"),
    ("pandas.core.indexes.category", "CategoricalIndex"), ("pandas.core.indexes.datetimes", "DatetimeIndex"),
    ("pandas.core.indexes.datetimes", "_new_DatetimeIndex"), ("pandas.core.indexes.multi", "MultiIndex"),
    ("pandas.core.indexes.numeric", "Float64Index"), ("pandas.core.indexes.numeric", "Int64Index"),
    ("pandas.core.indexes.numeric", "UInt64Index"), ("pandas.core.indexes.range", "RangeIndex"),
    ("pandas.core.indexes.timedeltas", "TimedeltaIndex"), ("pandas.core.internals.blocks", "new_block"),
    ("pandas.core.internals.managers", "BlockManager"),
    ("pandas.core.internals.managers", "SingleBlockManager"), ("pandas.core.series", "Series"),
    ("pytz", "_UTC"), ("pytz", "_p"),
}
BLOB_ROOTS = ("numpy", "pandas", "datetime", "decimal", "fractions", "array", "pytz")
MAX_MSG = 1 << 30


class _Plain(pickle.Unpickler):
    """The envelope: plain data only (no global may be named)."""
    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"refused: {module}.{name}")


class _Allowed(pickle.Unpickler):
    def find_class(self, module, name):
        if (module, name) not in ALLOW:
            raise pickle.UnpicklingError(f"refused: {module}.{name}")
        return super().find_class(module, name)


def _blob_load(b):
    return _Allowed(io.BytesIO(b)).load()


class StudentError(Exception):
    """Same name and module as academy_check.StudentError: the checker maps it to that class."""


StudentError.__module__ = "academy_check"


class Lost(Exception):
    pass


# ---------------------------------------------------------------- trusted / writable places
def read_only(path):
    """True if `path` is on a read-only mount (system, /academy/lib, /data…): a student cannot have
    written it. Anything else (home, /tmp…) is the student's."""
    try:
        return bool(os.statvfs(os.path.realpath(path)).f_flag & os.ST_RDONLY)
    except OSError:
        return False


def _module_path_ok(mod):
    f = getattr(mod, "__file__", None)
    return isinstance(mod, types.ModuleType) and (f is None or read_only(f))


# ---------------------------------------------------------------- one end of the pipe
_EXC_BASES = {n: getattr(__import__("builtins"), n) for n in dir(__import__("builtins"))
              if isinstance(getattr(__import__("builtins"), n), type)
              and issubclass(getattr(__import__("builtins"), n), BaseException)}
_UNARY = {"len": len, "iter": iter, "next": next, "bool": bool, "str": str, "repr": repr, "hash": hash,
          "float": float, "int": int, "index": operator.index, "complex": complex, "trunc": math.trunc,
          "floor": math.floor, "ceil": math.ceil, "neg": operator.neg, "pos": operator.pos,
          "abs": operator.abs, "invert": operator.invert, "dir": dir, "reversed": reversed,
          "copy": copy.copy, "enter": lambda o: o.__enter__()}
_BINARY = {n: getattr(operator, n) for n in ("add", "sub", "mul", "truediv", "floordiv", "mod", "pow",
                                              "matmul", "and_", "or_", "xor", "lshift", "rshift",
                                              "eq", "ne", "lt", "le", "gt", "ge", "getitem", "delitem",
                                              "contains")}
_BINARY.update({"r" + n: (lambda f: (lambda a, b: f(b, a)))(getattr(operator, n))
                for n in ("add", "sub", "mul", "truediv", "floordiv", "mod", "pow", "matmul", "and_",
                          "or_", "xor", "lshift", "rshift")})
_BINARY.update({"format": format, "round": round, "isinstance": isinstance, "issubclass": issubclass,
                "deepcopy": copy.deepcopy})
_INSPECT = ("getsource", "getsourcelines", "getsourcefile", "getfile", "getdoc", "getcomments",
            "isfunction", "ismethod", "isclass", "ismodule", "isroutine", "isbuiltin",
            "isgeneratorfunction", "iscoroutinefunction", "isgenerator", "getfullargspec")
_MUTABLE_TAGS = ("L", "D", "S", "B", "P")


class Peer:
    """One end. `trusted_other`: the other end is the checker (host side, no limits). The checker's
    end (trusted_other False) answers only call / public getattr / operators on what it exported."""

    def __init__(self, rfd, wfd, trusted_other, untrusted_roots=()):
        self.rfd, self.wfd = rfd, wfd
        self.trusted_other = trusted_other
        self.untrusted_roots = tuple(untrusted_roots)
        self.exported, self.export_ids = {}, {}
        self.proxies = {}
        self.next_req = 0
        self.gen = 0                     # bumped by the checker side when the host is restarted
        self.out_stack = []

    # ---- framing
    def _write(self, obj):
        data = pickle.dumps(obj, protocol=4)
        data = struct.pack("<Q", len(data)) + data
        view = memoryview(data)
        while view:
            n = os.write(self.wfd, view)
            view = view[n:]

    def _read_exact(self, n):
        chunks, got = [], 0
        while got < n:
            b = os.read(self.rfd, min(n - got, 1 << 20))
            if not b:
                raise EOFError
            chunks.append(b)
            got += len(b)
        return b"".join(chunks)

    def _read(self):
        (n,) = struct.unpack("<Q", self._read_exact(8))
        if n > MAX_MSG:
            raise pickle.UnpicklingError("message too large")
        return _Plain(io.BytesIO(self._read_exact(n))).load()

    # ---- values
    def export(self, obj):
        k = id(obj)
        rid = self.export_ids.get(k)
        if rid is None or self.exported.get(rid) is not obj:
            rid = len(self.exported) + 1
            self.exported[rid] = obj
            self.export_ids[k] = rid
        return rid

    def meta(self, obj):
        def s(v):
            return v if isinstance(v, str) else None
        kind = ("module" if isinstance(obj, types.ModuleType) else "class" if isinstance(obj, type) else
                "function" if isinstance(obj, (types.FunctionType, types.BuiltinFunctionType)) else
                "method" if isinstance(obj, types.MethodType) else "object")
        return {"n": s(getattr(obj, "__name__", None)) if kind != "object" else None,
                "q": s(getattr(obj, "__qualname__", None)) if kind != "object" else None,
                "m": s(getattr(obj, "__module__", None)) if kind in ("class", "function", "method") else None,
                "k": kind, "c": callable(obj), "t": type(obj).__name__}

    def encode(self, obj, depth=0):
        if obj is None or obj is True or obj is False:
            return obj
        t = type(obj)
        if t in (int, float, str, bytes):
            return obj
        if depth > 60:
            return self._ref(obj)
        if t is list:
            return ("L", [self.encode(x, depth + 1) for x in obj])
        if t is tuple:
            return ("T", [self.encode(x, depth + 1) for x in obj])
        if t is dict:
            return ("D", [(self.encode(k, depth + 1), self.encode(v, depth + 1)) for k, v in obj.items()])
        if t is set:
            return ("S", [self.encode(x, depth + 1) for x in obj])
        if t is frozenset:
            return ("F", [self.encode(x, depth + 1) for x in obj])
        if t is complex:
            return ("C", obj.real, obj.imag)
        if t is bytearray:
            return ("B", bytes(obj))
        if t is slice:
            return ("SL", self.encode(obj.start), self.encode(obj.stop), self.encode(obj.step))
        if t is range:
            return ("R", obj.start, obj.stop, obj.step)
        if obj is Ellipsis:
            return ("E",)
        if isinstance(obj, RemoteObject) and object.__getattribute__(obj, "_rp_peer") is self:
            return ("Y", obj._rp_target())                       # an object of the other side, back home
        if isinstance(obj, tuple) and hasattr(t, "_fields") and all(isinstance(f, str) for f in t._fields):
            return ("NT", t.__name__, list(t._fields), [self.encode(x, depth + 1) for x in obj])
        if isinstance(obj, dict) and t.__module__ == "collections":          # OrderedDict, defaultdict, Counter
            return ("D", [(self.encode(k, depth + 1), self.encode(v, depth + 1)) for k, v in obj.items()])
        root = (t.__module__ or "").split(".")[0]
        if root in BLOB_ROOTS:
            try:
                b = pickle.dumps(obj, protocol=4)
                _blob_load(b)                                       # only what the other side accepts
                return ("P", b)
            except Exception:
                pass
        if hasattr(t, "get_fields_and_field_types") and self._ros_ok(t):
            try:
                return ("ROS", t.__module__, t.__name__,
                        [(f, self.encode(getattr(obj, f), depth + 1)) for f in obj.get_fields_and_field_types()])
            except Exception:
                pass
        return self._ref(obj)

    def _ros_ok(self, t):
        mod = sys.modules.get(t.__module__)
        f = getattr(mod, "__file__", None) or ""
        return bool(f) and not any(os.path.realpath(f).startswith(r) for r in self.untrusted_roots) and read_only(f)

    def _ref(self, obj):
        if not self.trusted_other and isinstance(obj, types.ModuleType):
            raise TypeError("check.py cannot give a module to the student's code")
        return ("M", self.export(obj), self.meta(obj))

    def decode(self, v, path=None):
        if not isinstance(v, tuple):
            if v is None or isinstance(v, (bool, int, float, str, bytes)):
                return v
            raise pickle.UnpicklingError(f"bad value {type(v).__name__}")
        tag = v[0]
        if tag == "L":
            return [self.decode(x) for x in v[1]]
        if tag == "T":
            return tuple(self.decode(x) for x in v[1])
        if tag == "D":
            return {self.decode(k): self.decode(x) for k, x in v[1]}
        if tag == "S":
            return {self.decode(x) for x in v[1]}
        if tag == "F":
            return frozenset(self.decode(x) for x in v[1])
        if tag == "C":
            return complex(v[1], v[2])
        if tag == "B":
            return bytearray(v[1])
        if tag == "SL":
            return slice(self.decode(v[1]), self.decode(v[2]), self.decode(v[3]))
        if tag == "R":
            return range(v[1], v[2], v[3])
        if tag == "E":
            return Ellipsis
        if tag == "NT":
            return _namedtuple(v[1], tuple(v[2]))(*[self.decode(x) for x in v[3]])
        if tag == "P":
            return _blob_load(v[1])
        if tag == "ROS":
            return self._decode_ros(v)
        if tag == "M":                                   # an object living on the other side
            if not (isinstance(v[1], int) and isinstance(v[2], dict)):
                raise pickle.UnpicklingError("bad reference")
            return self.proxy(v[1], v[2], path)
        if tag == "Y":                                   # one of ours, coming back
            try:
                return self.exported[v[1]]
            except KeyError:
                raise Lost("unknown object") from None
        raise pickle.UnpicklingError(f"bad tag {tag!r}")

    def _decode_ros(self, v):
        import importlib
        modname, clsname, fields = v[1], v[2], v[3]
        if not (isinstance(modname, str) and ".msg" in modname and isinstance(clsname, str)):
            raise pickle.UnpicklingError("bad ROS message")
        mod = importlib.import_module(modname)
        cls = getattr(mod, clsname, None)
        if not (_module_path_ok(mod) and isinstance(cls, type) and hasattr(cls, "get_fields_and_field_types")):
            raise pickle.UnpicklingError(f"ROS message {modname}.{clsname} is not an installed type")
        m = cls()
        for f, x in fields:
            if f in cls.get_fields_and_field_types():
                setattr(m, f, self.decode(x))
        return m

    def proxy(self, rid, meta, path=None):
        key = (self.gen, rid)
        p = self.proxies.get(key)
        if p is None:
            p = _proxy_class(meta)()
            for k, val in (("_rp_peer", self), ("_rp_rid", rid), ("_rp_gen", self.gen), ("_rp_meta", meta),
                           ("_rp_path", path)):
                object.__setattr__(p, k, val)
            self.proxies[key] = p
        return p

    # ---- requests (both directions are re-entrant: a call may call back)
    def request(self, op, *args):
        self.next_req += 1
        rid = self.next_req
        # the checker's current folder goes along: check.py may os.chdir() before calling student code
        self._write(("q", rid, op, args, None if self.trusted_other else _cwd()))
        while True:
            msg = self._read()
            if not (isinstance(msg, tuple) and msg):
                raise pickle.UnpicklingError("bad message")
            if msg[0] == "q":
                self._serve(msg)
                continue
            if msg[0] == "r" and msg[1] == rid:
                return msg
            raise pickle.UnpicklingError("unexpected answer")

    def serve_forever(self):
        while True:
            try:
                msg = self._read()
            except EOFError:
                return
            except TimeoutError:                     # a late interrupt while idle
                continue
            if isinstance(msg, tuple) and msg and msg[0] == "q":
                self._serve(msg)

    def _serve(self, msg):
        _, rid, op, args = msg[:4]
        if self.trusted_other and len(msg) > 4 and isinstance(msg[4], str):
            try:
                if os.getcwd() != msg[4]:
                    os.chdir(msg[4])
            except OSError:
                pass
        out, err = io.StringIO(), io.StringIO()
        saved = sys.stdout, sys.stderr
        if self.trusted_other:                                   # the host captures the student's prints
            sys.stdout, sys.stderr = out, err
        mutations = []
        try:
            value = self._handle(op, args, mutations)
            reply = ("r", rid, True, self.encode(value), out.getvalue(), err.getvalue(), mutations)
        except BaseException as e:                               # noqa: BLE001 — everything goes back
            if isinstance(e, KeyboardInterrupt) and not self.trusted_other:
                raise
            reply = ("r", rid, False, self.encode_exc(e), out.getvalue(), err.getvalue(), [])
        finally:
            if self.trusted_other:
                sys.stdout, sys.stderr = saved
        try:
            self._write(reply)
        except (TypeError, pickle.PicklingError, RecursionError) as e:
            self._write(("r", rid, False, self.encode_exc(e), "", "", []))

    def _obj(self, ref):
        try:
            return self.exported[ref]
        except (KeyError, TypeError):
            raise Lost("this object was lost (the student's Python process was restarted)") from None

    def _handle(self, op, args, mutations):
        if not self.trusted_other:                               # the checker's end: very limited
            return self._handle_limited(op, args)
        if op == "load":
            return _host_load(*args)
        if op == "import":
            return _host_import(*args)
        if op == "getattr":
            return getattr(self._obj(args[0]), args[1])
        if op == "setattr":
            return setattr(self._obj(args[0]), args[1], self.decode(args[2]))
        if op == "delattr":
            return delattr(self._obj(args[0]), args[1])
        if op == "call":
            f = self._obj(args[0])
            pos = [self.decode(a) for a in args[1]]
            kw = {k: self.decode(a) for k, a in args[2]}
            r = f(*pos, **kw)
            for i, enc in enumerate(args[1]):
                if isinstance(enc, tuple) and enc and enc[0] in _MUTABLE_TAGS:
                    now = self._encode_quiet(pos[i])
                    if now is not None and now != enc:
                        mutations.append((i, now))
            for k, enc in args[2]:
                if isinstance(enc, tuple) and enc and enc[0] in _MUTABLE_TAGS:
                    now = self._encode_quiet(kw[k])
                    if now is not None and now != enc:
                        mutations.append((k, now))
            return r
        if op == "unary":
            return _UNARY[args[0]](self._obj(args[1]))
        if op == "binary":
            return _BINARY[args[0]](self.decode(args[1]), self.decode(args[2]))
        if op == "setitem":
            return operator.setitem(self._obj(args[0]), self.decode(args[1]), self.decode(args[2]))
        if op == "exit":
            return self._obj(args[0]).__exit__(*[self.decode(a) for a in args[1]])
        if op == "array":
            import numpy as np
            a = np.asarray(self._obj(args[0]))
            return a if args[1] is None else a.astype(args[1])
        if op == "inspect":
            import inspect
            if args[1] not in _INSPECT:
                raise ValueError(args[1])
            return getattr(inspect, args[1])(self._obj(args[0]))
        if op == "signature":
            import inspect
            sig = inspect.signature(self._obj(args[0]))
            return [(p.name, int(p.kind), p.default is not p.empty, None if p.default is p.empty else p.default)
                    for p in sig.parameters.values()]
        raise ValueError(f"unknown request {op!r}")

    def _handle_limited(self, op, args):
        if op == "call":
            f = self._obj(args[0])
            if not callable(f):
                raise TypeError("not callable")
            return f(*[self.decode(a) for a in args[1]], **{k: self.decode(a) for k, a in args[2]})
        if op == "getattr":
            name = args[1]
            if not isinstance(name, str) or name.startswith("_"):
                raise AttributeError(f"the student's code may not read {name!r} of the check's objects")
            return getattr(self._obj(args[0]), name)
        if op == "unary" and args[0] in _UNARY and args[0] != "dir":
            return _UNARY[args[0]](self._obj(args[1]))
        if op == "binary" and args[0] in _BINARY:
            return _BINARY[args[0]](self.decode(args[1]), self.decode(args[2]))
        raise PermissionError(f"the student's code may not do {op!r} on the check's objects")

    def _encode_quiet(self, obj):
        try:
            return self.encode(obj)
        except Exception:
            return None

    def encode_exc(self, e):
        import traceback
        bases = [c.__name__ for c in type(e).__mro__ if c.__module__ == "builtins" and c.__name__ in _EXC_BASES]
        try:
            eargs = self.encode(tuple(e.args)) if self.trusted_other else ("T", [str(e)])
        except Exception:
            eargs = ("T", [str(e)])
        where, tb = "", ""
        if self.trusted_other:                     # host: where in the student's files (never on the checker side)
            frames = [f for f in traceback.extract_tb(e.__traceback__)
                      if not f.filename.startswith(("/academy/lib/", "<frozen"))
                      and "importlib" not in f.filename]
            if frames:
                where = f"{_show(frames[-1].filename)} line {frames[-1].lineno}"
            tb = "".join(traceback.format_list(frames[-8:]))
            if isinstance(e, SyntaxError) and e.filename:
                where = f"{_show(e.filename)} line {e.lineno}"
        return (type(e).__name__, type(e).__module__ or "", bases, eargs, _safe_str(e), where, tb,
                getattr(e, "lineno", None) if isinstance(e, SyntaxError) else None,
                getattr(e, "msg", None) if isinstance(e, SyntaxError) else None,
                _show(e.filename) if isinstance(e, SyntaxError) and e.filename else None)

    def raise_exc(self, info):
        name, module, bases, eargs, text, where, tb, lineno, msg, filename = info
        cls = _exc_class(name, module, bases)
        try:
            args = self.decode(eargs)
        except Exception:
            args = (text,)
        e = None
        for attempt in ((lambda: cls(*args)) if isinstance(args, tuple) else (lambda: cls(text)),
                        lambda: cls(text), lambda: _exc_class(name, "student", ["Exception"])(text)):
            try:
                e = attempt()
                break
            except Exception:
                continue
        if isinstance(e, SyntaxError):
            e.lineno, e.msg, e.filename = lineno, msg or text, filename
        try:
            e.academy_where, e.academy_tb = where, tb
        except Exception:
            pass
        raise e


def _cwd():
    try:
        return os.getcwd()
    except OSError:
        return None


def _safe_str(e):
    try:
        return str(e)
    except Exception:
        return type(e).__name__


def _show(path):
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return os.path.basename(path)
    return os.path.basename(path) if rel.startswith("..") else rel


_NT = {}


def _namedtuple(name, fields):
    import collections
    key = (name, fields)
    if key not in _NT:
        try:
            _NT[key] = collections.namedtuple(name, fields)
        except ValueError:
            _NT[key] = lambda *a: tuple(a)
    return _NT[key]


_EXC = {}


def _exc_class(name, module, bases):
    if module == "builtins" and name in _EXC_BASES:
        return _EXC_BASES[name]
    if module == "academy_check" and name in ("StudentError", "CheckFailed"):
        import academy_check                       # both are failures; never Skip
        return getattr(academy_check, name)
    base = next((_EXC_BASES[b] for b in bases if b in _EXC_BASES), Exception)
    if base in (SystemExit, KeyboardInterrupt, GeneratorExit):
        base = RuntimeError if base is not SystemExit else SystemExit
    key = (name, base)
    if key not in _EXC:
        safe = name if name.isidentifier() else "StudentException"
        _EXC[key] = type(safe, (base,), {"__module__": "student"})
    return _EXC[key]


# ---------------------------------------------------------------- proxies (checker side, and host side)
class RemoteObject:
    __slots__ = ("_rp_peer", "_rp_rid", "_rp_gen", "_rp_meta", "_rp_path", "__weakref__")

    def __getattribute__(self, name):
        if name.startswith("_rp_") or name in ("__class__", "__slots__"):
            return object.__getattribute__(self, name)
        meta = object.__getattribute__(self, "_rp_meta")
        if name == "__name__" and meta.get("n"):
            return meta["n"]
        if name == "__qualname__" and meta.get("q"):
            return meta["q"]
        if name == "__module__" and meta.get("m"):
            return meta["m"]
        return _ask(self, "getattr", name, path_attr=name)

    def __setattr__(self, name, value):
        if name.startswith("_rp_"):
            return object.__setattr__(self, name, value)
        if name == "__spec__":                      # set by the import system: keep the host's own
            return None
        peer = object.__getattribute__(self, "_rp_peer")
        _ask(self, "setattr", name, peer.encode(value))

    def __delattr__(self, name):
        _ask(self, "delattr", name)

    def _rp_target(self):
        """The id of the object in the current host (reconnects a module/function/class after a restart)."""
        peer = object.__getattribute__(self, "_rp_peer")
        gen = object.__getattribute__(self, "_rp_gen")
        if gen == peer.gen:
            return object.__getattribute__(self, "_rp_rid")
        path = object.__getattribute__(self, "_rp_path")
        if not path or not hasattr(peer, "resolve_path"):
            raise StudentError("this object was lost when your code was stopped (time limit) — the check "
                               "restarted your code")
        p = peer.resolve_path(path)
        object.__setattr__(self, "_rp_rid", object.__getattribute__(p, "_rp_rid"))
        object.__setattr__(self, "_rp_gen", peer.gen)
        return object.__getattribute__(p, "_rp_rid")

    def __repr__(self):
        return _ask(self, "unary", "repr")

    def __str__(self):
        return _ask(self, "unary", "str")

    def __format__(self, spec):
        return _binary("format", self, spec)

    def __bool__(self):
        return _ask(self, "unary", "bool")

    def __len__(self):
        return _ask(self, "unary", "len")

    def __iter__(self):
        return _ask(self, "unary", "iter")

    def __next__(self):
        return _ask(self, "unary", "next")

    def __reversed__(self):
        return _ask(self, "unary", "reversed")

    def __getitem__(self, k):
        return _binary("getitem", self, k)

    def __setitem__(self, k, v):
        peer = object.__getattribute__(self, "_rp_peer")
        _ask(self, "setitem", peer.encode(k), peer.encode(v), first_is_self=True)

    def __delitem__(self, k):
        return _binary("delitem", self, k)

    def __contains__(self, k):
        return _binary("contains", self, k)

    def __hash__(self):
        return _ask(self, "unary", "hash")

    def __float__(self):
        return _ask(self, "unary", "float")

    def __int__(self):
        return _ask(self, "unary", "int")

    def __index__(self):
        return _ask(self, "unary", "index")

    def __complex__(self):
        return _ask(self, "unary", "complex")

    def __trunc__(self):
        return _ask(self, "unary", "trunc")

    def __floor__(self):
        return _ask(self, "unary", "floor")

    def __ceil__(self):
        return _ask(self, "unary", "ceil")

    def __round__(self, n=None):
        return _binary("round", self, n)

    def __neg__(self):
        return _ask(self, "unary", "neg")

    def __pos__(self):
        return _ask(self, "unary", "pos")

    def __abs__(self):
        return _ask(self, "unary", "abs")

    def __invert__(self):
        return _ask(self, "unary", "invert")

    def __dir__(self):
        return _ask(self, "unary", "dir")

    def __enter__(self):
        return _ask(self, "unary", "enter")

    def __exit__(self, *exc):
        peer = object.__getattribute__(self, "_rp_peer")
        args = [None, None, None] if exc[0] is None else [None, _safe_str(exc[1]), None]
        return _ask(self, "exit", [peer.encode(a) for a in args], first_is_self=True)

    def __array__(self, dtype=None):
        return _ask(self, "array", None if dtype is None else str(dtype), first_is_self=True)

    def __instancecheck__(self, obj):
        return _binary("isinstance", obj, self)

    def __subclasscheck__(self, cls):
        return _binary("issubclass", cls, self)

    def __copy__(self):
        return _ask(self, "unary", "copy")

    def __deepcopy__(self, memo):
        return _binary("deepcopy", self, None)

    def __reduce_ex__(self, proto):
        raise TypeError("an object of the student's code cannot be pickled by the check")


def _bin(name):
    def f(self, other):
        return _binary(name, self, other)
    f.__name__ = f"__{name.rstrip('_')}__"
    return f


for _n in ("add", "sub", "mul", "truediv", "floordiv", "mod", "pow", "matmul", "and_", "or_", "xor",
           "lshift", "rshift", "radd", "rsub", "rmul", "rtruediv", "rfloordiv", "rmod", "rpow", "rmatmul",
           "rand_", "ror_", "rxor", "rlshift", "rrshift", "eq", "ne", "lt", "le", "gt", "ge"):
    setattr(RemoteObject, f"__{_n.rstrip('_')}__", _bin(_n))


class RemoteCallable(RemoteObject):
    __slots__ = ()

    def __call__(self, *args, **kwargs):
        peer = object.__getattribute__(self, "_rp_peer")
        enc = [peer.encode(a) for a in args]
        kenc = [(k, peer.encode(v)) for k, v in kwargs.items()]
        r, mutations = _ask(self, "call", enc, kenc, first_is_self=True, want_mutations=True)
        for key, val in mutations:
            target = args[key] if isinstance(key, int) and key < len(args) else kwargs.get(key)
            _copy_back(target, peer.decode(val))
        return r


def _copy_back(target, new):
    try:
        if isinstance(target, (list, bytearray)):
            target[:] = new
        elif isinstance(target, (dict, set)):
            target.clear()
            target.update(new)
        elif type(target).__module__ == "numpy" and type(target).__name__ == "ndarray":
            if getattr(new, "shape", None) == target.shape:
                target[...] = new
    except Exception:
        pass


_PCLS = {}


def _proxy_class(meta):
    base = RemoteCallable if meta.get("c") else RemoteObject
    name = meta.get("t") or "object"
    if not name.isidentifier():
        name = "object"
    key = (name, base)
    if key not in _PCLS:
        _PCLS[key] = type(name, (base,), {"__slots__": (), "__module__": "student"})
    return _PCLS[key]


def _ask(proxy, op, *args, path_attr=None, first_is_self=True, want_mutations=False):
    peer = object.__getattribute__(proxy, "_rp_peer")
    if isinstance(peer, Host):
        peer.ensure()
    target = proxy._rp_target()
    if op == "unary":
        req = (args[0], target)
    else:
        req = (target,) + args
    ans = peer.call_remote(op, req)
    _, _, ok, value, out, err, mutations = ans
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    if not ok:
        peer.raise_exc(value)
    path = None
    if path_attr is not None:
        meta = object.__getattribute__(proxy, "_rp_meta")
        ppath = object.__getattribute__(proxy, "_rp_path")
        if ppath and meta.get("k") in ("module", "class"):
            path = ppath + (path_attr,)
    r = peer.decode(value, path)
    return (r, mutations) if want_mutations else r


def _binary(name, a, b):
    """a <op> b where a or b is a proxy: the host computes it with Python's own rules."""
    p = a if isinstance(a, RemoteObject) else b
    peer = object.__getattribute__(p, "_rp_peer")
    if isinstance(peer, Host):
        peer.ensure()
    ans = peer.call_remote("binary", (name, peer.encode(a), peer.encode(b)))
    _, _, ok, value, out, err, _m = ans
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    if not ok:
        peer.raise_exc(value)
    return peer.decode(value)


# ---------------------------------------------------------------- checker side: the host process
class Host(Peer):
    """The checker's end; starts (and restarts) the student's Python process."""

    def __init__(self, env, cwd, untrusted_roots):
        super().__init__(-1, -1, trusted_other=False, untrusted_roots=untrusted_roots)
        self.env, self.cwd, self.proc = env, cwd, None
        self.depth = 0

    def start(self):
        import subprocess
        c2h_r, c2h_w = os.pipe()
        h2c_r, h2c_w = os.pipe()
        self.proc = subprocess.Popen(
            [sys.executable, "-B", os.path.abspath(__file__), "--host", str(c2h_r), str(h2c_w),
             ":".join(self.untrusted_roots)],
            pass_fds=(c2h_r, h2c_w), env=self.env, cwd=self.cwd, stdin=subprocess.DEVNULL)
        os.close(c2h_r)
        os.close(h2c_w)
        self.rfd, self.wfd = h2c_r, c2h_w
        self.gen += 1
        self.exported, self.export_ids = {}, {}

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=5)
            except Exception:
                pass
            for fd in (self.rfd, self.wfd):
                try:
                    os.close(fd)
                except OSError:
                    pass
            self.proc = None

    def ensure(self):
        """A running host (restarted after a crash or a time limit: proxies of modules, functions and
        classes reconnect, other objects are lost)."""
        if not self.alive():
            self.stop()
            self.start()

    def call_remote(self, op, args):
        self.ensure()
        self.depth += 1
        try:
            return self.request(op, *args)
        except EOFError:
            code = self.proc.wait() if self.proc else None
            self.stop()
            raise StudentError(f"your code stopped the Python process (exit code {code}) — a call to "
                               "exit()/os._exit(), or a crash?") from None
        except pickle.UnpicklingError as e:
            self.stop()
            raise StudentError(f"your code sent something the check cannot read ({e})") from None
        except BaseException:
            # interrupted (the time limit of run(), Ctrl-C): stop the student's code, keep the process
            # if it answers in time, else kill it
            self._interrupt()
            raise
        finally:
            self.depth -= 1

    def _interrupt(self):
        if not self.alive():
            self.stop()
            return
        if self.depth > 1:
            self.stop()
            return
        try:
            os.kill(self.proc.pid, signal.SIGUSR1)
            import time
            end = time.monotonic() + 2.0
            while time.monotonic() < end:
                r, _, _ = select.select([self.rfd], [], [], max(0.0, end - time.monotonic()))
                if not r:
                    break
                msg = self._read()
                if isinstance(msg, tuple) and msg and msg[0] == "r" and msg[1] == self.next_req:
                    return                                    # the host is back in its loop
                if isinstance(msg, tuple) and msg and msg[0] == "q":
                    self._write(("r", msg[1], False, self.encode_exc(TimeoutError("stopped")), "", "", []))
        except Exception:
            pass
        self.stop()

    def resolve_path(self, path):
        kind = path[0]
        if kind == "load":
            p = load(path[1], fresh=False, _reconnect=True)
        elif kind == "import":
            p = _import_remote(path[1], path[2])
        else:
            raise StudentError("lost object")
        for name in path[3 if kind == "import" else 2:]:
            p = getattr(p, name)
        if not isinstance(p, RemoteObject):
            raise StudentError("lost object")
        return p


HOST = None
_loaded = {}


def activate(env, cwd, untrusted_roots):
    """Called once by academy_sealed: from now on student code runs in the host."""
    global HOST
    HOST = Host(env, cwd, untrusted_roots)
    _patch_inspect()
    sys.meta_path.insert(_pathfinder_index(), _RemoteFinder())


def shutdown():
    if HOST is not None:
        HOST.stop()


def deactivate():
    """Undo activate() (tests only)."""
    global HOST
    shutdown()
    HOST = None
    _loaded.clear()
    sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, _RemoteFinder)]
    import inspect
    for name, orig in _ORIG_INSPECT.items():
        setattr(inspect, name, orig)


def load(filename, fresh=False, _reconnect=False):
    """academy_check.load_student() of a sealed check: the module stays in the host."""
    key = os.path.abspath(filename)
    if key in _loaded and not fresh and not _reconnect:
        p = _loaded[key]
        HOST.ensure()
        if object.__getattribute__(p, "_rp_gen") == HOST.gen:
            return p
    ans = HOST.call_remote("load", (filename, bool(fresh)))
    _, _, ok, value, out, err, _m = ans
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    if not ok:
        HOST.raise_exc(value)
    if fresh:
        for k in [k for k in _loaded if k != key]:
            del _loaded[k]
    p = HOST.decode(value, ("load", filename))
    _loaded[key] = p
    return p


def _import_remote(fullname, paths):
    ans = HOST.call_remote("import", (fullname, list(paths)))
    _, _, ok, value, out, err, _m = ans
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    if not ok:
        HOST.raise_exc(value)
    return HOST.decode(value, ("import", fullname, tuple(paths)))


def is_remote(obj):
    return isinstance(obj, RemoteObject)


def _pathfinder_index():
    import importlib.machinery
    for i, f in enumerate(sys.meta_path):
        if f is importlib.machinery.PathFinder:
            return i
    return len(sys.meta_path)


class _RemoteFinder:
    """An import, in the checker, of a module found in a writable folder becomes a host module."""

    def find_spec(self, fullname, path=None, target=None):
        import importlib.machinery
        import importlib.util
        if path is not None and isinstance(path, RemoteObject):
            path = list(path)
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None:
            return None
        loc = spec.origin if spec.has_location else None
        if loc is None and spec.submodule_search_locations:
            loc = list(spec.submodule_search_locations)[0]
        if loc is None or read_only(loc):
            return spec
        paths = [p for p in sys.path if isinstance(p, str) and p and not read_only(p)]
        return importlib.util.spec_from_loader(fullname, _RemoteLoader(paths), is_package=False)


class _RemoteLoader:
    def __init__(self, paths):
        self.paths = paths

    def create_module(self, spec):
        return _import_remote(spec.name, self.paths)

    def exec_module(self, module):
        return None


_ORIG_INSPECT = {}


def _patch_inspect():
    import inspect
    if _ORIG_INSPECT:
        return
    _ORIG_INSPECT.update({n: getattr(inspect, n) for n in _INSPECT + ("signature",)})
    for name in _INSPECT:
        orig = getattr(inspect, name)

        def wrapped(obj, *a, _orig=orig, _name=name, **k):
            if isinstance(obj, RemoteObject):
                return _ask(obj, "inspect", _name)
            return _orig(obj, *a, **k)
        wrapped.__name__ = name
        wrapped.__doc__ = orig.__doc__
        setattr(inspect, name, wrapped)
    orig_sig = inspect.signature

    def signature(obj, *a, **k):
        if isinstance(obj, RemoteObject):
            params = []
            for name, kind, has_default, default in _ask(obj, "signature"):
                params.append(inspect.Parameter(name, inspect._ParameterKind(kind),
                                                default=default if has_default else inspect.Parameter.empty))
            return inspect.Signature(params)
        return orig_sig(obj, *a, **k)
    inspect.signature = signature


# make `_ask` reach the right method name on both ends
def _call_remote_generic(self, op, args):
    return self.request(op, *args)


Peer.call_remote = _call_remote_generic


# ---------------------------------------------------------------- student source: always compiled fresh
def _fresh_loader_class():
    import importlib.machinery

    class FreshSourceLoader(importlib.machinery.SourceFileLoader):
        """A student's file is compiled from its source every time: no __pycache__ read or written.
        (A .pyc is reused when the size and the mtime second match: an answer edited to a same-length
        value within one second was graded from the OLD bytecode.) Read-only files (system) keep their
        .pyc."""

        def get_code(self, fullname):
            path = self.get_filename(fullname)
            if read_only(path):
                return super().get_code(fullname)
            with open(path, "rb") as f:
                source = f.read()
            return compile(source, path, "exec", dont_inherit=True)

    return FreshSourceLoader


def install_fresh_source_hook():
    """Every import from a writable folder (the student's) compiles the source fresh."""
    import importlib.machinery
    if getattr(sys, "_academy_fresh_hook", None):
        return sys._academy_fresh_hook
    loader = _fresh_loader_class()
    exts = importlib.machinery.EXTENSION_SUFFIXES
    hook = importlib.machinery.FileFinder.path_hook(
        (importlib.machinery.ExtensionFileLoader, exts),
        (loader, importlib.machinery.SOURCE_SUFFIXES),
        (importlib.machinery.SourcelessFileLoader, importlib.machinery.BYTECODE_SUFFIXES))
    sys.path_hooks.insert(0, hook)
    sys.path_importer_cache.clear()
    sys.dont_write_bytecode = True
    sys._academy_fresh_hook = loader
    return loader


def spec_from_file_fresh(name, path):
    import importlib.util
    loader = install_fresh_source_hook()
    return importlib.util.spec_from_file_location(name, path, loader=loader(name, path))


# ---------------------------------------------------------------- host side
def _host_load(filename, fresh):
    """The old academy_check.load_student, run in the host."""
    import importlib
    import importlib.util
    if filename.endswith(".py"):
        rel = os.path.normpath(filename)
        modname = rel[:-3].replace(os.sep, ".")
    else:
        modname = filename
        rel = filename.replace(".", os.sep)
        rel = os.path.join(rel, "__init__.py") if os.path.isdir(rel) else rel + ".py"
    if "." not in modname and filename.endswith(".py"):
        path = os.path.abspath(filename)
        if not os.path.exists(path):
            raise StudentError(f"{filename} is missing — did you delete or rename it?")
        if path in _host_loaded and not fresh:
            return _host_loaded[path]
        name = "student_" + os.path.splitext(os.path.basename(path))[0]
        spec = spec_from_file_fresh(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, os.path.dirname(path))
        try:
            spec.loader.exec_module(mod)
        except SyntaxError as e:
            raise StudentError(f"{filename} has a syntax error on line {e.lineno}: {e.msg}")
        except BaseException as e:                 # noqa: BLE001
            raise StudentError(f"{filename} crashed when loading: {type(e).__name__}: {e}")
        finally:
            sys.path.pop(0)
        _host_loaded[path] = mod
        return mod
    path = os.path.abspath(rel)
    if not os.path.exists(path):
        raise StudentError(f"{rel} is missing — did you delete or rename it?")
    if path in _host_loaded and not fresh:
        return _host_loaded[path]
    here = os.getcwd()
    if here in sys.path:
        sys.path.remove(here)
    sys.path.insert(0, here)
    top = modname.split(".")[0]
    if fresh:
        for k in [k for k in sys.modules if k == top or k.startswith(top + ".")]:
            del sys.modules[k]
        for k in [k for k in _host_loaded if k.startswith(os.path.join(here, top) + os.sep)]:
            del _host_loaded[k]
        importlib.invalidate_caches()
    try:
        mod = importlib.import_module(modname)
    except SyntaxError as e:
        raise StudentError(f"{_show(e.filename or rel)} has a syntax error on line {e.lineno}: {e.msg}")
    except BaseException as e:                     # noqa: BLE001
        import traceback
        frames = [f for f in traceback.extract_tb(e.__traceback__)
                  if not f.filename.startswith(("/academy/lib/", "<frozen")) and "importlib" not in f.filename]
        where = f" ({_show(frames[-1].filename)} line {frames[-1].lineno})" if frames else ""
        raise StudentError(f"{rel} crashed when loading: {type(e).__name__}: {e}{where}")
    _host_loaded[path] = mod
    return mod


_host_loaded = {}


def _host_import(fullname, paths):
    import importlib
    for p in reversed(paths):
        if p not in sys.path:
            sys.path.insert(0, p)
    return importlib.import_module(fullname)


def _host_main(rfd, wfd, roots):
    os.set_inheritable(rfd, False)
    os.set_inheritable(wfd, False)

    def stop(*_):
        raise TimeoutError("stopped by the check's time limit")
    signal.signal(signal.SIGUSR1, stop)
    install_fresh_source_hook()
    if sys.path and sys.path[0] == os.path.dirname(os.path.abspath(__file__)):
        pass                                        # /academy/lib stays (academy_check was importable before)
    peer = Peer(rfd, wfd, trusted_other=True, untrusted_roots=[r for r in roots.split(":") if r])
    peer.call_remote = _call_remote_generic.__get__(peer)
    peer.serve_forever()


if __name__ == "__main__" and len(sys.argv) >= 4 and sys.argv[1] == "--host":
    sys.modules.setdefault("academy_remote", sys.modules["__main__"])
    _host_main(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "")
