# Sales Performance — what you will receive

**Derived from TDD-SALES-002. Written for the business. Signed before build.**

## What the figures mean

- **Net sales** is gross less discount, excluding tax, in AUD.
- Figures are built from **one row for every line on every customer order**. A line
  amended several times is counted **once**, at its latest values.
- You can **add the figures up** across days, months, regions, categories and segments
  without double counting.
- Every monthly figure can be **traced to the order lines** that make it up.

## How history behaves

- Sales stay with the **customer segment and region that applied on the date of the sale**.
  If a customer is reclassified in June, their March sales still report under the old segment.
- The same holds for **product category**, so category trends stay comparable over time.
- Customer names and contact details always show their **current** values.

## What is included and excluded

- **Cancelled lines remain visible** in the detail and are marked as cancelled. They are
  **not** counted in net sales.
- **Corrections arriving within 90 days** restate the affected period. Corrections after
  90 days do not change published figures.

## Timing

- Refreshed **hourly during the working day** (08:00 to 18:00 Perth time, Monday to Friday).
  The team is alerted if figures fall more than 90 minutes behind.
- If a sale has **no customer, or a negative quantity**, the figures are **not refreshed**,
  the team is alerted, and the unusable line is held aside with the reason. You keep seeing
  the last complete figures, never partial ones.

## Agreement with other teams

- Customer and product definitions are **shared with Finance and Merchandising**, so net
  sales reconciles to Finance's revenue for the same period and categories match the
  Merchandising range.

## Access

- Analysts can see **who** the customer is and **which segment** they are in, but **not
  their contact details**.
- The external analytics partner receives a **monthly extract of closed months only**, by
  month, product category and region, with no customer detail and no access to internal
  systems.

## Known limitations — please read

- **Segment, region and category history starts at go-live.** The source system does not
  keep a record of earlier values, so we begin tracking changes from the day this product
  goes live. Sales made **before** go-live show the values as they were at go-live.
- **Hourly, not immediate.** Reading the source more frequently needs a network connection
  that does not exist yet. Hourly was accepted as sufficient for lead reallocation, and a
  shorter interval can be delivered later without rebuilding anything.

---

The signature for this page is recorded in `signoff.yaml` beside it, bound to a digest of
this text and of every model's grain and history declaration. Changing either invalidates
the signature until it is signed again.
