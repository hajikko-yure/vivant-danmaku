import sys
import os
import time
import json
import re
import random
import threading
import queue
import urllib.request
import urllib.parse
import tkinter as tk
import ctypes
from ctypes import wintypes

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

def set_click_through(hwnd):
    try:
        ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
    except Exception:
        pass

def load_env(env_path=".env"):
    config = {
        'KEYWORD': 'VIVANT',
        'FETCH_INTERVAL_SEC': 2.0,
        'DELAY_OFFSET_SEC': 0.0,
        'MONITOR': 2,
        'ALPHA': 0.65,
        'FONT_SIZE_MIN': 14,
        'FONT_SIZE_MAX': 17,
        'SPEED_MIN': 280,
        'SPEED_MAX': 400,
        'MAX_CONCURRENT_COMMENTS': 14,
        'SPAWN_INTERVAL_SEC': 0.35
    }
    if not os.path.isabs(env_path):
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), env_path)

    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.split('#')[0].strip()
                        if k in ('FETCH_INTERVAL_SEC', 'DELAY_OFFSET_SEC', 'ALPHA', 'SPEED_MIN', 'SPEED_MAX', 'SPAWN_INTERVAL_SEC'):
                            config[k] = float(v)
                        elif k in ('MONITOR', 'FONT_SIZE_MIN', 'FONT_SIZE_MAX', 'MAX_CONCURRENT_COMMENTS'):
                            config[k] = int(v)
                        else:
                            config[k] = v
        except Exception:
            pass
    return config

def get_monitors():
    monitors = []
    def _callback(hmonitor, hdc, lprect, lparam):
        r = lprect.contents
        monitors.append({
            'x': r.left,
            'y': r.top,
            'width': r.right - r.left,
            'height': r.bottom - r.top
        })
        return 1

    MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_callback), 0)
    return monitors

class DanmakuComment:
    def __init__(self, canvas, text, start_x, y, speed_pps, font_size=15, color="#FFFFFF"):
        self.canvas = canvas
        self.text = text
        self.x = float(start_x)
        self.y = y
        self.speed_pps = speed_pps
        self.font = ("Meiryo", font_size, "bold")
        
        self.shadow_id = canvas.create_text(self.x + 1, self.y + 1, text=self.text, font=self.font, fill="#202020", anchor="w")
        self.text_id = canvas.create_text(self.x, self.y, text=self.text, font=self.font, fill=color, anchor="w")
        
        bbox = canvas.bbox(self.text_id)
        self.width = (bbox[2] - bbox[0]) if bbox else 200

    def move(self, dt):
        dx = self.speed_pps * dt
        self.x -= dx
        self.canvas.move(self.shadow_id, -dx, 0)
        self.canvas.move(self.text_id, -dx, 0)

    def is_offscreen(self):
        return (self.x + self.width) < -20

    def destroy(self):
        self.canvas.delete(self.shadow_id)
        self.canvas.delete(self.text_id)


