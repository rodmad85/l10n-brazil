All notable changes to this module will be documented in this file.

## 18.0.4.0.0 (2026-10-05)

- Add the applied fees to a **Credit Card Fees** list in the sale order,
  one line per card administrator of the selected payment methods, with
  the installment range, the **Taxa (%)**, the **Valor** and the **Valor
  da Taxa** of each fee.
- Support multiple payment methods: every selected payment method with a
  card administrator gets its own fee line.
- Fill the **Valor** of a new fee line with the order total including
  taxes when the payment method is selected. It stays editable and the
  **Valor da Taxa** is recalculated from it.
- Show the **Taxa (%)** with the applied fees separated by comma and the
  **Valor da Taxa** as the sum of the fee lines, in the sale order
  totals, in the *Create Invoice Plan* wizard and in the totals of the
  invoice plan tab.
- **Taxa (%)** becomes a text field, since it holds several
  percentages.

## 18.0.3.0.0 (2026-08-21)

- Include the credit card fee in installment invoices through a
  *Credit Card Fee* product line, proportional to each planned
  installment, when *Sum Fee* is enabled.
- Move the card administrator selection into the *Create Invoice Plan*
  wizard and show the fee preview (*Fee (%)*, fee amount,
  *Amount + Fee*).
- Add the *Sum Fee* option to charge or only track the fee.
- Restructure the sale order fee summary block.

## 18.0.1.0.0 (2025-01-01)

- Initial version: credit card administrators with fee ranges by
  installments, fee computation on sale orders based on the invoice
  plan and per-installment fee distribution.