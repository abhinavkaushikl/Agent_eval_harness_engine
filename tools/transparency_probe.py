"""A 1-file transparency probe. Run it, look at your screen, and tell me what you see.

    python tools/transparency_probe.py

It opens a small always-on-top window and draws ONLY a white circle and a red circle, with the
window set transparent the strongest way macOS Tk offers (native "plain" style + -transparent +
systemTransparent on the window and the canvas).

  * If you see JUST two circles floating with NOTHING behind them  -> transparency WORKS; the black
    box in the bot is a bug I can fix.
  * If you see the two circles sitting on a black (or grey/white) SQUARE  -> this Tk build cannot
    composite window transparency, and no amount of Tk tweaking will remove the box. That is the
    answer, and I will give you the real options instead of guessing again.

Press Esc to close.
"""

from __future__ import annotations

import tkinter as tk


def main() -> None:
    root = tk.Tk()
    root.title("probe")
    root.geometry("200x200+300+200")
    root.attributes("-topmost", True)
    canvas = tk.Canvas(root, width=200, height=200, highlightthickness=0, bd=0)
    canvas.pack()
    root.update()

    worked = True
    try:
        root.tk.call("::tk::unsupported::MacWindowStyle", "style", str(root), "plain", "none")
        root.wm_attributes("-transparent", True)
        root["bg"] = "systemTransparent"
        canvas["bg"] = "systemTransparent"
        root.update_idletasks()
    except tk.TclError as exc:
        worked = False
        print("the transparency calls raised:", exc)

    print("transparency calls accepted:", worked)
    print("LOOK AT THE WINDOW. Two circles only = transparent. Circles on a box = NOT transparent.")

    canvas.create_oval(40, 40, 110, 110, fill="#ffffff", outline="")   # white
    canvas.create_oval(95, 95, 160, 160, fill="#ff3b30", outline="")   # red
    canvas.create_text(100, 182, text="Esc to close", fill="#8e8e93", font=("Helvetica Neue", 10))

    root.bind("<Escape>", lambda _e: root.destroy())
    root.mainloop()


if __name__ == "__main__":
    main()
