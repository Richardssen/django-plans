from decimal import Decimal
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.contrib.auth.models import User
from django.conf import settings
from datetime import date
from datetime import timedelta
import mock
from plans.models import PlanPricing, Invoice, Order, Pricing, Plan
from django.core import mail
from django.db.models import Q
from plans.plan_change import PlanChangePolicy, StandardPlanChangePolicy
from plans.taxation import EUTaxationPolicy

class PlansTestCase(TestCase):
#    fixtures = ['test_user', 'test_plan.json']
    fixtures = ['initial_plan', 'test_django-plans_auth', 'test_django-plans_plans']

    def test_extend_account_same_plan_future(self):
        u = User.objects.get(username='test1')
        u.userplan.expire = date.today() + timedelta(days=50)
        u.userplan.active = False
        u.userplan.save()
        plan_pricing = PlanPricing.objects.get(plan=u.userplan.plan, pricing__period=30)
        u.userplan.extend_account(plan_pricing.plan, plan_pricing.pricing)
        self.assertEqual(u.userplan.expire,
            date.today() + timedelta(days=50) + timedelta(days=plan_pricing.pricing.period))
        self.assertEqual(u.userplan.plan, plan_pricing.plan)
        self.assertEqual(u.userplan.active, True)
        self.assertEqual(len(mail.outbox), 1)

    def test_extend_account_same_plan_before(self):
        u = User.objects.get(username='test1')
        u.userplan.expire = date.today() - timedelta(days=50)
        u.userplan.active = False
        u.userplan.save()
        plan_pricing = PlanPricing.objects.get(plan=u.userplan.plan, pricing__period=30)
        u.userplan.extend_account(plan_pricing.plan, plan_pricing.pricing)
        self.assertEqual(u.userplan.expire, date.today() + timedelta(days=plan_pricing.pricing.period))
        self.assertEqual(u.userplan.plan, plan_pricing.plan)
        self.assertEqual(u.userplan.active, True)
        self.assertEqual(len(mail.outbox), 1)

    def test_extend_account_other(self):
        """
        Tests extending account with other Plan that user had before:
        Tests if expire date is set correctly
        Tests if mail has been send
        Tests if account has been activated
        """
        u = User.objects.get(username='test1')
        print u.userplan
        u.userplan.expire = date.today() + timedelta(days=50)
        u.userplan.active = False
        u.userplan.save()
        plan_pricing = PlanPricing.objects.filter(~Q(plan=u.userplan.plan) & Q(pricing__period=30))[0]
        print plan_pricing
        u.userplan.extend_account(plan_pricing.plan, plan_pricing.pricing)
        self.assertEqual(u.userplan.expire, date.today() + timedelta(days=plan_pricing.pricing.period))
        self.assertEqual(u.userplan.plan, plan_pricing.plan)
        self.assertEqual(u.userplan.active, True)
        self.assertEqual(len(mail.outbox), 1)

    def test_expire_account(self):
        u = User.objects.get(username='test1')
        u.userplan.expire = date.today() + timedelta(days=50)
        u.userplan.active = True
        u.userplan.save()
        u.userplan.expire_account()
        self.assertEqual(u.userplan.active, False)
        self.assertEqual(len(mail.outbox), 1)

    def test_remind_expire(self):
        u = User.objects.get(username='test1')
        u.userplan.expire = date.today() + timedelta(days=14)
        u.userplan.active = True
        u.userplan.save()
        u.userplan.remind_expire_soon()
        self.assertEqual(u.userplan.active, True)
        self.assertEqual(len(mail.outbox), 1)


