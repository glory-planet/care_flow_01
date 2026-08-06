import ctypes
import os
import time
import tkinter as tk

from PIL import Image, ImageTk

from usage_timer import should_trigger_reminder, update_usage_seconds

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHARACTER_IMAGE_PATH = os.path.join(SCRIPT_DIR, "dashboard", "assets", "avatar", "stage3_transparent.png")

KEY_COLOR = "#ff00fe"
POLL_INTERVAL_MS = 10000
WALK_STEP_INTERVAL_MS = 100
WALK_STEP_PX = 4
CHARACTER_SIZE = 160
WINDOW_WIDTH = 220
TEXT_AREA_HEIGHT = 44
AUTO_CLOSE_MS = 60000


class LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def get_idle_seconds():
    info = LastInputInfo()
    info.cbSize = ctypes.sizeof(LastInputInfo)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    millis_idle = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return millis_idle / 1000.0


class StretchReminder:
    def __init__(self, root):
        self.root = root
        self.accumulated_seconds = 0
        self.last_poll_time = time.time()
        self.reminder_window = None
        self.walk_x = 0
        self.walk_direction = 1
        self.walk_label = None
        self.poll()

    def poll(self):
        now = time.time()
        elapsed = now - self.last_poll_time
        self.last_poll_time = now

        idle_seconds = get_idle_seconds()
        self.accumulated_seconds = update_usage_seconds(self.accumulated_seconds, idle_seconds, elapsed)

        if should_trigger_reminder(self.accumulated_seconds) and self.reminder_window is None:
            self.show_reminder()
            self.accumulated_seconds = 0

        self.root.after(POLL_INTERVAL_MS, self.poll)

    def show_reminder(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.wm_attributes("-transparentcolor", KEY_COLOR)
        win.configure(bg=KEY_COLOR)

        # NEAREST를 써야 리사이즈 시 가장자리 픽셀이 배경색(KEY_COLOR)과 섞이지 않는다.
        # 부드러운 보간(기본값)을 쓰면 경계에 반투명 픽셀이 생기고, 그 반투명 픽셀이
        # KEY_COLOR와 캐릭터색이 섞인 값이 되어 Windows 투명 처리가 안 먹혀 테두리로 남는다.
        character = Image.open(CHARACTER_IMAGE_PATH).convert("RGBA").resize(
            (CHARACTER_SIZE, CHARACTER_SIZE), Image.NEAREST
        )
        flipped = character.transpose(Image.FLIP_LEFT_RIGHT)
        x_offset = (WINDOW_WIDTH - CHARACTER_SIZE) // 2

        canvas_right = Image.new("RGBA", (WINDOW_WIDTH, CHARACTER_SIZE), KEY_COLOR)
        canvas_right.paste(character, (x_offset, 0), character)
        canvas_left = Image.new("RGBA", (WINDOW_WIDTH, CHARACTER_SIZE), KEY_COLOR)
        canvas_left.paste(flipped, (x_offset, 0), flipped)

        photo_right = ImageTk.PhotoImage(canvas_right)
        photo_left = ImageTk.PhotoImage(canvas_left)

        label = tk.Label(
            win, image=photo_right, text="스트레칭 할 시간이에요!",
            compound="top", bg=KEY_COLOR, fg="#33553c",
            font=("맑은 고딕", 12, "bold"),
            wraplength=WINDOW_WIDTH - 10, justify="center",
        )
        label.image_right = photo_right
        label.image_left = photo_left
        label.pack()
        label.bind("<Button-1>", lambda e: self.close_reminder())

        self.walk_x = 40
        self.walk_direction = 1
        y = screen_height - CHARACTER_SIZE - TEXT_AREA_HEIGHT - 60
        win.geometry(f"{WINDOW_WIDTH}x{CHARACTER_SIZE + TEXT_AREA_HEIGHT}+{self.walk_x}+{y}")

        self.reminder_window = win
        self.walk_label = label
        self.walk(screen_width, y)

        self.root.after(AUTO_CLOSE_MS, self.close_reminder)

    def walk(self, screen_width, y):
        if self.reminder_window is None:
            return

        self.walk_x += WALK_STEP_PX * self.walk_direction
        if self.walk_x <= 0 or self.walk_x >= screen_width - WINDOW_WIDTH:
            self.walk_direction *= -1
            self.walk_label.configure(
                image=self.walk_label.image_left if self.walk_direction < 0 else self.walk_label.image_right
            )

        self.reminder_window.geometry(f"+{self.walk_x}+{y}")
        self.root.after(WALK_STEP_INTERVAL_MS, lambda: self.walk(screen_width, y))

    def close_reminder(self):
        if self.reminder_window is not None:
            self.reminder_window.destroy()
            self.reminder_window = None


def main():
    root = tk.Tk()
    root.withdraw()
    StretchReminder(root)
    root.mainloop()


if __name__ == "__main__":
    main()
