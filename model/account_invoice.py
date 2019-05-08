# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
import logging
from odoo.exceptions import AccessError, UserError, RedirectWarning, ValidationError, Warning

_logger = logging.getLogger(__name__)
	
class AccountInvoice(models.Model):
	_inherit='account.invoice'
	
	@api.model
	def get_eli(self):
		ir_values_obj = self.env['ir.values']
		ids = ir_values_obj.sudo().get_default('account.config.settings', "default_users", company_id = self.env.user.company_id.id) or []
		return True if self.env.user.id in ids else False
		
	@api.model
	def _default_warehouse_id(self):
		company = self.env.user.company_id.id
		warehouse_ids = self.env['stock.warehouse'].search([('company_id', '=', company)], limit=1)
		return warehouse_ids
		
	@api.model
	def _default_picking_type(self):
		picking_type = self.env['stock.picking.type'].search([('code', '=', 'outgoing')], limit=1)
		return picking_type
			
	picking_policy = fields.Selection([
		('direct', 'Deliver each product when available'),
		('one', 'Deliver all products at once')],
		string='Shipping Policy', required=True, readonly=True, default='direct',
		states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})
	picking_type_id = fields.Many2one('stock.picking.type',
		string='Picking Type', required=True, readonly=True, default=_default_picking_type,
		states={'draft': [('readonly', False)]})
	warehouse_id = fields.Many2one(
		'stock.warehouse', string='Warehouse',
		required=True, readonly=True, states={'draft': [('readonly', False)]},
		default=_default_warehouse_id)
	picking_ids = fields.Many2many('stock.picking', compute='_compute_picking_ids', string='Picking associated to this sale')
	delivery_count = fields.Integer(string='Delivery Orders', compute='_compute_picking_ids')
	username = fields.Char('Username')
	password = fields.Char('Password')
	create_stock = fields.Boolean(default=False)
	show_credentials = fields.Boolean(default=get_eli)
	pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', required=True, readonly=True, states={'draft': [('readonly', False)]}, help="Pricelist for current invoices")
	
	@api.multi
	@api.depends()
	def _compute_picking_ids(self):
		for order in self:
			order.picking_ids = self.env['stock.picking'].search([('s_inv', '=', order.id)])
			order.delivery_count = len(order.picking_ids)
	
	@api.onchange('warehouse_id')
	def _onchange_warehouse_id(self):
		if self.warehouse_id.company_id:
			self.company_id = self.warehouse_id.company_id.id
			
	@api.multi
	def action_view_delivery(self):
		'''
		This function returns an action that display existing delivery orders
		of given sales order ids. It can either be a in a list or in a form
		view, if there is only one delivery order to show.
		'''
		action = self.env.ref('stock.action_picking_tree_all').read()[0]

		pickings = self.mapped('picking_ids')
		if len(pickings) > 1:
			action['domain'] = [('id', 'in', pickings.ids)]
		elif pickings:
			action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
			action['res_id'] = pickings.id
		return action
	
	@api.multi
	def action_invoice_open(self):
		# lots of duplicate calls to action_invoice_open, so we remove those already open
		to_open_invoices = self.filtered(lambda inv: inv.state != 'open')
		to_stock_invoices = self.filtered(lambda inv: inv.create_stock == True)
		if to_open_invoices.filtered(lambda inv: inv.state not in ['proforma2', 'draft']):
			raise UserError(_("Invoice must be in draft or Pro-forma state in order to validate it."))
		to_open_invoices.action_date_assign()
		to_open_invoices.action_move_create()
		to_stock_invoices.action_create_stock()
		return to_open_invoices.invoice_validate()
		
	@api.multi
	def action_create_stock(self):
		for rec in self:
			vals = rec._get_stock_move_values()
			if vals:
				stock = self.env['stock.picking'].create(vals)
				rec._get_stock_pick_line_vals(rec, stock)
				stock.do_new_transfer()
				
	def _get_stock_pick_line_vals(self, inv, stock):
		if self.picking_type_id.default_location_src_id:
			location_id = self.picking_type_id.default_location_src_id.id
		elif self.partner_id:
			location_id = self.partner_id.property_stock_supplier.id
		else:
			customerloc, location_id = self.env['stock.warehouse']._get_partner_locations()

		if self.picking_type_id.default_location_dest_id:
			location_dest_id = self.picking_type_id.default_location_dest_id.id
		elif self.partner_id:
			location_dest_id = self.partner_id.property_stock_customer.id
		else:
			location_dest_id, supplierloc = self.env['stock.warehouse']._get_partner_locations()
			
		for rec in inv.invoice_line_ids:
			self.env['stock.move'].create({
				'product_id': rec.product_id.id,
				'product_uom_qty': rec.quantity,
				'picking_id': stock.id,
				'product_uom': rec.uom_id.id or self.product_id.uom_id.id,
				'location_id': location_id,
				'location_dest_id': location_dest_id,
				'name': inv.number,
			})
		
	def _get_stock_move_values(self):
		vals = {}
		if self.picking_type_id:
			if self.picking_type_id.default_location_src_id:
				location_id = self.picking_type_id.default_location_src_id.id
			elif self.partner_id:
				location_id = self.partner_id.property_stock_supplier.id
			else:
				customerloc, location_id = self.env['stock.warehouse']._get_partner_locations()

			if self.picking_type_id.default_location_dest_id:
				location_dest_id = self.picking_type_id.default_location_dest_id.id
			elif self.partner_id:
				location_dest_id = self.partner_id.property_stock_customer.id
			else:
				location_dest_id, supplierloc = self.env['stock.warehouse']._get_partner_locations()
				
			vals = {
				'partner_id': self.partner_id.id,
				'min_date': self.date_invoice,
				'origin': self.name,
				'move_type': self.picking_policy,
				'picking_type_id': self.picking_type_id.id,
				'location_id': location_id,
				'location_dest_id': location_dest_id,
				's_inv': self.id,
			}
		return vals
	
	@api.model
	def create(self, vals):
		eligible=True
		if vals.get('username') and vals.get('password'):
			#authenticate user
			users = self.env['res.users'].search([('login', '=', vals.get('username'))])
			if users:
				vals['user_id'] = users.id
			else:
				raise UserError('Invalid username and password.')
			eligible = self.is_eligible(users)
		if any(f not in vals for f in ['pricelist_id']):
			partner = self.env['res.partner'].browse(vals.get('partner_id'))
			vals['pricelist_id'] = vals.setdefault('pricelist_id', partner.property_product_pricelist and partner.property_product_pricelist.id)
		res = super(AccountInvoice, self).create(vals)
		if res.amount_total <= 0.0 and not eligible:
			raise UserError('You cannot invoice amount less or equal to zero.')
		for order in res.invoice_line_ids:
			if order.price_unit_temp != order.price_unit and not eligible:
				raise UserError('You are not authorized to change product prices')
		return res
		
	@api.multi
	def write(self, vals):
		if not self.env.context.get('skipped'):
			eligible=True
			for rec in self:
				if rec.show_credentials:
					#authenticate user
					users = self.env['res.users'].search([('login', '=', rec.username)])
					if users:
						vals['user_id'] = users.id
					else:
						raise UserError('Invalid username and password.')
					eligible = self.is_eligible(users)
				if rec.amount_total <= 0.0 and not eligible:
					raise UserError('You cannot invoice amount less or equal to zero.')
				for order in rec.invoice_line_ids:
					if order.price_unit_temp != order.price_unit and not eligible:
						raise UserError('You are not authorized to change product prices')
		ctx = self.env.context.copy()
		ctx.update({
			'skipped': True
		})
		res = super(AccountInvoice, self.with_context(ctx)).write(vals)
		return res
		
	def is_eligible(self, users):
		ir_values_obj = self.env['ir.values']
		ids = ir_values_obj.sudo().get_default('account.config.settings', "default_user_priv", company_id = self.env.user.company_id.id) or []
		return True if users.id in ids else False
		
	@api.multi
	@api.onchange('partner_id')
	def onchange_partner_id_pricelist(self):
		"""
		Update the following fields when the partner is changed:
		- Pricelist
		"""
		
		values = {
			'pricelist_id': self.partner_id.property_product_pricelist and self.partner_id.property_product_pricelist.id or False,
		}
		self.update(values)
		
