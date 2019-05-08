# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class StockPicking(models.Model):
	_inherit = 'stock.picking'

	s_inv = fields.Many2one('account.invoice', "Invoice")
	
	
	

