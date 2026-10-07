import re
import sys

def md_to_wp_html(md_text, insert_after_paragraph_index, figure_html):
    lines = [l.rstrip() for l in md_text.strip().split('\n')]
    blocks = []
    buf = []
    for line in lines:
        if line.strip() == '':
            if buf:
                blocks.append('\n'.join(buf))
                buf = []
        else:
            buf.append(line)
    if buf:
        blocks.append('\n'.join(buf))

    def bold(text):
        return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    title = None
    if blocks and blocks[0].startswith('## '):
        title = blocks[0][3:].strip().replace('**', '')
        blocks = blocks[1:]

    html_parts = []
    paragraph_count = 0
    for block in blocks:
        if block.startswith('### '):
            text = block[4:].strip()
            text = text.replace('**', '')
            html_parts.append(f'<h3 class="wp-block-heading">{text}</h3>')
        elif block.startswith('## '):
            text = block[3:].strip()
            text = text.replace('**', '')
            html_parts.append(f'<h2 class="wp-block-heading">{text}</h2>')
        else:
            html_parts.append(f'<p class="wp-block-paragraph">{bold(block)}</p>')
            paragraph_count += 1
            if paragraph_count == insert_after_paragraph_index:
                html_parts.append(figure_html)

    return title, '\n\n\n\n'.join(html_parts)


def figure(url, width, height, alt, caption):
    return (f'<figure class="wp-block-image size-large"><img loading="lazy" decoding="async" '
            f'width="{width}" height="{height}" src="{url}" alt="{alt}" />'
            f'<figcaption class="wp-element-caption">{caption}</figcaption></figure>')


if __name__ == '__main__':
    note1 = open('note1_michigan.md').read()
    fig1 = figure(
        'https://www.nohuddle.com.ar/wp-content/uploads/2026/09/kyle-whittingham-michigan.jpg',
        1200, 900,
        "Kyle Whittingham, head coach de Michigan Wolverines",
        "Kyle Whittingham consiguió su primer triunfo con Michigan ante un rival rankeado (Foto: Bobak Ha'Eri / Wikimedia Commons, CC BY 3.0)"
    )
    title1, html1 = md_to_wp_html(note1, insert_after_paragraph_index=5, figure_html=fig1)
    open('note1_content.html', 'w').write(html1)
    open('note1_title.txt', 'w').write(title1)

    note2 = open('note2_raiders.md').read()
    fig2 = figure(
        'https://www.nohuddle.com.ar/wp-content/uploads/2026/09/kirk-cousins-scaled.jpg',
        1200, 1858,
        "Kirk Cousins, quarterback de Las Vegas Raiders",
        "Kirk Cousins no sufrió ningún sack en el debut de Klint Kubiak como head coach (Foto: All-Pro Reels / Wikimedia Commons, CC BY-SA 2.0)"
    )
    title2, html2 = md_to_wp_html(note2, insert_after_paragraph_index=2, figure_html=fig2)
    open('note2_content.html', 'w').write(html2)
    open('note2_title.txt', 'w').write(title2)

    print("OK")
