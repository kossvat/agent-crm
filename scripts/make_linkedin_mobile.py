"""Generate LinkedIn carousel PDF from mobile screenshots."""
from PIL import Image, ImageDraw, ImageFont
import os

MOBILE_DIR = os.path.expanduser("~/projects/agent-crm/screenshots/mobile")
OUTPUT = os.path.expanduser("~/projects/agent-crm/AgentCRM-LinkedIn-Mobile.pdf")

W, H = 1080, 1350
BG = (15, 15, 20)
ACCENT = (124, 58, 237)
WHITE = (255, 255, 255)
GRAY = (170, 170, 180)
RED = (239, 68, 68)

def get_font(size, bold=False):
    p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(p):
        return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def add_footer(draw):
    draw.rectangle([0, H-46, W, H], fill=(20, 20, 28))
    draw.rectangle([0, H-46, W, H-44], fill=ACCENT)
    draw.text((W//2, H-22), "AgentCRM", font=get_font(16, bold=True), fill=GRAY, anchor="mm")

def make_text_slide(lines_top, lines_mid, lines_bot=None, accent_text=None):
    """Generic text slide with centered content."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    
    # Calculate total height for centering
    y = H // 2 - 200
    
    for text, font_size, bold, color in lines_top:
        f = get_font(font_size, bold)
        draw.text((W//2, y), text, font=f, fill=color, anchor="mt")
        y += font_size + 16
    
    if accent_text:
        y += 20
        f = get_font(58, bold=True)
        draw.text((W//2, y), accent_text, font=f, fill=RED, anchor="mt")
        y += 80
    
    y += 10
    for text, font_size, bold, color in lines_mid:
        f = get_font(font_size, bold)
        draw.text((W//2, y), text, font=f, fill=color, anchor="mt")
        y += font_size + 14
    
    if lines_bot:
        y += 30
        for text, font_size, bold, color in lines_bot:
            f = get_font(font_size, bold)
            draw.text((W//2, y), text, font=f, fill=color, anchor="mt")
            y += font_size + 12
    
    add_footer(draw)
    return img

def make_phone_slide(title, subtitle, screenshot_path, caption=None):
    """Slide with mobile screenshot in phone-like frame."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    
    # Title
    y = 40
    draw.text((W//2, y), title, font=get_font(30, bold=True), fill=WHITE, anchor="mt")
    y += 42
    if subtitle:
        draw.text((W//2, y), subtitle, font=get_font(18), fill=GRAY, anchor="mt")
    y += 30
    
    # Load and place screenshot
    if os.path.exists(screenshot_path):
        scr = Image.open(screenshot_path)
        # Phone frame dimensions - make it tall
        max_h = 1100
        max_w = 520
        ratio = min(max_w / scr.width, max_h / scr.height)
        new_w = int(scr.width * ratio)
        new_h = int(scr.height * ratio)
        scr = scr.resize((new_w, new_h), Image.LANCZOS)
        
        sx = (W - new_w) // 2
        
        # Phone frame (rounded rect)
        pad = 8
        draw.rounded_rectangle(
            [sx - pad, y - pad, sx + new_w + pad, y + new_h + pad],
            radius=20, outline=(60, 60, 70), width=3
        )
        img.paste(scr, (sx, y))
        y += new_h + 15
    
    # Caption below
    if caption and y < H - 70:
        draw.text((W//2, y), caption, font=get_font(17), fill=GRAY, anchor="mt")
    
    add_footer(draw)
    return img

def make_dual_phone_slide(title, subtitle, left_path, right_path, left_label="", right_label=""):
    """Slide with two phone screenshots side by side."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    
    y = 40
    draw.text((W//2, y), title, font=get_font(30, bold=True), fill=WHITE, anchor="mt")
    y += 42
    if subtitle:
        draw.text((W//2, y), subtitle, font=get_font(18), fill=GRAY, anchor="mt")
    y += 35
    
    max_h = 1050
    max_w = 460
    
    for i, (path, label) in enumerate([(left_path, left_label), (right_path, right_label)]):
        if not os.path.exists(path):
            continue
        scr = Image.open(path)
        ratio = min(max_w / scr.width, max_h / scr.height)
        new_w = int(scr.width * ratio)
        new_h = int(scr.height * ratio)
        scr = scr.resize((new_w, new_h), Image.LANCZOS)
        
        # Left or right
        if i == 0:
            sx = (W // 2 - new_w) // 2 + 10
        else:
            sx = W // 2 + (W // 2 - new_w) // 2 - 10
        
        pad = 5
        draw.rounded_rectangle(
            [sx - pad, y - pad, sx + new_w + pad, y + new_h + pad],
            radius=14, outline=(60, 60, 70), width=2
        )
        img.paste(scr, (sx, y))
        
        if label:
            draw.text((sx + new_w // 2, y + new_h + 12), label, 
                      font=get_font(15, bold=True), fill=ACCENT, anchor="mt")
    
    add_footer(draw)
    return img

# ---- BUILD SLIDES ----
slides = []

# 1. Cover
slides.append(make_text_slide(
    [("AgentCRM", 54, True, WHITE),
     ("", 10, False, BG),
     ("A CRM for AI agent teams", 28, False, ACCENT)],
    [("Manage tasks, track costs, get alerts.", 22, False, GRAY),
     ("All from Telegram. Built in under a week.", 22, False, GRAY),
     ("", 20, False, BG),
     ("Real screenshots from my phone  -->", 20, False, ACCENT)],
))

# 2. Problem
slides.append(make_text_slide(
    [("The Problem", 42, True, WHITE)],
    [("One of my agents burned", 24, False, GRAY)],
    lines_bot=[
        ("in a single night.", 24, False, GRAY),
        ("", 16, False, BG),
        ("No visibility into costs.", 22, False, GRAY),
        ("No way to stop everything at once.", 22, False, GRAY),
        ("Tasks scattered across chats.", 22, False, GRAY),
        ("Managing 4 AI agents felt like chaos.", 22, False, GRAY),
        ("", 16, False, BG),
        ("So I built AgentCRM.", 28, True, ACCENT),
    ],
    accent_text="$100"
))

# 3. Dashboard
slides.append(make_phone_slide(
    "Dashboard",
    "Budget, agents, costs — all at a glance",
    os.path.join(MOBILE_DIR, "01-dashboard-top.jpg"),
))

# 4. Spending Analytics  
slides.append(make_phone_slide(
    "Spending Analytics",
    "Hourly + weekly charts, per-session breakdown",
    os.path.join(MOBILE_DIR, "02-dashboard-bottom.jpg"),
))

# 5. Task Board — single view (In Progress is more interesting)
slides.append(make_phone_slide(
    "Task Board",
    "Kanban with filters by agent and category",
    os.path.join(MOBILE_DIR, "04-board-progress.jpg"),
))

# 6. Agents
slides.append(make_phone_slide(
    "Agent Panel",
    "Switch models, track status and daily cost per agent",
    os.path.join(MOBILE_DIR, "06-agents.jpg"),
))

# 7. Crons
slides.append(make_phone_slide(
    "Automated Jobs",
    "Schedule tasks — toggle on/off with one tap",
    os.path.join(MOBILE_DIR, "07-crons.jpg"),
))

# 8. Alerts + Kill Switch
slides.append(make_phone_slide(
    "Alerts + Kill Switch",
    "Real-time monitoring. Stop everything in one tap.",
    os.path.join(MOBILE_DIR, "10-alerts-full.jpg"),
))

# 9. Journal
slides.append(make_phone_slide(
    "Agent Journal",
    "Daily logs — what each agent built, with commits and costs",
    os.path.join(MOBILE_DIR, "09-journal.jpg"),
))

# 10. CTA
slides.append(make_text_slide(
    [("Built by AI agents.", 38, True, WHITE),
     ("For AI agents.", 38, True, WHITE),
     ("In under a week.", 38, True, WHITE)],
    [("", 20, False, BG),
     ("FastAPI + SQLite + Telegram Mini App", 20, False, GRAY),
     ("Zero external SaaS", 20, False, GRAY),
     ("Open source \u2014 coming soon", 20, False, GRAY)],
    lines_bot=[
        ("", 20, False, BG),
        ("Interested? Comment 'AGENT'", 24, True, ACCENT),
        ("", 14, False, BG),
        ("@kos_svat", 20, False, GRAY),
    ]
))

# Save
slides[0].save(OUTPUT, save_all=True, append_images=slides[1:], resolution=150)
print(f"PDF saved: {OUTPUT} ({len(slides)} slides)")

for i, s in enumerate(slides):
    s.save(f"/home/caramel/.openclaw/workspace/mobile-{i+1:02d}.png")
print("PNGs saved")
