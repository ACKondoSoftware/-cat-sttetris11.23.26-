#!/usr/bin/env python3
# ============================================================
#  Cat's Tetris 0.1  —  A.C Holdings / Team Flames
#  Single-file Python + pygame. Locked 60 FPS, Famicom/NES rules:
#  NES gravity table, NES scoring, NES randomizer, DAS 16/6,
#  Nintendo rotation (no kicks), ARE, center-out line clear,
#  per-level palettes, piece statistics, danger-tempo music.
#  Soundtrack synthesized at boot (pulse + triangle + noise).
#  Controls: ←/→ move  ↓ soft drop  X/↑ rotate CW  Z rotate CCW
#            ENTER start/pause  ESC quit   (hold X + ENTER = level +10)
#
#  MAC BUILD: HiDPI+vsync display, tick() instead of tick_busy_loop(),
#  high score under Application Support, Menlo fonts.
# ============================================================
import pygame, random, math, array, json, os, sys

SR, S, W, H, FPS = 44100, 3, 256, 240, 60
VERSION = "0.1"

# ------------------------------------------------------------ audio synth
NOTE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}

def freq(n):
    semi, i = NOTE[n[0]], 1
    if n[i] == '#': semi, i = semi + 1, 2
    elif n[i] == 'b': semi, i = semi - 1, 2
    return 440.0 * 2 ** ((12 * (int(n[i:]) + 1) + semi - 69) / 12)

def parse(s):
    out = []
    for tok in s.split():
        n, b = tok.split(':')
        out.append((None if n == 'R' else n, float(b)))
    return out

def zeros(n):
    return array.array('h', bytes(2 * max(0, n)))

