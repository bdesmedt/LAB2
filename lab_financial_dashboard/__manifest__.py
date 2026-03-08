{
    'name': 'LAB Financieel Dashboard',
    'version': '17.0.1.0.0',
    'summary': 'Financieel dashboard (embedded Streamlit)',
    'description': """
        Integreert het LAB Groep financieel dashboard als een iframe
        binnen de Odoo interface. Geeft directe toegang tot omzet,
        budgetten, balans en financiële analyses vanuit het Odoo menu.
    """,
    'category': 'Accounting/Accounting',
    'author': 'LAB Groep',
    'website': 'https://lab.odoo.works',
    'depends': ['web'],
    'data': [
        'security/ir.model.access.csv',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'lab_financial_dashboard/static/src/js/dashboard.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
