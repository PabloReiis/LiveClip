"""Turns a time range into a vertical clip: 9:16 layout, bouncy word captions, hook title, cover."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config, roman
from . import liveclip_fx
from .media import NO_WINDOW, run

W, H = config.OUT_W, config.OUT_H

# ASS colours are &HBBGGRR. `size` is the ASS font size (line height); _Font turns it into real pixels.
STYLES = {
    "bounce": {"label": "Bounce", "font": "Poppins ExtraBold", "size": 132, "base": "FFFFFF", "active": "00F0FF",
               "strong": "FFFFFF", "outline": 7, "pop": 112, "upper": True, "per": 3},
    "hype": {"label": "Hype", "font": "Anton", "size": 152, "base": "FFFFFF", "active": "3C3CFF",
             "strong": "00D7FF", "outline": 7, "pop": 114, "upper": True, "per": 2},
    "clean": {"label": "Clean", "font": "Poppins ExtraBold", "size": 100, "base": "FFFFFF", "active": "6BD7FF",
              "strong": "FFFFFF", "outline": 5, "pop": 106, "upper": False, "per": 4},
}
HOOK = {"font": "Poppins ExtraBold", "size": 96, "ink": "14100E", "box": "FFFFFF", "pad_x": 36, "pad_y": 22, "radius": 26,
        "max_w": 900}
FONT_FILES = {"Poppins ExtraBold": "Poppins-ExtraBold.ttf", "Anton": "Anton-Regular.ttf", "Archivo Black": "ArchivoBlack-Regular.ttf"}
CAP_MAX_W = 960   # captions never run wider than this, whatever is said


class _Font:
    """Measures text exactly as the renderer will draw it, so every word can be placed by hand: the highlighted
    word can grow without pushing its neighbours, and the heading box fits its text."""
    _cache: dict = {}

    def __init__(self, name):
        import struct
        path = Path(__file__).resolve().parent / "fonts" / FONT_FILES.get(name, FONT_FILES["Poppins ExtraBold"])
        d = path.read_bytes()
        tables = {}
        for i in range(struct.unpack(">H", d[4:6])[0]):
            tag, _, off, _ = struct.unpack(">4sIII", d[12 + 16 * i: 28 + 16 * i])
            tables[tag] = off
        self.upm = struct.unpack(">H", d[tables[b"head"] + 18: tables[b"head"] + 20])[0]
        o = tables[b"OS/2"]
        self.asc, self.desc = struct.unpack(">HH", d[o + 74: o + 78])      # what the renderer sizes the font by
        self.cap = struct.unpack(">h", d[o + 88: o + 90])[0] or int(self.upm * 0.7)
        self.path = str(path)
        self._pil = {}

    @classmethod
    def get(cls, name):
        if name not in cls._cache:
            cls._cache[name] = cls(name)
        return cls._cache[name]

    def em(self, size):
        return size * self.upm / (self.asc + self.desc)

    def width(self, text, size):
        """Pixels wide at this ASS size."""
        try:
            from PIL import ImageFont
            if "f" not in self._pil:
                self._pil["f"] = ImageFont.truetype(self.path, 200)
            return self._pil["f"].getlength(text) * self.em(size) / 200
        except Exception:  # noqa: BLE001 - no measuring library: a fair estimate keeps clips rendering
            return len(text) * self.em(size) * 0.62

    def cap_shift(self, size):
        """How far below the anchor the middle of a capital letter sits when text is centred on a point."""
        return ((self.asc - self.desc) / 2 - self.cap / 2) * size / (self.asc + self.desc)


CAPTION_LEAD = 0.0  # measured: word stamps are within 0.15 s of the voice, so no shift is needed
def install_fonts():
    """Copy the bundled caption fonts next to the data, so captions look the same on every machine and server."""
    src = Path(__file__).resolve().parent / "fonts"
    for f in src.glob("*.ttf"):
        if not (config.FONTS_DIR / f.name).exists():
            shutil.copyfile(f, config.FONTS_DIR / f.name)


LAYOUTS = {"blur": "Full frame + blurred fill", "zoom": "Zoomed in + blurred fill", "crop": "Fill the screen (centre crop)",
           "left": "Fill the screen, keep the left side", "right": "Fill the screen, keep the right side",
           "fit": "Full frame on black", "split": "Split screen: left half on top, right half below (two people)",
           "gameplay": "Gameplay fills the screen, facecam in the corner",
           "gameplay_split": "Facecam on top, gameplay below (vertical split)"}
_FILLS = ("crop", "left", "right", "gameplay", "gameplay_split")      # layouts where the picture covers the whole frame


def _ts(t):
    t = max(0.0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def _clean(text):
    return re.sub(r"[\x00-\x1f\x7f]+", " ", re.sub(r"[{}\\]", "", str(text))).strip()


def _key(word):
    return re.sub(r"[^a-z0-9']", "", word.lower())


def _groups(words, per):
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= per or sum(len(x["w"]) for x in cur) + len(w["w"]) > 16
                    or w["s"] - cur[-1]["e"] > 0.45 or cur[-1]["w"][-1:] in ".?!"):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def geometry(src_w, src_h, layout):
    """Where the video sits in the 1080x1920 frame, and where hook and captions go."""
    if src_h >= src_w and layout != "crop":
        layout = "crop"  # already vertical or square: nothing to gain from a blurred fill
    if layout not in LAYOUTS:
        layout = "blur"
    if layout in ("blur", "fit"):
        fg_h = min(H, int(round(W * src_h / src_w / 2)) * 2)
    elif layout == "zoom":
        fg_h = 1000
    else:
        fg_h = H
    top = (H - fg_h) // 2
    if layout in _FILLS:
        return layout, fg_h, 300, 1380
    if layout == "split":
        return layout, fg_h, 230, H // 2        # captions sit on the line between the two people
    return layout, fg_h, max(230, top - 190), min(1640, top + fg_h + 180)


def _hook_events(hook, dur, y):
    """The heading: dark text in a white rounded box that fits it, on one line or two balanced ones."""
    f, size = _Font.get(HOOK["font"]), HOOK["size"]
    words = hook.split()
    if not words:
        return []
    lines = [" ".join(words)]
    if f.width(lines[0], size) > HOOK["max_w"] and len(words) > 1:      # two lines, split where they come out most even
        cut = min(range(1, len(words)), key=lambda i: max(f.width(" ".join(words[:i]), size), f.width(" ".join(words[i:]), size)))
        lines = [" ".join(words[:cut]), " ".join(words[cut:])]
    widest = max(f.width(l, size) for l in lines)
    if widest > HOOK["max_w"]:
        size = max(40, int(size * HOOK["max_w"] / widest))
        widest = max(f.width(l, size) for l in lines)
    line_h = f.em(size) * 1.16
    bw, bh = widest + 2 * HOOK["pad_x"], line_h * len(lines) + 2 * HOOK["pad_y"]
    x0, y0, r = (W - bw) / 2, y - bh / 2, min(HOOK["radius"], bh / 2)
    x1, y1 = x0 + bw, y0 + bh
    n = lambda v: f"{v:.0f}"                                                         # noqa: E731
    box = (f"m {n(x0 + r)} {n(y0)} l {n(x1 - r)} {n(y0)} b {n(x1)} {n(y0)} {n(x1)} {n(y0)} {n(x1)} {n(y0 + r)} "
           f"l {n(x1)} {n(y1 - r)} b {n(x1)} {n(y1)} {n(x1)} {n(y1)} {n(x1 - r)} {n(y1)} "
           f"l {n(x0 + r)} {n(y1)} b {n(x0)} {n(y1)} {n(x0)} {n(y1)} {n(x0)} {n(y1 - r)} "
           f"l {n(x0)} {n(y0 + r)} b {n(x0)} {n(y0)} {n(x0)} {n(y0)} {n(x0 + r)} {n(y0)}")
    span = f"{_ts(0)},{_ts(dur)}"
    ev = [f"Dialogue: 3,{span},Hook,,0,0,0,,{{\\an7\\pos(0,0)\\fad(160,0)\\c&H{HOOK['box']}&\\p1}}{box}{{\\p0}}"]
    for i, line in enumerate(lines):
        cy = y - line_h * (len(lines) - 1) / 2 + i * line_h - f.cap_shift(size)
        ev.append(f"Dialogue: 4,{span},Hook,,0,0,0,,{{\\an5\\pos({W // 2},{cy:.0f})\\fad(160,0)\\fs{size}}}{line}")
    return ev


def build_ass(words, start, end, hook, style_name, highlight, hook_y, cap_y) -> str:
    st = STYLES.get(style_name, STYLES["bounce"])
    words = [dict(w, s=w["s"] - CAPTION_LEAD, e=w["e"] - CAPTION_LEAD) for w in words]
    strong = {_key(h) for h in highlight if _key(h)}
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{st['size']},&H00{st['base']},&H00{st['base']},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,{st['outline']},0,5,0,0,0,1
Style: Hook,{HOOK['font']},{HOOK['size']},&H00{HOOK['ink']},&H00{HOOK['ink']},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dur = end - start
    ev = _hook_events(_clean(hook), dur, hook_y)
    f = _Font.get(st["font"])
    inside = [dict(w, w=_clean(w["w"])) for w in words if w["s"] >= start - 0.05 and w["s"] < end]
    inside = sorted((w for w in inside if w["w"]), key=lambda w: w["s"])
    for i, w in enumerate(inside[:-1]):
        w["e"] = max(w["s"], min(w["e"], inside[i + 1]["s"]))
    groups = _groups(inside, st["per"])
    for gi, g in enumerate(groups):
        g_start = max(0.0, g[0]["s"] - start)
        g_end = min(g[-1]["e"] + 0.25, groups[gi + 1][0]["s"] if gi + 1 < len(groups) else end) - start
        if g_end - g_start < 0.02:
            continue
        texts = []
        for x in g:
            t = re.sub(r"[.,;:]+$", "", x["w"])
            texts.append(t.upper() if st["upper"] else t)
        if not all(roman.drawable(t) for t in texts):
            # A script the caption font cannot draw (Japanese, Thai, Chinese...): its words cannot be measured, so
            # they are not placed one by one. The line is drawn whole and centred, in a font the system has for it.
            line = " ".join(texts)
            fs = max(44, min(int(st["size"] * 0.7), int(1500 / max(1, len(line)) * 1.6)))
            ev.append(f"Dialogue: 1,{_ts(g_start)},{_ts(g_end)},Cap,,60,60,0,,{{\\an5\\pos({W // 2},{cap_y:.0f})\\q0\\fs{fs}}}{line}")
            continue
        size = st["size"]
        gap = f.width("n n", size) - 2 * f.width("n", size) + (2 * st["outline"] + 6) * size / st["size"]   # a space, plus room for both outlines
        total = sum(f.width(t, size) for t in texts) + gap * (len(texts) - 1)
        if total > CAP_MAX_W:                                  # a long phrase: shrink it to fit, never run off the frame
            size = max(36, int(size * CAP_MAX_W / total))
            gap = f.width("n n", size) - 2 * f.width("n", size) + (2 * st["outline"] + 6) * size / st["size"]   # a space, plus room for both outlines
            total = sum(f.width(t, size) for t in texts) + gap * (len(texts) - 1)
        cy = cap_y - f.cap_shift(size)
        x = (W - total) / 2
        p = st["pop"]
        for i, (w, t) in enumerate(zip(g, texts)):
            wd = f.width(t, size)
            p = max(104, min(st["pop"], 100 + int(2200 / max(wd, 1))))   # long words grow less, so they never touch their neighbours
            pos = f"\\an5\\pos({x + wd / 2:.0f},{cy:.0f})\\fs{size}"
            x += wd + gap
            a = max(g_start, w["s"] - start)
            b = (g[i + 1]["s"] - start) if i + 1 < len(g) else g_end
            base = st["strong"] if _key(w["w"]) in strong else st["base"]
            if a - g_start >= 0.02:                                                   # waiting to be said
                ev.append(f"Dialogue: 1,{_ts(g_start)},{_ts(a)},Cap,,0,0,0,,{{{pos}\\c&H{base}&}}{t}")
            if b - a >= 0.02:                                                         # being said: colour and a quick pop, in front
                ev.append(f"Dialogue: 2,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{{{pos}\\c&H{st['active']}&\\fscx94\\fscy94"
                          f"\\t(0,90,\\fscx{p}\\fscy{p})\\t(90,200,\\fscx{p - 5}\\fscy{p - 5})}}{t}")
            if g_end - b >= 0.02:                                                     # said
                ev.append(f"Dialogue: 1,{_ts(b)},{_ts(g_end)},Cap,,0,0,0,,{{{pos}\\c&H{base}&\\fscx{p - 5}\\fscy{p - 5}"
                          f"\\t(0,90,\\fscx100\\fscy100)}}{t}")
    return head + "\n".join(ev) + "\n"


PIP_W = 440   # slightly larger than the original 380 px (about +16%)
PIP_MARGIN = 26


def _crop_piece(box, target_w, target_h, label):
    """Use a manually selected source rectangle; the source is never stretched."""
    x, y, w, h = (int(round(float(v))) for v in box)
    return (f"crop={w}:{h}:{x}:{y},scale={target_w}:{target_h}:"
            f"force_original_aspect_ratio=increase,crop={target_w}:{target_h},setsar=1[{label}]")


def _filter(layout, fg_h, facecam=None, pip_width=PIP_W, pip_height=None, pip_side="right", gamebox=None,
            pip_x=None, pip_y=None):
    game = (_crop_piece(gamebox, W, H, "b") if gamebox else
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[b]")
    if layout in ("gameplay", "gameplay_split") and facecam:
        fx, fy, fw, fh = (int(v) for v in facecam)
        if fw > 8 and fh > 8:
            if layout == "gameplay_split":
                top_h = 640
                low_h = H - top_h
                cam = _crop_piece(facecam, W, top_h, "cam")
                main = (_crop_piece(gamebox, W, low_h, "g") if gamebox else
                        f"scale={W}:{low_h}:force_original_aspect_ratio=increase,crop={W}:{low_h},setsar=1[g]")
                return (f"[0:v]fps={config.OUT_FPS},split=2[base][fc];"
                        f"[fc]{cam};[base]{main};"
                        f"[cam][g]vstack,drawbox=x=0:y={top_h-4}:w=iw:h=8:color=0x8d54ff@0.95:t=fill[v0];")
            # Output webcam dimensions are independent: 1080x500 fills the top of a vertical clip.
            # Legacy clips without pip_height keep their original aspect ratio.
            pw = max(100, min(W, int(pip_width)))
            ph = max(100, min(H, int(pip_height) if pip_height is not None else int(round(pw * fh / fw))))
            pos = {"left": str(PIP_MARGIN), "center": "(W-w)/2", "right": str(W - pw - PIP_MARGIN)}
            px = pos.get(pip_side, pos["right"])
            py = PIP_MARGIN
            if pip_x is not None and pip_y is not None:
                px = str(max(0, min(W-pw, int(pip_x))))
                py = max(0, min(H-ph, int(pip_y)))
            return (f"[0:v]fps={config.OUT_FPS},split=2[base][fc];"
                    f"[base]{game};"
                    f"[fc]crop={fw}:{fh}:{fx}:{fy},scale={pw}:{ph}:force_original_aspect_ratio=increase,"
                    f"crop={pw}:{ph},setsar=1[p];"
                    f"[b][p]overlay={px}:{py}[v0];")
    fill = f"[0:v]fps={config.OUT_FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if layout == "crop" or (layout in ("gameplay", "gameplay_split") and not facecam):
        return fill + ",setsar=1[v0];"
    if layout == "left":
        return fill + ":0:0,setsar=1[v0];"
    if layout == "right":
        return fill + ":in_w-out_w:0,setsar=1[v0];"
    if layout == "fit":
        return f"[0:v]fps={config.OUT_FPS},scale={W}:{fg_h},pad={W}:{H}:0:(oh-ih)/2:black,setsar=1[v0];"
    if layout == "split":
        half = f"scale={W}:{H // 2}:force_original_aspect_ratio=increase,crop={W}:{H // 2}"
        return (f"[0:v]fps={config.OUT_FPS},split=2[l][r];[l]crop=iw/2:ih:0:0,{half}[t];"
                f"[r]crop=iw/2:ih:iw/2:0,{half}[u];[t][u]vstack,setsar=1[v0];")
    return (f"[0:v]fps={config.OUT_FPS},split=2[a][b];"
            f"[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=6:2,"
            f"scale={W}:{H},eq=brightness=-0.14:saturation=1.15[bg];"
            f"[b]scale={W}:{fg_h}:force_original_aspect_ratio=increase,crop={W}:{fg_h}[fg];"
            f"[bg][fg]overlay=0:(H-h)/2,setsar=1[v0];")


def _hook_y(layout, hook_y, facecam=None, pip_width=PIP_W, pip_height=None, pip_y=None):
    if layout == "gameplay_split" and facecam:
        return 705
    if layout == "gameplay" and facecam and len(facecam) == 4 and facecam[2] > 8:
        height = int(pip_height) if pip_height is not None else int(round(pip_width * facecam[3] / facecam[2]))
        top = int(pip_y) if pip_y is not None else PIP_MARGIN
        # Keep the hook below a webcam at the top, with room for its text.
        if top + height <= H * .6:
            return max(hook_y, top + height + 52)
    return hook_y


_qsv_ok = None
RENDER_SECONDS = 600      # one clip's video encode; far beyond normal, so a frozen encoder is stopped, not waited on


def render_clip(src: Path, out_dir: Path, name: str, clip: dict, words: list, src_w: int, src_h: int) -> dict:
    """Writes <name>.mp4, <name>.jpg and <name>.ass into out_dir. Returns file names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = clip["start"], clip["end"]
    layout, fg_h, hook_y, cap_y = geometry(src_w, src_h, clip.get("layout", "blur"))
    face = clip.get("facecam")
    if layout in ("gameplay", "gameplay_split") and not (face and len(face) == 4):
        layout = "crop"     # no webcam found: the game fills the screen, which is still the right shape
    pip_width = max(100, min(W, int(clip.get("pip_width") or PIP_W)))
    pip_height = clip.get("pip_height")
    hook_y = _hook_y(layout, hook_y, face, pip_width, pip_height, clip.get("pip_y"))
    ass = build_ass(words if clip.get("captions", True) else [], start, end, clip.get("hook", ""), clip.get("style", "bounce"),
                    clip.get("highlight_words", []), hook_y, cap_y)
    # The clip is made in a short work folder and moved into place afterwards. The caption step of ffmpeg cannot
    # open files whose full path is longer than 260 characters on Windows, which a data folder deep inside other
    # folders easily reaches. Inside the work folder every name is short and relative (a drive colon would also
    # break the filter syntax).
    work = Path(tempfile.mkdtemp(prefix="pk"))
    try:
        # The title and description are also written into the file itself, for any place that reads them from it.
        meta = {"title": clip.get("title") or "", "description": clip.get("description") or "", "comment": clip.get("description") or ""}
        return _render_in(work, src, out_dir, name, start, end, layout, fg_h, ass, face=face, meta=meta,
                          pip_width=pip_width, pip_height=pip_height,
                          pip_side=clip.get("pip_side", "right"), gamebox=clip.get("gamebox"),
                          pip_x=clip.get("pip_x"), pip_y=clip.get("pip_y"),
                          frame_style=clip.get("frame_style", "none"),
                          bg_mode=clip.get("bg_mode", "none"), bg_animation=clip.get("bg_animation", "zoom"),
                          bg_video_scale=clip.get("bg_video_scale", 86),
                          fx_music=clip.get("fx_music", "none"),
                          fx_music_path=clip.get("fx_music_path"),
                          fx_music_volume=clip.get("fx_music_volume", .18),
                          fx_zoom_mode=clip.get("fx_zoom_mode", "none"),
                          fx_zoom_factor=clip.get("fx_zoom_factor", 1.6),
                          fx_zoom_intervals=clip.get("fx_zoom_intervals", []))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_in(work: Path, src: Path, out_dir: Path, name: str, start, end, layout, fg_h, ass: str, face=None, meta=None,
               pip_width=PIP_W, pip_height=None, pip_side="right", gamebox=None, pip_x=None, pip_y=None, frame_style="none",
               bg_mode="none", bg_animation="zoom", bg_video_scale=86,
               fx_music="none", fx_music_path=None, fx_music_volume=.18,
               fx_zoom_mode="none", fx_zoom_factor=1.6, fx_zoom_intervals=None) -> dict:
    global _qsv_ok
    (work / f"{name}.ass").write_text(ass, encoding="utf-8")
    (work / "f").mkdir()
    for f in config.FONTS_DIR.glob("*.ttf"):
        shutil.copyfile(f, work / "f" / f.name)
    # LIVECLIP_BG_GTA6_V1: animated image underneath the already-composed game/webcam.
    fc = _filter(layout, fg_h, face, pip_width=pip_width, pip_height=pip_height,
                 pip_side=pip_side, gamebox=gamebox, pip_x=pip_x, pip_y=pip_y)
    additional_input = []
    if bg_mode == "gta6":
        # LIVECLIP_BG_MOTION_V2: seamless loop with real particles, glow and camera movement.
        # The foreground starts at PTS 0, preventing empty background frames at clip start.
        bg_dir = Path(__file__).resolve().parent.parent / "web" / "brand"
        mode = bg_animation if bg_animation in ("zoom", "drift", "pulse") else "none"
        bg_path = bg_dir / (f"gta6_{mode}.mp4" if mode != "none" else "gta6_neon.png")
        if not bg_path.is_file():
            raise RuntimeError("Fundo GTA6 nao encontrado: " + str(bg_path))
        fps = int(config.OUT_FPS)
        duration = max(0.1, end - start)
        scale_pct = max(70, min(98, int(bg_video_scale)))
        ww = int(W * scale_pct / 100) // 2 * 2
        hh = int(H * scale_pct / 100) // 2 * 2
        bg_filter = (f"[1:v]fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,"
                     f"crop={W}:{H},setsar=1,trim=duration={duration:.3f},"
                     "setpts=PTS-STARTPTS[back];")
        # Do not place subtitles inside the smaller video. They are added full-size later.
        fc += (bg_filter + f"[v0]setpts=PTS-STARTPTS,scale={ww}:{hh}:flags=lanczos,setsar=1,"
               f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.45:t=4[foreground];"
               f"[back][foreground]overlay=(W-w)/2:(H-h)/2:shortest=1:repeatlast=1,"
               "setsar=1[vbackground];")
        source_label = "vbackground"
        if mode == "none":
            additional_input = ["-loop", "1", "-framerate", str(fps), "-i", str(bg_path)]
        else:
            additional_input = ["-stream_loop", "-1", "-i", str(bg_path)]
    else:
        source_label = "v0"
    # LIVECLIP_REACTION_FX_V1: zoom in on the webcam (not the animated background).
    zoom_events = fx_zoom_intervals or []
    if fx_zoom_mode == "auto" and layout == "gameplay" and face:
        zoom_events = liveclip_fx.automatic_reactions(src, start, end, no_window=NO_WINDOW,
                                                     factor=float(fx_zoom_factor))
    if fx_zoom_mode == "none" or layout != "gameplay":
        zoom_events = []
    fc, source_label = liveclip_fx.add_reaction_zooms(
        fc, source_label, zoom_events, width=W, height=H, facecam=face,
        pip_width=pip_width, pip_height=pip_height, pip_x=pip_x, pip_y=pip_y,
        pip_side=pip_side, bg_mode=bg_mode, bg_video_scale=bg_video_scale)
    # LIVECLIP_BIGTEXT_PREVIEW_V1: titulo/legenda ficam POR CIMA da moldura.
    if frame_style in ("static", "animated"):
        fc += f"[{source_label}]setpts=PTS-STARTPTS[v]"
    else:
        fc += f"[{source_label}]ass={name}.ass:fontsdir=f[v]"
    # Background music is optional and stays quieter than the streamer.
    music_source = None
    if fx_music == "neon":
        music_source = Path(__file__).resolve().parent.parent / "web" / "brand" / "neon_drive.mp3"
    elif fx_music == "custom" and fx_music_path:
        music_source = Path(fx_music_path)
    if music_source and not music_source.is_file():
        raise RuntimeError("Trilha selecionada nao encontrada. Reenvie a musica e refaca o corte.")
    music_i = 2 if bg_mode == "gta6" else 1
    if music_source:
        additional_input += ["-stream_loop", "-1", "-i", str(music_source)]
        fc += ";" + liveclip_fx.mix_music_filters(end-start, music_i, float(fx_music_volume))
    base = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{end - start:.2f}", "-i", str(src)] + additional_input + [
            "-filter_complex", fc, "-map", "[v]", "-map", "[audioout]" if music_source else "0:a:0"]
    if not music_source:
        base += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    base += ["-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    # LIVECLIP_FRAME_NEON_V1: moldura SOBRE todas as camadas, com canal alfa.
    # Acoplar como ULTIMA entrada para nao mudar os indices da musica e do fundo.
    if frame_style in ("static", "animated"):
        asset_name = ("moldura_liveclip.png" if frame_style == "static"
                      else "moldura_liveclip_anim.png")
        asset = Path(__file__).resolve().parent.parent / "web" / "brand" / asset_name
        if not asset.is_file():
            raise RuntimeError("Moldura neon nao encontrada: " + str(asset))
        graph_opt = base.index("-filter_complex")
        video_input_index = base[:graph_opt].count("-i")
        fps = int(config.OUT_FPS)
        inp = (["-loop", "1", "-framerate", str(fps), "-i", str(asset)]
               if frame_style == "static" else
               ["-stream_loop", "-1", "-i", str(asset)])
        base[graph_opt:graph_opt] = inp
        graph_idx = base.index("-filter_complex") + 1
        base[graph_idx] += (
            f";[v]setpts=PTS-STARTPTS[frame_scene];"
            f"[{video_input_index}:v]fps={fps},"
            f"scale={W}:{H}:flags=lanczos,format=rgba,"
            "setpts=PTS-STARTPTS[frame_art];"
            "[frame_scene][frame_art]overlay=0:0:shortest=1:"
            "format=auto,format=yuv420p[bordered];"
            f"[bordered]ass={name}.ass:fontsdir=f[vframed]"
        )
        map_idx = base.index("-map")
        if base[map_idx + 1] != "[v]":
            raise RuntimeError("Mapeamento de video inesperado: abortando moldura")
        base[map_idx + 1] = "[vframed]"
    for k, v in (meta or {}).items():
        if v:
            base += ["-metadata", f"{k}={v}"]
    base += ["-movflags", "+faststart", "-pix_fmt"]
    encoders = []
    if _qsv_ok is not False:
        encoders.append(("qsv", ["nv12", "-c:v", "h264_qsv", "-global_quality", "23", "-preset", "fast"]))
    encoders.append(("x264", ["yuv420p", "-c:v", "libx264", "-crf", "21", "-preset", "veryfast"]))
    err = None
    for label, enc in encoders:
        p = subprocess.run(base + enc + [f"{name}.mp4"], cwd=work, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW, timeout=RENDER_SECONDS)
        if p.returncode == 0:
            if label == "qsv":
                _qsv_ok = True
            break
        err = p.stderr[-1200:]
        if label == "qsv":
            _qsv_ok = False
    else:
        raise RuntimeError(f"Render failed: {err}")
    cover_t = min(1.2, (end - start) / 2)
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{cover_t:.2f}", "-i", f"{name}.mp4", "-frames:v", "1",
         "-q:v", "3", f"{name}.jpg"], cwd=work)
    for ext in ("mp4", "jpg", "ass"):
        shutil.move(str(work / f"{name}.{ext}"), str(out_dir / f"{name}.{ext}"))
    return {"file": f"{name}.mp4", "cover": f"{name}.jpg", "layout": layout}
