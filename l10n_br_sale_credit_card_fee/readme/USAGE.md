To use this module, you need to:

1. Configure the fee tables in *Sales → Configuration → Credit Card
   Administrators*, and set the **Card Administrator** of the credit
   card *Payment Methods*.
2. On a quotation or sale order, select the payment method(s). A line
   is added to the **Credit Card Fees** list for each card
   administrator, with the installment range of the administrator, the
   applicable **Taxa (%)** and the **Valor**, which is filled with the
   order total including taxes.
3. Adjust the list as needed: the **Taxa (%)** and the **Valor** of
   each line can be changed, and the **Valor da Taxa** of the line is
   recalculated as *Valor x Taxa (%)*. The **Taxa (%)** of the order
   shows the applied fees separated by comma and the **Valor da
   Taxa** is the sum of the fee lines.
4. Go to the *Invoice Plan* tab and click *⇒ Create Invoice Plan*. In
   the wizard, choose the number of installments and, if needed, the
   **Card Administrator**. The wizard shows the applicable
   **Taxa (%)**, the fee amount and the order total including the fee
   (**Amount + Fee**), and it refreshes the fee lines of the order.
5. Enable **Sum Fee** to add the credit card fee to the order total and
   to include it proportionally in each installment invoice. Leave it
   unchecked to track the fee without charging it.
6. Confirm the wizard and invoice the installments from the invoice
   plan; each customer invoice will contain a *Credit Card Fee* line
   with its proportional share of the fee.