class TestInvoice(TestCase):
    fixtures = ['initial_plan', 'test_django-plans_auth', 'test_django-plans_plans']

    def test_get_full_number(self):
        i = Invoice()
        i.number = 123
        i.issued = date(2010, 5, 30)
        self.assertEqual(i.get_full_number(), "123/FV/05/2010")

    def test_get_full_number_type1(self):
        i = Invoice()
        i.type = Invoice.INVOICE_TYPES.INVOICE
        i.number = 123
        i.issued = date(2010, 5, 30)
        self.assertEqual(i.get_full_number(), "123/FV/05/2010")

    def test_get_full_number_type2(self):
        i = Invoice()
        i.type = Invoice.INVOICE_TYPES.DUPLICATE
        i.number = 123
        i.issued = date(2010, 5, 30)
        self.assertEqual(i.get_full_number(), "123/FV/05/2010")

    def test_get_full_number_type3(self):
        i = Invoice()
        i.type = Invoice.INVOICE_TYPES.PROFORMA
        i.number = 123
        i.issued = date(2010, 5, 30)
        self.assertEqual(i.get_full_number(), "123/PF/05/2010")


    def test_get_full_number_with_settings(self):
        settings.INVOICE_NUMBER_FORMAT = "{{ invoice.issued|date:'Y' }}.{{ invoice.number }}.{{ invoice.issued|date:'m' }}"
        i = Invoice()
        i.number = 123
        i.issued = date(2010, 5, 30)
        self.assertEqual(i.get_full_number(), "2010.123.05")

    def test_set_issuer_invoice_data_raise(self):
        issdata = settings.ISSUER_DATA
        del settings.ISSUER_DATA
        i = Invoice()
        self.assertRaises(ImproperlyConfigured, i.set_issuer_invoice_data)
        settings.ISSUER_DATA = issdata

    def test_set_issuer_invoice_data(self):
        i = Invoice()
        i.set_issuer_invoice_data()
        self.assertEqual(i.issuer_name, settings.ISSUER_DATA['issuer_name'])
        self.assertEqual(i.issuer_street, settings.ISSUER_DATA['issuer_street'])
        self.assertEqual(i.issuer_zipcode, settings.ISSUER_DATA['issuer_zipcode'])
        self.assertEqual(i.issuer_city, settings.ISSUER_DATA['issuer_city'])
        self.assertEqual(i.issuer_country, settings.ISSUER_DATA['issuer_country'])
        self.assertEqual(i.issuer_tax_number, settings.ISSUER_DATA['issuer_tax_number'])

    def set_buyer_invoice_data(self):
        i = Invoice()
        u = User.objects.get(username='test1')
        i.set_buyer_invoice_data(u.billinginfo)
        self.assertEqual(i.buyer_name, u.billinginfo.name)
        self.assertEqual(i.buyer_street, u.billinginfo.street)
        self.assertEqual(i.buyer_zipcode, u.billinginfo.zipcode)
        self.assertEqual(i.buyer_city, u.billinginfo.city)
        self.assertEqual(i.buyer_country, u.billinginfo.country)
        self.assertEqual(i.buyer_tax_number, u.billinginfo.tax_number)
        self.assertEqual(i.buyer_name, u.billinginfo.shipping_name)
        self.assertEqual(i.buyer_street, u.billinginfo.shipping_street)
        self.assertEqual(i.buyer_zipcode, u.billinginfo.shipping_zipcode)
        self.assertEqual(i.buyer_city, u.billinginfo.shipping_city)
        self.assertEqual(i.buyer_country, u.billinginfo.shipping_country)

    def test_invoice_number(self):
        settings.INVOICE_NUMBER_FORMAT = "{{ invoice.number }}/{% ifequal invoice.type invoice.INVOICE_TYPES.PROFORMA %}PF{% else %}FV{% endifequal %}/{{ invoice.issued|date:'m/Y' }}"
        o = Order.objects.all()[0]
        day = date(2010, 05, 03)
        i = Invoice(issued=day, selling_date=day, payment_date=day)
        i.copy_from_order(o)
        i.set_issuer_invoice_data()
        i.set_buyer_invoice_data(o.user.billinginfo)
        i.clean()
        i.save()

        self.assertEqual(i.number, 1)
        self.assertEqual(i.full_number, '1/FV/05/2010')


    def test_invoice_number_daily(self):
        settings.INVOICE_NUMBER_FORMAT = "{{ invoice.number }}/{% ifequal invoice.type invoice.INVOICE_TYPES.PROFORMA %}PF{% else %}FV{% endifequal %}/{{ invoice.issued|date:'d/m/Y' }}"
        settings.INVOICE_COUNTER_RESET = Invoice.NUMBERING.DAILY

        user = User.objects.get(username='test1')
        plan_pricing = PlanPricing.objects.all()[0]
        tax = getattr(settings, "TAX")
        currency = getattr(settings, "CURRENCY")
        o1 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o1.save()

        o2 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o2.save()

        o3 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o3.save()

        day = date(2001, 05, 03)
        i1 = Invoice(issued=day, selling_date=day, payment_date=day)
        i1.copy_from_order(o1)
        i1.set_issuer_invoice_data()
        i1.set_buyer_invoice_data(o1.user.billinginfo)
        i1.clean()
        i1.save()

        i2 = Invoice(issued=day, selling_date=day, payment_date=day)
        i2.copy_from_order(o2)
        i2.set_issuer_invoice_data()
        i2.set_buyer_invoice_data(o2.user.billinginfo)
        i2.clean()
        i2.save()

        day = date(2001, 05, 04)
        i3 = Invoice(issued=day, selling_date=day, payment_date=day)
        i3.copy_from_order(o1)
        i3.set_issuer_invoice_data()
        i3.set_buyer_invoice_data(o1.user.billinginfo)
        i3.clean()
        i3.save()

        self.assertEqual(i1.full_number, "1/FV/03/05/2001")
        self.assertEqual(i2.full_number, "2/FV/03/05/2001")
        self.assertEqual(i3.full_number, "1/FV/04/05/2001")


    def test_invoice_number_monthly(self):
        settings.INVOICE_NUMBER_FORMAT = "{{ invoice.number }}/{% ifequal invoice.type invoice.INVOICE_TYPES.PROFORMA %}PF{% else %}FV{% endifequal %}/{{ invoice.issued|date:'m/Y' }}"
        settings.INVOICE_COUNTER_RESET = Invoice.NUMBERING.MONTHLY

        user = User.objects.get(username='test1')
        plan_pricing = PlanPricing.objects.all()[0]
        tax = getattr(settings, "TAX")
        currency = getattr(settings, "CURRENCY")
        o1 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o1.save()

        o2 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o2.save()

        o3 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o3.save()

        day = date(2002, 05, 03)
        i1 = Invoice(issued=day, selling_date=day, payment_date=day)
        i1.copy_from_order(o1)
        i1.set_issuer_invoice_data()
        i1.set_buyer_invoice_data(o1.user.billinginfo)
        i1.clean()
        i1.save()

        day = date(2002, 05, 13)
        i2 = Invoice(issued=day, selling_date=day, payment_date=day)
        i2.copy_from_order(o2)
        i2.set_issuer_invoice_data()
        i2.set_buyer_invoice_data(o2.user.billinginfo)
        i2.clean()
        i2.save()

        day = date(2002, 06, 01)
        i3 = Invoice(issued=day, selling_date=day, payment_date=day)
        i3.copy_from_order(o1)
        i3.set_issuer_invoice_data()
        i3.set_buyer_invoice_data(o1.user.billinginfo)
        i3.clean()
        i3.save()

        self.assertEqual(i1.full_number, "1/FV/05/2002")
        self.assertEqual(i2.full_number, "2/FV/05/2002")
        self.assertEqual(i3.full_number, "1/FV/06/2002")

    def test_invoice_number_annually(self):
        settings.INVOICE_NUMBER_FORMAT = "{{ invoice.number }}/{% ifequal invoice.type invoice.INVOICE_TYPES.PROFORMA %}PF{% else %}FV{% endifequal %}/{{ invoice.issued|date:'Y' }}"
        settings.INVOICE_COUNTER_RESET = Invoice.NUMBERING.ANNUALLY

        user = User.objects.get(username='test1')
        plan_pricing = PlanPricing.objects.all()[0]
        tax = getattr(settings, "TAX")
        currency = getattr(settings, "CURRENCY")
        o1 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o1.save()

        o2 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o2.save()

        o3 = Order(user=user, plan=plan_pricing.plan, pricing=plan_pricing.pricing, amount=plan_pricing.price, tax=tax, currency=currency)
        o3.save()

        day = date(1991, 05, 03)
        i1 = Invoice(issued=day, selling_date=day, payment_date=day)
        i1.copy_from_order(o1)
        i1.set_issuer_invoice_data()
        i1.set_buyer_invoice_data(o1.user.billinginfo)
        i1.clean()
        i1.save()

        day = date(1991, 07, 13)
        i2 = Invoice(issued=day, selling_date=day, payment_date=day)
        i2.copy_from_order(o2)
        i2.set_issuer_invoice_data()
        i2.set_buyer_invoice_data(o2.user.billinginfo)
        i2.clean()
        i2.save()

        day = date(1992, 06, 01)
        i3 = Invoice(issued=day, selling_date=day, payment_date=day)
        i3.copy_from_order(o1)
        i3.set_issuer_invoice_data()
        i3.set_buyer_invoice_data(o1.user.billinginfo)
        i3.clean()
        i3.save()

        self.assertEqual(i1.full_number, "1/FV/1991")
        self.assertEqual(i2.full_number, "2/FV/1991")
        self.assertEqual(i3.full_number, "1/FV/1992")


    def test_set_order(self):
        o = Order.objects.all()[0]

        i = Invoice()
        i.copy_from_order(o)

        self.assertEqual(i.order, o)
        self.assertEqual(i.user, o.user)
        self.assertEqual(i.total_net, o.amount)
        self.assertEqual(i.unit_price_net, o.amount)
        self.assertEqual(i.total, o.total())
        self.assertEqual(i.tax, o.tax)
        self.assertEqual(i.tax_total, o.total() - o.amount)
        self.assertEqual(i.currency, o.currency)



