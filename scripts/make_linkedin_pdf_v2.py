"""Generate LinkedIn carousel PDF v2 — improved layout."""
from PIL import Image, ImageDraw, ImageFont
import os

SCREENSHOTS_DIR = os.path.expanduser("~/projects/agent-crm/screenshots")
OUTPUT = os.path.expanduser("~/projects/agent-crm/AgentCRM-LinkedIn.pdf")

W, H = 1080, 1350
BG = (15, 15, 20)
ACCENT = (124, 58, 237)  # purple
WHITE = (255, 255, 255)
GRAY = (170, 170, 180)
DARK_GRAY = (40, 40, 50)

def get_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def add_brand_footer(draw):
    """Add AgentCRM brand to bottom of every slide."""
    draw.rectangle([0, H-50, W, H], fill=(20, 20, 28))
    draw.rectangle([0, H-50, W, H-48], fill=ACCENT)
    font = get_font(18, bold=True)
    draw.text((W//2, H-25), "AgentCRM", font=font, fill=GRAY, anchor="mm")

def make_cover():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 8], fill=ACCENT)
    
    # Centered vertically
    cy = H // 2 - 120
    
    # Emoji
    draw.text((W//2, cy - 60), "[AI]", font=get_font(72), fill=WHITE, anchor="mt")
    
    # Title
    font_big = get_font(58, bold=True)
    draw.text((W//2, cy + 50), "AgentCRM", font=font_big, fill=WHITE, anchor="mt")
    
    # Tagline
    font_tag = get_font(30)
    draw.text((W//2, cy + 130), "A CRM for AI agent teams.", font=font_tag, fill=ACCENT, anchor="mt")
    
    # Description
    font_desc = get_font(24)
    lines = [
        "Manage tasks, track costs, get alerts.",
        "All from your phone. Built in under a week.",
    ]
    y = cy + 200
    for line in lines:
        draw.text((W//2, y), line, font=font_desc, fill=GRAY, anchor="mt")
        y += 40
    
    # Swipe hint
    font_small = get_font(22)
    draw.text((W//2, H - 120), "Swipe to explore →", font=font_small, fill=ACCENT, anchor="mt")
    
    add_brand_footer(draw)
    return img

def make_problem():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 8], fill=ACCENT)
    
    font_title = get_font(42, bold=True)
    font_body = get_font(26)
    font_big_num = get_font(64, bold=True)
    
    y = 100
    draw.text((W//2, y), "The Problem", font=font_title, fill=WHITE, anchor="mt")
    
    y = 220
    # Big number callout
    draw.text((W//2, y), "$100", font=font_big_num, fill=(239, 68, 68), anchor="mt")
    y += 85
    draw.text((W//2, y), "burned by one agent in one night.", font=font_body, fill=GRAY, anchor="mt")
    y += 50
    draw.text((W//2, y), "I had no idea until it was too late.", font=font_body, fill=GRAY, anchor="mt")
    
    # Pain points
    y = 520
    pains = [
        "X  No visibility into agent costs",
        "X  Tasks scattered across chat messages",
        "X  No alerts when spending spikes",
        "X  No way to stop everything at once",
        "X  Managing AI felt like chaos",
    ]
    for pain in pains:
        draw.text((120, y), pain, font=get_font(24), fill=GRAY)
        y += 55
    
    # Transition
    y += 40
    draw.text((W//2, y), "So I built AgentCRM.", font=get_font(30, bold=True), fill=ACCENT, anchor="mt")
    
    add_brand_footer(draw)
    return img

def make_screenshot_slide(title, subtitle, screenshot_path, bullets):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    
    font_title = get_font(34, bold=True)
    font_sub = get_font(20)
    font_bullet = get_font(20)
    
    # Title + subtitle at top
    y = 50
    draw.text((W//2, y), title, font=font_title, fill=WHITE, anchor="mt")
    y += 48
    draw.text((W//2, y), subtitle, font=font_sub, fill=GRAY, anchor="mt")
    y += 45
    
    # Screenshot — make it bigger
    if os.path.exists(screenshot_path):
        scr = Image.open(screenshot_path)
        max_w = W - 60
        max_h = 820  # bigger
        ratio = min(max_w / scr.width, max_h / scr.height)
        new_w = int(scr.width * ratio)
        new_h = int(scr.height * ratio)
        scr = scr.resize((new_w, new_h), Image.LANCZOS)
        
        sx = (W - new_w) // 2
        # Border
        draw.rounded_rectangle([sx-3, y-3, sx+new_w+3, y+new_h+3], radius=8, outline=DARK_GRAY, width=2)
        img.paste(scr, (sx, y))
        y += new_h + 20
    
    # Bullets below screenshot
    for bp in bullets:
        draw.text((80, y), f"→  {bp}", font=font_bullet, fill=GRAY)
        y += 32
    
    add_brand_footer(draw)
    return img

def make_cta():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 8], fill=ACCENT)  # purple, not green
    
    font_big = get_font(40, bold=True)
    font_sub = get_font(26)
    font_btn = get_font(24, bold=True)
    font_small = get_font(20)
    
    # Centered
    cy = H // 2 - 150
    
    lines = [
        "Built by AI agents.",
        "For AI agents.",
        "In under a week.",
    ]
    for line in lines:
        draw.text((W//2, cy), line, font=font_big, fill=WHITE, anchor="mt")
        cy += 58
    
    cy += 50
    tech = [
        "FastAPI + SQLite + Telegram Mini App",
        "Zero external SaaS dependencies",
        "Open source — coming soon",
    ]
    for t in tech:
        draw.text((W//2, cy), t, font=font_small, fill=GRAY, anchor="mt")
        cy += 35
    
    # CTA button
    cy += 60
    btn_w, btn_h = 500, 60
    bx = (W - btn_w) // 2
    draw.rounded_rectangle([bx, cy, bx + btn_w, cy + btn_h], radius=30, fill=ACCENT)
    draw.text((W//2, cy + 30), "Comment 'AGENT' for early access", font=font_btn, fill=WHITE, anchor="mm")
    
    cy += 100
    draw.text((W//2, cy), "@kos_svat", font=font_small, fill=GRAY, anchor="mm")
    
    add_brand_footer(draw)
    return img

# Build slides
slides = [
    make_cover(),
    make_problem(),
    make_screenshot_slide(
        ">> Dashboard",
        "Real-time overview of your entire AI team",
        os.path.join(SCREENSHOTS_DIR, "01-dashboard.png"),
        ["Budget tracking (daily / weekly / monthly)",
         "Agent status & cost breakdown at a glance",
         "Kill Switch — shut down all agents in one tap"]
    ),
    make_screenshot_slide(
        ">> Spending Analytics",
        "Track costs hourly and weekly — catch spikes early",
        os.path.join(SCREENSHOTS_DIR, "01b-charts.png"),
        ["Hourly & weekly spend graphs",
         "Per-session cost details",
         "Active session monitoring"]
    ),
    make_screenshot_slide(
        ">> Task Board",
        "Kanban-style task management for your AI team",
        os.path.join(SCREENSHOTS_DIR, "02-board.png"),
        ["TODO → In Progress → Done",
         "Filter by agent or category",
         "Assign tasks with priorities"]
    ),
    make_screenshot_slide(
        ">> Agent Panel",
        "See every agent's role, model, status & daily cost",
        os.path.join(SCREENSHOTS_DIR, "03-agents.png"),
        ["Switch models (Opus / Sonnet / Haiku)",
         "Monitor active vs idle status",
         "Track daily API cost per agent"]
    ),
    make_screenshot_slide(
        ">> Automated Jobs",
        "Schedule recurring tasks — toggle with one tap",
        os.path.join(SCREENSHOTS_DIR, "04-crons.png"),
        ["Trend scans, drafts, market reports",
         "Each job assigned to a specific agent",
         "Enable/disable instantly"]
    ),
    make_screenshot_slide(
        ">> Smart Alerts",
        "Auto-alerts when any agent spikes above budget",
        os.path.join(SCREENSHOTS_DIR, "05-alerts.png"),
        ["Real-time Telegram notifications",
         "One-tap Fix — pause all + reset sessions",
         "Kill Switch to stop everything instantly"]
    ),
    make_cta(),
]

slides[0].save(OUTPUT, save_all=True, append_images=slides[1:], resolution=150)
print(f"✅ PDF saved: {OUTPUT} ({len(slides)} slides)")

# Save individual PNGs for preview
for i, s in enumerate(slides):
    s.save(f"/home/caramel/.openclaw/workspace/slide-{i+1:02d}.png")
print("✅ Individual PNGs saved to workspace")
