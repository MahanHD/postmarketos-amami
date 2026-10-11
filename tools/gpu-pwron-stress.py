#!/usr/bin/env python3
"""Make Xorg draw once every PERIOD ms, so the GPU (66 ms autosuspend) powers
down between draws and every draw is the first submission after a power-on.

  pwron-stress.py [period_ms] [minutes]
"""
import sys
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

period = int(sys.argv[1]) if len(sys.argv) > 1 else 200
minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 20
n = 0

def draw(area, cr):
    c = (n % 3) / 2.0
    cr.set_source_rgb(c, 1 - c, 0.5)
    cr.paint()
    cr.set_source_rgb(0, 0, 0)
    cr.move_to(20, 60)
    cr.set_font_size(40)
    cr.show_text("draw %d" % n)

def tick():
    global n
    n += 1
    area.queue_draw()
    return True

win = Gtk.Window(title="pwron-stress")
win.set_default_size(600, 400)
area = Gtk.DrawingArea()
area.connect("draw", draw)
win.add(area)
win.connect("destroy", Gtk.main_quit)
win.show_all()
GLib.timeout_add(period, tick)
GLib.timeout_add(int(minutes * 60000), lambda: (print("draws", n), Gtk.main_quit()))
Gtk.main()
