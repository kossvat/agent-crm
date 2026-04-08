"""Generate LinkedIn carousel PDF from CRM screenshots."""
from PIL import Image, ImageDraw, ImageFont
import os

SCREENSHOTS_DIR = os.path.expanduser("~/projects/agent-crm/screenshots")
OUTPUT = os.path.expanduser("~/projects/agent-crm/AgentCRM-LinkedIn.pdf")

# LinkedIn carousel optimal: 1080x1080 or 1080x1350
W, H = 1080, 1350
BG = (15, 15, 20)  # dark background
ACCENT = (124, 58, 237)  # purple accent
WHITE = (255, 255, 255)
GRAY = (160, 160, 170)
GREEN = (16, 185, 129)

def get_font(size, bold=False):
    """Try to get a decent font, fall back to default."""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def make_slide(title, subtitle, screenshot_path=None, bullet_points=None, is_cover=False, is_cta=False):
    """Create a single slide."""
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    
    y = 80
    
    if is_cover:
        # Cover slide
        font_big = get_font(64, bold=True)
        font_sub = get_font(28)
        font_small = get_font(22)
        
        # Purple accent bar
        draw.rectangle([0, 0, W, 8], fill=ACCENT)
        
        y = 200
        draw.text((W//2, y), "🤖", font=get_font(80), fill=WHITE, anchor="mt")
        y += 120
        
        # Title
        for line in title.split("\n"):
            bbox = draw.textbbox((0, 0), line, font=font_big)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, y), line, font=font_big, fill=WHITE)
            y += 80
        
        y += 40
        for line in subtitle.split("\n"):
            bbox = draw.textbbox((0, 0), line, font=font_sub)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, y), line, font=font_sub, fill=GRAY)
            y += 45
        
        # Bottom
        draw.text((W//2, H - 100), "Swipe →", font=font_small, fill=ACCENT, anchor="mt")
        return img
    
    if is_cta:
        font_big = get_font(48, bold=True)
        font_sub = get_font(28)
        font_small = get_font(24)
        
        draw.rectangle([0, 0, W, 8], fill=GREEN)
        
        y = 300
        for line in title.split("\n"):
            bbox = draw.textbbox((0, 0), line, font=font_big)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, y), line, font=font_big, fill=WHITE)
            y += 65
        
        y += 60
        for line in subtitle.split("\n"):
            bbox = draw.textbbox((0, 0), line, font=font_sub)
            tw = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, y), line, font=font_sub, fill=GRAY)
            y += 45
        
        # CTA button shape
        btn_w, btn_h = 400, 60
        bx = (W - btn_w) // 2
        by = H - 250
        draw.rounded_rectangle([bx, by, bx + btn_w, by + btn_h], radius=30, fill=ACCENT)
        draw.text((W//2, by + 30), "Drop a comment 👇", font=font_small, fill=WHITE, anchor="mm")
        
        return img
    
    # Regular slide with screenshot
    font_title = get_font(36, bold=True)
    font_sub = get_font(22)
    font_bullet = get_font(20)
    
    # Purple top bar
    draw.rectangle([0, 0, W, 6], fill=ACCENT)
    
    # Title
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, y), title, font=font_title, fill=WHITE)
    y += 55
    
    # Subtitle
    if subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y), subtitle, font=font_sub, fill=GRAY)
    y += 50
    
    # Screenshot
    if screenshot_path and os.path.exists(screenshot_path):
        scr = Image.open(screenshot_path)
        # Scale to fit within padding
        max_w = W - 80
        max_h = 700
        ratio = min(max_w / scr.width, max_h / scr.height)
        new_w = int(scr.width * ratio)
        new_h = int(scr.height * ratio)
        scr = scr.resize((new_w, new_h), Image.LANCZOS)
        
        # Center screenshot
        sx = (W - new_w) // 2
        # Add subtle border
        draw.rectangle([sx-2, y-2, sx+new_w+2, y+new_h+2], outline=(40, 40, 50), width=2)
        img.paste(scr, (sx, y))
        y += new_h + 30
    
    # Bullet points
    if bullet_points:
        for bp in bullet_points:
            draw.text((80, y), f"→  {bp}", font=font_bullet, fill=GRAY)
            y += 35
    
    return img

# Build slides
slides = []

# 1. Cover
slides.append(make_slide(
    "AgentCRM",
    "A CRM for AI agent teams.\nManage tasks, costs & alerts\nfrom your phone.",
    is_cover=True
))

# 2. Problem
slides.append(make_slide(
    "The Problem",
    "Running AI agents without visibility is expensive.",
    bullet_points=[
        "My AI engineer burned $100 in one night",
        "No way to see which agent costs what",
        "Tasks scattered across chat messages",
        "No alerts when spending spikes",
        "Managing 4 agents felt like chaos"
    ]
))

# 3. Dashboard
slides.append(make_slide(
    "📊 Dashboard",
    "Real-time overview of your entire AI team",
    screenshot_path=os.path.join(SCREENSHOTS_DIR, "01-dashboard.png"),
    bullet_points=[
        "Budget tracking (daily / weekly / monthly)",
        "Agent status at a glance",
        "Cost breakdown per agent",
        "One-tap Stop / Resume controls"
    ]
))

# 4. Dashboard charts
slides.append(make_slide(
    "📈 Spending Analytics",
    "Track costs hourly and weekly — catch spikes early",
    screenshot_path=os.path.join(SCREENSHOTS_DIR, "01b-charts.png"),
    bullet_points=[
        "Hourly spend graph (green)",
        "Weekly trend (purple)",
        "Active sessions with cost details"
    ]
))

# 5. Board
slides.append(make_slide(
    "📋 Task Board",
    "Kanban-style task management for your AI team",
    screenshot_path=os.path.join(SCREENSHOTS_DIR, "02-board.png"),
    bullet_points=[
        "TODO → In Progress → Done",
        "Filter by agent or category",
        "Assign tasks, set priorities"
    ]
))

# 6. Agents
slides.append(make_slide(
    "🤖 Agent Panel",
    "See every agent's role, model, status & daily cost",
    screenshot_path=os.path.join(SCREENSHOTS_DIR, "03-agents.png"),
    bullet_points=[
        "Switch models (Opus / Sonnet / Haiku)",
        "Monitor active vs idle status",
        "Track daily API cost per agent"
    ]
))

# 7. Crons
slides.append(make_slide(
    "⏰ Automated Jobs",
    "Schedule recurring tasks — enable/disable with one tap",
    screenshot_path=os.path.join(SCREENSHOTS_DIR, "04-crons.png"),
    bullet_points=[
        "Trend scans, tweet drafts, market reports",
        "Toggle on/off instantly",
        "Each job assigned to a specific agent"
    ]
))

# 8. Alerts
slides.append(make_slide(
    "🚨 Smart Alerts",
    "Auto-alerts when any agent spikes above budget",
    screenshot_path=os.path.join(SCREENSHOTS_DIR, "05-alerts.png"),
    bullet_points=[
        "Real-time Telegram notifications",
        "One-tap Fix button (pause + reset)",
        "Never get surprised by a $100 day again"
    ]
))

# 9. CTA
slides.append(make_slide(
    "Built by AI agents.\nFor AI agents.\nIn under a week.",
    "FastAPI + SQLite + Telegram Mini App\nZero external SaaS. Open source soon.\n\nInterested?",
    is_cta=True
))

# Save as PDF
slides[0].save(OUTPUT, save_all=True, append_images=slides[1:], resolution=150)
print(f"✅ PDF saved: {OUTPUT}")
print(f"   {len(slides)} slides")
