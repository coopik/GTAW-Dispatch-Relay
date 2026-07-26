
import argparse
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCENARIO = [
    "[HQ] Police Officer II Connor Myer has gone on duty under 2W63!",
    "** [S: 1 | CH: BASE] Kiara Eponimos says: 25M14, show me clear from MRS.",
    [
        "********** EMERGENCY CALL **********",
        "* Log Number: 26-448120",
        "* Phone Number: 16087253 (Unknown)",
        "* Location: Strawberry Avenue, near the liquor store.",
        "* Situation: Two males just robbed the store at gunpoint, one has a pistol.",
    ],
    "** [S: 1 | CH: BASE] Connor Myer says: 2W63, show me responding from Davis.",
    "Marcus Webb says: Someone call 911, he's bleeding out!",
    [
        "********** EMERGENCY CALL **********",
        "* Log Number: 26-448135",
        "* Phone Number: 53676442 (Unknown)",
        "* Location: Vinewood Boulevard and Alta Street.",
        "* Situation: There is a dead body on the sidewalk, nobody is moving him.",
    ],
    "** [S: 1 | CH: BASE] Connor Myer says: 2W63, show me code six on Strawberry Avenue.",
    "** [S: 3 | CH: TRAFFIC] Alyssa Nowakowski says: 25T15, traffic stop, black Sultan, plate SWQ221.",
    "(( (10) Sergeant II Kayayday: nice one lol ))",
    "> Connor Myer reaches for a OC Spray.",
    [
        "********** NON-EMERGENCY CALL **********",
        "* Log Number: 26-448190",
        "* Phone Number: 16087253 (Unknown)",
        "* Location: Pillbox Hill.",
        "* Situation: I would like to report a parked car blocking my driveway.",
    ],
    "** [S: 1 | CH: BASE] Connor Myer says: 2W63, shots fired, shots fired, Strawberry Avenue!",
    "[DISPATCH] You have updated your status.",
    "** [S: 1 | CH: BASE] Connor Myer says: 2W63, show me clear.",
]


def stamp(line):
    return time.strftime("[%H:%M:%S] ") + line


def write_storage(path, lines, keep):
    payload = {
        "server_version": "GTA World",
        "chat_log": "\n".join(lines[-keep:]),
    }
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def events_from_file(path):
    from modules.file_watcher import read_chat_lines

    out = []
    for line in read_chat_lines(path):
        _t, body = line.split("] ", 1) if line.startswith("[") and "] " in line else ("", line)
        if body.strip():
            out.append(body)
    return out


def main():
    ap = argparse.ArgumentParser(description="Simulate GTA World chat for testing.")
    ap.add_argument("--out", default=os.path.join(os.path.abspath("sim_client_resources"), ".storage"),
                    help="where to write the fake .storage file")
    ap.add_argument("--interval", type=float, default=6.0, help="seconds between events")
    ap.add_argument("--keep", type=int, default=120, help="lines of history to keep (the game trims too)")
    ap.add_argument("--once", action="store_true", help="write everything at once, then exit")
    ap.add_argument("--no-loop", action="store_true",
                    help="play the scenario once instead of repeating until Ctrl+C")
    ap.add_argument("--list", action="store_true", help="print the scenario and exit")
    ap.add_argument("--from-file", default=None,
                    help="replay the chat out of a real .storage file instead of the fake scenario")
    args = ap.parse_args()

    events = SCENARIO
    if args.from_file:
        events = events_from_file(args.from_file)
        if not events:
            print("No chat lines found in", args.from_file)
            return 1
        print("Replaying %d real lines from %s" % (len(events), args.from_file))

    if args.list:
        for ev in events:
            for line in (ev if isinstance(ev, list) else [ev]):
                print(" ", line)
        return 0

    path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    lines = []
    write_storage(path, lines, args.keep)

    print()
    print("Fake chat log ready:")
    print("   " + path)
    print()
    print("1. In the app: Settings > Chat log input > File path  (or Dashboard > Browse...)")
    print("   Paste that path, turn OFF 'Auto-detect the file on start', and Save.")
    print("2. Press Start on the Dashboard. Turn on 'Show Chat' to watch it parse.")
    print("3. Come back here and leave this window running. Ctrl+C to stop.")
    print()
    print("Chat repeats until you stop it, so it does not matter which order you")
    print("start things in - the app only ever reacts to lines written AFTER you")
    print("pressed Start, never to the backlog.")
    print()
    time.sleep(3)

    round_no = 0
    while True:
        round_no += 1
        for ev in events:
            block = ev if isinstance(ev, list) else [ev]
            for line in block:
                lines.append(stamp(line))
            write_storage(path, lines, args.keep)
            for line in block:
                print("  wrote:", line[:100])
            if not args.once:
                try:
                    time.sleep(args.interval)
                except KeyboardInterrupt:
                    print("\nStopped.")
                    return 0
        if args.once:
            print("\nWrote %d lines. Done." % len(lines))
            return 0
        if args.no_loop:
            print("\nScenario finished (%d lines). Drop --no-loop to repeat forever." % len(lines))
            return 0
        print("--- restarting scenario (round %d) ---" % (round_no + 1))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
