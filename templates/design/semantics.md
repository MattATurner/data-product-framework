# {Product name} — what you will receive

**Derived from TDD-{DOMAIN}-{nnn}. Written for the business. Signed before build.**

<!--
semantics.md template · Design stage · Data Product Framework

This page tells the business owner what the design will deliver, in their own words. They
sign it before anything is built. Save it as
openspec/specs/products/{domain}/{product}/tdd/semantics.md, beside the TDD. The worked
example is openspec/specs/products/sales/sales-performance/tdd/semantics.md.

- Write for the business owner. Use the words of the BRD.
- Do not use modelling or technology words: no grain, dimension, fact, SCD, surrogate key,
  partition, view, table, pipeline or product names such as BigQuery.
- Every statement must be true of the design in the TDD. If one is not, change the design
  or the statement, and say which.
- Use a real example where behaviour could surprise someone, with dates and values.
- Put anything that the business might not expect under "Known limitations".
- Delete a section that does not apply, for example "Agreement with other teams".
- Replace every {placeholder}.
- When the business owner agrees the page, delete these comments and record the signature:
  dpf signoff {product} --by "{name}" --role business_owner
  The signature is bound to this text and to the grain and history of every model.
  Changing either makes it invalid until it is signed again.
-->

## What the figures mean

<!-- From: required outputs (figures), level of detail and totalling. -->

- **{Figure}** is {its definition in business words, with the currency and what it leaves out}.
- Figures are built from **one row for every {thing the business counts}**. {How an item
  that is amended several times is counted.}
- You can **add the figures up** across {time, regions and other breakdowns} without double
  counting. {Name any figure that cannot be added up, and why.}
- Every {summary figure} can be **traced to the {detail items}** that make it up.

## How history behaves

<!-- From: history behaviour (HB-n). One bullet for each attribute the business asked about. -->

- {Figures} stay with the **{attribute} that applied on the date of the {event}**. If
  {a real example, for example a customer is reclassified in June}, {what their earlier
  figures show}.
- {Attribute} always shows its **current** value.

## What is included and excluded

<!-- From: exceptions and fitness. -->

- {A rule, for example: cancelled items stay visible and are marked as cancelled. They are
  not counted in totals.}
- **Corrections arriving within {n} days** restate the affected period. Corrections after
  {n} days do not change published figures.

## Timing

<!-- From: timeliness, and the service levels decided in the TDD. -->

- Refreshed **{how often}** ({hours}, {time zone}, {days}). The team is alerted if the
  figures fall more than {time} behind.
- If {a condition that makes data unusable}, the figures are **not refreshed**, the team is
  alerted, and the unusable item is held aside with the reason. You keep seeing the last
  complete figures, never partial ones.

## Agreement with other teams

<!-- From: agreement with other teams. -->

- {Which definitions are shared with which team, and which figures will reconcile.}

## Access

<!-- From: protection and external readers. -->

- {Who can see what, and what is hidden from whom.}
- {What an external reader receives, how often, and what they cannot see.}

## Known limitations — please read

<!-- From: the feasibility finding and any change to the BRD that the business accepted. Say
what the business will not get, why, what happens instead, and whether it can change later. -->

- **{Limitation}.** {Why, in business terms. What happens instead. Whether it can be
  delivered later, and what that needs.}

---

The signature for this page is recorded in `signoff.yaml` beside it, bound to a digest of
this text and of every model's grain and history declaration. Changing either invalidates
the signature until it is signed again.
