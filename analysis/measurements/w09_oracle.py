#!/usr/bin/env python3
"""W-09: 03-LLD.md 3.6.1 / 3.6.2 / 3.7.1, transcribed verbatim, applied to a
recorded (rc, stderr) pair.  No apparatus code exists yet; this is the reference
implementation the fixtures are classified with, and it is committed beside the
mining record so the fixtures can be re-derived.

usage: oracle.py <stderr file> <rc> [--sdk DIR] [--build DIR] [--json]
"""
import json, os, re, subprocess, sys, signal as _signal

# --- 3.6.1, the three firing patterns, verbatim -----------------------------
_ASSERT_GLIBC = re.compile(
    r"^(?:.*?: )?(?P<file>[^\s:]+):(?P<line>\d+): "
    r"(?P<func>.+?): Assertion `(?P<expr>.*)' failed\.$")
_ASSERT_UNREACHABLE = re.compile(
    r"^UNREACHABLE executed(?: at (?P<file>[^\s:]+):(?P<line>\d+))?!$")
_FATAL_ERROR = re.compile(r"^LLVM ERROR: (?P<message>.*)$")

# --- 3.6.2, the frame pattern, verbatim -------------------------------------
_FRAME = re.compile(
    r"^\s*#(?P<i>\d+)\s+(?P<addr>0x[0-9a-f]+)\s+"
    r"(?:(?P<func>.*?)\s+)?"
    r"(?:\((?P<module>[^()]+)\+(?P<offset>0x[0-9a-f]+)\)"
    r"|(?P<file>[^\s()]+):(?P<line>\d+):(?P<col>\d+))$")

# --- 3.6's classify_build allocation literals, verbatim ---------------------
_ALLOC = ("std::bad_alloc", "out of memory", "LLVM ERROR: out of memory")
_ARGV_REJECT = "does not refer to a registered pass or pass pipeline"

# --- 3.7.1's prologue set, verbatim -----------------------------------------
_PROLOGUE = ("llvm::sys::PrintStackTrace", "llvm::sys::RunSignalHandlers", "SignalHandler",
             "__restore_rt", "pthread_kill", "raise", "abort", "__assert_fail",
             "llvm::report_fatal_error", "llvm::llvm_unreachable_internal")


def signal_of(rc):
    """subprocess reports death by signal n as -n; a shell reports it as 128+n."""
    if rc is None:
        return None
    n = -rc if rc < 0 else (rc - 128 if 128 < rc <= 192 else 0)
    if n <= 0:
        return None
    try:
        return _signal.Signals(n).name
    except ValueError:
        return None


def classify(rc, stderr, limit_hit=None):
    """3.6 step 3's table, in its order.  Returns (status, reason)."""
    sig = signal_of(rc)
    lines = stderr.splitlines()
    if limit_hit == "wall":
        return "timeout", "wall_limit"
    if limit_hit == "cpu":
        return "timeout", "cpu_limit"
    if limit_hit == "address_space" or (
            sig and any(a in ln for ln in lines for a in _ALLOC)):
        return "oom", "allocation_failure"
    for ln in lines:
        if _ASSERT_GLIBC.match(ln) or _ASSERT_UNREACHABLE.match(ln):
            return "assertion", "assertion_failed"
    for ln in lines:
        if _FATAL_ERROR.match(ln):
            return "fatal_error", "llvm_error"
    if sig:
        return "crash", "died_by_signal"
    if rc != 0:
        reason = "tool_rejected_argv" if _ARGV_REJECT in stderr else "tool_rejected_input"
        return "parse_error", reason
    return "clean_exit", ""


def extract(status, stderr):
    """3.6.2 step 2."""
    lines = stderr.splitlines()
    if status == "assertion":
        for i, ln in enumerate(lines):
            m = _ASSERT_GLIBC.match(ln)
            if m:
                return (m.group("expr"), f'{m.group("file")}:{m.group("line")}',
                        None, "glibc", m.group("func"))
            m = _ASSERT_UNREACHABLE.match(ln)
            if m:
                matched = ln[:-1] if ln.endswith("!") else ln
                text = (lines[i - 1] + "\n" + matched) if i > 0 else matched
                site = (f'{m.group("file")}:{m.group("line")}'
                        if m.group("file") else None)
                return text, site, None, "unreachable", None
    if status == "fatal_error":
        for ln in lines:
            m = _FATAL_ERROR.match(ln)
            if m:
                return None, None, m.group("message"), "fatal", None
    return None, None, None, None, None


def parse_frames(stderr):
    out = []
    for ln in stderr.splitlines():
        m = _FRAME.match(ln)
        if not m:
            continue
        out.append(dict(i=int(m.group("i")), addr=m.group("addr"),
                        func=(m.group("func") or "").strip(),
                        module=m.group("module"), offset=m.group("offset"),
                        file=m.group("file"), line=m.group("line"),
                        shape="module_offset" if m.group("module") else "attributed"))
    return out


def normalise_func(name):
    """3.7.1 steps 2 to 4."""
    if not name:
        return ""
    depth, cut = 0, len(name)
    for i, ch in enumerate(name):
        if ch in "<[{":
            depth += 1
        elif ch in ">]}":
            depth -= 1
        elif ch == "(" and depth == 0:
            cut = i
            break
    name = name[:cut]
    if name.endswith(" const"):
        name = name[:-len(" const")]
    return " ".join(name.split())


