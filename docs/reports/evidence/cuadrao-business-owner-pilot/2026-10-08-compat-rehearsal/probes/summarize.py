"""Per run log: the pytest totals, failing tests by file, and one cause per failure."""
import collections, re, sys

EXC = re.compile(r"^E\s+([\w.]*(Error|Exception|Violation|Incomplete|Unavailable|Column|Function|Table|Object|Failed)[\w.]*:.*)")

def norm(s):
    s = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", s)
    s = re.sub(r"dlopen\(.*", "dlopen(scipy) macOS loader", s)
    return s[:170]

for path in sys.argv[1:]:
    text = open(path).read()
    totals = [l for l in text.splitlines() if re.search(r"\d+ (passed|failed)", l)]
    print("==", path.split("/")[-1].removeprefix("run_").removesuffix(".log"), "|", totals[-1].strip("= ") if totals else "?")
    sections = re.split(r"\n_{5,} (.+?) _{5,}\n", text)
    causes = {}
    for name, body in zip(sections[1::2], sections[2::2]):
        lines = body.splitlines()
        hit = next((m.group(1) for l in lines if (m := EXC.match(l))), None)
        hit = hit or next((l[1:].strip() for l in lines if l.startswith("E ")), "?")
        causes[name.replace("ERROR at setup of ", "")] = norm(hit)
    failed = [re.match(r"(FAILED|ERROR) (\S+)", l).group(2) for l in text.splitlines() if re.match(r"(FAILED|ERROR) \S", l)]
    byfile = collections.Counter(f.split("::")[0] for f in failed)
    for f, n in sorted(byfile.items()):
        print(f"  {n:3d} {f}")
    bycause = collections.Counter(causes.values())
    for c, n in bycause.most_common(int(sys.argv[0] and 15)):
        print(f"      cause seen: {c}")
