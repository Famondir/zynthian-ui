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
V5_LED_RADIUS = 8

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
            self.draw_chassis_device()

        self.buttons = [
            # default label, alt label, rectangle id, text id, image id, image, tk image, led state, led id
            ["OPT\nADMIN", None] + [None] * 9,             #0 OPT
            ["MIX\nLEVEL", None] + [None] * 9,             #1 MIX
            ["CTRL\nPRESET", None] + [None] * 9,           #2 CTRL
            ["ZS3\nSHOT", None] + [None] * 9,              #3 ZS3
            ["ALT\nHELP", None] + [None] * 9,                    #4 ALT
            ["_icons/metronome.svg", None] + [None] * 9,   #5 METRO
            ["PAD\nSTEP", None] + [None] * 9,              #6 PAD
            ["F1", "F5"] + [None] * 9,                     #7 F1
            ["\uf111", None] + [None] * 9,                 #8 RECORD
            ["\uf04d", None] + [None] * 9,                 #9 STOP
            ["\uf04b", None] + [None] * 9,                 #10 PLAY
            ["F2", "F6"] + [None] * 9,                     #11 F2
            ["BACK\nNO", None] + [None] * 9,               #12 BACK
            ["\uf077", None] + [None] * 9,                 #13 UP
            ["SEL\nYES", None] + [None] * 9,               #14 SEL
            ["F3", "F7"] + [None] * 9,                     #15 F3
            ["\uf053", None] + [None] * 9,                 #16 LEFT
            ["\uf078", None] + [None] * 9,                 #17 DOWN
            ["\uf054", None] + [None] * 9,                 #18 RIGHT
            ["F4", "F8"] + [None] * 9                      #19 F4
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

        draw_fn = self.draw_button_device if self.style in ("device", "device_cables") else self.draw_button
        for row, row_data in enumerate(layout):
            for column, button in enumerate(row_data):
                draw_fn(row, column, button)

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

    def draw_chassis_device(self):
        """ Draw the official V5 mockup render (from zynthian-webconf's
        mockup player - see the V5_* constants and design.md) as the
        background, at (0, cable_margin) so device_cables has room above it
        for connection cables. The image already has the button
        labels/legends and port icons baked in - we only overlay invisible
        clickable hit-areas (draw_button_device) and per-button backlight
        glow circles on top of it.
        """

        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")
        image_path = os.path.join(icons_dir, V5_IMAGE_PATH)
        self.chassis_image = Image.open(image_path)
        self.chassis_tkimage = ImageTk.PhotoImage(self.chassis_image)

        # The render's background/silhouette margin AND some overlay icons
        # (e.g. the panic/all-notes-off "!" button) are transparent cutouts
        # meant to show through to the page background - white in the
        # original zynthian-webconf mockup player. Our canvas defaults to a
        # black background, which turned those cutouts solid black (an
        # invisible "!" glyph, a black halo around the device). A white
        # backing rectangle, exactly the image's size, restores the
        # intended look regardless of our own bg colour elsewhere on this
        # canvas (e.g. device_cables' cable-graphics strip stays dark).
        w, h = V5_IMAGE_SIZE
        self.create_rectangle(0, self.cable_margin, w, self.cable_margin + h,
                               fill="#ffffff", outline="", tags="v5_chassis")
        self.create_image(0, self.cable_margin, anchor="nw", image=self.chassis_tkimage, tags="v5_chassis")

        if self.cable_margin:
            self.create_line(0, self.cable_margin, V5_IMAGE_SIZE[0], self.cable_margin,
                              fill=self.border_color, width=2, tags="v5_chassis")

    def draw_connections(self):
        """ "device_cables" style: draw a labelled cable line coming down
        from outside the top edge for every audio capture port that is
        actually present, so what's physically plugged into this machine
        is visible at a glance instead of buried in the Audio Input screen.
        """

        if not self.cable_margin:
            return
        try:
            import zynautoconnect
            ports = zynautoconnect.get_audio_capture_ports()
        except Exception as e:
            logging.warning(f"Can't read capture ports for connection display => {e}")
            ports = []

        max_slots = 6
        slot_width = V5_IMAGE_SIZE[0] // max_slots
        for i, scp in enumerate(ports[:max_slots]):
            cx = slot_width * i + slot_width // 2
            label = scp.aliases[0] if scp.aliases else scp.name
            line_id = self.create_line(cx, 0, cx, self.cable_margin - 2,
                                        fill=zynthian_gui_config.color_hl, width=3,
                                        tags="v5_connections")
            plug_id = self.create_oval(cx - 5, self.cable_margin - 10, cx + 5, self.cable_margin,
                                        fill=zynthian_gui_config.color_hl, outline="",
                                        tags="v5_connections")
            text_id = self.create_text(cx, self.cable_margin // 2, text=label,
                                        fill=self.text_color, font=(zynthian_gui_config.font_family, 9),
                                        tags="v5_connections")
            self.connection_slots.append((line_id, plug_id, text_id))

    def refresh_connections(self):
        """ Periodically redraw the connection cables so unplugging/plugging
        a device (or the accordion powering on later) is reflected live. """

        self.delete("v5_connections")
        self.connection_slots = []
        self.draw_connections()
        self.after(3000, self.refresh_connections)

    def draw_button_device(self, row, column, button):
        """ "device"/"device_cables" style: the button's face/label is
        already part of the chassis render, so this only adds an invisible
        clickable hit-area (a fully transparent image - Tkinter hit-tests
        images by their bounding box regardless of pixel transparency,
        unlike an unfilled rectangle, which only hit-tests its outline) plus
        a per-button backlight glow circle for LED-style feedback.
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

        lx = V5_LED_GROUP[0] + V5_BUTTON_COLS[column]
        ly = self.cable_margin + V5_LED_GROUP[1] + V5_BUTTON_ROWS[row]
        r = V5_LED_RADIUS
        config[LED_ID] = self.create_oval(lx - r, ly - r, lx + r, ly + r,
                                           fill="#505050", outline="", tags=tag)

        hit_image = ImageTk.PhotoImage(Image.new("RGBA", (w, h), (0, 0, 0, 0)))
        config[TKIMG] = hit_image  # keep a reference or Tk garbage-collects it
        config[IMG_ID] = self.create_image(x, y, anchor="nw", image=hit_image, tags=tag)

        config[RECT_ID] = self.create_rectangle(
            x, y, x + w, y + h,
            outline="#F0F000", width=4, state="hidden", tags=tag
        )

        self.tag_bind(tag, "<Button-1>", lambda e, i=button: self.cb_button_push(i))
        self.tag_bind(tag, "<ButtonRelease-1>", lambda e, i=button: self.cb_button_release(i))

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
            self.itemconfig(self.buttons[button][RECT_ID], state="normal")
        else:
            self.move(f"v5_button_{button}", 2, 2)
        zynthian_gui_config.zyngui.cuia_queue.put_nowait(f"zynswitch {button + 4},P")

    def cb_button_release(self, button):
        """ Handle button release
        Args:
            button: Index of button
        """

        if self.style in ("device", "device_cables"):
            self.itemconfig(self.buttons[button][RECT_ID], state="hidden")
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
        # don't bother with update if nothing has really changed (redrawing images causes visible blinking!)
        if config[LED_STATE] == mode:
            return
        config[LED_STATE] = mode
        if self.style in ("device", "device_cables"):
            # The button's own label/face is baked into the chassis render;
            # feedback here is the per-button backlight glow circle instead.
            self.itemconfig(config[LED_ID], fill=color if mode else "#505050")
            return
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
