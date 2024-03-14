# Copyright Odoo S.A. (https://www.odoo.com/)
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl)

# TODO:
#   Error treatment: exception, request, ... -> send request to user_id

from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _get_document_types(self):
    res = [(doc.model.model, doc.name) for doc
            in self.env['subscription.document'].search([], order='name')]
    return res


class SubscriptionDocument(models.Model):
    _name = "subscription.document"
    _description = "Subscription Document"

    name = fields.Char(required=True)
    active = fields.Boolean(
        default=True,
        help="If the active field is set to False, it will allow you to "
        "hide the subscription document without removing it.")
    # in v14, Odoo doesn't allow to have the 'model' field required=True, so I set it as
    # required in the view
    model = fields.Many2one('ir.model', string="Object")
    field_ids = fields.One2many(
        'subscription.document.fields', 'document_id', string='Fields',
        copy=True)


class SubscriptionDocumentFields(models.Model):
    _name = "subscription.document.fields"
    _description = "Subscription Document Fields"
    _rec_name = 'field'

    # in v14, Odoo doesn't allow to have the 'model' field required=True, so I set it as
    # required in the view
    field = fields.Many2one(
        'ir.model.fields', domain="[('model_id', '=', parent.model)]")
    value = fields.Selection([
        ('false', 'False'),
        ('date', 'Current Date')],
        string='Default Value',
        help="Default value is considered for field when new document "
        "is generated.")
    document_id = fields.Many2one(
        'subscription.document', string='Subscription Document',
        ondelete='cascade')


class Subscription(models.Model):
    _name = "subscription.subscription"
    _description = "Subscription"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(
        default=True, tracking=True,
        states={'running': [('readonly', True)]})
    partner_id = fields.Many2one(
        'res.partner', string='Partner', ondelete='restrict', tracking=True)
    notes = fields.Text(string='Internal Notes')
    user_id = fields.Many2one(
        'res.users', string='User', required=True,
        default=lambda self: self.env.user, tracking=True)
    interval_number = fields.Integer(
        readonly=True, states={'draft': [('readonly', False)]},
        string='Internal Qty', default=1, tracking=True)
    interval_type = fields.Selection([
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')],
        string='Interval Unit', default='months', tracking=True,
        readonly=True, states={'draft': [('readonly', False)]})
    exec_init = fields.Integer(
        string='Number of Documents', tracking=True,
        default=-1)
    date_init = fields.Datetime(
        string='First Date', default=fields.Datetime.now, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done')],
        string='Status', copy=False, default='draft', tracking=True)
    doc_source = fields.Reference(
        selection=_get_document_types, string='Source Document',
        required=True,
        help="User can choose the source document on which he wants to create "
        "documents")
    doc_lines = fields.One2many(
        'subscription.subscription.history', 'subscription_id',
        string='Documents created', readonly=True)
    cron_id = fields.Many2one(
        'ir.cron', string='Cron Job',
        help="Scheduler which runs on subscription",
        states={'running': [('readonly', True)], 'done': [('readonly', True)]})
    nextcall = fields.Datetime(
        related='cron_id.nextcall',
        help='Next call of the Odoo scheduler for this subscription.')

    @api.model
    def _auto_end(self):
        super()._auto_end()
        # drop the FK from subscription to ir.cron, as it would cause
        # deadlocks during cron job execution. When model_copy()
        # tries to write() on the subscription, it has to wait for an
        # ExclusiveLock on the cron job record, but the latter is locked
        # by the cron system for the duration of the job!

        # FIXME: the subscription module should be reviewed to simplify the
        #        scheduling process and to use a unique cron job for all
        #        subscriptions, so that it never needs to be updated during
        #        its execution.
        self.env.cr.execute(
            "ALTER TABLE %s DROP CONSTRAINT %s" % (
                self._table, '%s_cron_id_fkey' % self._table))

    def set_process(self):
        sub_model = self.env['ir.model'].search([('model', '=', self._name)])
        assert len(sub_model) == 1

        for subscription in self:
            cron_vals = {
                'name': subscription.name,
                'interval_number': subscription.interval_number,
                'interval_type': subscription.interval_type,
                'numbercall': subscription.exec_init,
                'nextcall': subscription.date_init,
                'model_id': sub_model.id,
                'state': 'code',
                'code': 'model._cron_model_copy(%d)' % subscription.id,
                'priority': 6,
                'user_id': subscription.user_id.id
            }
            cron = self.env['ir.cron'].sudo().create(cron_vals)
            subscription.write({'cron_id': cron.id, 'state': 'running'})

    @api.model
    def _cron_model_copy(self, ids):
        self.browse(ids).model_copy()

    def model_copy(self):
        for subscription in self.filtered(lambda sub: sub.cron_id):
            if not subscription.doc_source.exists():
                raise UserError(_(
                    'Please provide another source document.\n'
                    'This one does not exist!'))

            default = {'state': 'draft'}
            documents = self.env['subscription.document'].search(
                [('model.model', '=', subscription.doc_source._name)], limit=1)
            fieldnames = dict(
                (f.field.name, f.value == 'date' and fields.Date.today() or
                 False) for f in documents.field_ids)
            default.update(fieldnames)

            # if there was only one remaining document to generate
            # the subscription is over and we mark it as being done
            if subscription.cron_id.numbercall == 1:
                subscription.write({'state': 'done'})
            else:
                subscription.write({'state': 'running'})
            copied_doc = subscription.doc_source.copy(default)
            self.env['subscription.subscription.history'].create({
                'subscription_id': subscription.id,
                'date': fields.Datetime.now(),
                'document_id': '%s,%s' % (subscription.doc_source._name,
                                          copied_doc.id)})

    def unlink(self):
        for sub in self:
            if sub.state == "running":
                raise UserError(_(
                    "You cannot delete subscription '%s' "
                    "because it is in running state.") % sub.display_name)
        return super().unlink()

    def set_done(self):
        self.mapped('cron_id').write({'active': False})
        self.write({'state': 'done'})

    def set_draft(self):
        self.write({'state': 'draft'})


class SubscriptionHistory(models.Model):
    _name = "subscription.subscription.history"
    _description = "Subscription history"
    _rec_name = 'date'

    date = fields.Datetime()
    subscription_id = fields.Many2one(
        'subscription.subscription', string='Subscription', ondelete='cascade')
    document_id = fields.Reference(
        selection=_get_document_types, string='Source Document', required=True)
