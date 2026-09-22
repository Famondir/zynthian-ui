#!/usr/bin/python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# ZYNTHIAN PROJECT: Zynthian GUI
#
# Zynthian Touchscreen Keypad V5 Class
#
# Copyright (C) 2024-2026 Pavel Vondřička <pavel.vondricka@ff.cuni.cz>
#                         Brian Walton <riban@zynthian.org>
#
# ******************************************************************************
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the LICENSE.txt file.
#
# ******************************************************************************

import os
import logging
import tkinter
from io import BytesIO
from PIL import Image, ImageTk
import tkinter.font as tkfont

try:
    import cairosvg
except:
    cairosvg = None

# Zynthian specific modules
from zyngui import zynthian_gui_config
# zynautoconnect is imported lazily (see draw_connections) - this class is
# built from inside zynthian_gui_config's own module-level init, well before
# zynautoconnect's lib_zyncore_init() has run; importing zynautoconnect here
# would make it cache a still-None lib_zyncore permanently (it reads the
# value once at import time via "from zyncoder.zyncore import lib_zyncore").

LABEL       = 0
ALT_LABEL   = 1
ACT_LABEL   = 2
ACT2_LABEL  = 3
RECT_ID     = 4
TXT_ID      = 5
IMG_ID      = 6
IMG         = 7
TKIMG       = 8
LED_STATE   = 9
LED_ID      = 10
BOLD_TIMER_ID = 11  # pending after() job id for the Bold-colour outline change, or None
LONG_TIMER_ID = 12  # pending after() job id for the Long-colour outline change, or None

# Per-knob canvas-item slots (parallel to the button LABEL/RECT_ID/etc
# indices above; knobs have no label/LED state - their face is fixed
# artwork and press classification (short/bold/long) is handled entirely
# by the existing zynswitch CUIA thread, not locally - but the press-outline
# DOES mirror the buttons' live Bold/Long colour feedback, see
# KNOB_BOLD_TIMER_ID/KNOB_LONG_TIMER_ID below).
KNOB_TKIMG      = 0  # hit-area PhotoImage (kept alive - Tk garbage-collects it otherwise)
KNOB_HIT_ID     = 1  # hit-area canvas image id
KNOB_PRESS_ID   = 2  # press-outline oval id (hidden until clicked)
KNOB_HOVER_ID   = 3  # hover-ring oval id, or None while not hovered
KNOB_BOLD_TIMER_ID = 4  # pending after() job id for the Bold-colour outline change, or None
KNOB_LONG_TIMER_ID = 5  # pending after() job id for the Long-colour outline change, or None

# Real V5 mockup coordinates, lifted from zynthian-webconf's mockup player
# (mockup/index.html, viewBox "0 0 1920 1000" over the 1910x960 render) -
# see openspec/changes/touchkeypad-visual-styles/design.md for how these
# were found/derived. All values are pixel offsets within the render image.
V5_IMAGE_PATH = "v5_mockup/v5_render_zenital_mockup_1910.png"
V5_IMAGE_SIZE = (1910, 960)
V5_SCREEN_RECT = (731, 254, 800, 480)          # x, y, w, h - matches the real screen's native 800x480
V5_BUTTON_GROUP = (79, 154)                    # push-buttons-outline group offset
V5_BUTTON_COLS = (50, 172, 294, 416)
V5_BUTTON_ROWS = (50, 165, 275, 390, 505)
V5_BUTTON_SIZE = (110, 105)
V5_LED_GROUP = (133, 208)                      # per-button status dot, same col/row grid
V5_LED_RADIUS = 30

# Rotary-encoder knob column (right of the screen), measured directly
# against the vendored render (script-driven crop/grid-overlay, not
# eyeballed) - see openspec/changes/touchkeypad-functional-knobs/design.md.
# Supersedes touchkeypad-visual-styles/tasks.md task 5.14's rough
# "(1658,125) group offset, r=52" note, which was never actually verified
# against the pixel art. Knob index 0 is the top knob (labelled "1" in the
# render) through index 3 (bottom, "4") - the same index space ZYNPOT/
# ZYNSWITCH CUIAs already use for the 4 physical encoders.
V5_KNOB_CENTER_X = 1711
V5_KNOB_TOP_Y = 197
V5_KNOB_SPACING_Y = 198
V5_KNOB_RADIUS = 44                            # hit-area radius; a touch larger than the ~40px visible knob face

# Top-edge port-icon x-positions. Left to right on the real chassis:
# headphone, speaker jacks 1/2, mic/audio-in jacks 1/2, MIDI IN/THRU/OUT,
# ethernet, USB-3, USB-2, USB-B, power.
#
# Values below are as measured by hand against a reference screenshot of
# the render that was _V5_PORT_REF_WIDTH pixels wide - NOT the same as
# V5_IMAGE_SIZE's actual 1910px, so they're scaled at load time. If these
# ever need re-measuring, measure against whatever image you have open and
# just update _V5_PORT_REF_WIDTH to that image's width - don't hand-convert
# the numbers.
_V5_PORT_REF_WIDTH = 2383


def _v5_port_x(*values):
    scale = V5_IMAGE_SIZE[0] / _V5_PORT_REF_WIDTH
    return tuple(round(v * scale) for v in values)


