"""Static HTML mockup of how a business site could look after the proposed improvements."""

from __future__ import annotations

from html import escape

from nexcoder_agents.leadgen.models import BusinessCandidate, SignalCode, SiteObservation

_SECTION_COPY = {
    "servicos": ("Servicos", "Apresente os principais servicos com fotos, precos de referencia e prazos."),
    "sobre": ("Sobre", "Conte a historia do negocio, a equipe e o que o diferencia na regiao."),
    "depoimentos": ("Depoimentos", "Mostre avaliacoes de clientes para gerar confianca."),
}


def render_mockup(business: BusinessCandidate, observation: SiteObservation) -> str:
    """Return a self-contained, responsive HTML page. All business values are escaped."""
    name = escape(business.name)
    segment = escape(business.segment)
    region = escape(business.region)
    contact_lines: list[str] = []
    if business.public_phone:
        phone = escape(business.public_phone)
        contact_lines.append(f'<a class="btn" href="tel:{phone}">Ligar: {phone}</a>')
    if business.public_email:
        mail = escape(business.public_email)
        contact_lines.append(f'<a class="btn" href="mailto:{mail}">E-mail: {mail}</a>')
    if not contact_lines:
        contact_lines.append('<a class="btn" href="#contato">Fale conosco</a>')
    address = f"<p>{escape(business.address)}</p>" if business.address else ""

    sections = "\n".join(
        f'    <section id="{key}"><h2>{title}</h2><p>{text}</p></section>'
        for key, (title, text) in _SECTION_COPY.items()
    )
    notes: list[str] = []
    if observation.has(SignalCode.NO_HTTPS) or observation.has(SignalCode.NO_WEBSITE):
        notes.append("Publicado com HTTPS (certificado gratuito e renovacao automatica).")
    if observation.has(SignalCode.NOT_RESPONSIVE) or observation.has(SignalCode.NO_WEBSITE):
        notes.append("Layout responsivo para celular, tablet e desktop.")
    if observation.has(SignalCode.NO_CONTACT_INFO) or observation.has(SignalCode.NO_WEBSITE):
        notes.append("Contato visivel no topo e formulario simples.")
    if observation.has(SignalCode.OUTDATED_DESIGN):
        notes.append("Visual atualizado, tipografia legivel e carregamento rapido.")
    contact_html = " ".join(contact_lines)
    notes_html = "".join(f"<li>{escape(n)}</li>" for n in notes) or "<li>Visual atualizado.</li>"

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name} - {segment} em {region} (mockup)</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; color: #1f2933; line-height: 1.5; }}
    header {{ background: #12355b; color: #fff; padding: 2rem 1rem; text-align: center; }}
    main {{ max-width: 960px; margin: 0 auto; padding: 1rem; display: grid; gap: 1rem; }}
    section {{ border: 1px solid #d9e2ec; border-radius: 8px; padding: 1rem; }}
    .btn {{ display: inline-block; margin: .25rem; padding: .6rem 1rem; border-radius: 6px;
            background: #f0b429; color: #12355b; text-decoration: none; font-weight: 600; }}
    footer {{ text-align: center; font-size: .85rem; color: #52606d; padding: 1rem; }}
    @media (min-width: 720px) {{
      main {{ grid-template-columns: repeat(3, 1fr); }}
      #contato {{ grid-column: 1 / -1; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{name}</h1>
    <p>{segment} em {region}</p>
    {contact_html}
  </header>
  <main>
{sections}
    <section id="contato"><h2>Contato</h2>{address}
      <p>Formulario de contato com resposta em ate 1 dia util.</p></section>
  </main>
  <footer>
    <p>Mockup ilustrativo gerado pelo NexCoder. Melhorias previstas:</p>
    <ul>{notes_html}</ul>
  </footer>
</body>
</html>
"""
