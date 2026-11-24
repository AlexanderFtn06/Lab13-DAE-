"""Your cart. Complete every TODO until `python manage.py test` is green.

The rules (money, stock, coupons, checkout) are in README.md and in shop/domain.py. Do not change
shop/domain.py or the tests. Money is Decimal (never float) and the price always comes from the
catalog, never from the request.
"""
from decimal import Decimal  # noqa: F401

from shop.domain import (  # noqa: F401  (you will need most of these)
    COUPONS,
    IGV_RATE,
    CartError,
    InvalidCoupon,
    InvalidQuantity,
    Line,
    OutOfStock,
    UnknownProduct,
    fmt,
    money,
)


class Cart:
    def __init__(self, catalog):
        self._catalog = catalog  # sku -> Product (price Decimal, stock int)
        self._qty = {}  # sku -> quantity, in insertion order
        self._coupon = None  # one coupon per cart

    # --- persistence between requests (already done) ---
    def to_state(self):
        return {"qty": dict(self._qty), "coupon": self._coupon}

    @classmethod
    def from_state(cls, catalog, state):
        cart = cls(catalog)
        cart._qty = {sku: int(q) for sku, q in state.get("qty", {}).items() if sku in catalog}
        cart._coupon = state.get("coupon")
        return cart

    # --- lines ---
    def add(self, sku, qty=1):
        """Add qty units of sku. qty must be an int >= 1 (InvalidQuantity) and the sku must exist
        (UnknownProduct). What is already in the cart plus qty must not exceed the product stock
        (OutOfStock, cart unchanged)."""
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise InvalidQuantity(f"qty must be an int >= 1, got {qty!r}")
        product = self._catalog.get(sku)
        if product is None:
            raise UnknownProduct(f"unknown sku: {sku!r}")
        already = self._qty.get(sku, 0)
        if already + qty > product.stock:
            raise OutOfStock(f"{sku}: {already} in cart + {qty} requested, stock is {product.stock}")
        self._qty[sku] = already + qty

    def remove(self, sku, qty=None):
        """qty=None removes the whole line; otherwise subtract qty and drop the line when it
        reaches zero. A sku that is not in the cart is UnknownProduct and qty must be an int >= 1
        (InvalidQuantity, cart unchanged). The quantity is never negative."""
        if sku not in self._qty:
            raise UnknownProduct(f"sku not in cart: {sku!r}")
        if qty is None:
            del self._qty[sku]
            return
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise InvalidQuantity(f"qty must be an int >= 1, got {qty!r}")
        remaining = self._qty[sku] - qty
        if remaining <= 0:
            del self._qty[sku]
        else:
            self._qty[sku] = remaining

    def qty_of(self, sku):
        return self._qty.get(sku, 0)

    def lines(self):
        """One Line(sku, name, unit_price, qty) per sku in the cart, in insertion order.
        name and unit_price always come from the catalog."""
        return [
            Line(sku, self._catalog[sku].name, self._catalog[sku].price, qty)
            for sku, qty in self._qty.items()
        ]

    # --- coupon and totals ---
    def apply_coupon(self, code):
        """Trim and upper-case the code; a non-string or unknown code raises InvalidCoupon and keeps
        the current coupon. A valid coupon REPLACES the previous one (it never accumulates)."""
        if not isinstance(code, str):
            raise InvalidCoupon(f"coupon code must be a string, got {code!r}")
        normalized = code.strip().upper()
        if normalized not in COUPONS:
            raise InvalidCoupon(f"unknown coupon: {code!r}")
        self._coupon = normalized

    def subtotal(self):
        """Sum of price * qty over every line, rounded to cents with money(). Empty cart -> 0.00."""
        return money(sum((line.unit_price * line.qty for line in self.lines()), Decimal("0")))

    def discount(self):
        """Coupon discount rounded to cents. No coupon -> 0.00; "percent" -> that share of the
        subtotal; "fixed" -> the amount, never more than the subtotal."""
        if self._coupon is None:
            return Decimal("0.00")
        kind, amount = COUPONS[self._coupon]
        if kind == "percent":
            return money(self.subtotal() * amount / 100)
        return money(min(amount, self.subtotal()))

    def igv(self):
        """IGV_RATE (18 %) of (subtotal - discount), rounded to cents with money()."""
        return money((self.subtotal() - self.discount()) * IGV_RATE)

    def total(self):
        """(subtotal - discount) + igv, adding the already rounded parts (never a raw total)."""
        return self.subtotal() - self.discount() + self.igv()

    def summary(self):
        """The dict the API returns: one entry per line with unit_price and line_total as 2-decimal
        strings, plus coupon and the four money totals (also 2-decimal strings via fmt)."""
        return {
            "lines": [
                {
                    "sku": line.sku,
                    "name": line.name,
                    "unit_price": fmt(line.unit_price),
                    "qty": line.qty,
                    "line_total": fmt(line.total),
                }
                for line in self.lines()
            ],
            "coupon": self._coupon,
            "subtotal": fmt(self.subtotal()),
            "discount": fmt(self.discount()),
            "igv": fmt(self.igv()),
            "total": fmt(self.total()),
        }

    # --- checkout ---
    def checkout(self):
        """Empty cart -> CartError. Stock is checked AGAIN for every line before any stock is
        lowered, so an OutOfStock leaves both the catalog and the cart untouched. On success the
        order summary is computed first, then the catalog stock goes down and the cart is emptied."""
        if not self._qty:
            raise CartError("cannot checkout an empty cart")
        for sku, qty in self._qty.items():
            if qty > self._catalog[sku].stock:
                raise OutOfStock(f"{sku}: {qty} in cart, stock is {self._catalog[sku].stock}")
        order = self.summary()
        for sku, qty in self._qty.items():
            self._catalog[sku].stock -= qty
        self._qty.clear()
        self._coupon = None
        return order


def add_from_payload(cart, payload):
    """Translate the untrusted JSON body of POST /api/cart/items/ into cart.add(sku, qty).
    Not a dict, a missing "sku" or a non-string "sku" -> CartError. qty defaults to 1 and is
    validated by add; every other key (including "price") is ignored: the catalog sets the price."""
    if not isinstance(payload, dict):
        raise CartError("the body must be a JSON object")
    sku = payload.get("sku")
    if not isinstance(sku, str):
        raise CartError("the body must have a string 'sku'")
    cart.add(sku, payload.get("qty", 1))