def period(kind, f, vol):
    p, amp = max(2, int(round(SR / f))), int(32767 * vol)
    if kind == 'tri':  # NES-style 4-bit stepped triangle
        return array.array('h', [int(amp * (round((4 * abs(k / p - .5) - 1) * 7.5) / 7.5)) for k in range(p)])
    duty = {'p12': 8, 'p25': 4, 'p50': 2}[kind]
    hi = max(1, p // duty)
    return array.array('h', [amp] * hi + [-amp] * (p - hi))

def tile(per, n):
    a = per * (n // len(per) + 1)
    del a[n:]
    return a

def render_voice(seq, bpm, kind, vol, gate=.88, decay=.55):
    spb, buf, t, cache = 60.0 / bpm * SR, array.array('h'), 0.0, {}
    for n, beats in seq:
        st = int(round(t)); t += beats * spb; ln = int(round(t)) - st
        if n is None:
            buf.extend(zeros(ln)); continue
        if n not in cache:
            f = freq(n)
            cache[n] = (period(kind, f, vol), period(kind, f, vol * decay))
        full, soft = cache[n]
        on = int(ln * gate)
        head = (min(on, int(on * .4) + SR // 30) // len(full)) * len(full)
        buf.extend(tile(full, head)); buf.extend(tile(soft, on - head)); buf.extend(zeros(ln - on))
    return buf

_rng = random.Random(1985)
def _noise(n, amp):
    return array.array('h', [int(_rng.uniform(-1, 1) * amp * (1 - k / n) ** 2) for k in range(n)])
HAT, SNARE = _noise(SR // 30, 2600), _noise(SR // 11, 4200)
KICK = array.array('h')
_ph, _kn = 0.0, int(SR * .09)
for _k in range(_kn):
    _ph += 2 * math.pi * (40 + 140 * (1 - _k / _kn)) / SR
    KICK.append(int(8000 * math.sin(_ph) * (1 - _k / _kn)))

def render_drums(total, bpm, meter):
    spb, buf, i = 60.0 / bpm * SR, zeros(total), 0
    while True:
        pos = int(i * spb / 2)
        if pos >= total: break
        beat, on = i // 2, i % 2 == 0
        smp = (KICK if beat % meter == 0 else SNARE) if on else HAT
        end = min(total, pos + len(smp))
        buf[pos:end] = smp[:end - pos]
        i += 1
    return buf

def bass(roots, bpb, lo=2):
    seq = []
    for r in roots:
        for i in range(bpb * 2):
            seq.append((f"{r}{lo + (i % 2)}", .5))
    return seq

# --- TYPE-A : Korobeiniki (Russian folk, 1861 — public domain)
KORO_A = parse("E5:1 B4:.5 C5:.5 D5:1 C5:.5 B4:.5  A4:1 A4:.5 C5:.5 E5:1 D5:.5 C5:.5 "
               "B4:1.5 C5:.5 D5:1 E5:1  C5:1 A4:1 A4:1 R:1 "
               "R:.5 D5:1 F5:.5 A5:1 G5:.5 F5:.5  E5:1.5 C5:.5 E5:1 D5:.5 C5:.5 "
               "B4:1 B4:.5 C5:.5 D5:1 E5:1  C5:1 A4:1 A4:1 R:1")
KORO_B = parse("E5:2 C5:2 D5:2 B4:2 C5:2 A4:2 G#4:2 B4:2 "
               "E5:2 C5:2 D5:2 B4:2 C5:1 E5:1 A5:2 G#5:4")
SONG_A = dict(bpm=150, meter=2,
              lead=KORO_A * 2 + KORO_B * 2,
              bass=bass("EAEADCEA", 4) * 2 + bass("AEAEAEAE", 4) * 2)

# --- TYPE-B : "Hemet Skyline" (original, Team Flames)
HEMET = parse("C5:.5 E5:.5 G5:.5 E5:.5 C6:1 G5:1  A5:.5 G5:.5 F5:.5 E5:.5 D5:2 "
              "B4:.5 D5:.5 G5:.5 D5:.5 B5:1 G5:1  A5:.5 G5:.5 F5:.5 D5:.5 C5:2 "
              "E5:1 F5:.5 G5:.5 A5:1 G5:.5 F5:.5  E5:.5 F5:.5 E5:.5 D5:.5 C5:2 "
              "D5:.5 E5:.5 F5:.5 A5:.5 G5:1 B4:1  C5:3 R:1")
SONG_B = dict(bpm=140, meter=2, lead=HEMET * 2, bass=bass("CFGCFCGC", 4) * 2)

# --- TYPE-C : Minuet in G, BWV Anh. 114 (Petzold, c.1725 — public domain)
MIN_1 = parse("D5:1 G4:.5 A4:.5 B4:.5 C5:.5  D5:1 G4:1 G4:1  E5:1 C5:.5 D5:.5 E5:.5 F#5:.5 "
              "G5:1 G4:1 G4:1  C5:1 D5:.5 C5:.5 B4:.5 A4:.5  B4:1 C5:.5 B4:.5 A4:.5 G4:.5")
MIN_X = parse("F#4:1 G4:.5 A4:.5 B4:.5 G4:.5  A4:3")
MIN_Y = parse("A4:1 B4:.5 A4:.5 G4:.5 F#4:.5  G4:3")
SONG_C = dict(bpm=132, meter=3,
              lead=(MIN_1 + MIN_X + MIN_1 + MIN_Y) * 2,
              bass=(bass("GGCGAGDD", 3) + bass("GGCGAGDG", 3)) * 2)

SONGS = [SONG_A, SONG_B, SONG_C]
SONG_NAMES = ["TYPE-A", "TYPE-B", "TYPE-C", "OFF"]

class Audio:
    def __init__(self):
        self.ok = False
        try:
            pygame.mixer.pre_init(SR, -16, 1, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            pygame.mixer.set_reserved(3)
            self.stereo = pygame.mixer.get_init()[2] == 2
            self.mus = [pygame.mixer.Channel(i) for i in range(3)]
            self.sfx = [pygame.mixer.Channel(i) for i in (3, 4)]
            self.ok = True
        except Exception as e:
            print("audio off:", e)
        self.cur, self.tracks, self.fx = None, {}, {}

    def snd(self, a):
        if self.stereo:
            st = zeros(len(a) * 2); st[0::2] = a; st[1::2] = a; a = st
        return pygame.mixer.Sound(buffer=a.tobytes())

    def build(self, progress=lambda f: None):
        if not self.ok: return
        steps = len(SONGS) * 2
        for i, sg in enumerate(SONGS):
            for fast in (False, True):
                bpm = sg['bpm'] * (1.35 if fast else 1)
                lead = render_voice(sg['lead'], bpm, 'p25', .16)
                bs = render_voice(sg['bass'], bpm, 'tri', .30, gate=.95, decay=.9)
                n = max(len(lead), len(bs))
                lead.extend(zeros(n - len(lead))); bs.extend(zeros(n - len(bs)))
                dr = render_drums(n, bpm, sg['meter'])
                self.tracks[(i, fast)] = [self.snd(lead), self.snd(bs), self.snd(dr)]
                progress((i * 2 + fast + 1) / steps)
        fx = {
            'move':   ("A6:.25", 900, 'p50', .12),
            'rotate': ("E6:.25 B6:.25", 1400, 'p25', .12),
            'lock':   ("C4:.25 G3:.25", 900, 'p12', .16),
            'clear':  ("C6:.25 E6:.25 G6:.25 C7:.5 G6:.25 C7:1", 1100, 'p50', .14),
            'tetris': ("C6:.25 E6:.25 G6:.25 C7:.25 E7:.25 G7:.25 C7:.25 E7:.25 G7:.25 C8:1.5", 900, 'p25', .15),
            'level':  ("G5:.5 C6:.5 E6:.5 G6:.5 C7:1.5", 700, 'p50', .14),
            'pause':  ("E6:.5 C6:.5 E6:.5 C6:1", 700, 'p50', .12),
            'select': ("C6:.25 G6:.5", 900, 'p25', .12),
            'over':   ("C5:1 G4:1 E4:1 C4:1 G3:1 C3:3", 300, 'p25', .16),
        }
        for k, (s, bpm, kind, v) in fx.items():
            self.fx[k] = self.snd(render_voice(parse(s), bpm, kind, v, gate=.97, decay=.6))

    def play(self, idx, fast=False):
        if not self.ok or (idx, fast) == self.cur: return
        self.stop()
        if idx is None or idx > 2: return
        self.cur = (idx, fast)
        for ch, s in zip(self.mus, self.tracks[(idx, fast)]):
            ch.play(s, loops=-1)

    def stop(self):
        self.cur = None
        if self.ok:
            for ch in self.mus: ch.stop()

    def pause(self, on):
        if self.ok:
            for ch in self.mus: ch.pause() if on else ch.unpause()

    def sfx_play(self, k):
        if self.ok and k in self.fx:
            ch = self.sfx[1] if k in ('move', 'rotate') else self.sfx[0]
            ch.play(self.fx[k])

# ------------------------------------------------------------ rules
# Piece order T J Z O S L I (NES). Offsets (x,y), y down, pivot spawns at (5,0).
SHAPES = [
    [[(-1,0),(0,0),(1,0),(0,1)], [(0,-1),(-1,0),(0,0),(0,1)], [(-1,0),(0,0),(1,0),(0,-1)], [(0,-1),(0,0),(1,0),(0,1)]],
    [[(-1,0),(0,0),(1,0),(1,1)], [(0,-1),(0,0),(-1,1),(0,1)], [(-1,-1),(-1,0),(0,0),(1,0)], [(0,-1),(1,-1),(0,0),(0,1)]],
    [[(-1,0),(0,0),(0,1),(1,1)], [(1,-1),(0,0),(1,0),(0,1)]],
    [[(-1,0),(0,0),(-1,1),(0,1)]],
    [[(0,0),(1,0),(-1,1),(0,1)], [(0,-1),(0,0),(1,0),(1,1)]],
    [[(-1,0),(0,0),(1,0),(-1,1)], [(-1,-1),(0,-1),(0,0),(0,1)], [(1,-1),(-1,0),(0,0),(1,0)], [(0,-1),(0,0),(0,1),(1,1)]],
    [[(-2,0),(-1,0),(0,0),(1,0)], [(0,-2),(0,-1),(0,0),(0,1)]],
]
STYLE = [0, 1, 2, 0, 1, 2, 0]                       # T/O/I framed, J/S color1, Z/L color2
GRAVITY = [48,43,38,33,28,23,18,13,8,6,5,5,5,4,4,4,3,3,3] + [2] * 10 + [1]
LINE_PTS = [0, 40, 100, 300, 1200]
DAS_INIT, DAS_REP = 16, 6
PALETTE = [((0,88,248),(60,188,252)), ((0,168,0),(184,248,24)), ((216,0,204),(248,120,248)),
           ((0,88,248),(88,216,84)), ((228,0,88),(88,248,152)), ((88,248,152),(104,136,252)),
           ((248,56,0),(124,124,124)), ((104,68,252),(168,0,32)), ((0,88,248),(248,56,0)),
           ((248,56,0),(252,160,68))]
WHITE, BLACK, GREY = (252,252,252), (0,0,0), (124,124,124)
FONT_FAMILY = "menlo,monospaced,dejavusansmono,monospace"
TOP_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "CatsTetris")
TOP_FILE = os.path.join(TOP_DIR, "top.json")

def load_top():
    try:
        with open(TOP_FILE) as f: return int(json.load(f).get("top", 10000))
    except Exception: return 10000

def save_top(v):
    try:
        os.makedirs(TOP_DIR, exist_ok=True)
        with open(TOP_FILE, "w") as f: json.dump({"top": v}, f)
    except Exception: pass

# ------------------------------------------------------------ logo (original block-letter mark)
GLYPH = {
    'C': [".###", "#...", "#...", "#...", ".###"],
    'A': [".##.", "#..#", "####", "#..#", "#..#"],
    'T': ["###", ".#.", ".#.", ".#.", ".#."],
    "'": ["#", "#", ".", ".", "."],
    'S': [".###", "#...", ".##.", "...#", "###."],
    'E': ["###", "#..", "##.", "#..", "###"],
    'R': ["###.", "#..#", "###.", "#.#.", "#..#"],
    'I': ["###", ".#.", ".#.", ".#.", "###"],
}
LOGO_COLS = [(248,56,0), (252,160,68), (248,216,0), (88,216,84), (60,188,252), (216,0,204)]

# ------------------------------------------------------------ game
class Game:
    def __init__(self, screen, audio):
        self.scr, self.au = screen, audio
        self.font = pygame.font.SysFont(FONT_FAMILY, 8 * S, bold=True)
        self.fsmall = pygame.font.SysFont(FONT_FAMILY, 6 * S, bold=True)
        self.tcache = {}
        self.state, self.t = 'title', 0
        self.music_sel, self.level_sel, self.row = 0, 0, 0
        self.top = load_top()
        self.held, self.pressed = set(), set()
        self.bg = self.make_bg()

    # ---------- drawing primitives (NES coords → window)
    def r(self, x, y, w, h, c):
        self.scr.fill(c, (int(x * S), int(y * S), int(w * S), int(h * S)))

    def txt(self, s, x, y, c=WHITE, small=False, center=False):
        key = (s, c, small)
        if key not in self.tcache:
            self.tcache[key] = (self.fsmall if small else self.font).render(s, False, c)
        surf = self.tcache[key]
        px = x * S - (surf.get_width() // 2 if center else 0)
        self.scr.blit(surf, (px, y * S))

    def box(self, x, y, w, h, title=None):
        self.r(x - 2, y - 2, w + 4, h + 4, (60,188,252))
        self.r(x - 1, y - 1, w + 2, h + 2, (0,64,88))
        self.r(x, y, w, h, BLACK)
        if title: self.txt(title, x + 3, y + 2)

    def make_bg(self):
        bg = pygame.Surface((W * S, H * S))
        bg.fill((24, 24, 40))
        for yy in range(0, H, 8):
            for xx in range(0, W, 8):
                if (xx // 8 + yy // 8) % 2 == 0:
                    bg.fill((32, 32, 56), (xx * S, yy * S, 8 * S, 8 * S))
                bg.fill((44, 44, 72), (xx * S, yy * S, S, S))
        return bg

    def cell(self, x, y, pid, sz=8, pal=None):
        c1, c2 = pal or PALETTE[self.level % 10]
        st = STYLE[pid]
        if st == 0:
            self.r(x, y, sz - 1, sz - 1, c1)
            self.r(x + 1, y + 1, sz - 3, sz - 3, WHITE)
            self.r(x, y, 1, 1, WHITE)
        else:
            self.r(x, y, sz - 1, sz - 1, c1 if st == 1 else c2)
            self.r(x, y, 1, 1, WHITE)
            self.r(x + 1, y + 1, 2 if sz > 5 else 1, 1, WHITE)
            self.r(x + 1, y + 2, 1, 1, WHITE)

    def piece_at(self, pid, rot, px, py, sz=8, pal=None):
        for dx, dy in SHAPES[pid][rot]:
            self.cell(px + dx * sz, py + dy * sz, pid, sz, pal)

    def logo(self, cx, y):
        def word(s, b, yy, ci):
            cols = sum(len(GLYPH[ch][0]) for ch in s) + len(s) - 1
            x = cx - cols * b / 2
            for ch in s:
                col = LOGO_COLS[ci % len(LOGO_COLS)]; ci += 1
                dark = tuple(v // 2 for v in col)
                lite = tuple(min(255, v + 90) for v in col)
                g = GLYPH[ch]
                for gy, line in enumerate(g):
                    for gx, p in enumerate(line):
                        if p == '#':
                            bx, by = x + gx * b, yy + gy * b
                            self.r(bx, by, b, b, dark)
                            self.r(bx, by, b - 1, b - 1, col)
                            self.r(bx, by, b - 1, 1, lite)
                            self.r(bx, by, 1, b - 1, lite)
                x += (len(g[0]) + 1) * b
            return ci
        bob = math.sin(self.t / 20) * 1.5
        ci = word("CAT'S", 4, y + bob, 0)
        word("TETRIS", 7, y + 26 + bob, ci)

    # ---------- input
    def hit(self, *ks): return any(k in self.pressed for k in ks)
    def down(self, *ks): return any(k in self.held for k in ks)

    # ---------- state machine
    def step(self):
        self.t += 1
        getattr(self, 'st_' + self.state)()
        self.pressed.clear()

    def st_title(self):
        if self.hit(pygame.K_RETURN):
            self.au.sfx_play('select'); self.state = 'menu'; self.au.play(self.music_sel)

    def st_menu(self):
        if self.hit(pygame.K_UP, pygame.K_DOWN):
            self.row ^= 1; self.au.sfx_play('move')
        d = (1 if self.hit(pygame.K_RIGHT) else 0) - (1 if self.hit(pygame.K_LEFT) else 0)
        if d:
            self.au.sfx_play('move')
            if self.row == 0:
                self.music_sel = (self.music_sel + d) % 4; self.au.play(self.music_sel)
            else:
                self.level_sel = (self.level_sel + d) % 10
        if self.hit(pygame.K_RETURN):
            self.au.sfx_play('select')
            self.start(self.level_sel + (10 if self.down(pygame.K_x) else 0))

    def start(self, level):
        self.board = [[0] * 10 for _ in range(20)]
        self.level = level
        self.lines = self.score = 0
        self.next_lines = min(level * 10 + 10, max(100, level * 10 - 50))
        self.stats = [0] * 7
        self.prev = 7
        self.nxt = self.roll()
        self.das = self.fall = self.soft = self.soft_rows = 0
        self.clear_rows, self.clear_t, self.are, self.flash = [], 0, 0, 0
        self.danger, self.soft_lock = False, True
        self.state = 'play'
        self.au.play(self.music_sel, False)
        self.spawn()

    def roll(self):
        r = random.randrange(8)
        if r == 7 or r == self.prev: r = random.randrange(7)
        self.prev = r
        return r

    def fits(self, p, rot, x, y):
        b = self.board
        for dx, dy in SHAPES[p][rot]:
            cx, cy = x + dx, y + dy
            if cx < 0 or cx > 9 or cy > 19: return False
            if cy >= 0 and b[cy][cx]: return False
        return True

    def spawn(self):
        self.cur, self.nxt = self.nxt, self.roll()
        self.rot, self.x, self.y, self.fall, self.soft_rows = 0, 5, 0, 0, 0
        self.stats[self.cur] += 1
        if self.down(pygame.K_DOWN): self.soft_lock = True
        if not self.fits(self.cur, 0, 5, 0): self.game_over()

    def shift(self, dx):
        if self.fits(self.cur, self.rot, self.x + dx, self.y):
            self.x += dx; self.au.sfx_play('move')
        else:
            self.das = DAS_INIT

    def rotate(self, d):
        nr = (self.rot + d) % len(SHAPES[self.cur])
        if self.fits(self.cur, nr, self.x, self.y):
            self.rot = nr; self.au.sfx_play('rotate')

    def drop(self, soft=False):
        self.fall = 0
        if self.fits(self.cur, self.rot, self.x, self.y + 1):
            self.y += 1
            if soft: self.soft_rows += 1
        else:
            self.lock()

    def lock(self):
        for dx, dy in SHAPES[self.cur][self.rot]:
            if self.y + dy < 0:
                self.game_over(); return
            self.board[self.y + dy][self.x + dx] = self.cur + 1
        self.score += self.soft_rows
        self.cur = None
        self.are = 10 + max(0, (19 - self.y) // 4) * 2          # NES-ish height-based ARE
        full = [r for r in range(20) if all(self.board[r])]
        if full:
            n = len(full)
            self.clear_rows, self.clear_t = full, 0
            self.score += LINE_PTS[n] * (self.level + 1)
            self.lines += n
            up = False
            while self.lines >= self.next_lines:
                self.level += 1; self.next_lines += 10; up = True
            if n == 4: self.flash = 24
            self.au.sfx_play('level' if up else 'tetris' if n == 4 else 'clear')
        else:
            self.au.sfx_play('lock')
            self.check_danger()

    def check_danger(self):
        d = any(any(row) for row in self.board[:6])
        if d != self.danger:
            self.danger = d
            self.au.play(self.music_sel, d)

    def game_over(self):
        self.cur, self.state, self.over_t = None, 'over', 0
        self.au.stop(); self.au.sfx_play('over')
        if self.score > self.top:
            self.top = self.score; save_top(self.top)

    def st_play(self):
        K = pygame
        if self.flash: self.flash -= 1
        if self.hit(K.K_RETURN, K.K_p):
            self.state = 'pause'; self.au.pause(True); self.au.sfx_play('pause'); return
        if self.clear_rows:
            self.clear_t += 1
            if self.clear_t >= 20:
                for r in sorted(self.clear_rows):
                    del self.board[r]; self.board.insert(0, [0] * 10)
                self.clear_rows = []
                self.check_danger()
            return
        if self.cur is None:
            self.are -= 1
            if self.are <= 0: self.spawn()
            return
        L, R = self.down(K.K_LEFT), self.down(K.K_RIGHT)
        if self.hit(K.K_LEFT) or self.hit(K.K_RIGHT):
            self.das = 0; self.shift(-1 if self.hit(K.K_LEFT) else 1)
        elif L ^ R:
            self.das += 1
            if self.das >= DAS_INIT:
                self.das = DAS_INIT - DAS_REP; self.shift(-1 if L else 1)
        if self.cur is None: return
        if self.hit(K.K_x, K.K_UP): self.rotate(1)
        if self.hit(K.K_z): self.rotate(-1)
        if not self.down(K.K_DOWN): self.soft_lock = False
        soft = self.down(K.K_DOWN) and not self.soft_lock and not (L or R)
        if soft:
            self.soft += 1
            if self.soft >= 2:
                self.soft = 0; self.drop(True); return
        else:
            self.soft = 0; self.soft_rows = 0
        self.fall += 1
        if self.fall >= GRAVITY[min(self.level, 29)]: self.drop()

    def st_pause(self):
        if self.hit(pygame.K_RETURN, pygame.K_p):
            self.state = 'play'; self.au.pause(False)

    def st_over(self):
        self.over_t += 1
        if self.over_t > 90 and self.hit(pygame.K_RETURN):
            self.state = 'menu'; self.au.play(self.music_sel)

    # ---------- render
    def draw(self):
        self.scr.blit(self.bg, (0, 0))
        getattr(self, 'dr_' + ('play' if self.state in ('play', 'pause', 'over') else self.state))()

    def dr_title(self):
        self.box(24, 28, 208, 84)
        self.logo(128, 40)
        demo = [(0, 40, 140), (6, 72, 140), (3, 104, 140), (2, 136, 140), (4, 168, 140), (1, 200, 140)]
        for i, (p, x, y) in enumerate(demo):
            self.piece_at(p, (self.t // 40 + i) % len(SHAPES[p]), x, y + math.sin(self.t / 15 + i) * 3, 8, PALETTE[i])
        if (self.t // 30) % 2 == 0: self.txt("PUSH START", 128, 170, center=True)
        self.txt(f"v{VERSION}  60 FPS  FAMICOM RULES", 128, 196, GREY, True, True)
        self.txt("A.C HOLDINGS / TEAM FLAMES 2026", 128, 212, (252,160,68), True, True)

    def dr_menu(self):
        self.logo(128, 10)
        self.box(40, 76, 176, 52, "MUSIC TYPE")
        for i, n in enumerate(SONG_NAMES):
            x, y = 50 + (i % 2) * 84, 92 + (i // 2) * 14
            sel = i == self.music_sel
            if sel and (self.row != 0 or (self.t // 8) % 2 == 0):
                self.r(x - 4, y - 1, 74, 11, (168, 0, 32))
            self.txt(n, x, y, WHITE if sel else GREY)
        self.box(40, 142, 176, 56, "LEVEL")
        for i in range(10):
            x, y = 54 + (i % 5) * 32, 158 + (i // 5) * 18
            sel = i == self.level_sel
            if sel and (self.row != 1 or (self.t // 8) % 2 == 0):
                self.r(x - 4, y - 2, 20, 14, (252, 160, 68))
            self.r(x - 3, y - 1, 18, 12, (0, 64, 88) if not sel else (248, 56, 0))
            self.txt(str(i), x + 3, y, WHITE)
        self.txt("↑↓ ROW  ←→ PICK  ENTER START  (X+ENTER +10)", 128, 212, GREY, True, True)
        self.txt(f"TOP {self.top:06d}", 128, 226, (252,160,68), True, True)

    def dr_play(self):
        pal = PALETTE[self.level % 10]
        # flash on tetris
        if self.flash and (self.flash // 4) % 2: self.scr.fill(WHITE)
        # LINES
        self.box(96, 14, 80, 14)
        self.txt(f"LINES-{self.lines:03d}", 101, 16)
        # board
        self.box(96, 40, 80, 160)
        clr = set(self.clear_rows)
        step = self.clear_t // 4 if self.clear_rows else -1
        hide = 120 if self.state == 'pause' else 0
        for ry in range(20):
            if hide: break
            for rx in range(10):
                v = self.board[ry][rx]
                if not v: continue
                if ry in clr and 4 - step <= rx <= 5 + step: continue
                self.cell(96 + rx * 8, 40 + ry * 8, v - 1)
        if self.cur is not None and self.state == 'play':
            for dx, dy in SHAPES[self.cur][self.rot]:
                if self.y + dy >= 0:
                    self.cell(96 + (self.x + dx) * 8, 40 + (self.y + dy) * 8, self.cur)
        if self.state == 'pause':
            self.txt("PAUSE", 136, 112, WHITE, center=True)
        # type label
        self.box(16, 14, 64, 14)
        self.txt(SONG_NAMES[self.music_sel] if self.music_sel < 3 else "NO BGM", 22, 16)
        # stats
        self.box(16, 40, 64, 160, "STATS")
        for i in range(7):
            y = 58 + i * 20
            self.piece_at(i, 0, 30, y, 5, pal)
            self.txt(f"{self.stats[i]:03d}", 50, y - 2, (248, 56, 0))
        # score
        self.box(192, 14, 56, 54)
        self.txt("TOP", 196, 16); self.txt(f"{min(self.top, 999999):06d}", 196, 26)
        self.txt("SCORE", 196, 40); self.txt(f"{min(self.score, 999999):06d}", 196, 50)
        # next
        self.box(192, 96, 40, 36, "NEXT")
        if self.nxt is not None:
            cells = SHAPES[self.nxt][0]
            mnx, mxx = min(c[0] for c in cells), max(c[0] for c in cells)
            mny, mxy = min(c[1] for c in cells), max(c[1] for c in cells)
            ox = 212 - ((mxx - mnx + 1) * 8) / 2 - mnx * 8
            oy = 118 - ((mxy - mny + 1) * 8) / 2 - mny * 8
            self.piece_at(self.nxt, 0, ox, oy)
        # level
        self.box(192, 148, 40, 26, "LEVEL")
        self.txt(f"{self.level:02d}", 204, 160)
        # danger lamp
        if self.danger and (self.t // 10) % 2:
            self.txt("!", 240, 160, (248, 56, 0))
        # game over curtain
        if self.state == 'over':
            rows = min(20, self.over_t // 4)
            for ry in range(rows):
                self.r(96, 40 + ry * 8, 80, 7, pal[0]); self.r(96, 47 + ry * 8, 80, 1, pal[1])
            if self.over_t > 90:
                self.box(100, 96, 72, 40)
                self.txt("GAME", 136, 100, WHITE, center=True)
                self.txt("OVER", 136, 112, WHITE, center=True)
                if (self.t // 20) % 2: self.txt("ENTER", 136, 124, (252,160,68), True, True)

# ------------------------------------------------------------ boot
def main():
    pygame.init()
    audio = Audio()
    flags = getattr(pygame, "SCALED", 0) | getattr(pygame, "HIGHDPI", 0)
    screen = None
    if flags:
        try:
            screen = pygame.display.set_mode((W * S, H * S), flags, vsync=1)
        except (pygame.error, TypeError):
            try:
                screen = pygame.display.set_mode((W * S, H * S), flags)
            except pygame.error:
                screen = None
    if screen is None:
        screen = pygame.display.set_mode((W * S, H * S))
    pygame.display.set_caption(f"Cat's Tetris {VERSION}")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(FONT_FAMILY, 24, bold=True)

    def progress(f):
        screen.fill(BLACK)
        screen.blit(font.render("SYNTHESIZING OST...", True, WHITE), (W * S // 2 - 150, H * S // 2 - 40))
        screen.fill((60, 188, 252), (W * S // 2 - 200, H * S // 2, int(400 * f), 20))
        pygame.display.flip(); pygame.event.pump()
    progress(0)
    audio.build(progress)

    game = Game(screen, audio)
    frames = int(os.environ.get("CATS_TETRIS_FRAMES", "0"))   # headless smoke-test hook
    n = 0
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit(); return
            if e.type == pygame.KEYDOWN:
                game.pressed.add(e.key); game.held.add(e.key)
            elif e.type == pygame.KEYUP:
                game.held.discard(e.key)
        game.step()
        game.draw()
        pygame.display.flip()
        clock.tick(FPS)
        n += 1
        if frames and n >= frames:
            pygame.image.save(screen, os.environ.get("CATS_TETRIS_SHOT", "shot.png"))
            pygame.quit(); return

if __name__ == "__main__":
    main()
