from academy_check import Checker, load_student, need, sh

c = Checker()


@c.test("hello_navera.py runs without errors",
        hint="Run `python3 hello_navera.py` in the terminal and read the error. A missing quote is the usual reason.")
def _():
    code, out = sh("python3 hello_navera.py", timeout=20)
    c.ok(code == 0, "the program stopped with an error:\n" + out[-600:])


@c.test("PILOT_NAME is your name", hint='Replace "???" by your name between the quotes.')
def _():
    m = load_student("hello_navera.py")
    (name,) = need(m, "PILOT_NAME")
    c.ok(isinstance(name, str) and name.strip() not in ("", "???"), "PILOT_NAME is still \"???\"")


@c.test("FAVOURITE_VEHICLE is drone, car, boat or robot", hint="Write exactly one of the four words, in lower case.")
def _():
    (v,) = need(load_student("hello_navera.py"), "FAVOURITE_VEHICLE")
    c.ok(str(v).strip().lower() in ("drone", "car", "boat", "robot"), f'FAVOURITE_VEHICLE is "{v}"')


@c.test("CITY is filled in", hint='Replace "???" by your city.')
def _():
    (v,) = need(load_student("hello_navera.py"), "CITY")
    c.ok(str(v).strip() not in ("", "???"), "CITY is still empty")


ANSWERS = {"Q1": ("b", "Fake signals = spoofing. Jamming is only noise."),
           "Q2": ("a", "Read the part 'Day vision' of the course again."),
           "Q3": ("c", "Its name is in the course: it decides who to trust.")}

for q, (good, hint) in ANSWERS.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")

c.run()