class DanmakuApp:
    def __init__(self, config=None, monitor_idx=None):
        self.config = config or load_env()
        self.running = True
        
        monitors = get_monitors()
        if not monitors:
            monitors = [{'x': 0, 'y': 0, 'width': 1920, 'height': 1080}]
        
        if monitor_idx is None:
            monitor_idx = self.config.get('MONITOR', 1) - 1
            
        if monitor_idx < 0 or monitor_idx >= len(monitors):
            monitor_idx = 0
            
        m = monitors[monitor_idx]
        self.mon_x = m['x']
        self.mon_y = m['y']
        self.screen_width = m['width']
        self.screen_height = m['height']

        self.root = tk.Tk()
        self.root.title(f"Danmaku Overlay - {self.config['KEYWORD']}")
        
        self.root.geometry(f"{self.screen_width}x{self.screen_height}+{self.mon_x}+{self.mon_y}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        
        bg_color = "#010101"
        self.root.configure(bg=bg_color)
        self.root.attributes("-transparentcolor", bg_color)
        self.root.attributes("-alpha", float(self.config.get('ALPHA', 0.65)))
        
        self.canvas = tk.Canvas(
            self.root,
            width=self.screen_width,
            height=self.screen_height,
            bg=bg_color,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.active_comments = []
        self.comment_queue = queue.Queue()
        self.seen_ids = set()
        
        self.num_lanes = max(8, self.screen_height // 55)
        lane_height = (self.screen_height * 0.82) / self.num_lanes
        self.lane_y = [int(self.screen_height * 0.06 + i * lane_height) for i in range(self.num_lanes)]
        self.last_lane = 0
        
        self.fetch_thread = threading.Thread(target=self.fetch_loop, daemon=True)
        self.fetch_thread.start()
        
        self.console_thread = threading.Thread(target=self._console_exit_listener, daemon=True)
        self.console_thread.start()
        
        self.root.after(100, self._apply_click_through)
        
        self.last_time = time.perf_counter()
        self.last_spawn_time = 0
        self.update_danmaku()

    def _console_exit_listener(self):
        try:
            print("Enterキーで終了")
            input()
            self.root.after(0, self.close)
        except Exception:
            pass

    def _apply_click_through(self):
        hwnd = self.root.winfo_id()
        parent_hwnd = ctypes.windll.user32.GetParent(hwnd)
        target_hwnd = parent_hwnd if parent_hwnd else hwnd
        set_click_through(target_hwnd)

    def clean_text(self, text):
        text = re.sub(r'\tSTART\t|\tEND\t', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = text.replace('\n', ' ').replace('\r', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 70:
            text = text[:67] + "..."
        return text

    def fetch_tweets(self):
        keyword = self.config.get('KEYWORD', 'VIVANT')
        url = f"https://search.yahoo.co.jp/realtime/search?p={urllib.parse.quote(keyword)}&ei=UTF-8&ifr=tp_sc"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
            
            m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if not m:
                return []
            
            data = json.loads(m.group(1))
            entries = data.get('props', {}).get('pageProps', {}).get('pageData', {}).get('timeline', {}).get('entry', [])
            
            now = time.time()
            new_items = []
            for entry in entries:
                t_id = entry.get('id')
                created_at = entry.get('createdAt', now)
                
                if (now - created_at) > 45:
                    continue

                if t_id and t_id not in self.seen_ids:
                    self.seen_ids.add(t_id)
                    raw_text = entry.get('displayText', '') or entry.get('displayTextBody', '')
                    cleaned = self.clean_text(raw_text)
                    if cleaned:
                        new_items.append({
                            'id': t_id,
                            'text': cleaned,
                            'created_at': created_at,
                            'received_at': now
                        })
            
            if len(self.seen_ids) > 8000:
                self.seen_ids = set(list(self.seen_ids)[-4000:])

            return new_items
        except Exception:
            return []

    def fetch_loop(self):
        first_run = True
        interval = float(self.config.get('FETCH_INTERVAL_SEC', 2.0))
        while self.running:
            items = self.fetch_tweets()
            if items:
                items.sort(key=lambda x: x['created_at'])
                if first_run:
                    for item in items[-5:]:
                        self.comment_queue.put(item)
                    first_run = False
                else:
                    for item in items:
                        self.comment_queue.put(item)
            time.sleep(interval)

    def spawn_comment(self, text):
        lane = (self.last_lane + random.randint(1, 3)) % self.num_lanes
        self.last_lane = lane
        y = self.lane_y[lane]
        
        s_min = float(self.config.get('SPEED_MIN', 280))
        s_max = float(self.config.get('SPEED_MAX', 400))
        speed_pps = random.uniform(s_min, s_max)
        
        f_min = int(self.config.get('FONT_SIZE_MIN', 14))
        f_max = int(self.config.get('FONT_SIZE_MAX', 17))
        font_size = random.randint(min(f_min, f_max), max(f_min, f_max))
        
        colors = ["#FFFFFF", "#F5F5F5", "#E8E8E8", "#FFEAA7", "#DFE6E9"]
        color = random.choice(colors)
        
        comment = DanmakuComment(self.canvas, text, self.screen_width + 10, y, speed_pps, font_size, color)
        self.active_comments.append(comment)

    def update_danmaku(self):
        if not self.running:
            return

        now = time.perf_counter()
        real_now = time.time()
        dt = now - self.last_time
        self.last_time = now

        if dt > 0.1:
            dt = 0.016

        spawn_interval = float(self.config.get('SPAWN_INTERVAL_SEC', 0.35))
        max_comments = int(self.config.get('MAX_CONCURRENT_COMMENTS', 14))
        delay_offset = float(self.config.get('DELAY_OFFSET_SEC', 0.0))

        qsize = self.comment_queue.qsize()
        if qsize > 8:
            discard_count = qsize - 5
            for _ in range(discard_count):
                try:
                    self.comment_queue.get_nowait()
                except queue.Empty:
                    break

        burst_limit = 2 if qsize > 3 else 1
        spawned = 0

        while (now - self.last_spawn_time > spawn_interval or qsize > 3) and not self.comment_queue.empty() and spawned < burst_limit:
            if len(self.active_comments) < max_comments:
                try:
                    item = self.comment_queue.get_nowait()
                    if delay_offset > 0:
                        target_time = item['created_at'] + delay_offset
                        if real_now < target_time:
                            self.comment_queue.put(item)
                            break
                    self.spawn_comment(item['text'])
                    self.last_spawn_time = now
                    spawned += 1
                except queue.Empty:
                    break
            else:
                break

        still_active = []
        for c in self.active_comments:
            c.move(dt)
            if c.is_offscreen():
                c.destroy()
            else:
                still_active.append(c)
        self.active_comments = still_active

        self.root.after(12, self.update_danmaku)

    def close(self):
        self.running = False
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass
        self.root.destroy()
        sys.exit(0)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Danmaku Overlay")
    parser.add_argument("--monitor", type=int, default=None, help="Monitor index (1, 2, ...)")
    args = parser.parse_args()

    cfg = load_env()
    selected_idx = (args.monitor - 1) if args.monitor is not None else (cfg.get('MONITOR', 2) - 1)

    app = DanmakuApp(config=cfg, monitor_idx=selected_idx)
    app.run()
