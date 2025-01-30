import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo12-addons-akretion-subscription",
    description="Meta package for akretion-subscription Odoo addons",
    version=version,
    install_requires=[
        'odoo12-addon-subscription',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 12.0',
    ]
)
