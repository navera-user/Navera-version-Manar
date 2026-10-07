# Lab 1 — First steps in your workspace

**Goal:** run your first program on the NAVERA computer, edit a file, and answer three questions.
**Time:** about 30 minutes.

## Step 1 — Open a terminal

Click the **⌨️ Terminal** tab on the right. You see a line like this:

```
student@navera:~/lessons/01-welcome$
```

It means: you are the user `student`, on the computer `navera`, in the folder `lessons/01-welcome`.
The computer waits for a command.

## Step 2 — Run your first program

Click **▶ Run** on the block below (or type it yourself and press `Enter`):

```bash
python3 hello_navera.py
```

The program prints a little "mission card". It does not know your name yet.

## Step 3 — Edit the program

Open [hello_navera.py](file:./hello_navera.py) in the **📝 Code** tab (it should already be open).
At the top you will find three lines:

```python
PILOT_NAME = "???"
FAVOURITE_VEHICLE = "???"
CITY = "???"
```

> [!TASK]
> Replace each `"???"` with your own answer **between the quotes**, for example `PILOT_NAME = "Sarra"`.
> For the vehicle, write one of: `drone`, `car`, `boat`, `robot`. Save with `Ctrl+S`.

Run it again:

```bash
python3 hello_navera.py
```

Your mission card now shows your name. 🎉

> [!WARNING]
> Keep the quotes `" "`. In Python, text must be between quotes. If you delete one, the program shows
> a `SyntaxError` — just put the quote back.

## Step 4 — Look around

Try these commands one after the other. Don't worry if you don't understand everything: lesson 2 is
all about the terminal.

```bash
ls
```

```bash
ls ~/navera
```

The second one lists the folders of **your NAVERA copy**: `day_pkg` is day vision, `night_pkg` night
vision, `cn_pkg` the stars, `gps_pkg` the GPS, `navera_estimator` the arbiter…

## Step 5 — Answer the quiz

Open [answers.py](file:./answers.py). Each question has choices `"a"`, `"b"`, `"c"`. Write the letter of
your answer between the quotes, then save.

> [!TASK]
> Answer the three questions in `answers.py`. The course tab has everything you need.

## Step 6 — Check your work

Press **✔ Check my work** at the bottom left. Green means done. If something is red, read the hint,
fix it, save and check again — you can check as many times as you want.

## Going further (optional)

- Open the **🧭 Operator view** tab. If it says the page cannot be reached, that is normal: NAVERA is
  not running yet. You will start it in lesson 28.
- In the terminal, run `cat ~/navera/README.md | head -30` to read the start of NAVERA's own manual.
