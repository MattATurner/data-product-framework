# Sales Performance — what you will receive

**Derived from TDD-SALES-002. Written for the business. Signed before build.**

## What the figures mean

- **Net sales** is gross less discount, excluding tax, in AUD.
- Figures are built from **one row for every line on every customer order**. A line
  amended several times is counted **once**, at its latest values.
- You can **add the figures up** across days, months, regions, categories and segments
  without double counting.

## How history behaves

- Sales stay with the **customer segment that applied on the date of the sale**. If a
  customer is reclassified in June, their March sales still report under the old segment.
- The same holds for **product category**, so category trends stay comparable over time.

## What is included and excluded

- **Cancelled lines remain visible** in the detail and are marked as cancelled. They are
  **not** counted in net sales.
- **Corrections arriving within 90 days** restate the affected period. Corrections after
  90 days do not change published figures.

## Timing

- Refreshed **hourly during the working day**.
- If a sale has **no customer, or a negative quantity**, nothing is published and the team
  is alerted. You will not see partially loaded figures.

## Agreement with other teams

- Customer and product definitions are **shared with Finance and Merchandising**, so net
  sales reconciles to Finance's revenue for the same period and categories match the
  Merchandising range.

## Access

- Analysts can see **who** the customer is and **which segment** they are in, but **not
  their contact details**.
- The external analytics partner receives a **monthly extract only**, with no access to
  internal systems.

## Known limitations — please read

- **Segment and category history starts at go-live.** The source system does not keep a
  record of what a customer's segment used to be, so we begin tracking changes from the
  day this product goes live. Sales made **before** go-live will show the segment as it
  was at go-live, not as it was at the time of that sale.
- **Hourly, not immediate.** Reading the source more frequently needs a network connection
  that does not exist yet. Hourly was accepted as sufficient for lead reallocation, and a
  shorter interval can be delivered later without rebuilding anything.

---

**Signed off:** Sales Operations, 2026-09-09 · covers acceptance examples AX-1 to AX-6.
