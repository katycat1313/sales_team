"""
Stripe Tool
-----------
Creates payment links and invoices for Katy's service sales.

Setup: Add STRIPE_SECRET_KEY to .env
Get it from: dashboard.stripe.com → Developers → API keys

Pricing model:
- Free GBP audit (lead magnet, automated by agents)
- $197 one-time optimization (full upfront, or $98 deposit / $97 on delivery split)
- $98/month ongoing management (Stripe Subscription)
"""

import os

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")


def is_configured() -> bool:
    return bool(STRIPE_SECRET_KEY)


def _get_stripe():
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        return None


def create_payment_link(
    amount_dollars: float,
    description: str,
    customer_email: str = None,
    metadata: dict = None,
) -> dict:
    """
    Create a one-time Stripe Payment Link.
    Returns {"url": "https://buy.stripe.com/...", "id": "..."}
    """
    if not is_configured():
        return {
            "error": "Stripe not configured. Add STRIPE_SECRET_KEY to .env",
            "url": None,
        }

    stripe = _get_stripe()
    if not stripe:
        return {"error": "stripe library not installed. Run: pip install stripe", "url": None}

    try:
        # Create product + price inline
        price = stripe.Price.create(
            unit_amount=int(amount_dollars * 100),  # cents
            currency="usd",
            product_data={
                "name": description,
                "metadata": metadata or {},
            },
        )
        link_params = {
            "line_items": [{"price": price.id, "quantity": 1}],
            "metadata": metadata or {},
        }
        if customer_email:
            link_params["customer_creation"] = "always"

        link = stripe.PaymentLink.create(**link_params)
        return {
            "url": link.url,
            "id": link.id,
            "amount": amount_dollars,
            "description": description,
        }

    except Exception as e:
        return {"error": str(e), "url": None}


def create_invoice(
    customer_email: str,
    customer_name: str,
    amount_dollars: float,
    description: str,
    due_days: int = 7,
) -> dict:
    """
    Create and send a Stripe Invoice (for final payment on delivery).
    Returns {"invoice_url": "...", "invoice_id": "..."}
    """
    if not is_configured():
        return {"error": "Stripe not configured", "invoice_url": None}

    stripe = _get_stripe()
    if not stripe:
        return {"error": "stripe not installed", "invoice_url": None}

    try:
        # Find or create customer
        customers = stripe.Customer.list(email=customer_email, limit=1)
        if customers.data:
            customer = customers.data[0]
        else:
            customer = stripe.Customer.create(
                email=customer_email,
                name=customer_name,
            )

        # Create invoice item
        stripe.InvoiceItem.create(
            customer=customer.id,
            amount=int(amount_dollars * 100),
            currency="usd",
            description=description,
        )

        # Create and finalize invoice
        invoice = stripe.Invoice.create(
            customer=customer.id,
            collection_method="send_invoice",
            days_until_due=due_days,
            auto_advance=True,
        )
        invoice = stripe.Invoice.finalize_invoice(invoice.id)
        stripe.Invoice.send_invoice(invoice.id)

        return {
            "invoice_id": invoice.id,
            "invoice_url": invoice.hosted_invoice_url,
            "amount": amount_dollars,
            "customer_email": customer_email,
        }

    except Exception as e:
        return {"error": str(e), "invoice_url": None}


def create_subscription_link(
    monthly_amount_dollars: float,
    description: str,
) -> dict:
    """
    Create a recurring monthly subscription payment link.
    Use for the $98/month ongoing GBP management retainer.
    """
    if not is_configured():
        return {"error": "Stripe not configured", "url": None}

    stripe = _get_stripe()
    if not stripe:
        return {"error": "stripe not installed", "url": None}

    try:
        price = stripe.Price.create(
            unit_amount=int(monthly_amount_dollars * 100),
            currency="usd",
            recurring={"interval": "month"},
            product_data={"name": description},
        )
        link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
        )
        return {
            "url": link.url,
            "id": link.id,
            "monthly_amount": monthly_amount_dollars,
            "description": description,
        }
    except Exception as e:
        return {"error": str(e), "url": None}
