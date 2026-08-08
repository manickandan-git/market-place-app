RETURNS_POLICY = """\
You may return most items within 30 days of the delivery date for a full \
refund or exchange. The return window starts on the day the carrier marks \
your package as delivered, not the day you placed the order.

Returned items must be unused, unworn, and in their original packaging with \
all tags, manuals, and accessories included. Items that show signs of use, \
damage not caused by the seller, or missing original packaging may be \
refused or subject to a restocking fee.

Some items cannot be returned: perishable goods, personalized or \
custom-made products, digital downloads, gift cards, and items marked as \
"final sale" at the time of purchase. Health and personal care items can \
only be returned if the packaging is unopened.

To start a return, go to Your Orders, select the item, and choose "Request \
Return." Pick a reason for the return and print the prepaid return label if \
one is provided. Drop the package off at the specified carrier within 14 \
days of requesting the return.

If an item arrived damaged, defective, or different from what you ordered, \
the seller covers return shipping and you'll receive a full refund \
including original shipping charges. For returns made because you simply \
changed your mind, return shipping is deducted from your refund unless the \
seller's listing states otherwise.
"""

SHIPPING_POLICY = """\
Orders are processed within 1-2 business days after payment is confirmed. \
Processing time does not include weekends or public holidays, and can take \
longer during peak sale periods, which will be noted on the product page.

Standard shipping typically arrives within 5-7 business days, and expedited \
shipping within 2-3 business days, depending on the seller's location and \
the carrier used. Estimated delivery windows are shown at checkout before \
you place your order and are not guaranteed delivery dates.

Shipping is free on orders over $50 within the continental United States. \
Orders under that amount are charged a flat shipping rate of $5.99, unless \
the individual seller offers their own free-shipping promotion on their \
listings.

International shipping is available to select countries and is calculated \
at checkout based on destination and package weight. International buyers \
are responsible for any customs duties, import taxes, or brokerage fees \
charged by their country; these are not included in the item price or \
shipping cost.

If your package is lost in transit or arrives visibly damaged, contact \
support within 7 days of the expected delivery date. We will work with the \
carrier and the seller to send a replacement or issue a full refund, \
whichever you prefer.
"""

REFUNDS_POLICY = """\
Once your return is received and inspected, we will notify you by email \
whether your refund is approved. Approved refunds are issued within 5-7 \
business days of that inspection.

Refunds are issued to your original payment method. If you paid by credit \
or debit card, it may take an additional 3-5 business days for the credit \
to appear on your statement depending on your bank. We do not issue cash \
or check refunds.

If only part of a return qualifies, for example if some items in a multi- \
item order are missing or not in resellable condition, a partial refund \
will be issued for the qualifying items only. You'll see an itemized \
breakdown in your refund confirmation email.

Original shipping charges are refunded only when the return is due to a \
seller error, such as sending the wrong item or a defective product. \
Shipping charges are not refunded when a return is made because the buyer \
changed their mind or ordered the wrong size or color.

You can check the status of a refund at any time from Your Orders by \
selecting the order and viewing "Refund Status." If it has been more than \
10 business days since your return was marked as received and you have not \
seen a refund or update, contact support with your order number.
"""

SEED_POLICIES: dict[str, str] = {
    "returns": RETURNS_POLICY,
    "shipping": SHIPPING_POLICY,
    "refunds": REFUNDS_POLICY,
}
