from __future__ import annotations

from utils import format_price, html_escape


def apply_title(title: str, with_bold: bool) -> str:
    return f"<b>{html_escape(title)}</b>" if with_bold else html_escape(title)


def apply_plain_paragraphs(lines: list[str]) -> str:
    return "\n\n".join(line for line in lines if line.strip())


def render_signal_text(
    *,
    symbol: str,
    side: str,
    entry_zone: tuple[float, float],
    leverage: int,
    targets: list[float],
    stop: float,
    stop_to_be_rule: str | None,
    description: str,
    with_bold: bool,
) -> str:
    title = apply_title(f"🎯 {symbol} - {side.title()}", with_bold)
    lines = [
        title,
        f"• Зона набора: {format_price(entry_zone[0])}-{format_price(entry_zone[1])}$",
        f"• Плечо: {leverage}x",
        f"• Цели: {', '.join(f'{format_price(price)}$' for price in targets)}",
        f"• Стоп: {format_price(stop)}$",
    ]
    if stop_to_be_rule:
        lines.append(f"• Стоп в БУ: {html_escape(stop_to_be_rule)}")
    lines.append("")
    lines.append(html_escape(description.strip()))
    return "\n".join(lines)


def render_news_text(events_lines: list[str], closing_line: str, with_bold: bool) -> str:
    title = apply_title("Новости на сегодня 📊", with_bold)
    sections = [title, "\n".join(events_lines)]
    if closing_line:
        sections.append(html_escape(closing_line.strip()))
    return "\n\n".join(section for section in sections if section.strip())


def render_simple_text(title: str | None, body: str, with_bold: bool) -> str:
    if title:
        return apply_plain_paragraphs([apply_title(title, with_bold), html_escape(body.strip())])
    return html_escape(body.strip())
