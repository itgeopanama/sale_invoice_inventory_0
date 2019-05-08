# -*- coding: utf-8 -*-

import time
import datetime
from dateutil.relativedelta import relativedelta

import odoo
from odoo import SUPERUSER_ID
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountConfigSettings(models.TransientModel):
	_inherit = 'account.config.settings'

	default_users = fields.Many2many('res.users', 'default_users_1', 'user_id','account_id', string='Generic Users')
	default_user_priv = fields.Many2many('res.users','default_users_2', 'user_id','account_id', string='Price Change Eligible Users')

	@api.onchange('company_id')
	def onchange_company_id(self):
		# update related fields
		res = super(AccountConfigSettings, self).onchange_company_id()
		if self.company_id:
			company = self.company_id
			# update taxes
			ir_values = self.env['ir.values']
			default_users = ir_values.get_default('account.config.settings', 'default_users', company_id = self.company_id.id)
			default_user_priv = ir_values.get_default('account.config.settings', 'default_user_priv', company_id = self.company_id.id)
			self.default_users = default_users
			self.default_user_priv = default_user_priv
		return res
		
	@api.multi
	def set_users(self):
		""" Set the Generic Users if they have changed """
		ir_values_obj = self.env['ir.values']
		ir_values_obj.sudo().set_default('account.config.settings', "default_users", self.default_users.ids if self.default_users else False,for_all_users=True, company_id=self.company_id.id)
		ir_values_obj.sudo().set_default('account.config.settings', "default_user_priv", self.default_user_priv.ids if self.default_user_priv else False,for_all_users=True, company_id=self.company_id.id)