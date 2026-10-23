"""Render a 1200x630 "judge reliability card" as an SVG (and a PNG when a converter
is installed). The card states what was measured about this judge, this prompt and
this data: a one-word risk level, the probe percentages with their 95% intervals, the
sample size and date, and the command to reproduce it. No claim the numbers do not
support.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

W, H = 1200, 630

# dataviz reference tokens (dark surface) + fixed status palette.
SURFACE = "#1a1a19"
PLANE = "#0d0d0d"
INK = "#f0efec"
INK2 = "#c3c2b7"
MUTED = "#898781"
TRACK = "#2c2c2a"
STATUS = {"good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b"}
RISK_WORD = {"good": "LOW", "warning": "MEDIUM", "critical": "HIGH"}


@dataclass
class Meter:
    label: str  # what the number means, in words
    pct: float  # 0..1, the bar length
    status: str  # good | warning | critical
    value_text: str  # the number as shown (e.g. "71%")
    ci_text: str  # e.g. "CI 60-80%" or "" when none


@dataclass
class Card:
    model: str
    risk: str  # good | warning | critical
    headline: str  # one-sentence verdict
    meters: list[Meter]
    n_text: str  # e.g. "n = 30 pairs, 330 calls"
    date: str
    source: str
    reproduce: str  # the command


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _text(
    x: float,
    y: float,
    s: str,
    size: int,
    fill: str,
    weight: str = "400",
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
        f'font-weight="{weight}" text-anchor="{anchor}" '
        f'font-family="system-ui,-apple-system,Segoe UI,sans-serif">{_esc(s)}</text>'
    )


def render_svg(card: Card) -> str:
    accent = STATUS[card.risk]
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img">',
        f'<rect width="{W}" height="{H}" fill="{PLANE}"/>',
        f'<rect x="24" y="24" width="{W - 48}" height="{H - 48}" rx="20" fill="{SURFACE}" '
        f'stroke="rgba(255,255,255,0.10)"/>',
        f'<rect x="24" y="24" width="10" height="{H - 48}" rx="5" fill="{accent}"/>',
    ]
    pad = 72
    parts.append(_text(pad, 96, "LLM JUDGE RELIABILITY CARD", 22, MUTED, "700"))
    model = card.model if len(card.model) <= 42 else card.model[:41] + "…"
    parts.append(_text(pad, 152, model, 44, INK, "700"))

    # risk pill
    word = RISK_WORD[card.risk]
    pill_label = f"Coin flip risk: {word}"
    pill_w = 34 + len(pill_label) * 15
    parts.append(
        f'<rect x="{pad}" y="178" width="{pill_w}" height="46" rx="23" fill="{accent}"/>'
    )
    pill_ink = "#111111" if card.risk == "warning" else "#ffffff"
    parts.append(_text(pad + 18, 209, pill_label, 24, pill_ink, "700"))

    # one-sentence headline, wrapped
    y = 272
    for line in _wrap(card.headline, 78)[:2]:
        parts.append(_text(pad, y, line, 21, INK2, "400"))
        y += 30

    # meters
    y = 348
    bar_x = pad + 300
    bar_w = W - pad - bar_x - 36
    for m in card.meters:
        parts.append(_text(pad, y + 6, m.label, 20, INK2, "500"))
        parts.append(_text(pad + 288, y + 6, m.value_text, 22, INK, "700", anchor="end"))
        parts.append(
            f'<rect x="{bar_x}" y="{y - 14}" width="{bar_w}" height="20" rx="10" '
            f'fill="{TRACK}"/>'
        )
        fill_w = max(6.0, min(1.0, m.pct) * bar_w)
        parts.append(
            f'<rect x="{bar_x}" y="{y - 14}" width="{fill_w:.1f}" height="20" rx="10" '
            f'fill="{STATUS[m.status]}"/>'
        )
        if m.ci_text:
            parts.append(
                _text(bar_x + bar_w, y + 28, m.ci_text, 15, MUTED, "400", anchor="end")
            )
        y += 62

    # footer
    fy = H - 56
    parts.append(
        f'<line x1="{pad}" y1="{fy - 30}" x2="{W - pad}" y2="{fy - 30}" stroke="{TRACK}"/>'
    )
    footer = f"{card.n_text}  ·  {card.date}  ·  {card.source}"
    parts.append(_text(pad, fy, footer, 15, MUTED, "400"))
    parts.append(_text(pad, fy + 24, _esc_cmd(card.reproduce), 16, INK2, "600"))
    parts.append("</svg>")
    return "\n".join(parts)


def _esc_cmd(s: str) -> str:
    return s


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def write_card(card: Card, svg_path: str | Path) -> dict[str, str]:
    """Write the SVG, and a PNG too if a converter is available. Returns written paths."""
    svg_path = Path(svg_path)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg = render_svg(card)
    svg_path.write_text(svg, encoding="utf-8")
    out = {"svg": str(svg_path)}
    png = _try_png(svg, svg_path.with_suffix(".png"))
    if png:
        out["png"] = png
    return out


def _try_png(svg: str, png_path: Path) -> str | None:
    try:
        import cairosvg  # type: ignore
    except Exception:
        return None
    try:
        cairosvg.svg2png(
            bytestring=svg.encode(), write_to=str(png_path), output_width=W, output_height=H
        )
    except Exception:
        return None
    return str(png_path)
