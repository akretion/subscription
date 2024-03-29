# Copyright Odoo S.A. (https://www.odoo.com/)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

{
    'name': 'Recurring Documents',
    'version': '14.0.1.0.0',
    'category': 'Extra Tools',
    'summary': 'Generate recurring invoices, sale orders, purchase orders, etc.',
    'license': 'LGPL-3',
    'author': 'Odoo SA, Akretion',
    'maintainers': ['alexis-via'],
    'website': 'https://github.com/akretion/subscription',
    'depends': ['mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/subscription.xml',
    ],
    'demo': ['demo/subscription_demo.xml'],
    'installable': True,
}
