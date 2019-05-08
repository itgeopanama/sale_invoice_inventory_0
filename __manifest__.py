{
	'name': "Sales Invoice Inventory",
	'version': '1.0',
	'category': '',
	'author': "Onedoos",
	'website': 'https://www.onedoos.com',
	'description': """
		Invoice Validation, Prices, Stocks etc.
	""",
	'depends': ['account', 'account_accountant', 'stock'],
	'data': [
		'views/account_invoice_view.xml',
		'views/res_config_settings_view.xml',
	],
	'installable': True,
	'application': True,
}
