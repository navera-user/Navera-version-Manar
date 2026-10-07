# Your first NAVERA program.
# Change the three lines below, save (Ctrl+S), then run:  python3 hello_navera.py

PILOT_NAME = "???"
FAVOURITE_VEHICLE = "???"     # drone, car, boat or robot
CITY = "???"


# ---- you don't need to change anything below this line (but you can read it!) ----
ICONS = {"drone": "🚁", "car": "🚗", "boat": "🚤", "robot": "🤖"}


def mission_card(name, vehicle, city):
    icon = ICONS.get(vehicle.lower(), "❓")
    lines = [
        "+--------------------------------------------+",
        "|          NAVERA  —  MISSION CARD           |",
        "+--------------------------------------------+",
        f"  Pilot    : {name}",
        f"  Vehicle  : {icon} {vehicle}",
        f"  Home     : {city}",
        "  Sources  : GPS, day camera, night camera, stars",
        "+--------------------------------------------+",
    ]
    if name == "???":
        lines.append("  (Edit PILOT_NAME at the top of the file!)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(mission_card(PILOT_NAME, FAVOURITE_VEHICLE, CITY))