class OrderTestCase(TestCase):

    def test_amount_taxed_none(self):
        o = Order()
        o.amount = Decimal(123)
        o.tax = None
        self.assertEqual(o.total(), Decimal('123'))

    def test_amount_taxed_0(self):
        o = Order()
        o.amount = Decimal(123)
        o.tax = Decimal(0)
        self.assertEqual(o.total(), Decimal('123'))

    def test_amount_taxed_23(self):
        o = Order()
        o.amount = Decimal(123)
        o.tax = Decimal(23)
        self.assertEqual(o.total(), Decimal('151.29'))


class PlanChangePolicyTestCase(TestCase):
    fixtures = ['initial_plan', 'test_django-plans_auth', 'test_django-plans_plans']

    def setUp(self):
        self.policy = PlanChangePolicy()

    def test_calculate_day_cost(self):
        plan = Plan.objects.get(pk=5)
        self.assertEqual(self.policy._calculate_day_cost(plan, 13), Decimal('6.67'))

    def test_get_change_price(self):
        p1 = Plan.objects.get(pk=3)
        p2 = Plan.objects.get(pk=4)
        self.assertEqual(self.policy.get_change_price(p1, p2, 23), Decimal('8.97'))
        self.assertEqual(self.policy.get_change_price(p2, p1, 23), None)

    def test_get_change_price1(self):
        p1 = Plan.objects.get(pk=3)
        p2 = Plan.objects.get(pk=4)
        self.assertEqual(self.policy.get_change_price(p1, p2, 53), Decimal('20.67'))
        self.assertEqual(self.policy.get_change_price(p2, p1, 53), None)

    def test_get_change_price2(self):
        p1 = Plan.objects.get(pk=3)
        p2 = Plan.objects.get(pk=4)
        self.assertEqual(self.policy.get_change_price(p1, p2, -53), None)
        self.assertEqual(self.policy.get_change_price(p1, p2, 0), None)


