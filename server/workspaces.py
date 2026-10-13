"""The base snapshot and the students' copies.

base/       git repo: NAVERA at one commit of the real repo (git archive, read only on
            the real repo), built with colcon inside a sandbox at /home/student/navera so
            the symlinked install works in every student sandbox. Tag "base".
students/<name>/home/navera    a clone of base (branch "work"): staff and students given NAVERA access only
students/<name>/home/lessons   the lesson files (starter code, the student's answers)
students/<name>/backups        git bundles taken before every full reset
"""
import datetime
import json
import os
import shutil
import subprocess
import tarfile
import tempfile

import config
import netns
import sandbox

ADMIN_NAME = "_builder"
GIT_ID = ["-c", "user.name=NAVERA Academy", "-c", "user.email=academy@localhost"]


def _run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def base_info():
    p = os.path.join(config.BASE, ".academy_base.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def build_base(commit, log=print):
    """Snapshot `commit` of the real repo into base/ and build it. The real repo is only read."""
    commit = _run(["git", "-C", config.REAL_REPO, "rev-parse", "--verify", commit + "^{commit}"]).stdout.strip()
    subject = _run(["git", "-C", config.REAL_REPO, "log", "-1", "--format=%h %s", commit]).stdout.strip()
    new = config.BASE + ".new"
    shutil.rmtree(new, ignore_errors=True)
    os.makedirs(new)
    log(f"snapshot {subject}")
    with tempfile.TemporaryFile() as t:
        subprocess.run(["git", "-C", config.REAL_REPO, "archive", "--format=tar", commit],
                       stdout=t, check=True)
        t.seek(0)
        with tarfile.open(fileobj=t) as tar:
            members = [m for m in tar.getmembers()
                       if not any(m.name == e.rstrip("/") or m.name.startswith(e) for e in config.BASE_EXCLUDE)]
            tar.extractall(new, members=members)
    # Student-friendly notes on top of the product's own README.
    with open(os.path.join(new, "ACADEMY_README.md"), "w") as f:
        f.write(ACADEMY_README)
    gi = os.path.join(new, ".gitignore")
    with open(gi, "a") as f:
        f.write("\n# academy\nbuild/\ninstall/\nlog/\n")
    log("colcon build (2–6 min)…")
    builder_home = os.path.join(config.ACADEMY, "state", "builder_home")
    os.makedirs(builder_home, exist_ok=True)
    cmd = ["bash", "-lc", "source /opt/ros/humble/setup.bash && cd ~/navera && "
           "colcon build --symlink-install --packages-select " + " ".join(config.BUILD_PACKAGES) +
           " --event-handlers console_direct- 2>&1 | tail -25; exit ${PIPESTATUS[0]}"]
    r = subprocess.run(sandbox.bwrap_argv(ADMIN_NAME, builder_home, 0, cmd, writable_base=new,
                                          heavy=True, host_net=True), text=True, capture_output=True)
    log(r.stdout[-3000:] + r.stderr[-2000:])
    if r.returncode != 0:
        raise RuntimeError("colcon build failed — base not changed")
    _run(["git", "init", "-q", "-b", "work", new])
    _run(["git", "-C", new, "add", "-A"])
    _run(["git", "-C", new, *GIT_ID, "commit", "-q", "-m", f"NAVERA base — {subject}"])
    _run(["git", "-C", new, "tag", "base"])
    with open(os.path.join(new, ".academy_base.json"), "w") as f:
        json.dump({"commit": commit, "subject": subject,
                   "built": datetime.datetime.now().isoformat(timespec="seconds")}, f)
    old = config.BASE + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.exists(config.BASE):
        os.rename(config.BASE, old)
    os.rename(new, config.BASE)
    shutil.rmtree(old, ignore_errors=True)
    log("base ready")
    return base_info()


def student_home(name):
    return os.path.join(config.STUDENTS, name, "home")


def _copy_build(dst):
    for d in ("build", "install"):
        shutil.rmtree(os.path.join(dst, d), ignore_errors=True)
        shutil.copytree(os.path.join(config.BASE, d), os.path.join(dst, d), symlinks=True)


def create_student(name):
    home = student_home(name)
    os.makedirs(os.path.join(home, "lessons"), exist_ok=True)
    os.makedirs(os.path.join(config.STUDENTS, name, "backups"), exist_ok=True)
    nav = os.path.join(home, "navera")
    if config.navera_allowed(name):
        if not os.path.exists(nav):
            _clone(nav)
    elif os.path.exists(nav):            # real NAVERA is not part of the course: keep a backup, remove the copy
        backup(name)
        shutil.rmtree(nav, ignore_errors=True)
    with open(os.path.join(home, ".bashrc"), "w") as f:
        f.write(bashrc(config.navera_allowed(name)))
    return home


def _clone(nav):
    _run(["git", "clone", "-q", "--no-hardlinks", config.BASE, nav])
    _run(["git", "-C", nav, "remote", "rename", "origin", "base"])
    # Without base/HEAD, "base" means only the tag: no "refname 'base' is ambiguous" warning.
    _run(["git", "-C", nav, "remote", "set-head", "base", "-d"])
    _copy_build(nav)


def backup(name):
    nav = os.path.join(student_home(name), "navera")
    if not os.path.isdir(os.path.join(nav, ".git")):
        return None
    _run(["git", "-C", nav, "add", "-A"])
    subprocess.run(["git", "-C", nav, *GIT_ID, "commit", "-q", "-m", "auto-save before reset"],
                   capture_output=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(config.STUDENTS, name, "backups", f"navera-{ts}.bundle")
    _run(["git", "-C", nav, "bundle", "create", out, "--all"])
    return out


def reset_navera(name):
    """Back to the base: the student's changes are saved in a bundle first."""
    if not config.navera_allowed(name):
        raise PermissionError("NAVERA is not part of the course: your teacher can open it for you")
    saved = backup(name)
    nav = os.path.join(student_home(name), "navera")
    shutil.rmtree(nav, ignore_errors=True)
    _clone(nav)
    return saved


def course_version(lesson_id):
    """Hash of a lesson's starter files: changes when the teacher updates the lab."""
    import hashlib
    src = os.path.join(config.COURSES, lesson_id, "files")
    h = hashlib.sha1()
    for root, dirs, files in sorted(os.walk(src)):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            h.update(os.path.relpath(p, src).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()[:12]


VERSION_FILE = ".academy_version"


def installed_version(name, lesson_id):
    p = os.path.join(lesson_dir(name, lesson_id), VERSION_FILE)
    return open(p).read().strip() if os.path.exists(p) else None


def lesson_dir(name, lesson_id):
    return os.path.join(student_home(name), "lessons", lesson_id)


def install_lesson(name, lesson_id, overwrite=False):
    """Copy the lesson's starter files into the student's lessons folder (once)."""
    src = os.path.join(config.COURSES, lesson_id, "files")
    dst = lesson_dir(name, lesson_id)
    if os.path.exists(dst) and not overwrite:
        return dst
    if os.path.exists(dst):
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")     # two resets in one second: two backups
        bk = os.path.join(config.STUDENTS, name, "backups", f"{lesson_id}-{ts}")
        shutil.copytree(dst, bk, symlinks=True)
        shutil.rmtree(dst)
    if os.path.isdir(src):
        shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    else:
        os.makedirs(dst)
    with open(os.path.join(dst, VERSION_FILE), "w") as f:
        f.write(course_version(lesson_id) + "\n")
    return dst


def delete_student(name):
    netns.stop(name)                     # the student's private network (sandbox.py / netns.py)
    shutil.rmtree(os.path.join(config.STUDENTS, name), ignore_errors=True)


ACADEMY_README = """# Your NAVERA copy

This folder is **your own copy** of NAVERA. Change anything, break anything: the
**Reset NAVERA** button of the dashboard puts it back as it was (your changes are saved
in a backup first). Nothing you do here can change the real product.

- `git status` / `git diff` — what you changed
- `git diff base` — everything you changed since the start
- `colcon build --symlink-install --packages-select <pkg>` — needed only after changing
  messages (`navera_msgs`) or `setup.py`; Python edits work straight away.
"""

def bashrc(navera):
    """~/.bashrc of a sandbox. NAVERA's workspace is sourced (and the prompt says "navera") only for staff
    and students given NAVERA access; everyone else gets a neutral "academy" prompt."""
    host = "navera" if navera else "academy"
    src = "[ -f ~/navera/install/setup.bash ] && source ~/navera/install/setup.bash\n" if navera else ""
    return BASHRC.replace("@NAVERA_SETUP@\n", src).replace("@HOST@", host)


BASHRC = r"""# NAVERA Academy sandbox
[ -f /etc/bash.bashrc ] && . /etc/bash.bashrc
source /opt/ros/humble/setup.bash
@NAVERA_SETUP@
# the ros2 CLI daemon in its own session: a `timeout ros2 …` cannot leave it half-dead
(setsid ros2 daemon start >/dev/null 2>&1 &)
export PS1='\[\e[1;36m\]student\[\e[0m\]@\[\e[1;33m\]@HOST@\[\e[0m\]:\[\e[1;34m\]\w\[\e[0m\]\$ '
alias ll='ls -la --color=auto'
alias ls='ls --color=auto'
"""