class AccountInvoiceLine(models.Model):
	_inherit="account.invoice.line"
	
	price_unit_temp = fields.Float('Temp Price')
	
	@api.multi
	def _get_display_price_ext(self, product):
		# TO DO: move me in master/saas-16 on sale.order
		if self.invoice_id.pricelist_id.discount_policy == 'with_discount':
			return product.with_context(pricelist=self.invoice_id.pricelist_id.id).price
		price, rule_id = self.invoice_id.pricelist_id.get_product_price_rule(self.product_id, self.quantity or 1.0, self.invoice_id.partner_id)
		pricelist_item = self.env['product.pricelist.item'].browse(rule_id)
		if (pricelist_item.base == 'pricelist' and pricelist_item.base_pricelist_id.discount_policy == 'with_discount'):
			price, rule_id = pricelist_item.base_pricelist_id.get_product_price_rule(self.product_id, self.quantity or 1.0, self.invoice_id.partner_id)
			return price
		else:
			from_currency = self.invoice_id.company_id.currency_id
			return from_currency.compute(product.lst_price, self.invoice_id.pricelist_id.currency_id)
		
	@api.onchange('product_id')
	def _onchange_product_id(self):
		domain = {}
		if not self.invoice_id:
			return

		part = self.invoice_id.partner_id
		fpos = self.invoice_id.fiscal_position_id
		company = self.invoice_id.company_id
		currency = self.invoice_id.currency_id
		type = self.invoice_id.type

		if not part:
			warning = {
					'title': _('Warning!'),
					'message': _('You must first select a partner!'),
				}
			return {'warning': warning}

		if not self.product_id:
			if type not in ('in_invoice', 'in_refund'):
				self.price_unit = 0.0
				self.price_unit_temp = 0.0
			domain['uom_id'] = []
		else:
			if part.lang:
				product = self.product_id.with_context(lang=part.lang)
			else:
				product = self.product_id

			self.name = product.partner_ref
			account = self.get_invoice_line_account(type, product, fpos, company)
			if account:
				self.account_id = account.id
			self._set_taxes()

			if type in ('in_invoice', 'in_refund'):
				if product.description_purchase:
					self.name += '\n' + product.description_purchase
			else:
				if product.description_sale:
					self.name += '\n' + product.description_sale

			if not self.uom_id or product.uom_id.category_id.id != self.uom_id.category_id.id:
				self.uom_id = product.uom_id.id
			domain['uom_id'] = [('category_id', '=', product.uom_id.category_id.id)]

			if company and currency:
				if company.currency_id != currency:
					self.price_unit = self.price_unit * currency.with_context(dict(self._context or {}, date=self.invoice_id.date_invoice)).rate
					self.price_unit_temp = self.price_unit

				if self.uom_id and self.uom_id.id != product.uom_id.id:
					self.price_unit = product.uom_id._compute_price(self.price_unit, self.uom_id)
					self.price_unit_temp = self.price_unit
					
				if self.invoice_id.pricelist_id and self.invoice_id.partner_id:
					self.price_unit = self.env['account.tax']._fix_tax_included_price(self._get_display_price_ext(product), product.taxes_id, self.invoice_line_tax_ids)
					self.price_unit_temp = self.price_unit
					
		return {'domain': domain}