def symbolise(frames, sdk, build_root, src_root):
    """3.6.2 step 3 / 4.9: one llvm-symbolizer call per module, file offsets on stdin."""
    sym = os.path.join(sdk, "bin", "llvm-symbolizer")
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = os.path.join(sdk, "lib") + ":" + \
        os.path.expanduser("~/.cache/chia-pin-smoke/shim")
    bymod = {}
    for f in frames:
        if f["shape"] == "module_offset":
            bymod.setdefault(f["module"], []).append(f)
    for mod, fs in bymod.items():
        if not os.path.exists(mod):
            continue
        p = subprocess.run([sym, f"--obj={mod}", "--demangle", "--output-style=JSON"],
                           input="\n".join(f["offset"] for f in fs) + "\n",
                           capture_output=True, text=True, env=env)
        outs = [ln for ln in p.stdout.splitlines() if ln.strip()]
        for f, ln in zip(fs, outs):
            try:
                j = json.loads(ln)
            except ValueError:
                continue
            s = (j.get("Symbol") or [{}])[0]
            f["sym_func"] = s.get("FunctionName", "")
            f["sym_file"] = s.get("FileName", "")
            f["sym_line"] = s.get("Line", 0)
    for f in frames:
        if f["shape"] == "attributed":
            f["sym_func"], f["sym_file"] = f["func"], f["file"]
            f["sym_line"] = int(f["line"])
        f.setdefault("sym_func", "")
        f.setdefault("sym_file", "")
        f.setdefault("sym_line", 0)
        f["norm"] = normalise_func(f["sym_func"] or f["func"])
        # 3.6.2's in_circt_object predicate, with /workspace/circt/ rebound to the
        # host's build root and source root (the fixtures are mined on the host).
        if f["shape"] == "module_offset":
            m = f["module"] or ""
            f["in_circt_object"] = (m == os.path.join(build_root, "bin", "circt-opt")
                                    or m.startswith(build_root + "/bin/")
                                    or re.search(r"/lib/libCIRCT[^/]*\.so", m) is not None)
        else:
            fl = f["sym_file"] or ""
            f["in_circt_object"] = fl.startswith(src_root) or fl.startswith(build_root)
    return frames


def strip_prologue(frames):
    n = 0
    for f in frames:
        is_libc = (not f["norm"]) and (f["module"] or "").find("libc.so") >= 0
        if f["norm"] in _PROLOGUE or is_libc:
            n += 1
            continue
        break
    return frames[n:], n


def run(stderr, rc, sdk, build_root, src_root, top_n=5, limit_hit=None):
    status, reason = classify(rc, stderr, limit_hit)
    text, site, fatal, kind, func = extract(status, stderr)
    frames = symbolise(parse_frames(stderr), sdk, build_root, src_root)
    stripped, dropped = strip_prologue(frames)
    fframe = None
    for f in stripped:
        if f["in_circt_object"] and f["sym_line"] and f["norm"] and f["norm"] != "operator":
            fframe = f'{f["norm"]} {os.path.basename(f["sym_file"])}'
            break
    first_circt = None
    for f in stripped:
        if f["in_circt_object"] and f["sym_line"]:
            first_circt = f'{f["norm"]} {f["sym_file"]}:{f["sym_line"]}'
            break
    sig = signal_of(rc)
    return dict(
        status=status, reason=reason, fired=status in ("crash", "assertion", "fatal_error"),
        signal=sig, exit_status=rc,
        assertion_text=text, assertion_site=site, assertion_kind=kind,
        assertion_func=func, fatal_message=fatal,
        frames_total=len(frames), prologue_dropped=dropped,
        frames_resolved=sum(1 for f in frames if f["norm"]),
        frames_with_location=sum(1 for f in frames
                                 if f["sym_line"] and f["in_circt_object"]),
        fingerprint_frame=fframe,
        first_circt_frame=first_circt,
        out_of_scope_root=bool(stripped) and not stripped[0]["in_circt_object"],
        top_frames=[f["norm"] for f in stripped[:top_n]],
        frames=[{k: f[k] for k in ("i", "shape", "module", "offset", "norm",
                                   "sym_file", "sym_line", "in_circt_object")}
                for f in frames[:40]],
    )


if __name__ == "__main__":
    a = sys.argv[1:]
    err = open(a[0], errors="backslashreplace").read()
    # The second argument is the exit status, or the runner's own run.json, which
    # also carries `limit_hit`: a run killed at the wall or the CPU bound has no
    # exit status at all, and 3.6 step 3 classifies it `timeout` before it looks
    # at stderr.  int("None") is what the earlier spelling did instead.
    if a[1].endswith(".json"):
        rec = json.load(open(a[1]))
        rc, limit_hit = rec["rc"], rec.get("limit_hit")
    else:
        rc, limit_hit = int(a[1]), None
    sdk = a[a.index("--sdk") + 1] if "--sdk" in a else ""
    b = a[a.index("--build") + 1] if "--build" in a else ""
    s = a[a.index("--src") + 1] if "--src" in a else ""
    print(json.dumps(run(err, rc, sdk, b, s, limit_hit=limit_hit), indent=1))
