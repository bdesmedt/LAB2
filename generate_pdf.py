"""Generate a print-friendly PDF from the Odoo boekhouding guide."""
from weasyprint import HTML, CSS

print_css = CSS(string="""
    @page {
        size: A4;
        margin: 20mm 15mm;
        @bottom-center {
            content: "FID Finance - Odoo 19 Boekhouding Gids | Pagina " counter(page) " van " counter(pages);
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 8pt;
            color: #6c6c7a;
        }
    }

    /* Show all content, no tabs/interactivity */
    .tab-content { display: block !important; }
    .nav-tabs { display: none !important; }
    .section-content { max-height: none !important; overflow: visible !important; }
    .section.collapsed .section-content { max-height: none !important; }
    .section-toggle { display: none !important; }
    .action-bar { display: none !important; }
    .progress-mini { display: none !important; }
    .version-badge { display: none !important; }
    .checklist-checkbox { print-color-adjust: exact; -webkit-print-color-adjust: exact; }

    /* Keep backgrounds in print */
    * { print-color-adjust: exact !important; -webkit-print-color-adjust: exact !important; }

    /* Sticky headers off for print */
    .header { position: static !important; }
    .nav-tabs { position: static !important; }

    /* Page breaks */
    .section { break-inside: avoid; }
    .hero { break-after: avoid; }
    .checklist-item { break-inside: avoid; }
    .reference-card { break-inside: avoid; }

    /* Reduce hero padding for print */
    .hero { padding: 24px !important; margin-bottom: 16px !important; }
    .hero-text h1 { font-size: 1.5rem !important; }

    /* Tighter spacing */
    .main-content { padding: 16px 0 !important; }
    .section { margin-bottom: 16px !important; }
    .progress-overview { margin-bottom: 16px !important; }
    .freq-legend { margin-bottom: 16px !important; }

    /* Tab content spacing - add page break between major sections */
    #tab-operations { page-break-before: always; }
    #tab-reference { page-break-before: always; }
""")

html = HTML(filename="/home/user/LAB2/odoo-boekhouding-gids.html")
html.write_pdf(
    "/home/user/LAB2/odoo-boekhouding-gids.pdf",
    stylesheets=[print_css],
)
print("PDF generated: odoo-boekhouding-gids.pdf")