V5_PORT_X_AUDIO_OUT = _v5_port_x(330, 477)   # speaker jacks 1/2
V5_PORT_X_AUDIO_IN = _v5_port_x(630, 777)    # mic/audio-in jacks 1/2
V5_PORT_X_MIDI_IN = _v5_port_x(945)          # MIDI "IN" DIN jack (only one on real hardware)
V5_PORT_X_MIDI_THRU = _v5_port_x(1130)
V5_PORT_X_MIDI_OUT = _v5_port_x(1320)
V5_PORT_LAN = _v5_port_x(1510)
V5_PORT_USB_3 = _v5_port_x(1673)
V5_PORT_USB_2 = _v5_port_x(1840)
V5_PORT_USB_B = _v5_port_x(2000)


# ------------------------------------------------------------------------------
# Zynthian Touchscreen Keypad V5 Class
# ------------------------------------------------------------------------------


class zynthian_gui_touchkeypad_v5(tkinter.Canvas):

    def __init__(self):

        super().__init__(zynthian_gui_config.top,
                width=zynthian_gui_config.display_width,
                height=zynthian_gui_config.display_height,
                bg=zynthian_gui_config.color_bg,
                bd=0,
                highlightthickness=0)
        self.shown = False

        # Four parallel, selectable looks (set ZYNTHIAN_GUI_KEYPAD_STYLE before
        # launch, see run_zynthian.sh):
        #  - "classic": the original, unmodified upstream layout (uneven
        #    6-row grid, kept verbatim for comparison/fallback)
        #  - "standard" (default): same idea but the button grid actually
        #    matches the real V5 panel's 4x5 arrangement
        #  - "device": adds a chassis-style background/bezel + top port strip,
        #    matching the real V5's physical proportions
        #  - "device_cables": "device" plus live cable graphics for whatever is
        #    actually plugged into the capture ports (see draw_connections())
        self.style = os.environ.get("ZYNTHIAN_GUI_KEYPAD_STYLE", "standard")

        if self.style in ("device", "device_cables"):
            # Fixed, absolute geometry lifted from the real V5 mockup render
            # (see V5_* constants above) - not derived from display_width/
            # height at all. run_zynthian.sh sets DISPLAY_WIDTH/HEIGHT to
            # match V5_IMAGE_SIZE (plus this reserved cable margin) exactly
            # for these styles, so the canvas this __init__ creates above is
            # already the right size.
            self.cable_margin = 160 if self.style == "device_cables" else 0
            self.top_margin = self.cable_margin + V5_SCREEN_RECT[1]
            self.panel_width = V5_SCREEN_RECT[0]
            self.screen_width = V5_SCREEN_RECT[2]
            self.screen_height = V5_SCREEN_RECT[3]
            self.button_width, self.button_height = V5_BUTTON_SIZE
        elif self.style == "classic":
            self.button_width = zynthian_gui_config.display_width // 10
            self.button_height = zynthian_gui_config.display_height // 6
            self.panel_width = self.button_width * 2
            self.top_margin = 0
        else:
            # standard: buttons fill the full available height with no gap;
            # the screen area matches this exactly too (see
            # zynthian_gui_config.set_touch_keypad), so there's never a
            # black strip below either. To ALSO make standard's screen box
            # exactly match classic's (avoiding the icon/text overlap other
            # screens get when the screen aspect ratio changes - see
            # design.md), run_zynthian.sh pre-adjusts DISPLAY_WIDTH/
            # DISPLAY_HEIGHT for standard so this plain formula lands on
            # classic's exact screen_width/screen_height.
            self.button_width = zynthian_gui_config.display_width // 10
            self.button_height = zynthian_gui_config.display_height // 5
            self.panel_width = self.button_width * 4
            self.top_margin = 0
        self.bg_color = zynthian_gui_config.color_variant(zynthian_gui_config.color_panel_bg, -28)
        self.bg_color_over = zynthian_gui_config.color_variant(zynthian_gui_config.color_panel_bg, -22)
        self.border_color = zynthian_gui_config.color_bg
        self.text_color = zynthian_gui_config.color_header_tx
        self.chassis_color = zynthian_gui_config.color_variant(zynthian_gui_config.color_panel_bg, -36)

        self.place(x=0, y=0)

        if self.style in ("device", "device_cables"):
            self.draw_chassis_background()

        self.buttons = [
            # default label, alt label, rectangle id, text id, image id, image, tk image, led state, led id, bold timer id, long timer id
            ["OPT\nADMIN", None] + [None] * 11,             #0 OPT
            ["MIX\nLEVEL", None] + [None] * 11,             #1 MIX
            ["CTRL\nPRESET", None] + [None] * 11,           #2 CTRL
            ["ZS3\nSHOT", None] + [None] * 11,              #3 ZS3
            ["ALT\nHELP", None] + [None] * 11,                    #4 ALT
            ["_icons/metronome.svg", None] + [None] * 11,   #5 METRO
            ["PAD\nSTEP", None] + [None] * 11,              #6 PAD
            ["F1", "F5"] + [None] * 11,                     #7 F1
            ["\uf111", None] + [None] * 11,                 #8 RECORD
            ["\uf04d", None] + [None] * 11,                 #9 STOP
            ["\uf04b", None] + [None] * 11,                 #10 PLAY
            ["F2", "F6"] + [None] * 11,                     #11 F2
            ["BACK\nNO", None] + [None] * 11,               #12 BACK
            ["\uf077", None] + [None] * 11,                 #13 UP
            ["SEL\nYES", None] + [None] * 11,               #14 SEL
            ["F3", "F7"] + [None] * 11,                     #15 F3
            ["\uf053", None] + [None] * 11,                 #16 LEFT
            ["\uf078", None] + [None] * 11,                 #17 DOWN
            ["\uf054", None] + [None] * 11,                 #18 RIGHT
            ["F4", "F8"] + [None] * 11                      #19 F4
        ]
        if self.style == "classic":
            # Verbatim original layout: 20 buttons crammed into 6 uneven
            # rows (mostly 2 per row, the last row holding 10).
            if zynthian_gui_config.touch_navigation == "v5_keypad_left":
                self.x_offset = 0
                layout = (
                    (0, 1),
                    (2, 6),
                    (5, 3),
                    (12, 14),
                    (4, 13),
                    (16, 17, 18, 8, 9, 10, 7, 11, 15, 19)
                )
            else:
                self.x_offset = zynthian_gui_config.display_width - self.button_width * 2
                layout = (
                    (0, 1),
                    (2, 6),
                    (5, 3),
                    (12, 14),
                    (13, 4),
                    (7, 11, 15, 19, 8, 9, 10, 16, 17, 18)
                )
        else:
            # Layout mirrors the real V5 panel's 4x5 button grid (left column
            # to right column, top row to bottom row). standard docks it to
            # either screen edge (no separate physical panel here);
            # device/device_cables use the real panel's fixed absolute
            # positions instead (see draw_button_device()), so left/right
            # docking doesn't apply to them.
            layout = (
                (0, 1, 2, 3),
                (4, 5, 6, 7),
                (8, 9, 10, 11),
                (12, 13, 14, 15),
                (16, 17, 18, 19)
            )
            if self.style == "standard":
                if zynthian_gui_config.touch_navigation == "v5_keypad_left":
                    self.x_offset = 0
                else:
                    self.x_offset = zynthian_gui_config.display_width - self.button_width * 4

        if self.style in ("device", "device_cables"):
            # Z-order matters: LED dots first (bottom), then the chassis
            # image on top of them (its per-button areas are transparent/
            # semi-transparent cutouts that let only a small "window" of
            # each LED dot show through - verified against the actual PNG
            # alpha data, matching the real mockup's own leds-then-image
            # SVG order), then invisible hit-areas/press-outline on top of
            # everything so they stay clickable/visible.
            for row, row_data in enumerate(layout):
                for column, button in enumerate(row_data):
                    self.draw_button_led(row, column, button)
            self.draw_chassis_image()
            for row, row_data in enumerate(layout):
                for column, button in enumerate(row_data):
                    self.draw_button_hitarea(row, column, button)
            # Knob hit-areas go on top of everything else, same as the
            # button hit-areas - see draw_knob_device().
            self.knobs = [[None, None, None, None, None, None] for _ in range(4)]
            for i in range(4):
                self.draw_knob_device(i)
        else:
            for row, row_data in enumerate(layout):
                for column, button in enumerate(row_data):
                    self.draw_button(row, column, button)

        # update with user settings from the environment
        self.apply_user_config()

        if self.style == "device_cables":
            self.connection_slots = []
            # Deferred via after(): this object is built from inside
            # zynthian_gui_config's own module-level init, before jackd/
            # zynautoconnect are up, so the first real refresh has to wait
            # until the Tk mainloop is running (see the zynautoconnect
            # import note above draw_connections()).
            self.after(1000, self.refresh_connections)

    def draw_chassis_background(self):
        """ Bottom layer for "device"/"device_cables": a white backing
        covering the *whole* canvas, including device_cables' cable-graphics
        strip above the render - matching the original zynthian-webconf
        mockup player's page background (white), which the render's
        transparent cutouts (the panic/all-notes-off "!" icon's plate, the
        device's outer silhouette margin, the whole cable-graphics area) are
        meant to show through to. Anything less than the whole canvas left
        the cable-graphics strip on our default dark canvas colour, visibly
        inconsistent with the now-white render area below it.
        """

        w = V5_IMAGE_SIZE[0]
        h = V5_IMAGE_SIZE[1] + self.cable_margin
        self.create_rectangle(0, 0, w, h, fill="#ffffff", outline="", tags="v5_chassis")
        # No separator line between the cable-graphics strip and the render:
        # both are the same white now (see the docstring above), so a drawn
        # line just reads as an unwanted black seam across an otherwise
        # seamless white background.

    def draw_chassis_image(self):
        """ Draw the render on top of the LED dots (drawn earlier - see
        draw_button_led()): the render's per-button areas are transparent/
        semi-transparent cutouts that let only a small "window" of each LED
        dot show through, verified against the actual PNG alpha data and
        matching the real mockup's own leds-then-image SVG order. Hit-areas
        are drawn afterwards, on top (see draw_button_hitarea()).
        """

        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")
        image_path = os.path.join(icons_dir, V5_IMAGE_PATH)
        self.chassis_image = Image.open(image_path)
        self.chassis_tkimage = ImageTk.PhotoImage(self.chassis_image)
        self.create_image(0, self.cable_margin, anchor="nw", image=self.chassis_tkimage, tags="v5_chassis")

    def draw_connections(self):
        """ "device_cables" style: draw a labelled cable line coming down
        from outside the top edge for every audio/MIDI capture port and
        audio output port that is actually present, so what's physically
        plugged into this machine is visible at a glance instead of buried
        in the Audio Input screen (which only ever showed audio inputs).
        """

        if not self.cable_margin:
            return
        # Groups of (label, colour), one group per port category, so each
        # cable lands under its actual matching port icon in the render
        # instead of being evenly spread with no relation to the artwork.
        # x-anchors were measured directly off the vendored PNG (brightness
        # clustering across the top port-icon row) and corrected by hand
        # against the live render (see V5_PORT_X_* above).
        #
        # MIDI THRU and the USB/USB-B ports have anchors reserved above but
        # aren't wired to a real "is this actually connected" check yet -
        # unlike audio/MIDI (JACK ports) and LAN, there's no honest signal
        # available for them from here without more investigation, and
        # showing a cable that doesn't reflect reality would defeat the
        # point of this style.
        groups = []
        try:
            import zynautoconnect
            audio_in = [(scp.aliases[0] if scp.aliases else scp.name, zynthian_gui_config.color_hl)
                        for scp in zynautoconnect.get_audio_capture_ports()]
            groups.append((audio_in, V5_PORT_X_AUDIO_IN))
            midi_in = [(dev.aliases[0] if dev.aliases else dev.name, zynthian_gui_config.color_midi)
                       for dev in zynautoconnect.devices_in if dev is not None]
            groups.append((midi_in, V5_PORT_X_MIDI_IN))
            midi_out = [(dev.aliases[0] if dev.aliases else dev.name, zynthian_gui_config.color_midi)
                        for dev in zynautoconnect.devices_out if dev is not None]
            groups.append((midi_out, V5_PORT_X_MIDI_OUT))
            audio_out = [(dst.aliases[0] if dst.aliases else dst.name, zynthian_gui_config.color_alt2)
                         for dst in zynautoconnect.get_hw_audio_dst_ports()]
            groups.append((audio_out, V5_PORT_X_AUDIO_OUT))
        except Exception as e:
            logging.warning(f"Can't read connection ports for connection display => {e}")

        # LAN: a single static cable, not a live host-interface scan - this
        # simulates the *device's* LAN port existing/being usable for local
        # control, not this development machine's actual network setup
        # (which might have e.g. both WiFi and a wired adapter active,
        # irrelevant noise for what this style is showing).
        groups.append(([("network", zynthian_gui_config.color_ml)], V5_PORT_LAN))

        # Real hardware has exactly len(anchors) physical jacks per
        # category (e.g. 1 MIDI-in DIN jack) - if more logical devices are
        # routed there than that (e.g. 3 MIDI controllers into the one
        # MIDI-in), they all still share that single cable; only the
        # label becomes a numbered list instead of plain text. Distributed
        # round-robin in the rare case a category has >1 anchor and still
        # overflows.
        cable_slots = []  # list of (cx, [(label, colour), ...])
        for members, anchors in groups:
            if not members:
                continue
            if len(members) <= len(anchors):
                for i, member in enumerate(members):
                    cable_slots.append((anchors[i], [member]))
            else:
                buckets = [[] for _ in anchors]
                for i, member in enumerate(members):
                    buckets[i % len(anchors)].append(member)
                for anchor, bucket in zip(anchors, buckets):
                    if bucket:
                        cable_slots.append((anchor, bucket))

        # The plug end (not the top/outside end) sits 25px lower than the
        # cable-margin boundary, so it visually reaches closer into/onto the
        # device instead of stopping right at the strip's edge.
        plug_bottom = self.cable_margin + 25
        font = tkfont.Font(family=zynthian_gui_config.font_family, size=9)
        line_h = font.metrics("linespace")
        row_gap = 3
        max_chip_chars = 30  # includes the "N. " enumeration prefix
        for cx, members in cable_slots:
            color = members[0][1]  # one category per cable, so one colour
            line_id = self.create_line(cx, 0, cx, plug_bottom - 2,
                                        fill=color, width=3, tags="v5_connections")
            plug_id = self.create_oval(cx - 5, plug_bottom - 10, cx + 5, plug_bottom,
                                        fill=color, outline="", tags="v5_connections")
            self.connection_slots.append((line_id, plug_id, None))

            # Multiple devices sharing one physical jack: a left-aligned,
            # numbered stack of colour-chip labels (one row per device)
            # instead of cramming all names into one centred text block.
            # A single device just gets one plain chip, no numbering. Long
            # labels wrap *inside* their own chip (~30 chars, prefix
            # included) instead of growing one giant single-line chip.
            texts = []
            for i, (label, mcolor) in enumerate(members):
                raw = f"{i + 1}. {label}" if len(members) > 1 else label
                texts.append((self._wrap_cable_text(raw, max_chip_chars), mcolor))
            row_heights = [len(lines) * line_h + 4 for lines, _ in texts]
            block_h = sum(row_heights) + (len(texts) - 1) * row_gap
            y = (self.cable_margin - block_h) // 2
            left_x = cx - 40
            for (lines, mcolor), row_h in zip(texts, row_heights):
                text = "\n".join(lines)
                text_w = max(font.measure(line) for line in lines) + 8
                rect_id = self.create_rectangle(left_x, y, left_x + text_w, y + row_h,
                                                 fill=mcolor, outline="", tags="v5_connections")
                text_id = self.create_text(left_x + 4, y + row_h // 2, text=text, anchor="w",
                                            justify=tkinter.LEFT, fill="#000000", font=font,
                                            tags="v5_connections")
                self.connection_slots.append((rect_id, text_id, None))
                y += row_h + row_gap

    @staticmethod
    def _wrap_cable_text(text, max_chars):
        """ Wrap text to at most max_chars per line, breaking on spaces
        where possible but hard-breaking a single overlong token (JACK/
        ALSA port names are often one space-free string). """

        lines = []
        remaining = text
        while len(remaining) > max_chars:
            break_at = remaining.rfind(" ", 0, max_chars)
            if break_at <= 0:
                break_at = max_chars
            lines.append(remaining[:break_at].strip())
            remaining = remaining[break_at:].strip()
        lines.append(remaining)
        return lines

    def refresh_connections(self):
        """ Periodically redraw the connection cables so unplugging/plugging
        a device (or the accordion powering on later) is reflected live. """

        self.delete("v5_connections")
        self.connection_slots = []
        self.draw_connections()
        self.after(3000, self.refresh_connections)

    def draw_button_led(self, row, column, button):
        """ "device"/"device_cables" style, layer 1 (bottom, drawn before
        the chassis image): a backlight dot per button. The image drawn on
        top of this (draw_chassis_image()) has a transparent/semi-
        transparent cutout at this exact position for most buttons, so only
        a small "window" of this dot ends up visible - matching the real
        mockup's own leds-then-image z-order. set_button_color() re-fills
        this to reflect the wsled colour.
        """

        try:
            config = self.buttons[button]
        except IndexError:
            return
        # Cover the whole button footprint (not just a small dot at the
        # nominal LED position) so every transparent bit of this button's
        # cutout (the full label/glyph shape, not only its centre) gets
        # filled by the backlight colour instead of leaking the white
        # backing through around the edges.
        gx, gy = V5_BUTTON_GROUP
        x = gx + V5_BUTTON_COLS[column]
        y = self.cable_margin + gy + V5_BUTTON_ROWS[row]
        w, h = V5_BUTTON_SIZE
        config[LED_ID] = self.create_rectangle(x, y, x + w, y + h,
                                                fill="#505050", outline="")

    def draw_button_hitarea(self, row, column, button):
        """ "device"/"device_cables" style, layer 2 (top, drawn after the
        chassis image): an invisible clickable hit-area (a fully
        transparent image - Tkinter hit-tests images by their bounding box
        regardless of pixel transparency, unlike an unfilled rectangle,
        which only hit-tests its outline) plus a hidden press-outline.
        """

        try:
            config = self.buttons[button]
        except IndexError:
            return
        gx, gy = V5_BUTTON_GROUP
        x = gx + V5_BUTTON_COLS[column]
        y = self.cable_margin + gy + V5_BUTTON_ROWS[row]
        w, h = V5_BUTTON_SIZE
        tag = f"v5_button_{button}"

        hit_image = ImageTk.PhotoImage(Image.new("RGBA", (w, h), (0, 0, 0, 0)))
        config[TKIMG] = hit_image  # keep a reference or Tk garbage-collects it
        config[IMG_ID] = self.create_image(x, y, anchor="nw", image=hit_image, tags=tag)

        config[RECT_ID] = self.create_rectangle(
            x, y, x + w, y + h,
            outline="#F0F000", width=4, state="hidden", tags=tag
        )

        self.tag_bind(tag, "<Button-1>", lambda e, i=button: self.cb_button_push(i))
        self.tag_bind(tag, "<ButtonRelease-1>", lambda e, i=button: self.cb_button_release(i))

    def draw_knob_device(self, index):
        """ "device"/"device_cables" style: an interactive overlay for one
        of the 4 rotary-encoder knob graphics baked into the chassis render
        (see V5_KNOB_* above). Mirrors draw_button_hitarea()'s "invisible
        transparent PhotoImage" hit-area technique, plus a hover ring and a
        press-outline, and routes hover/scroll/click straight onto the same
        zynpot/zynswitch CUIA pipeline the real hardware encoder (and the
        keyboard bindings in zynthian_gui_keybinding.py) already use - no
        new dispatch logic, this is purely a second input source feeding
        the existing one.
        """

        cx = V5_KNOB_CENTER_X
        cy = self.cable_margin + V5_KNOB_TOP_Y + index * V5_KNOB_SPACING_Y
        r = V5_KNOB_RADIUS
        tag = f"v5_knob_{index}"
        config = self.knobs[index]

        hit_image = ImageTk.PhotoImage(Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0)))
        config[KNOB_TKIMG] = hit_image  # keep a reference or Tk garbage-collects it
        config[KNOB_HIT_ID] = self.create_image(cx - r, cy - r, anchor="nw", image=hit_image, tags=tag)

        config[KNOB_PRESS_ID] = self.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline="#F0F000", width=4, state="hidden", tags=tag
        )

        # Hover ring: pre-created hidden (like the press-outline above) and
        # only ever itemconfig()'d visible/hidden afterwards - NEVER
        # created/deleted at runtime, and deliberately given no tag of its
        # own (not "tag"/v5_knob_{index}). Creating a new stacked canvas
        # item that shares the hit-area's own event tag while handling that
        # tag's <Enter> callback made Tk's crossing-event machinery
        # re-fire: the new item becomes topmost under the pointer, which
        # fires <Leave> on the tag (deleting the ring) then <Enter> again
        # (recreating it) - an infinite loop that pegs the CPU and starves
        # the Tk mainloop (real bug hit during manual testing - the UI
        # became fully unresponsive, including to SIGINT/SIGTERM, since
        # Tkinter's default per-callback exception/interrupt handling
        # swallows KeyboardInterrupt raised inside a callback and just
        # keeps the mainloop going).
        config[KNOB_HOVER_ID] = self.create_oval(
            cx - r - 4, cy - r - 4, cx + r + 4, cy + r + 4,
            outline=zynthian_gui_config.color_hl, width=2, state="hidden"
        )

        self.tag_bind(tag, "<Enter>", lambda e, i=index: self.cb_knob_enter(i))
        self.tag_bind(tag, "<Leave>", lambda e, i=index: self.cb_knob_leave(i))
        self.tag_bind(tag, "<Button-4>", lambda e, i=index: self.cb_knob_wheel(i, 1))
        self.tag_bind(tag, "<Button-5>", lambda e, i=index: self.cb_knob_wheel(i, -1))
        self.tag_bind(tag, "<Button-1>", lambda e, i=index: self.cb_knob_push(i))
        self.tag_bind(tag, "<ButtonRelease-1>", lambda e, i=index: self.cb_knob_release(i))

    def cb_knob_enter(self, index):
        """ Hover feedback: an adjust-style cursor plus the pre-created
        highlight ring (see draw_knob_device()) made visible. Cleared in
        cb_knob_leave(). Only ever itemconfig()'s the ring's state - never
        creates/deletes a canvas item here (see draw_knob_device() for why
        that matters). """

        self.config(cursor="sb_v_double_arrow")
        # state="disabled", not "normal": a "normal" item becomes eligible
        # to be Tk's "current" (topmost-under-pointer) item, which can flip
        # current away from the hit-area mid-hover and re-fire <Leave>/
        # <Enter> on its tag - if the handler for that also toggles a
        # state, you get an infinite ping-pong (reproduced and confirmed
        # via isolated testing; see design.md). "disabled" still draws the
        # ring but is permanently excluded from that picking, so it can
        # never contend for "current" no matter when it's toggled.
        self.itemconfig(self.knobs[index][KNOB_HOVER_ID], state="disabled")

    def cb_knob_leave(self, index):
        """ Clears the hover feedback from cb_knob_enter(). """

        self.config(cursor="")
        self.itemconfig(self.knobs[index][KNOB_HOVER_ID], state="hidden")

    def cb_knob_wheel(self, index, direction):
        """ One wheel notch = one encoder detent, matching both the real
        hardware encoder's per-detent CUIA and the existing keyboard
        binding (Comma/Period -> "ZYNPOT ...,-1"/"...,1" in
        zynthian_gui_keybinding.py) - no custom acceleration curve here;
        whatever the current screen's zynpot_cb does with a run of +/-1
        deltas applies unchanged, same as it would for a real encoder.
        """

        zynthian_gui_config.zyngui.cuia_queue.put_nowait(f"zynpot {index},{direction}")

    def cb_knob_push(self, index):
        """ Mirrors cb_button_push(): the knob's push-button is zynswitch
        index `index` directly - no "+4" offset, since that offset only
        exists to keep the 20 keypad buttons out of the 4 encoder
        switches' reserved index range (0-3). Short/bold/long press
        *classification/dispatch* is handled entirely by the existing CUIA
        thread (zynthian_gui.py), not duplicated here - only the
        press-outline's live colour feedback (yellow -> Bold -> Long) is
        local state, mirroring cb_button_push()'s BOLD_TIMER_ID/
        LONG_TIMER_ID pattern exactly.
        """

        config = self.knobs[index]
        # state="disabled", not "normal" - see cb_knob_enter()'s comment.
        # This is exactly what the real crash (click-triggered, not just
        # hover) turned out to be: revealing the press-outline as "normal"
        # made IT win "current item" over the hit-area, which fed back
        # into the hover ring the same way. Colour (outline=) is unrelated
        # to that bug - only `state=` affects Tk's current-item picking -
        # so resetting it back to yellow here, and recolouring it from
        # _set_knob_press_duration_color() below, is safe.
        self.itemconfig(config[KNOB_PRESS_ID], state="disabled", outline="#F0F000")
        config[KNOB_BOLD_TIMER_ID] = self.after(
            zynthian_gui_config.zynswitch_bold_us // 1000,
            lambda i=index: self._set_knob_press_duration_color(i, KNOB_BOLD_TIMER_ID, zynthian_gui_config.color_warn)
        )
        config[KNOB_LONG_TIMER_ID] = self.after(
            zynthian_gui_config.zynswitch_long_us // 1000,
            lambda i=index: self._set_knob_press_duration_color(i, KNOB_LONG_TIMER_ID, zynthian_gui_config.color_error)
        )
        zynthian_gui_config.zyngui.cuia_queue.put_nowait(f"zynswitch {index},P")

    def _set_knob_press_duration_color(self, index, timer_id_slot, color):
        """ Scheduled via cb_knob_push()'s after() timers: recolours the
        press-outline once a press-duration threshold (Bold/Long) is
        crossed while the knob is still held. Mirrors
        _set_press_duration_color() (buttons) exactly. Clears its own
        timer slot first so cb_knob_release() won't try to after_cancel()
        a job that already fired.
        """

        config = self.knobs[index]
        config[timer_id_slot] = None
        self.itemconfig(config[KNOB_PRESS_ID], outline=color)

    def cb_knob_release(self, index):
        """ See cb_knob_push(). """

        config = self.knobs[index]
        for slot in (KNOB_BOLD_TIMER_ID, KNOB_LONG_TIMER_ID):
            if config[slot] is not None:
                self.after_cancel(config[slot])
                config[slot] = None
        self.itemconfig(config[KNOB_PRESS_ID], state="hidden")
        zynthian_gui_config.zyngui.cuia_queue.put_nowait(f"zynswitch {index},R")

    def draw_button(self, row, column, button):
        """ Draw button onto canvas
        Args:
            row: Row in which to draw button
            column: Column in which to draw button
            button: Button index
        """

        try:
            config = self.buttons[button]
            label = config[0]
        except:
            return
        if self.style == "classic" and row == 5:
            # Original layout's mega-row spans the full width, ignoring
            # x_offset, to fit its 10 buttons.
            x = self.button_width * column
        else:
            x = self.x_offset + self.button_width * column
        y = self.top_margin + self.button_height * row
        tag = f"v5_button_{button}"
        config[RECT_ID] = self.create_rectangle(
            x, y,
            x+self.button_width, y+self.button_height,
            outline=zynthian_gui_config.color_bg,
            width=1,
            fill=self.bg_color,
            tags=tag
        )
        if label.startswith('_'):
            # button contains an icon/image instead of a label
            img_width = int(0.6 * self.button_width)
            img_name = label[1:]
            if img_name.endswith('.svg'):
                # convert SVG icon into PNG of appropriate size
                if cairosvg:
                    png = BytesIO()
                    cairosvg.svg2png(url=img_name, write_to=png, output_width=img_width)
                    image = Image.open(png)
                else:
                    png = img_name[:-4]+".png"
                    image = Image.open(png)
                    img_height = int(img_width * image.size[1] / image.size[0])
                    image = image.resize((img_width, img_height), Image.Resampling.LANCZOS)
            elif img_name.endswith('.png'):
                # PNG icons can be imported directly
                image = Image.open(img_name)
                img_height = int(img_width * image.size[1] / image.size[0])
                image = image.resize((img_width, img_height), Image.Resampling.LANCZOS)
            else:
                image = None
            if image:
                # store the original image for the purpose of later changes of color (useful for image icons)
                config[IMG] = image
                config[TKIMG] = ImageTk.PhotoImage(image)
                config[IMG_ID] = self.create_image(
                    x+self.button_width//2, y+self.button_height//2,
                    image=config[TKIMG],
                    tags=tag
                )
        else:
            # Button has a simple text label: either standard text
            # or an icon included in the "forkawesome" font (unicode char >= \uf000)
            if label[0] >= '\uf000':
                font_family = "forkawesome"
                font_size = int(1.5 * zynthian_gui_config.font_size)
            else:
                font_family = zynthian_gui_config.font_family
                if len(label) <= 3:
                    font_size = int(1.3 * zynthian_gui_config.font_size)
                else:
                    font_size = int(0.9 * zynthian_gui_config.font_size)
            font = tkfont.Font(family=font_family, size=font_size)

            #label = label.replace("/", "\n")
            longer_line = ""
            width = 0
            # Find longer line ...
            for line in label.split("\n"):
                w = font.measure(line)
                if (w > width):
                    width = w
                    longer_line = line
            # Reduce font until text fits the button ...
            max_width = int(0.8 * self.button_width)
            while width > max_width:
                font_size -= 1
                if font_size < 8:       # Fontsize smaller than 8 pixels is too small!!
                    break
                font = tkfont.Font(family=font_family, size=font_size)
                width = font.measure(longer_line)

            config[TXT_ID] =  self.create_text(
                x+self.button_width//2, y+self.button_height//2,
                text=label,
                font=font,
                justify=tkinter.CENTER,
                fill=self.text_color,
                tags=tag
            )
        self.tag_bind(tag, "<Button-1>", lambda e,i=button:self.cb_button_push(i))
        self.tag_bind(tag, "<ButtonRelease-1>", lambda e,i=button:self.cb_button_release(i))

    def cb_button_push(self, button):
        """ Handle button press
        Args:
            button: Index of button
        """

        if self.style in ("device", "device_cables"):
            config = self.buttons[button]
            self.itemconfig(config[RECT_ID], state="normal", outline="#F0F000")
            config[BOLD_TIMER_ID] = self.after(
                zynthian_gui_config.zynswitch_bold_us // 1000,
                lambda b=button: self._set_press_duration_color(b, BOLD_TIMER_ID, zynthian_gui_config.color_warn)
            )
            config[LONG_TIMER_ID] = self.after(
                zynthian_gui_config.zynswitch_long_us // 1000,
                lambda b=button: self._set_press_duration_color(b, LONG_TIMER_ID, zynthian_gui_config.color_error)
            )
        else:
            self.move(f"v5_button_{button}", 2, 2)
        zynthian_gui_config.zyngui.cuia_queue.put_nowait(f"zynswitch {button + 4},P")

    def _set_press_duration_color(self, button, timer_id_slot, color):
        """ Scheduled via cb_button_push()'s after() timers: recolours the
        press-outline once a press-duration threshold (Bold/Long) is
        crossed while the button is still held. Clears its own timer slot
        first so cb_button_release() won't try to after_cancel() a job
        that already fired.
        """

        config = self.buttons[button]
        config[timer_id_slot] = None
        self.itemconfig(config[RECT_ID], outline=color)

    def cb_button_release(self, button):
        """ Handle button release
        Args:
            button: Index of button
        """

        if self.style in ("device", "device_cables"):
            config = self.buttons[button]
            for slot in (BOLD_TIMER_ID, LONG_TIMER_ID):
                if config[slot] is not None:
                    self.after_cancel(config[slot])
                    config[slot] = None
            self.itemconfig(config[RECT_ID], state="hidden")
        else:
            self.move(f"v5_button_{button}", -2, -2)
        zynthian_gui_config.zyngui.cuia_queue.put_nowait(f"zynswitch {button + 4},R")

    def set_button_color(self, button, color, mode):
        """ Change color of a button according to the wsleds signal
        Args:
            button: Index of the button
            color : Color requested by the wsled system
            mode : A wanna-be abstraction (string name) of the mode/state - currently
            just derived from the requested color by the `wsleds_v5touch` "fake NeoPixel" emulator
        """

        config = self.buttons[button]
        if self.style in ("device", "device_cables"):
            # The button's own label/face is baked into the chassis render;
            # feedback here is the per-button backlight rectangle instead.
            # Dedupe on the literal colour, not "mode": most of the wsled
            # system's steady-state colours (red, yellow, ...) aren't one
            # of the 4 named modes (default/alt/active/active2), so `mode`
            # is None for them - same as this button's untouched initial
            # LED_STATE, which made the very first (and every later) call
            # look like "no change" and get silently skipped forever.
            if config[LED_STATE] == color:
                return
            config[LED_STATE] = color
            self.itemconfig(config[LED_ID], fill=color)
            return
        # don't bother with update if nothing has really changed (redrawing images causes visible blinking!)
        if config[LED_STATE] == mode:
            return
        config[LED_STATE] = mode
        # in case the color is still the original wsled integer number, convert it
        label = config[LABEL]
        if  label.startswith('_'):
            # image buttons must be recomposed to change the foreground color
            image = config[IMG]
            mask = image.convert("LA")
            bgimage = Image.new("RGBA", image.size, color)
            fgimage = Image.new("RGBA", image.size, (0, 0, 0, 0))
            composed = Image.composite(bgimage, fgimage, mask)
            tkimage = ImageTk.PhotoImage(composed)
            config[TKIMG] = tkimage
            self.itemconfig(config[IMG_ID], image=tkimage)
        else:
            # plain text labels may just change the color and possibly also its label if a special label
            # is associated with the requested mode (<=color) in the button definition
            if mode == "alt" and config[ALT_LABEL]:
                label = config[ALT_LABEL]
            else:
                label = config[LABEL]
            self.itemconfig(config[TXT_ID], text=label, fill=color)

    def apply_user_config(self):
        for i, config in enumerate(self.buttons):
            config[LABEL] = os.environ.get(f'ZYNTHIAN_TOUCH_KEYPAD_LABEL_{i+1:02d}_DEFAULT', config[LABEL])
            config[ALT_LABEL] = os.environ.get(f'ZYNTHIAN_TOUCH_KEYPAD_LABEL_{i+1:02d}_ALT', config[ALT_LABEL])
            config[ACT_LABEL] = os.environ.get(f'ZYNTHIAN_TOUCH_KEYPAD_LABEL_{i+1:02d}_ACTIVE', config[ACT_LABEL])
            config[ACT2_LABEL] = os.environ.get(f'ZYNTHIAN_TOUCH_KEYPAD_LABEL_{i+1:02d}_ACTIVE2', config[ACT2_LABEL])