class StandardPlanChangePolicyTestCase(TestCase):
    fixtures = ['initial_plan', 'test_django-plans_auth', 'test_django-plans_plans']

    def setUp(self):
        self.policy = StandardPlanChangePolicy()


    def test_get_change_price(self):
        p1 = Plan.objects.get(pk=3)
        p2 = Plan.objects.get(pk=4)
        self.assertEqual(self.policy.get_change_price(p1, p2, 23), Decimal('9.87'))
        self.assertEqual(self.policy.get_change_price(p2, p1, 23), None)


class EUTaxationPolicyTestCase(TestCase):
    def setUp(self):
        self.policy = EUTaxationPolicy()

    def test_none(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate(None, None), Decimal('23.0'))

    def test_private_nonEU(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate(None, 'RU'), None)

    def test_private_EU_same(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate(None, 'PL'), Decimal('23.0'))

    def test_private_EU_notsame(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate(None, 'AT'), Decimal('23.0'))

    def test_company_nonEU(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate('123456', 'RU'), None)

    def test_company_EU_same(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate('123456', 'PL'), Decimal('23.0'))

    @mock.patch("vatnumber.check_vies", lambda x: True)
    def test_company_EU_notsame_vies_ok(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate('123456', 'AT'), None)

    @mock.patch("vatnumber.check_vies", lambda x: False)
    def test_company_EU_notsame_vies_not_ok(self):
        with self.settings(TAX=Decimal('23.0'), TAX_COUNTRY='PL'):
            self.assertEqual(self.policy.get_tax_rate('123456', 'AT'), Decimal('23.0'))
