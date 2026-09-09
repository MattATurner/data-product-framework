# Customer Orders — what you will receive

**Derived from TDD-SALES-001. Written for the business. Signed before build.**

- You will get **one row for every customer order**. An order with three lines is still
  one row.
- **The order's lines come with it.** You do not need a second lookup to see them.
- Each order appears **exactly once**, showing its most recent state. An order amended
  twice shows the latest values.
- **Cancelled orders stay visible** and are marked as cancelled. They are **not** counted
  in order value totals.
- Customer details shown are the customer's **current** details. If a customer moves in
  June, their March order will show the new address.
- Data is refreshed **once daily, before 07:00**. Orders placed today appear tomorrow morning.
- If an order has **no customer, or a negative quantity**, nothing is published and the
  team is alerted. You will not see partial data.
- Access is limited to **Sales Operations and Data Analytics**.

---

**Signed off:** Sales Operations, 2026-09-09 · covers acceptance examples AX-1 to AX-5.
