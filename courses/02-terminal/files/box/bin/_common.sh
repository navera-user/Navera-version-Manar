# _common.sh — shared by the pretend nodes of box.sh (lab 02). Not a program: the others `source` it.
# BOX = the box/ folder; NAME = the program's name. say "text" writes one journal line, like systemd's
# journal: "Oct 13 09:14:02 box NAME[PID]: text".
JOURNAL="$BOX/log/journal.log"
say() {
    local ts
    printf -v ts '%(%b %d %T)T' -1          # the time without starting a date process
    echo "$ts box $NAME[$$]: $*" >> "$JOURNAL"
}
